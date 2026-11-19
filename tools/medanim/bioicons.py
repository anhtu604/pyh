"""Pure-stdlib Bioicons lookup, SVG sanitizer, ID prefixer, and manifest exporter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

BIOICONS_ICONS_URL = (
    "https://raw.githubusercontent.com/duerrsimon/bioicons/main/static/icons/icons.json"
)
BIOICONS_AUTHORS_URL = (
    "https://raw.githubusercontent.com/duerrsimon/bioicons/main/static/icons/authors.json"
)
BIOICONS_RAW_BASE = (
    "https://raw.githubusercontent.com/duerrsimon/bioicons/main/static/icons"
)
BIOICONS_BLOB_BASE = (
    "https://github.com/duerrsimon/bioicons/blob/main/static/icons"
)

ALLOWED_BIOICONS_LICENSES: dict[str, str] = {
    "cc-0": "CC0",
    "cc-by-3.0": "CC BY 3.0",
    "cc-by-4.0": "CC BY 4.0",
}

LICENSE_URLS: dict[str, str] = {
    "cc-0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc-by-3.0": "https://creativecommons.org/licenses/by/3.0/",
    "cc-by-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "cc-by-sa-3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "cc-by-sa-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "mit": "https://opensource.org/licenses/MIT",
    "bsd": "https://opensource.org/licenses/BSD-3-Clause",
}

LICENSE_LABELS: dict[str, str] = {
    **ALLOWED_BIOICONS_LICENSES,
    "cc-by-sa-3.0": "CC BY-SA 3.0",
    "cc-by-sa-4.0": "CC BY-SA 4.0",
    "mit": "MIT",
    "bsd": "BSD",
}

_LICENSE_PRIORITY: dict[str, int] = {
    "cc-0": 0,
    "cc-by-4.0": 1,
    "cc-by-3.0": 2,
}

_STRIPPED_NAMESPACES: frozenset[str] = frozenset(
    {
        "http://www.inkscape.org/namespaces/inkscape",
        "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "http://creativecommons.org/ns#",
        "http://purl.org/dc/elements/1.1/",
        "http://ns.adobe.com/AdobeIllustrator/10.0/",
        "http://ns.adobe.com/AdobeSVGViewerExtensions/3.0/",
        "http://ns.adobe.com/Extensibility/1.0/",
        "http://ns.adobe.com/Flows/1.0/",
        "http://ns.adobe.com/Graphs/1.0/",
        "http://ns.adobe.com/ImageReplacement/1.0/",
        "http://ns.adobe.com/SaveForWeb/1.0/",
        "http://ns.adobe.com/Variables/1.0/",
        "http://ns.adobe.com/XPath/1.0/",
    }
)
_STRIPPED_ATTR_NS: frozenset[str] = frozenset(
    {
        "http://www.inkscape.org/namespaces/inkscape",
        "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
        "http://ns.adobe.com/AdobeIllustrator/10.0/",
        "http://ns.adobe.com/Extensibility/1.0/",
    }
)
_FORBIDDEN_TAG_LOCALS: frozenset[str] = frozenset({"script", "foreignobject"})
_STRIPPED_TAG_LOCALS: frozenset[str] = frozenset({"namedview", "metadata"})
_SAFE_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")
_URL_REF_RE = re.compile(r"""url\(\s*(['"]?)#([^)'"\s]+)\1\s*\)""")
_CSS_ID_SEL_RE = re.compile(r"(?<![:\w])#([A-Za-z_][A-Za-z0-9_.-]*)(?=\s*[{,:.\[>+~\s])")
_DANGEROUS_URI_RE = re.compile(r"^\s*(?:javascript|vbscript|data\s*:\s*text/html)\s*:", re.IGNORECASE)

Fetcher = Callable[[str], bytes]

ET.register_namespace("", "http://www.w3.org/2000/svg")
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


@dataclass(frozen=True)
class BioiconEntry:
    """Normalized catalog entry for one SVG icon on Bioicons."""

    name: str
    category: str
    license_slug: str
    license: str
    author: str
    author_url: str | None
    raw_url: str
    source_page: str
    license_url: str

    def is_sharealike(self) -> bool:
        return "sa" in self.license_slug.casefold() or "by-sa" in self.license.casefold()

    def is_allowed_by_default(self) -> bool:
        return self.license_slug in ALLOWED_BIOICONS_LICENSES


def default_fetcher(url: str, *, timeout: float = 20.0) -> bytes:
    """Download bytes using Python stdlib urllib."""
    req = Request(url, headers={"User-Agent": "PYH-MedAnim-Bioicons/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _tag_parts(tag: str) -> tuple[str, str]:
    if tag.startswith("{") and "}" in tag:
        ns, local = tag[1:].split("}", 1)
        return ns, local
    return "", tag


def _is_stripped_namespace(ns: str) -> bool:
    if not ns:
        return False
    if ns in _STRIPPED_NAMESPACES:
        return True
    lowered = ns.casefold()
    return "inkscape" in lowered or "sodipodi" in lowered or "ns.adobe.com" in lowered


def _build_entry(raw: dict[str, Any], authors_map: dict[str, str]) -> BioiconEntry:
    name = str(raw["name"])
    category = str(raw["category"])
    lic_slug = str(raw["license"]).strip().lower()
    author = str(raw["author"])
    author_dir = author.replace(" ", "_")
    rel = f"{quote(lic_slug, safe='')}/{quote(category, safe='')}/{quote(author_dir, safe='')}/{quote(name, safe='')}.svg"
    return BioiconEntry(
        name=name,
        category=category,
        license_slug=lic_slug,
        license=LICENSE_LABELS.get(lic_slug, lic_slug),
        author=author,
        author_url=authors_map.get(author),
        raw_url=f"{BIOICONS_RAW_BASE}/{rel}",
        source_page=f"{BIOICONS_BLOB_BASE}/{rel}",
        license_url=LICENSE_URLS.get(lic_slug, "https://bioicons.com/"),
    )


def fetch_catalog(
    *,
    icons_url: str = BIOICONS_ICONS_URL,
    authors_url: str = BIOICONS_AUTHORS_URL,
    fetcher: Fetcher | None = None,
) -> list[BioiconEntry]:
    """Load and parse the Bioicons icon catalog and author URL table."""
    fetch = fetcher or default_fetcher
    icons_raw = json.loads(fetch(icons_url).decode("utf-8"))
    if not isinstance(icons_raw, list):
        raise TypeError("Bioicons icons.json must be a JSON array")
    authors_map: dict[str, str] = {}
    try:
        authors_raw = json.loads(fetch(authors_url).decode("utf-8"))
        if isinstance(authors_raw, dict):
            authors_map = {str(k): str(v) for k, v in authors_raw.items() if isinstance(v, str)}
    except Exception:  # noqa: BLE001
        authors_map = {}

    entries: list[BioiconEntry] = []
    for item in icons_raw:
        if isinstance(item, dict) and {"name", "category", "license", "author"} <= set(item):
            entries.append(_build_entry(item, authors_map))
    return entries


def search_icons(
    query: str,
    *,
    category: str | None = None,
    license_filter: str | None = None,
    allow_sharealike: bool = False,
    limit: int = 25,
    catalog: list[BioiconEntry] | None = None,
    fetcher: Fetcher | None = None,
) -> list[BioiconEntry]:
    """Search Bioicons icons, rejecting CC BY-SA and non-open-allowlist licenses by default."""
    if license_filter and not allow_sharealike and (
        "sa" in license_filter.casefold() or license_filter.strip().lower() not in ALLOWED_BIOICONS_LICENSES
    ):
        raise ValueError(
            f"License filter {license_filter!r} is rejected by default; "
            f"allowed licenses are {sorted(ALLOWED_BIOICONS_LICENSES)}"
        )

    entries = catalog if catalog is not None else fetch_catalog(fetcher=fetcher)
    tokens = [tok for tok in query.casefold().split() if tok]
    cat_filter = category.strip().casefold() if category else None
    lic_filter = license_filter.strip().casefold() if license_filter else None

    matches: list[tuple[int, int, BioiconEntry]] = []
    for entry in entries:
        if not allow_sharealike and not entry.is_allowed_by_default():
            continue
        if cat_filter and entry.category.casefold() != cat_filter:
            continue
        if lic_filter and entry.license_slug.casefold() != lic_filter and entry.license.casefold() != lic_filter:
            continue
        haystack = f"{entry.name} {entry.category} {entry.author}".casefold()
        if tokens and not all(tok in haystack for tok in tokens):
            continue
        exact_rank = 0 if entry.name.casefold() == query.strip().casefold() else 1
        lic_rank = _LICENSE_PRIORITY.get(entry.license_slug, 9)
        matches.append((exact_rank, lic_rank, entry))

    matches.sort(key=lambda row: (row[0], row[1], row[2].name.casefold(), row[2].category.casefold()))
    return [row[2] for row in matches[: max(1, limit)]]


def _normalize_prefix(prefix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", prefix.strip()).strip("-")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"bio-{cleaned}" if cleaned else "bio"
    cleaned = cleaned[:47]
    if not _SAFE_PREFIX_RE.fullmatch(cleaned):
        raise ValueError(f"Invalid SVG ID prefix: {prefix!r}")
    return cleaned if cleaned.endswith(("-", "_")) else f"{cleaned}-"


def _rewrite_url_refs(text: str, id_map: dict[str, str]) -> str:
    def _sub(match: re.Match[str]) -> str:
        quote_ch = match.group(1)
        old_id = match.group(2)
        new_id = id_map.get(old_id)
        if new_id is None:
            return match.group(0)
        return f"url({quote_ch}#{new_id}{quote_ch})"

    return _URL_REF_RE.sub(_sub, text)


def _rewrite_css_text(css: str, id_map: dict[str, str]) -> str:
    updated = _rewrite_url_refs(css, id_map)

    def _sub_sel(match: re.Match[str]) -> str:
        old_id = match.group(1)
        new_id = id_map.get(old_id)
        return f"#{new_id}" if new_id is not None else match.group(0)

    return _CSS_ID_SEL_RE.sub(_sub_sel, updated)


def sanitize_svg(svg_text: str, *, prefix: str) -> str:
    """Strip Inkscape/Sodipodi/RDF tags and prefix all id attributes & references."""
    if not isinstance(svg_text, str) or not svg_text.strip():
        raise ValueError("SVG content must be non-empty")

    norm_prefix = _normalize_prefix(prefix)
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed SVG XML: {exc}") from exc

    _, root_local = _tag_parts(root.tag)
    if root_local.casefold() != "svg":
        raise ValueError(f"Expected root <svg> element, got <{root_local}>")

    def _clean_tree(elem: ET.Element) -> None:
        kept_children: list[ET.Element] = []
        for child in list(elem):
            if not isinstance(child.tag, str):
                continue
            ns, local = _tag_parts(child.tag)
            local_cf = local.casefold()
            if local_cf in _FORBIDDEN_TAG_LOCALS:
                raise ValueError(f"Unsafe SVG element rejected: <{local}>")
            if local_cf in _STRIPPED_TAG_LOCALS or _is_stripped_namespace(ns):
                continue
            _clean_tree(child)
            kept_children.append(child)
        elem[:] = kept_children

        for attr_key in list(elem.attrib):
            attr_ns, attr_local = _tag_parts(attr_key)
            attr_val = elem.attrib[attr_key]
            if attr_local.casefold().startswith("on"):
                raise ValueError(f"Unsafe SVG event attribute rejected: {attr_local}")
            if attr_local.casefold() == "href" and _DANGEROUS_URI_RE.match(attr_val):
                raise ValueError(f"Unsafe SVG URI rejected in {attr_local}")
            if _is_stripped_namespace(attr_ns) or attr_ns in _STRIPPED_ATTR_NS:
                del elem.attrib[attr_key]

    _clean_tree(root)

    id_map: dict[str, str] = {}
    for elem in root.iter():
        raw_id = elem.attrib.get("id")
        if raw_id:
            id_map[raw_id] = raw_id if raw_id.startswith(norm_prefix) else f"{norm_prefix}{raw_id}"

    if id_map:
        for elem in root.iter():
            if "id" in elem.attrib and elem.attrib["id"] in id_map:
                elem.attrib["id"] = id_map[elem.attrib["id"]]
            for attr_key, attr_val in list(elem.attrib.items()):
                if attr_key == "id":
                    continue
                _, attr_local = _tag_parts(attr_key)
                if attr_local.casefold() == "href" and attr_val.startswith("#"):
                    ref_id = attr_val[1:]
                    if ref_id in id_map:
                        elem.attrib[attr_key] = f"#{id_map[ref_id]}"
                elif "url(" in attr_val:
                    elem.attrib[attr_key] = _rewrite_url_refs(attr_val, id_map)
            _, elem_local = _tag_parts(elem.tag)
            if elem_local.casefold() == "style" and elem.text:
                elem.text = _rewrite_css_text(elem.text, id_map)

    return ET.tostring(root, encoding="unicode") + "\n"


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def build_attribution_line(entry: BioiconEntry) -> str:
    """Format a concise Vietnamese attribution credit for the downloaded icon."""
    author_part = f"{entry.author} ({entry.author_url})" if entry.author_url else entry.author
    return (
        f"Hình {entry.name} (Bioicons — {entry.category}): "
        f"{author_part}, {entry.license} ({entry.license_url})."
    )


def _extract_viewbox(svg_text: str) -> str | None:
    root = ET.fromstring(svg_text)
    vb = root.attrib.get("viewBox")
    if vb:
        return " ".join(vb.split())
    w = root.attrib.get("width")
    h = root.attrib.get("height")
    if w and h:
        return f"0 0 {w} {h}"
    return None


def _safe_filename(raw: str) -> str:
    cleaned = Path(raw.strip()).name
    if not cleaned or cleaned != raw.strip() or "\\" in raw or "/" in raw or ".." in raw:
        raise ValueError(f"Invalid output filename: {raw!r}")
    if not cleaned.lower().endswith(".svg"):
        cleaned = f"{cleaned}.svg"
    return cleaned


def get_icon(
    name: str,
    *,
    out_dir: Path,
    public_dir: Path | None = None,
    prefix: str | None = None,
    filename: str | None = None,
    category: str | None = None,
    license_filter: str | None = None,
    allow_sharealike: bool = False,
    catalog: list[BioiconEntry] | None = None,
    fetcher: Fetcher | None = None,
) -> dict[str, Any]:
    """Fetch one Bioicons SVG, reject CC BY-SA by default, sanitize, and emit manifest metadata."""
    entries = catalog if catalog is not None else fetch_catalog(fetcher=fetcher)
    fetch = fetcher or default_fetcher
    target_name = name.strip()
    if not target_name:
        raise ValueError("Icon name must be nonblank")

    all_matching_name = [
        e for e in entries
        if e.name.casefold() == target_name.casefold()
        and (category is None or e.category.casefold() == category.strip().casefold())
        and (
            license_filter is None
            or e.license_slug.casefold() == license_filter.strip().casefold()
            or e.license.casefold() == license_filter.strip().casefold()
        )
    ]
    if not all_matching_name:
        raise LookupError(f"Bioicons icon not found: {target_name!r}")

    if not allow_sharealike:
        permitted = [e for e in all_matching_name if e.is_allowed_by_default()]
        if not permitted:
            found_lics = ", ".join(sorted({e.license for e in all_matching_name}))
            raise ValueError(
                f"Rejected Bioicons icon {target_name!r}: license {found_lics} is not permitted by default "
                "(CC BY-SA and non-open-allowlist licenses are blocked)"
            )
        candidates = permitted
    else:
        candidates = all_matching_name

    candidates.sort(key=lambda e: (_LICENSE_PRIORITY.get(e.license_slug, 9), e.category.casefold(), e.author.casefold()))
    chosen = candidates[0]

    raw_bytes = fetch(chosen.raw_url)
    svg_prefix = prefix or f"bio-{chosen.name}"
    cleaned_svg = sanitize_svg(raw_bytes.decode("utf-8"), prefix=svg_prefix)
    cleaned_bytes = cleaned_svg.encode("utf-8")
    digest = hashlib.sha256(cleaned_bytes).hexdigest()

    out_name = _safe_filename(filename or f"bioicons-{chosen.name}.svg")
    out_path = out_dir / out_name
    _write_bytes_atomic(out_path, cleaned_bytes)

    pub_path_str: str | None = None
    if public_dir is not None:
        pub_path = public_dir / out_name
        _write_bytes_atomic(pub_path, cleaned_bytes)
        pub_path_str = str(pub_path)

    attribution = build_attribution_line(chosen)
    manifest_asset = {
        "file": out_name,
        "source_page": chosen.source_page,
        "original_url": chosen.raw_url,
        "author": chosen.author,
        "license": chosen.license,
        "license_url": chosen.license_url,
        "sha256": digest,
        "attribution": attribution,
    }
    return {
        "icon": asdict(chosen),
        "asset": manifest_asset,
        "attribution_line": attribution,
        "viewBox": _extract_viewbox(cleaned_svg),
        "path": str(out_path),
        "public_path": pub_path_str,
    }


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def format_manifest_yaml_snippet(result: dict[str, Any]) -> str:
    """Format a ready-to-paste YAML list item for animation.yaml without external PyYAML."""
    asset = result["asset"]
    lines = [f"- file: {_yaml_scalar(asset['file'])}"]
    for key in ("source_page", "original_url", "author", "license", "license_url", "sha256", "attribution"):
        if asset.get(key) is not None:
            lines.append(f"  {key}: {_yaml_scalar(asset[key])}")
    if result.get("viewBox"):
        lines.append(f"  # viewBox: {result['viewBox']}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bioicons", description="Search and download open Bioicons SVGs.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Search Bioicons catalog (CC BY-SA rejected by default)")
    p_search.add_argument("query", help="Search keywords (icon name, category, or author)")
    p_search.add_argument("--category", default=None, help="Exact Bioicons category filter")
    p_search.add_argument("--license", dest="license_filter", default=None, help="Allowed license filter")
    p_search.add_argument("--limit", type=int, default=20, help="Max results")
    p_search.add_argument("--allow-sharealike", action="store_true", help="Include CC BY-SA icons")
    p_search.add_argument("--json", action="store_true", help="Output JSON")

    p_get = sub.add_parser("get", help="Download, sanitize, prefix IDs, and emit manifest snippet")
    p_get.add_argument("name", help="Exact icon name from search results")
    p_get.add_argument("--out-dir", type=Path, required=True, help="Output assets directory")
    p_get.add_argument("--public-dir", type=Path, default=None, help="Optional video/public/medanim/<id> mirror dir")
    p_get.add_argument("--filename", default=None, help="Output SVG filename")
    p_get.add_argument("--prefix", default=None, help="Custom prefix for SVG id attributes")
    p_get.add_argument("--category", default=None, help="Disambiguate category")
    p_get.add_argument("--license", dest="license_filter", default=None, help="Disambiguate license")
    p_get.add_argument("--allow-sharealike", action="store_true", help="Allow CC BY-SA icons (off by default)")
    p_get.add_argument("--json", action="store_true", help="Output full JSON payload")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for Bioicons search and download."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "search":
            hits = search_icons(
                args.query,
                category=args.category,
                license_filter=args.license_filter,
                allow_sharealike=args.allow_sharealike,
                limit=args.limit,
            )
            if args.json:
                print(json.dumps([asdict(h) for h in hits], ensure_ascii=False, indent=2))
            else:
                for h in hits:
                    print(f"{h.name}\t{h.category}\t{h.license}\t{h.author}\t{h.raw_url}")
            return 0
        if args.command == "get":
            result = get_icon(
                args.name,
                out_dir=args.out_dir,
                public_dir=args.public_dir,
                prefix=args.prefix,
                filename=args.filename,
                category=args.category,
                license_filter=args.license_filter,
                allow_sharealike=args.allow_sharealike,
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(format_manifest_yaml_snippet(result))
                print(f"ATTRIBUTION: {result['attribution_line']}")
            return 0
    except (ValueError, LookupError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
