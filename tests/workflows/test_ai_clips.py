import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.asset_manifest import AssetKind, load_asset_manifest
from healthvideo.domain.license_ledger import LicenseLedger
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.video_ai.base import VeoRequest, VeoResult, VideoProbeResult
from healthvideo.workflows import ai_clips
from healthvideo.workflows.ai_clips import (
    AIClipRights,
    generate_ai_clip,
    probe_ai_clip_media,
    recover_ai_clip_generation,
)


class FakeTransport:
    def __init__(self, content: bytes = b"disposable synthetic bytes") -> None:
        self.content = content
        self.requests: list[VeoRequest] = []

    def generate(self, request: VeoRequest) -> VeoResult:
        self.requests.append(request)
        return VeoResult(video_bytes=self.content, mime_type="video/mp4")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(Path("tests/fixtures/golden-project-v2"), root)
    project_data = read_yaml(root / "project.yaml")
    project_data["state"] = "draft_ready"
    write_yaml_atomic(root / "project.yaml", project_data)
    board_path = root / "revisions/001/storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["visual_budget_profile"] = "m6_5_v1"
    scene = board["scenes"][3]
    scene["visual"] = "ai_clip"
    scene["duration_frames"] = 120
    write_yaml_atomic(board_path, board)
    return root


def rights(**changes: str) -> AIClipRights:
    data = {
        "source": "Google Vertex AI generation",
        "creator": "Protect Your Health operator",
        "license": "operator-recorded provider terms",
        "rights_basis": "operator confirmed authorized generation and use",
    }
    data.update(changes)
    return AIClipRights(**data)


def probe(path: Path) -> VideoProbeResult:
    assert path.read_bytes()
    return VideoProbeResult(
        mime_type="video/mp4",
        container="mp4",
        width=1080,
        height=1920,
        source_fps=24,
        duration_ms=4000,
        source_frame_count=96,
        video_stream_count=1,
    )


def generate(project: Path, transport: FakeTransport, **changes: object) -> Path:
    args: dict[str, object] = {
        "scene_id": "S04",
        "prompt": "  Minh họa chọn món ít muối.  ",
        "duration_seconds": 4,
        "requested_seed": 17,
        "rights": rights(),
        "transport": transport,
        "now": datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        "probe": probe,
    }
    args.update(changes)
    return generate_ai_clip(project, **args)  # type: ignore[arg-type]


def set_medically_approved(project: Path) -> None:
    write_yaml_atomic(
        project / "project.yaml",
        read_yaml(project / "project.yaml") | {"state": "medically_approved"},
    )


def add_medical_approval(project: Path) -> None:
    path = project / "revisions/001/reviews/medical-approval.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x: y", encoding="utf-8")


def test_generate_registers_semantic_clip_rights_and_storyboard(project: Path) -> None:
    fake = FakeTransport()
    output = generate(project, fake)
    revision = project / "revisions/001"
    manifest = load_asset_manifest(revision / "assets/asset-manifest.yaml")
    record = next(item for item in manifest.assets if item.path.endswith("S04.mp4"))
    ledger = LicenseLedger.model_validate(
        read_yaml(revision / "assets/license-ledger.yaml")
    )
    board = Storyboard.model_validate(
        read_yaml(revision / "storyboard/storyboard.yaml")
    )

    assert output.read_bytes() == fake.content
    assert record.kind is AssetKind.AI_CLIP and record.semantic is True
    assert record.ai_provenance is not None
    assert record.ai_provenance.prompt == "  Minh họa chọn món ít muối.  "
    assert ledger.entries[-1].rights_basis == rights().rights_basis
    assert board.scenes[3].visual_assets[0].path == record.path
    assert len(fake.requests) == 1
    assert not (revision / ai_clips.AI_CLIP_INTENT).exists()


def test_decorative_classification_is_derived(project: Path) -> None:
    board_path = project / "revisions/001/storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][3]["claim_id"] = None
    board["scenes"][3]["source_marker"] = None
    write_yaml_atomic(board_path, board)

    generate(project, FakeTransport())
    record = load_asset_manifest(
        project / "revisions/001/assets/asset-manifest.yaml"
    ).assets[-1]
    assert record.semantic is False
    assert "decorative" in (record.classification_reason or "").lower()


