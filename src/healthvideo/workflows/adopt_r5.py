"""Adopt R5 quality standards on a new revision and stage licensed library assets."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from healthvideo.approver_pin import PinError, pin_path, verify_pin
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.revision import RevisionRecord
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.revisions import create_revision
from healthvideo.visuals.medanim_assets import (
    assert_safe_path,
    copy_used_assets,
    load_asset_catalog,
)
from healthvideo.workflows.factory_standards import SNAPSHOT, pin_standards
from healthvideo.workflows.gate_review import MEDICAL_APPROVAL_ARTIFACT, R5_CATALOG

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def r5_active(revision_root: Path) -> bool:
    """Return True when ``revision_root`` pins ``quality_profile: r5_v1``."""
    snapshot = revision_root / SNAPSHOT
    if not snapshot.is_file():
        return False
    data = read_yaml(snapshot)
    if not isinstance(data, dict):
        return False
    quality = data.get("quality_standard")
    return isinstance(quality, dict) and quality.get("profile") == "r5_v1"


def _resolve_project_dir_by_slug(root: Path, slug: str) -> Path:
    if (
        not slug
        or len(slug) > 80
        or "/" in slug
        or "\\" in slug
        or ".." in slug
        or not _SLUG_RE.fullmatch(slug)
    ):
        raise ValueError(f"Slug không hợp lệ: {slug!r}")
    projects_base = assert_safe_path(root / "projects").resolve()
    project_dir = assert_safe_path(root / "projects" / slug)
    if not project_dir.resolve().is_relative_to(projects_base):
        raise ValueError("Thư mục dự án nằm ngoài phạm vi cho phép.")
    if not (project_dir / "project.yaml").is_file():
        raise FileNotFoundError(f"Không tìm thấy project: {slug}")
    return project_dir


def _resolve_project_dir(root: Path, slug_or_project: str | Path) -> Path:
    if isinstance(slug_or_project, str) and _SLUG_RE.fullmatch(slug_or_project):
        by_slug = root / "projects" / slug_or_project
        if (by_slug / "project.yaml").is_file():
            return _resolve_project_dir_by_slug(root, slug_or_project)
    candidate = Path(slug_or_project)
    project_dir = candidate if candidate.is_absolute() else (root / candidate)
    assert_safe_path(project_dir)
    if not (project_dir / "project.yaml").is_file():
        raise FileNotFoundError(f"Không tìm thấy project: {slug_or_project}")
    return project_dir


_PARENT_HOLDS = ("blocked.txt", "agent-retry.yaml", "production-retry.yaml", "leader-guidance.yaml")


def _release_parent_holds(root: Path, slug: str) -> None:
    """The doctor's PIN-approved restart supersedes the old revision's repair holds."""
    from healthvideo.workflows import doctor_questions

    logs = root / "topics" / "logs" / slug
    for name in _PARENT_HOLDS:
        (logs / name).unlink(missing_ok=True)
    repair = logs / "leader-repair.yaml"
    if repair.is_file():
        data = read_yaml(repair)
        if isinstance(data, dict) and data.get("phase") in {"needs_attention", "repair_failed"}:
            repair.unlink()
    doctor_questions.supersede_kind(root, slug, "escalation", reason="Bác sĩ đã làm lại theo chuẩn R5.")


def adopt_r5_project(
    root: Path,
    slug: str,
    *,
    reason: str,
    pin: str,
    now: datetime | None = None,
    pin_file: Path | None = None,
    limiter: Any | None = None,
    recover: bool = False,
) -> dict[str, Any]:
    """Create a new R5-pinned revision from the active revision and reset to writer step.

    Requires doctor PIN verification because the new revision supersedes any
    prior medical/video approvals. Leaves the parent revision byte-unchanged,
    never writes ``profiles/doctor-feedback.yaml`` or ``profiles/factory-standards.yaml``,
    and supports idempotent recovery when ``recover=True``.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Cần nhập lý do chuyển sang chuẩn R5.")
    reason_clean = reason.strip()

    project_dir = _resolve_project_dir_by_slug(root, slug)

    resolved_pin_file = pin_path() if pin_file is None else pin_file
    if not resolved_pin_file.is_file():
        raise PinError("Chưa đặt PIN; chạy healthvideo review set-pin một lần.")
    if limiter is not None:
        limiter.check(pin, lambda value: verify_pin(value, path=resolved_pin_file))
    elif not pin or not verify_pin(pin, path=resolved_pin_file):
        raise PinError("PIN không đúng.")

    manifest_path = project_dir / "project.yaml"
    manifest_data = read_yaml(manifest_path)
    if manifest_data.get("schema_version") != "2.0":
        raise ValueError("Chỉ hỗ trợ project schema 2.0.")
    manifest = ProjectManifestV2.model_validate(manifest_data)

    if recover:
        active_root = project_dir / "revisions" / manifest.active_revision
        workflow_path = active_root / "workflow.yaml"
        if workflow_path.is_file():
            prior = RevisionRecord.model_validate(read_yaml(workflow_path))
            if (
                prior.parent_revision is not None
                and prior.reason == reason_clean
                and not (active_root / MEDICAL_APPROVAL_ARTIFACT).exists()
            ):
                if not (active_root / SNAPSHOT).is_file():
                    pin_standards(root, project_dir, quality_profile="r5_v1")
                if not r5_active(active_root):
                    raise ValueError(
                        f"Revision {manifest.active_revision} đã ghim chuẩn khác, không thể khôi phục R5."
                    )
                if (
                    manifest.state is not WorkflowState.EVIDENCE_READY
                    or manifest.side_state is not None
                    or manifest.artifact_hashes
                ):
                    updated = manifest.model_copy(
                        update={
                            "state": WorkflowState.EVIDENCE_READY,
                            "side_state": None,
                            "artifact_hashes": {},
                        }
                    )
                    write_yaml_atomic(manifest_path, updated.model_dump(mode="json"))
                return {
                    "ok": True,
                    "slug": slug,
                    "parent_revision": prior.parent_revision,
                    "revision": manifest.active_revision,
                    "state": WorkflowState.EVIDENCE_READY.value,
                    "quality_profile": "r5_v1",
                    "recovered": True,
                }

    parent_revision = manifest.active_revision
    parent_root = project_dir / "revisions" / parent_revision
    if not (parent_root / "evidence" / "ledger.yaml").is_file():
        raise ValueError(
            f"Revision {parent_revision} chưa có evidence/ledger.yaml; "
            "hoàn tất bước nghiên cứu trước khi chuyển sang chuẩn R5."
        )

    timestamp = now if now is not None else datetime.now().astimezone()
    new_revision = create_revision(
        project_dir, reason_clean, now=timestamp, recover=recover
    )
    pin_standards(root, project_dir, quality_profile="r5_v1")
    new_root = project_dir / "revisions" / new_revision
    if not r5_active(new_root):
        raise ValueError(f"Không thể ghim chuẩn R5 cho revision {new_revision}.")

    updated_manifest = ProjectManifestV2.model_validate(read_yaml(manifest_path)).model_copy(
        update={
            "state": WorkflowState.EVIDENCE_READY,
            "side_state": None,
            "artifact_hashes": {},
        }
    )
    write_yaml_atomic(manifest_path, updated_manifest.model_dump(mode="json"))
    _release_parent_holds(root, slug)
    return {
        "ok": True,
        "slug": slug,
        "parent_revision": parent_revision,
        "revision": new_revision,
        "state": WorkflowState.EVIDENCE_READY.value,
        "quality_profile": "r5_v1",
        "recovered": False,
    }


