"""Workflow operations and immutable doctor approval for the medical animation library."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from healthvideo.approver_pin import pin_path, verify_pin
from healthvideo.domain.medanim_library import (
    MedAnimApprovalRecord,
    MedAnimEntry,
    MedAnimRejectionRecord,
    validate_safe_relative_path,
)
from healthvideo.storage.files import read_yaml, sha256_file
from healthvideo.storage.immutable import write_yaml_once
from healthvideo.visuals.medanim_assets import assert_safe_path, load_asset_catalog

_ANIM_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PREVIEW_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_MEDANIM_LIBRARY_SUBDIR = Path("library") / "medanim"
_PUBLIC_MEDANIM_SUBDIR = Path("video") / "public" / "medanim"


def medanim_library_root(root: Path) -> Path:
    """Return the root directory containing reusable medical animation entries."""
    return root / _MEDANIM_LIBRARY_SUBDIR


def _validate_anim_id(anim_id: str) -> str:
    if not isinstance(anim_id, str) or not _ANIM_ID_RE.fullmatch(anim_id):
        raise LookupError(f"Mã hoạt cảnh không hợp lệ: {anim_id!r}")
    return anim_id


def _assert_inside(base: Path, target: Path) -> Path:
    assert_safe_path(base)
    assert_safe_path(target)
    if target.is_symlink():
        raise ValueError(f"Từ chối liên kết ngoài phạm vi thư viện: {target.name}")
    resolved_base = base.resolve()
    resolved_target = target.resolve(strict=False)
    if not resolved_target.is_relative_to(resolved_base):
        raise ValueError(f"Đường dẫn thoát khỏi thư mục thư viện: {target}")
    return resolved_target


def load_medanim_entry(path: Path, *, raw: dict[str, Any] | None = None) -> MedAnimEntry:
    """Resolve catalog IDs, while keeping inline legacy entries readable."""
    assert_safe_path(path)
    data = read_yaml(path) if raw is None else raw
    assets = data.get("assets")
    if isinstance(assets, list) and any(isinstance(item, str) for item in assets):
        if not all(isinstance(item, str) for item in assets) or len(set(assets)) != len(assets):
            raise ValueError("Asset references must be unique IDs, without inline metadata")
        catalog = {asset.id: asset for asset in load_asset_catalog(path.parent / "assets.yaml")}
        if any(asset_id not in catalog for asset_id in assets):
            raise ValueError("Unknown catalog asset ID")
        data = {**data, "assets": [catalog[asset_id] for asset_id in assets]}
    return MedAnimEntry.model_validate(data)


def _content_sha256(path: Path, *, raw: dict[str, Any] | None = None) -> str:
    """Legacy hashes stay byte-identical; references bind catalog provenance too."""
    assert_safe_path(path)
    if raw is None:
        try:
            raw = read_yaml(path)
        except (ValueError, TypeError, yaml.YAMLError):
            # A doctor can still reject malformed legacy YAML and retain its hash.
            return sha256_file(path)
    assets = raw.get("assets")
    if isinstance(assets, list) and any(isinstance(item, str) for item in assets):
        catalog_path = assert_safe_path(path.parent / "assets.yaml")
        if not catalog_path.is_file():
            return sha256_file(path)
        return hashlib.sha256(
            b"medanim-catalog-v1\0" + path.read_bytes() + b"\0" + catalog_path.read_bytes()
        ).hexdigest()
    return sha256_file(path)


def _entry_dir(root: Path, anim_id: str) -> Path:
    _validate_anim_id(anim_id)
    lib_root = medanim_library_root(root)
    if lib_root.is_symlink():
        raise ValueError("Thư mục library/medanim không được là symlink")
    candidate = lib_root / anim_id
    _assert_inside(lib_root, candidate)
    if not candidate.is_dir():
        raise LookupError(f"Không tìm thấy hoạt cảnh: {anim_id}")
    return candidate


def _asset_candidate_paths(root: Path, entry_dir: Path, anim_id: str, rel_file: str) -> tuple[Path, Path]:
    rel = validate_safe_relative_path(rel_file)
    posix_parts = PurePosixPath(rel).parts
    assets_dir = entry_dir / "assets"
    public_dir = root / _PUBLIC_MEDANIM_SUBDIR / anim_id
    return assets_dir.joinpath(*posix_parts), public_dir.joinpath(*posix_parts)


def verify_entry_assets(
    root: Path,
    entry_dir: Path,
    entry: MedAnimEntry,
) -> tuple[dict[str, str], dict[str, bool], list[str]]:
    """Verify every declared asset exists on disk and matches its declared SHA-256.

    Checks ``library/medanim/<id>/assets/<file>`` and/or
    ``video/public/medanim/<id>/<file>``. If both exist, both must match
    ``asset.sha256``.
    """
    actual_hashes: dict[str, str] = {}
    asset_ok: dict[str, bool] = {}
    errors: list[str] = []
    lib_assets_base = entry_dir / "assets"
    pub_assets_base = root / _PUBLIC_MEDANIM_SUBDIR / entry.id

    for asset in entry.assets:
        lib_path, pub_path = _asset_candidate_paths(root, entry_dir, entry.id, asset.file)
        existing: list[tuple[Path, Path]] = []
        for base, path in ((lib_assets_base, lib_path), (pub_assets_base, pub_path)):
            if path.is_symlink():
                errors.append(f"Asset là symlink không hợp lệ: {asset.file}")
                asset_ok[asset.file] = False
                continue
            try:
                resolved = _assert_inside(base, path)
            except ValueError as exc:
                errors.append(str(exc))
                asset_ok[asset.file] = False
                continue
            if resolved.is_file():
                existing.append((base, resolved))

        if asset.file in asset_ok and not asset_ok[asset.file]:
            continue
        if not existing:
            errors.append(
                f"Thiếu file tài sản {asset.file!r} trong library/medanim/{entry.id}/assets/ "
                f"hoặc video/public/medanim/{entry.id}/"
            )
            asset_ok[asset.file] = False
            continue

        digests = {sha256_file(resolved) for _, resolved in existing}
        if len(digests) != 1:
            errors.append(
                f"File {asset.file!r} giữa assets/ và video/public/medanim/{entry.id}/ không khớp nhau"
            )
            asset_ok[asset.file] = False
            continue

        digest = next(iter(digests))
        actual_hashes[asset.file] = digest
        if digest != asset.sha256:
            errors.append(
                f"SHA-256 không khớp cho {asset.file!r}: khai báo {asset.sha256}, thực tế {digest}"
            )
            asset_ok[asset.file] = False
        else:
            asset_ok[asset.file] = True

    return actual_hashes, asset_ok, errors


def _best_effort_disk_hashes(root: Path, entry_dir: Path, anim_id: str, raw: dict[str, Any]) -> dict[str, str]:
    """Read current disk SHA-256 values for any declared assets without assuming validity."""
    result: dict[str, str] = {}
    assets = raw.get("assets")
    if not isinstance(assets, list):
        return result
    if any(isinstance(item, str) for item in assets):
        try:
            assets = [asset.model_dump() for asset in load_medanim_entry(entry_dir / "animation.yaml").assets]
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            return result
    lib_assets_base = entry_dir / "assets"
    pub_assets_base = root / _PUBLIC_MEDANIM_SUBDIR / anim_id
    for item in assets:
        if not isinstance(item, dict) or not isinstance(item.get("file"), str):
            continue
        try:
            rel = validate_safe_relative_path(item["file"])
        except ValueError:
            continue
        lib_path, pub_path = _asset_candidate_paths(root, entry_dir, anim_id, rel)
        for base, path in ((lib_assets_base, lib_path), (pub_assets_base, pub_path)):
            if not path.is_symlink():
                try:
                    resolved = _assert_inside(base, path)
                except ValueError:
                    continue
                if resolved.is_file():
                    result[rel] = sha256_file(resolved)
                    break
    return result


def _unique_history_path(entry_dir: Path, now: datetime, suffix: str) -> Path:
    reviews_dir = entry_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.astimezone().strftime("%Y%m%dT%H%M%S%f")
    candidate = reviews_dir / f"{stamp}-{suffix}.yaml"
    counter = 1
    while candidate.exists():
        candidate = reviews_dir / f"{stamp}-{suffix}-{counter}.yaml"
        counter += 1
    return candidate


def _latest_rejection(entry_dir: Path) -> MedAnimRejectionRecord | None:
    reviews_dir = entry_dir / "reviews"
    if not reviews_dir.is_dir():
        return None
    for path in sorted(reviews_dir.glob("*-rejected*.yaml"), reverse=True):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            return MedAnimRejectionRecord.model_validate(read_yaml(path))
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            continue
    return None


def _preview_items(entry_dir: Path, anim_id: str, preview_frames: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for rel in preview_frames:
        posix = PurePosixPath(rel)
        target = entry_dir.joinpath(*posix.parts)
        exists = False
        if not target.is_symlink():
            try:
                exists = _assert_inside(entry_dir, target).is_file()
            except ValueError:
                exists = False
        items.append(
            {
                "name": posix.name,
                "path": rel,
                "url": f"/api/medanim/{anim_id}/preview/{rel}",
                "exists": exists,
            }
        )
    return items


def inspect_medanim_entry(root: Path, entry_dir: Path) -> dict[str, Any]:
    """Load, validate, verify asset hashes, and compute approval status for one library entry."""
    anim_id = entry_dir.name
    animation_path = entry_dir / "animation.yaml"
    approval_path = entry_dir / "doctor-approval.yaml"
    if not animation_path.is_file():
        raise LookupError(f"Thiếu animation.yaml trong {entry_dir}")

    content_sha256 = ""
    errors: list[str] = []
    raw_yaml: dict[str, Any] = {}
    entry: MedAnimEntry | None = None

    try:
        raw_yaml = read_yaml(animation_path)
        content_sha256 = _content_sha256(animation_path, raw=raw_yaml)
        entry = load_medanim_entry(animation_path, raw=raw_yaml)
        if entry.id != anim_id:
            raise ValueError(f"animation.yaml id {entry.id!r} không khớp tên thư mục {anim_id!r}")
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        if not content_sha256:
            try:
                content_sha256 = sha256_file(animation_path)
            except OSError:
                content_sha256 = ""
        errors.append(f"animation.yaml không hợp lệ: {exc}")

    approval_record: MedAnimApprovalRecord | None = None
    approval_parse_error: str | None = None
    has_approval_file = approval_path.is_file()
    if has_approval_file:
        try:
            approval_record = MedAnimApprovalRecord.model_validate(read_yaml(approval_path))
        except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
            approval_parse_error = f"doctor-approval.yaml không hợp lệ: {exc}"
            errors.append(approval_parse_error)

    rejection_record = _latest_rejection(entry_dir)

    actual_hashes: dict[str, str] = {}
    asset_ok: dict[str, bool] = {}
    if entry is not None:
        actual_hashes, asset_ok, asset_errors = verify_entry_assets(root, entry_dir, entry)
        errors.extend(asset_errors)
    else:
        actual_hashes = _best_effort_disk_hashes(root, entry_dir, anim_id, raw_yaml)

    reapproval_reasons: list[str] = []
    if has_approval_file:
        if approval_parse_error is not None or approval_record is None:
            status = "needs_reapproval"
            reapproval_reasons.append(approval_parse_error or "Bản duyệt trước không đọc được")
        elif entry is None:
            status = "needs_reapproval"
            reapproval_reasons.append("animation.yaml đã thay đổi hoặc không hợp lệ sau khi duyệt")
        else:
            if approval_record.anim_id != entry.id:
                reapproval_reasons.append("Mã hoạt cảnh không khớp bản duyệt")
            if approval_record.content_sha256 != content_sha256:
                reapproval_reasons.append("animation.yaml đã thay đổi sau khi bác sĩ duyệt")
            if approval_record.asset_sha256 != actual_hashes:
                reapproval_reasons.append("Tài sản hình/SVG đã thay đổi sau khi bác sĩ duyệt")
            if not entry.medical_audit.passed:
                reapproval_reasons.append("medical_audit.passed không còn là true")
            if any(not ok for ok in asset_ok.values()):
                reapproval_reasons.append("Một hoặc nhiều tài sản thiếu hoặc lệch SHA-256")
            status = "approved" if not reapproval_reasons else "needs_reapproval"
    elif errors:
        status = "invalid"
    elif (
        rejection_record is not None
        and rejection_record.content_sha256 == content_sha256
        and rejection_record.asset_sha256 == actual_hashes
    ):
        status = "rejected"
    else:
        status = "pending"

    if entry is not None:
        payload = entry.model_dump(mode="json")
        assets_view = [
            {**asset, "hash_ok": asset_ok.get(asset["file"], False)}
            for asset in payload["assets"]
        ]
        previews = _preview_items(entry_dir, entry.id, entry.preview_frames)
    else:
        payload = {
            "schema_version": str(raw_yaml.get("schema_version") or "1.0"),
            "id": anim_id,
            "title": str(raw_yaml.get("title") or anim_id),
            "category": str(raw_yaml.get("category") or ""),
            "summary": str(raw_yaml.get("summary") or ""),
            "target_duration_seconds": raw_yaml.get("target_duration_seconds") or 0,
            "compositions": raw_yaml.get("compositions") if isinstance(raw_yaml.get("compositions"), dict) else {},
            "sources": raw_yaml.get("sources") if isinstance(raw_yaml.get("sources"), list) else [],
            "steps": raw_yaml.get("steps") if isinstance(raw_yaml.get("steps"), list) else [],
            "medical_audit": raw_yaml.get("medical_audit") if isinstance(raw_yaml.get("medical_audit"), dict) else {},
            "open_issues": raw_yaml.get("open_issues") if isinstance(raw_yaml.get("open_issues"), list) else [],
        }
        assets_view = []
        previews = []

    return {
        **payload,
        "assets": assets_view,
        "preview_frames": previews,
        "status": status,
        "approved": status == "approved",
        "content_sha256": content_sha256,
        "asset_sha256": actual_hashes,
        "approval": approval_record.model_dump(mode="json") if approval_record is not None else None,
        "rejection": rejection_record.model_dump(mode="json") if rejection_record is not None else None,
        "reapproval_reasons": reapproval_reasons,
        "errors": errors,
    }


def list_medanim_library(root: Path) -> list[dict[str, Any]]:
    """List all medical animations in ``library/medanim/`` with live hash and approval status."""
    lib_root = medanim_library_root(root)
    if lib_root.is_symlink() or not lib_root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for child in sorted(lib_root.iterdir(), key=lambda p: p.name):
        if child.is_symlink() or not child.is_dir():
            continue
        if not _ANIM_ID_RE.fullmatch(child.name):
            continue
        try:
            _assert_inside(lib_root, child)
        except ValueError:
            continue
        if not (child / "animation.yaml").is_file():
            continue
        entries.append(inspect_medanim_entry(root, child))
    return entries


def approved_medanim_catalog(root: Path) -> list[dict[str, Any]]:
    """Return only entries whose immutable doctor approval matches current bytes on disk."""
    return [entry for entry in list_medanim_library(root) if entry.get("status") == "approved"]


def resolve_medanim_preview(root: Path, anim_id: str, name: str) -> Path:
    """Resolve a raster preview image inside ``library/medanim/<id>/`` safely."""
    entry_dir = _entry_dir(root, anim_id)
    cleaned = name.strip()
    if not cleaned or "\\" in cleaned or ":" in cleaned or cleaned.startswith("/"):
        raise LookupError("Tên ảnh preview không hợp lệ")
    posix = PurePosixPath(cleaned)
    if not posix.parts or ".." in posix.parts or posix.suffix.lower() not in _PREVIEW_EXTENSIONS:
        raise LookupError("Đường dẫn ảnh preview không hợp lệ")

    candidates: list[Path] = []
    if len(posix.parts) == 1:
        candidates.append(entry_dir / "previews" / posix.name)
        candidates.append(entry_dir / posix.name)
    else:
        candidates.append(entry_dir.joinpath(*posix.parts))

    animation_path = entry_dir / "animation.yaml"
    if animation_path.is_file():
        try:
            raw = read_yaml(animation_path)
            frames = raw.get("preview_frames") if isinstance(raw, dict) else None
            if isinstance(frames, list):
                for rel in frames:
                    if not isinstance(rel, str):
                        continue
                    try:
                        safe_rel = validate_safe_relative_path(rel, allowed_extensions=_PREVIEW_EXTENSIONS)
                    except ValueError:
                        continue
                    if safe_rel == cleaned or PurePosixPath(safe_rel).name == posix.name:
                        candidates.append(entry_dir.joinpath(*PurePosixPath(safe_rel).parts))
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            pass

    for candidate in candidates:
        if candidate.is_symlink():
            continue
        try:
            resolved = _assert_inside(entry_dir, candidate)
        except ValueError:
            continue
        if resolved.is_file() and resolved.suffix.lower() in _PREVIEW_EXTENSIONS:
            return resolved
    raise LookupError(f"Không tìm thấy ảnh preview {name!r} cho hoạt cảnh {anim_id!r}")


def approve_medanim_entry(
    root: Path,
    anim_id: str,
    *,
    reviewer: str,
    pin: str,
    note: str = "",
    pin_file: Path | None = None,
    now: datetime | None = None,
) -> MedAnimApprovalRecord:
    """Approve one medical animation entry once with doctor PIN and immutable hash binding."""
    target_pin_file = pin_path() if pin_file is None else pin_file
    if not verify_pin(pin, path=target_pin_file):
        raise PermissionError("PIN bác sĩ không đúng hoặc chưa được đặt.")

    clean_reviewer = str(reviewer or "").strip()
    if not clean_reviewer:
        raise ValueError("Cần nhập tên bác sĩ duyệt.")

    reviewed_at = (now or datetime.now().astimezone())
    if reviewed_at.utcoffset() is None:
        raise ValueError("Thời điểm duyệt phải có múi giờ.")

    entry_dir = _entry_dir(root, anim_id)
    animation_path = entry_dir / "animation.yaml"
    if animation_path.is_symlink() or not animation_path.is_file():
        raise LookupError(f"Thiếu animation.yaml cho {anim_id!r}")

    entry = load_medanim_entry(animation_path)
    if entry.id != anim_id:
        raise ValueError(f"animation.yaml id {entry.id!r} không khớp {anim_id!r}")
    if not entry.medical_audit.passed:
        raise ValueError("Không thể duyệt: medical_audit.passed phải là true.")

    actual_hashes, _, asset_errors = verify_entry_assets(root, entry_dir, entry)
    if asset_errors:
        raise ValueError("Không thể duyệt vì kiểm tra tài sản thất bại: " + "; ".join(asset_errors))

    for preview in entry.preview_frames:
        target = entry_dir.joinpath(*PurePosixPath(preview).parts)
        if target.is_symlink() or not _assert_inside(entry_dir, target).is_file():
            raise FileNotFoundError(f"Thiếu ảnh preview đã khai báo: {preview}")

    content_sha256 = _content_sha256(animation_path)
    asset_sha256 = {asset.file: actual_hashes[asset.file] for asset in entry.assets}
    approval_path = entry_dir / "doctor-approval.yaml"

    if approval_path.is_symlink():
        raise ValueError("doctor-approval.yaml không được là symlink")
    if approval_path.exists():
        try:
            existing = MedAnimApprovalRecord.model_validate(read_yaml(approval_path))
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            existing = None
        if (
            existing is not None
            and existing.anim_id == anim_id
            and existing.content_sha256 == content_sha256
            and existing.asset_sha256 == asset_sha256
        ):
            raise FileExistsError(f"Hoạt cảnh {anim_id!r} đã được duyệt cho phiên bản hiện tại.")
        superseded = _unique_history_path(entry_dir, reviewed_at, "superseded-approval")
        os.replace(approval_path, superseded)

    record = MedAnimApprovalRecord(
        anim_id=anim_id,
        reviewer=clean_reviewer,
        reviewed_at=reviewed_at,
        content_sha256=content_sha256,
        asset_sha256=asset_sha256,
        note=str(note or "").strip(),
    )
    write_yaml_once(approval_path, record.model_dump(mode="json"))
    return record


def reject_medanim_entry(
    root: Path,
    anim_id: str,
    *,
    reviewer: str,
    reason: str,
    pin: str,
    pin_file: Path | None = None,
    now: datetime | None = None,
) -> MedAnimRejectionRecord:
    """Reject a medical animation entry with doctor PIN and immutable audit record."""
    target_pin_file = pin_path() if pin_file is None else pin_file
    if not verify_pin(pin, path=target_pin_file):
        raise PermissionError("PIN bác sĩ không đúng hoặc chưa được đặt.")

    clean_reviewer = str(reviewer or "").strip()
    if not clean_reviewer:
        raise ValueError("Cần nhập tên bác sĩ từ chối.")
    clean_reason = str(reason or "").strip()
    if not clean_reason:
        raise ValueError("Cần nhập lý do từ chối hoặc yêu cầu sửa.")

    reviewed_at = (now or datetime.now().astimezone())
    if reviewed_at.utcoffset() is None:
        raise ValueError("Thời điểm từ chối phải có múi giờ.")

    entry_dir = _entry_dir(root, anim_id)
    animation_path = entry_dir / "animation.yaml"
    if animation_path.is_symlink() or not animation_path.is_file():
        raise LookupError(f"Thiếu animation.yaml cho {anim_id!r}")

    content_sha256 = _content_sha256(animation_path)
    try:
        raw_yaml = read_yaml(animation_path)
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        raw_yaml = {}
    asset_sha256 = _best_effort_disk_hashes(root, entry_dir, anim_id, raw_yaml)

    approval_path = entry_dir / "doctor-approval.yaml"
    if approval_path.is_symlink():
        raise ValueError("doctor-approval.yaml không được là symlink")
    if approval_path.exists():
        superseded = _unique_history_path(entry_dir, reviewed_at, "superseded-approval")
        os.replace(approval_path, superseded)

    record = MedAnimRejectionRecord(
        anim_id=anim_id,
        reviewer=clean_reviewer,
        reviewed_at=reviewed_at,
        reason=clean_reason,
        content_sha256=content_sha256,
        asset_sha256=asset_sha256,
    )
    rejection_path = _unique_history_path(entry_dir, reviewed_at, "rejected")
    write_yaml_once(rejection_path, record.model_dump(mode="json"))
    return record