@pytest.mark.parametrize(
    "mutation,match",
    [
        (set_medically_approved, "pre-medical"),
        (add_medical_approval, "approval"),
        (lambda p: None, "duration"),
    ],
)
def test_preflight_failures_make_zero_provider_calls(
    project: Path, mutation: object, match: str
) -> None:
    callable_mutation = mutation  # keep parametrization readable
    callable_mutation(project)  # type: ignore[operator]
    fake = FakeTransport()
    changes = {"duration_seconds": 6} if match == "duration" else {}
    with pytest.raises(ValueError, match=match):
        generate(project, fake, **changes)
    assert fake.requests == []


def test_probe_failure_leaves_no_intent_or_declared_asset(project: Path) -> None:
    fake = FakeTransport()

    def bad_probe(_: Path) -> VideoProbeResult:
        raise ValueError("bad media")

    with pytest.raises(ValueError, match="bad media"):
        generate(project, fake, probe=bad_probe)
    revision = project / "revisions/001"
    assert not (revision / ai_clips.AI_CLIP_INTENT).exists()
    assert not (revision / "assets/ai-clips/S04.mp4").exists()
    assert all(
        item.kind is not AssetKind.AI_CLIP
        for item in load_asset_manifest(revision / "assets/asset-manifest.yaml").assets
    )


def test_identical_retry_does_not_call_provider_again(project: Path) -> None:
    fake = FakeTransport()
    first = generate(project, fake)
    second = generate(project, fake)
    assert first == second
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"prompt": "Khác"},
        {"requested_seed": 99},
        {"rights": rights(rights_basis="different")},
    ],
)
def test_existing_clip_with_changed_identity_refuses_regeneration(
    project: Path, changes: dict[str, object]
) -> None:
    first = FakeTransport()
    generate(project, first)
    second = FakeTransport()
    with pytest.raises(ValueError, match="differs"):
        generate(project, second, **changes)
    assert second.requests == []


def test_ffprobe_parser_accepts_one_video_and_ignores_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "streams": [
            {"codec_type": "audio"},
            {
                "codec_type": "video",
                "width": 1080,
                "height": 1920,
                "r_frame_rate": "24/1",
                "nb_read_frames": "96",
            },
        ],
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "4.000000"},
    }
    seen: list[object] = []

    class Completed:
        stdout = json.dumps(payload)

    def fake_run(argv: object, **kwargs: object) -> Completed:
        seen.append((argv, kwargs))
        return Completed()

    monkeypatch.setattr(ai_clips.subprocess, "run", fake_run)
    result = probe_ai_clip_media(tmp_path / "disposable.mp4")
    assert result.source_frame_count == 96
    argv, kwargs = seen[0]  # type: ignore[misc]
    assert argv[0] == "ffprobe" and kwargs["shell"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("width", 720),
        ("height", 1080),
        ("r_frame_rate", "24000/1001"),
        ("nb_read_frames", "95"),
    ],
)
def test_ffprobe_parser_rejects_unreviewed_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    video = {
        "codec_type": "video",
        "width": 1080,
        "height": 1920,
        "r_frame_rate": "24/1",
        "nb_read_frames": "96",
    }
    video[field] = value
    payload = {
        "streams": [video],
        "format": {"format_name": "mp4", "duration": "4.000000"},
    }

    class Completed:
        stdout = json.dumps(payload)

    monkeypatch.setattr(ai_clips.subprocess, "run", lambda *_args, **_kwargs: Completed())
    with pytest.raises(ValueError):
        probe_ai_clip_media(tmp_path / "disposable.mp4")


def test_recovery_advances_after_manifest_write_failure(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTransport()
    real_write = ai_clips._write_manifest
    calls = 0

    def fail_once(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected crash")
        real_write(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ai_clips, "_write_manifest", fail_once)
    with pytest.raises(OSError, match="injected"):
        generate(project, fake)
    revision = project / "revisions/001"
    assert (revision / ai_clips.AI_CLIP_INTENT).is_file()
    assert (revision / "assets/ai-clips/S04.mp4").is_file()

    recover_ai_clip_generation(project)
    assert not (revision / ai_clips.AI_CLIP_INTENT).exists()


def test_recovery_refuses_unrelated_storyboard_edit(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_clips, "_write_manifest", lambda *_: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError):
        generate(project, FakeTransport())
    board_path = project / "revisions/001/storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["title"] = "unrelated edit"
    write_yaml_atomic(board_path, board)
    with pytest.raises(ValueError, match="conflict"):
        recover_ai_clip_generation(project)
