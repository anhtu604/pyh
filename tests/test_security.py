import ast
from pathlib import Path

from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project import ProjectState
from healthvideo.security import audit_project
from healthvideo.workflows.backup import is_backup_excluded
from tests.helpers import create_project_fixture, create_v2_project_fixture


def test_clean_project_has_no_findings(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    assert audit_project(project) == ()


def test_clean_v1_project_has_no_findings(tmp_path: Path) -> None:
    project = create_project_fixture(tmp_path / "source", ProjectState.PRODUCING.value)
    assert audit_project(project) == ()


def test_audit_finds_forbidden_approval_binding_without_leaking_bytes(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    forbidden = project / "revisions/001/cache/private.bin"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_bytes(b"private-secret-value")
    manifest = project / "revisions/001/assets/asset-manifest.yaml"
    from healthvideo.storage.files import read_yaml, write_yaml_atomic

    data = read_yaml(manifest)
    data["assets"][0]["path"] = "cache/private.bin"
    write_yaml_atomic(manifest, data)
    findings = audit_project(project)
    assert any(item.rule_id == "backup-binding" for item in findings)
    assert "private-secret-value" not in repr(findings)


def test_audit_detects_link_without_following_it(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    outside = tmp_path / "outside.txt"
    outside.write_text("private-secret-value", encoding="utf-8")
    link = project / "escape.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("symlink unavailable on this filesystem")
    findings = audit_project(project)
    assert any(item.rule_id == "unsafe-entry" and item.relative_path == "escape.txt" for item in findings)
    assert "private-secret-value" not in repr(findings)


def test_audit_secret_fields_are_sanitized_and_cli_fails(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    typed = project / "revisions/001/evidence/provider-response.json"
    typed.write_text('{"access_token":"private-secret-value"}', encoding="utf-8")
    result = CliRunner().invoke(app, ["security-audit", str(project)])
    assert result.exit_code == 1
    assert "credential-field" in result.stdout
    assert "private-secret-value" not in result.stdout
    assert "access_token" not in result.stdout


def test_audit_is_deterministic(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    (project / ".env").write_text("TOKEN=private-secret-value", encoding="utf-8")
    first = audit_project(project)
    assert first == audit_project(project)
    assert all(item.relative_path and "private-secret-value" not in repr(item) for item in first)


def test_unignored_generated_media_is_reported(tmp_path: Path, monkeypatch) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    media = project / "revisions/001/renders/video.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"fake media")
    monkeypatch.setattr("healthvideo.security._repo_root", lambda _root: tmp_path)
    monkeypatch.setattr("healthvideo.security._is_ignored", lambda _repo, _path: False)
    assert any(item.rule_id == "commit-risk" and item.relative_path.endswith("video.mp4") for item in audit_project(project))


def test_gate_contract_remains_two_human_gates() -> None:
    assert {kind.value for kind in GateKind} == {"medical", "video"}


def test_audit_rejects_generic_token_and_raw_provider_response(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    typed = project / "revisions/001/evidence/provider-response.json"
    typed.write_text('{"token":"private-secret-value","data":"raw"}', encoding="utf-8")
    findings = audit_project(project)
    assert {item.rule_id for item in findings} >= {"credential-field", "raw-provider-response"}
    assert "private-secret-value" not in repr(findings)


def test_backup_exclusion_policy_is_pinned_independently() -> None:
    for relative in (
        ".healthvideo/write-lease.yaml", ".env", "cache/provider.json",
        "source-documents/fulltext.pdf", "revisions/001/assets/model.onnx",
        "revisions/001/renders/video.mp4.tmp",
    ):
        assert is_backup_excluded(relative), relative
    for relative in (
        "project.yaml", "revisions/001/reviews/medical-approval.yaml",
        "revisions/001/workflow/pending-ai-clip-generation.yaml",
        "revisions/001/workflow/staged-ai-clips/scene.mp4",
    ):
        assert not is_backup_excluded(relative), relative


def test_oversized_typed_artifact_fails_closed(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    typed = project / "revisions/001/evidence/large.json"
    typed.write_bytes(b" " * 2_000_001)
    assert any(item.rule_id == "typed-artifact" and item.relative_path.endswith("large.json") for item in audit_project(project))


def test_production_and_package_do_not_import_provider_or_publish_clients() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = {"httpx", "requests", "urllib", "selenium", "playwright", "tiktok"}
    for relative in (
        "src/healthvideo/workflows/produce.py",
        "src/healthvideo/workflows/package.py",
        "src/healthvideo/render/run.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        imports = [
            name.name for node in ast.walk(tree) if isinstance(node, ast.Import)
            for name in node.names
        ] + [
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ]
        assert all(name.split(".")[0] not in forbidden for name in imports), relative
        assert all(not name.startswith("healthvideo.video_ai") for name in imports), relative
