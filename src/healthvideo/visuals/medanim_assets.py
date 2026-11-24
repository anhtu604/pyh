"""Offline catalog, controlled downloads and verified copies for licensed medanim assets.

The injected client provides resolve_host(host) -> iterable of IP strings and
stream(method, url, resolved_ips=..., follow_redirects=False, timeout=30).
Its transport MUST connect
only to those resolved addresses (including on retries), without cookies/auth or
environment proxies. No default network client is constructed here.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import yaml

from healthvideo.domain.medanim_library import MedAnimAsset, validate_safe_relative_path

MAX_ASSET_BYTES = 5 * 1024 * 1024
ACCEPTED_LICENSES = frozenset({"Public Domain", "CC0", "CC BY 4.0"})
# Evidence: library/medanim/liver-enzyme-leak/animation.yaml (before extraction)
# Servier liver-overview/foie_coupe, NIAID bioart/230, DBCLS 201904_hepatic_lobule,
# Reactome R-ICO-014108. DBCLS is evidenced ONLY via Wikimedia; no togotv URL
# occurs in existing animation.yaml files. Bioicons/GitHub mirrors are excluded.
# NIAID's Wikimedia download mirror: macrophage-phagocytosis/animation.yaml,
# niaid-macrophage-308 (source bioart/308, upload.wikimedia.org original_url).
REPOSITORY_HOSTS = {
    "servier": frozenset({"smart.servier.com"}),
    "niaid": frozenset({"bioart.niaid.nih.gov", "upload.wikimedia.org"}),
    "dbcls": frozenset({"commons.wikimedia.org", "upload.wikimedia.org"}),
    "reactome": frozenset({"reactome.org"}),
}
_HOSTS = frozenset().union(*REPOSITORY_HOSTS.values())


def validate_download_url(url: str) -> None:
    """Require HTTPS and an exact evidenced hostname, without credentials/ports."""
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url) or "\\" in url:
        raise ValueError("Invalid download URL")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in _HOSTS or
            parsed.username is not None or parsed.password is not None or
            parsed.port not in (None, 443) or parsed.fragment):
        raise ValueError(f"URL outside HTTPS host allowlist: {url!r}")


def _repository(record: MedAnimAsset) -> str:
    validate_download_url(record.source_page)
    host = urlsplit(record.source_page).hostname
    return {"smart.servier.com": "servier", "bioart.niaid.nih.gov": "niaid",
            "commons.wikimedia.org": "dbcls", "reactome.org": "reactome"}.get(host, "")


def _validate_record(record: MedAnimAsset, *, require_id: bool = False) -> MedAnimAsset:
    # Revalidate even model_copy/model_construct inputs at trust boundaries.
    record = MedAnimAsset.model_validate(record.model_dump(mode="python"))
    if record.license not in ACCEPTED_LICENSES:
        raise ValueError(f"Unsupported catalog/download license: {record.license}")
    if require_id and not record.id:
        raise ValueError("Catalog asset requires id")
    repository = _repository(record)
    if not repository:
        raise ValueError("Missing supported source-page provenance")
    _validate_repository_url(record.original_url, repository)
    return record


def _validate_repository_url(url: str, repository: str) -> None:
    validate_download_url(url)
    if urlsplit(url).hostname not in REPOSITORY_HOSTS[repository]:
        raise ValueError("URL outside repository allowlist")


def assert_safe_path(path: Path) -> Path:
    """Reject traversal and links/junctions in every existing path component."""
    path = Path(path)
    if ".." in path.parts:
        raise ValueError(f"Path traversal: {path}")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"Symlink/junction path: {path}")
        try:
            # st_file_attributes is available on Windows Python 3.11 too;
            # reject all reparse points, including directory junctions.
            attributes = getattr(part.lstat(), "st_file_attributes", 0)
        except FileNotFoundError:
            continue
        if attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
            raise ValueError(f"Symlink/junction path: {path}")
    return path


def load_asset_catalog(path: Path) -> tuple[MedAnimAsset, ...]:
    """Read the strict R5 catalog; unknown acquisition dates may be null."""
    assert_safe_path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if (not isinstance(raw, dict) or set(raw) != {"assets"} or
            not isinstance(raw["assets"], list) or not raw["assets"]):
        raise ValueError("Catalog must contain only an assets list")
    records = tuple(_validate_record(MedAnimAsset.model_validate(item), require_id=True)
                    for item in raw["assets"])
    _check_unique(records)
    return records


def _check_unique(records: tuple[MedAnimAsset, ...]) -> None:
    if (len({r.id for r in records}) != len(records) or
            len({r.file.casefold() for r in records}) != len(records)):
        raise ValueError("Duplicate catalog asset id/file")


def _target(destination: Path, record: MedAnimAsset) -> Path:
    validate_safe_relative_path(record.file)
    assert_safe_path(destination)
    return assert_safe_path(destination / record.file)


def _write_verified(record: MedAnimAsset, destination: Path, data: bytes) -> Path:
    if len(data) > MAX_ASSET_BYTES:
        raise ValueError("Asset exceeds 5 MB")
    if hashlib.sha256(data).hexdigest() != record.sha256:
        raise ValueError("Asset SHA-256 mismatch")
    target = _target(destination, record)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        _target(destination, record)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def fetch_licensed_asset(record: MedAnimAsset, destination: Path, *, client) -> Path:
    """Fetch at most 5 MB through an injected, IP-pinning streaming client.

    destination is a trusted caller-selected directory; record.file is relative
    to it. Every redirect is explicitly validated BEFORE another HTTP request.
    """
    record = _validate_record(record)
    _target(destination, record)
    repository = _repository(record)
    url = record.original_url
    for _ in range(6):
        _validate_repository_url(url, repository)
        addresses = tuple(client.resolve_host(urlsplit(url).hostname))
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ValueError("Private/nonpublic download IP")
        with client.stream("GET", url, resolved_ips=addresses, follow_redirects=False, timeout=30) as response:
            if str(response.url) != url:
                raise ValueError("Client followed an unchecked redirect")
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location") or response.headers.get("Location")
                if not location:
                    raise ValueError("Missing redirect Location")
                url = urljoin(url, location)
                _validate_repository_url(url, repository)
                continue
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Expected complete HTTP 200 asset")
            length = response.headers.get("content-length")
            if length is not None and (int(length) < 0 or int(length) > MAX_ASSET_BYTES):
                raise ValueError("Asset exceeds 5 MB or invalid Content-Length")
            data = bytearray()
            for chunk in response.iter_bytes(chunk_size=64 * 1024):
                if len(data) + len(chunk) > MAX_ASSET_BYTES:
                    raise ValueError("Asset exceeds 5 MB")
                data.extend(chunk)
            return _write_verified(record, destination, bytes(data))
    raise ValueError("Too many asset redirects")


def copy_used_assets(
    records: tuple[MedAnimAsset, ...], asset_ids: list[str], source: Path, destination: Path,
) -> tuple[MedAnimAsset, ...]:
    """Copy only selected IDs, rehash bytes and return provenance for credits/snapshot.

    Caller supplies the IDs actually used by the approved storyboard. This does
    not grant approval or write a revision ledger; integration belongs to R5.3.8.
    """
    _check_unique(records)
    index = {record.id: record for record in records if record.id}
    used = []
    for asset_id in dict.fromkeys(asset_ids):
        if asset_id not in index:
            raise ValueError(f"Unknown used asset: {asset_id}")
        used.append(_validate_record(index[asset_id], require_id=True))
    # Check all selected inputs before writing any output.
    checked = []
    for record in used:
        path = _target(source, record)
        _target(destination, record)
        with path.open("rb") as stream:
            data = stream.read(MAX_ASSET_BYTES + 1)
        if len(data) > MAX_ASSET_BYTES or hashlib.sha256(data).hexdigest() != record.sha256:
            raise ValueError("Asset size/SHA-256 mismatch while copying")
        checked.append((record, data))
    for record, data in checked:
        _write_verified(record, destination, data)
    return tuple(used)