def stage_r5_assets(
    root: Path,
    slug_or_project: str | Path,
    *,
    catalog: Path,
    asset_ids: list[str],
) -> dict[str, Any]:
    """Copy verified repo-library assets into the active revision's ``assets/r5/`` catalog.

    Reads only from ``<root>/library/medanim/**``; performs no network I/O;
    verifies license, provenance URLs, size limit, and SHA-256 via ``medanim_assets``.
    Refuses to modify a revision that already has medical approval.
    """
    root = Path(root)
    project_dir = _resolve_project_dir(root, slug_or_project)
    layout = resolve_project_layout(project_dir)
    revision_root = assert_safe_path(layout.artifact_root)
    if (revision_root / MEDICAL_APPROVAL_ARTIFACT).exists():
        raise ValueError(
            "Revision đã duyệt y khoa; cần mở lại cổng hoặc tạo revision mới trước khi dàn asset R5."
        )

    library_root = assert_safe_path(root / "library" / "medanim").resolve()
    catalog_path = catalog if catalog.is_absolute() else (root / catalog)
    assert_safe_path(catalog_path)
    resolved_catalog = catalog_path.resolve()
    if not resolved_catalog.is_relative_to(library_root):
        raise ValueError("Catalog phải nằm trong thư viện library/medanim của repo.")
    if not resolved_catalog.is_file():
        raise FileNotFoundError(f"Không tìm thấy catalog: {catalog_path}")

    cleaned_ids = [item.strip() for item in asset_ids if item and item.strip()]
    if not cleaned_ids:
        raise ValueError("Cần chỉ định ít nhất một asset id qua --ids.")

    records = load_asset_catalog(resolved_catalog)
    r5_dir = assert_safe_path(revision_root / "assets" / "r5")
    used = copy_used_assets(records, cleaned_ids, resolved_catalog.parent, r5_dir)

    staged_records = [
        record.model_copy(
            update={"file": (PurePosixPath("assets/r5") / record.file).as_posix()}
        )
        for record in used
    ]

    rev_catalog_path = assert_safe_path(revision_root / R5_CATALOG)
    existing = list(load_asset_catalog(rev_catalog_path)) if rev_catalog_path.is_file() else []
    merged_by_id = {item.id: item for item in existing}
    for staged_record in staged_records:
        merged_by_id[staged_record.id] = staged_record

    write_yaml_atomic(
        rev_catalog_path,
        {"assets": [item.model_dump(mode="json") for item in merged_by_id.values()]},
    )
    # Re-validate the merged revision catalog to guarantee uniqueness and provenance.
    load_asset_catalog(rev_catalog_path)

    return {
        "ok": True,
        "slug": layout.manifest.slug,
        "revision": layout.manifest.active_revision,
        "catalog": R5_CATALOG,
        "staged": [
            {
                "id": record.id,
                "file": record.file,
                "sha256": record.sha256,
                "license": record.license,
            }
            for record in staged_records
        ],
    }
