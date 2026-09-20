import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

import healthvideo.tts.pronunciation as pronunciation_module
import healthvideo.workflows.ai_clips as ai_clips_module
import healthvideo.workflows.produce as produce_workflow
from healthvideo.domain.brand import LogoVariant, MascotPose
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.base import TTSRequest, TTSResult
from healthvideo.tts.silent import SilentTTS
from healthvideo.video_ai.veo import GoogleVeoTransport
from healthvideo.workflows.gate_review import (
    approve_gate,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
    video_reviewed_paths,
)
from healthvideo.workflows.hook_outro import author_hook_outro
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import _input_hash, produce_project
from healthvideo.workflows.visual_assets import (
    create_brand_logo_asset,
    create_mascot_reaction_asset,
)
from tests.helpers import create_project_fixture, create_v2_project_fixture
from tests.workflows.test_gate_review import _author_ai_clip, _create_ai_project

V2_REVIEWED_AT = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


def test_m64_production_records_measured_audio_and_rejects_stale_qa(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][0]["duration_frames"] = 1350
    write_yaml_atomic(board_path, board)
    author_hook_outro(project, duration_frames=90)
    create_brand_logo_asset(project, scene_id="OUTRO", asset_name="pyh-logo", variant=LogoVariant.MONOGRAM)
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)

    def runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    produce_project(project, SilentTTS(), runner)
    qa_path = revision / "reviews/video-qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    assert qa["audio_duration_ms"] > 0
    assert qa["composition_duration_ms"] == 48000
    assert qa["trailing_visual_ms"] >= 0
    qa.pop("audio_duration_ms")
    qa_path.write_text(json.dumps(qa), encoding="utf-8")
    with pytest.raises(ValueError, match="medically_approved"):
        produce_project(project, SilentTTS(), runner)


def test_m64_production_retry_reuses_promoted_timing_qa(tmp_path: Path) -> None:
    project = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][0]["duration_frames"] = 1350
    write_yaml_atomic(board_path, board)
    author_hook_outro(project, duration_frames=90)
    create_brand_logo_asset(
        project,
        scene_id="OUTRO",
        asset_name="pyh-logo",
        variant=LogoVariant.MONOGRAM,
    )
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)

    def runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    first = produce_project(project, SilentTTS(), runner)
    assert (revision / "reviews/video-qa.json").is_file()

    class NoSynthesis(SilentTTS):
        def synthesize(self, request: TTSRequest, output_path: Path) -> TTSResult:
            pytest.fail("TTS invoked on retry")

    assert produce_project(
        project,
        NoSynthesis(),
        lambda _: pytest.fail("renderer invoked on retry"),
    ) == first

    project_data = read_yaml(project / "project.yaml")
    project_data["state"] = WorkflowState.MEDICALLY_APPROVED.value
    write_yaml_atomic(project / "project.yaml", project_data)
    assert produce_project(
        project,
        NoSynthesis(),
        lambda _: pytest.fail("renderer invoked during recovery"),
    ) == first
    assert read_yaml(project / "project.yaml")["state"] == (
        WorkflowState.AWAITING_VIDEO_REVIEW.value
    )

    qa_path = revision / "reviews/video-qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    original_qa = dict(qa)
    qa["audio_duration_ms"] += 1000
    qa["trailing_visual_ms"] = max(
        0, qa["composition_duration_ms"] - qa["audio_duration_ms"]
    )
    qa_path.write_text(json.dumps(qa), encoding="utf-8")
    with pytest.raises(ValueError, match="medically_approved"):
        produce_project(project, SilentTTS(), runner)

    qa = original_qa
    qa["composition_duration_ms"] += 1000
    qa["trailing_visual_ms"] = max(
        0, qa["composition_duration_ms"] - qa["audio_duration_ms"]
    )
    qa_path.write_text(json.dumps(qa), encoding="utf-8")
    with pytest.raises(ValueError, match="medically_approved"):
        produce_project(project, SilentTTS(), runner)


def _m65_project(
    tmp_path: Path, *, ai: bool = False
) -> Path:
    project = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    highlight = dict(board["scenes"][0])
    highlight["id"] = "S02"
    if ai:
        whiteboard_frames, highlight_frames, ai_frames = 830, 250, 120
    else:
        whiteboard_frames, highlight_frames, ai_frames = 750, 250, 0
    board["visual_budget_profile"] = "m6_5_v1"
    board["scenes"] = [
        {
            "id": "S01",
            "start_frame": 0,
            "duration_frames": whiteboard_frames,
            "narration": "Whiteboard synthetic.",
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "whiteboard",
        },
        {
            **highlight,
            "start_frame": whiteboard_frames,
            "duration_frames": highlight_frames,
        },
    ]
    if ai_frames:
        board["scenes"].append(
            {
                "id": "S03",
                "start_frame": whiteboard_frames + highlight_frames,
                "duration_frames": ai_frames,
                "narration": "AI clip placeholder.",
                "visual": "ai_clip",
            }
        )
    write_yaml_atomic(board_path, board)
    if not ai:
        approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)
    return project


class CountingSilent(SilentTTS):
    def __init__(self) -> None:
        self.calls = 0

    def synthesize(self, request: TTSRequest, output_path: Path) -> TTSResult:
        self.calls += 1
        return super().synthesize(request, output_path)


class NoSynthesis(SilentTTS):
    def synthesize(self, request: TTSRequest, output_path: Path) -> TTSResult:
        pytest.fail("TTS invoked while validating M6.5 cache")


def test_m65_production_revalidates_budget_before_tts_or_render(tmp_path: Path) -> None:
    project = _m65_project(tmp_path)
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][0]["duration_frames"] = 600
    board["scenes"][1]["start_frame"] = 600
    board["scenes"][1]["duration_frames"] = 400
    write_yaml_atomic(board_path, board)
    approval_path = revision / "reviews/medical-approval.yaml"
    approval = read_yaml(approval_path)
    approval["artifact_hashes"] = hash_reviewed_artifacts(
        medical_reviewed_paths(revision)
    )
    write_yaml_atomic(approval_path, approval)
    tts = CountingSilent()
    render_calls: list[list[str]] = []

    with pytest.raises(ValueError, match="visual budget failed"):
        produce_project(project, tts, lambda argv: render_calls.append(argv) or 0)

    assert tts.calls == 0 and render_calls == []
    assert read_yaml(project / "project.yaml")["state"] == "medically_approved"


def test_m65_ai_clip_without_declared_asset_fails_at_medical_gate(
    tmp_path: Path,
) -> None:
    project = _m65_project(tmp_path, ai=True)

    with pytest.raises(ValueError, match="exactly one ai_clip asset"):
        approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)

    assert read_yaml(project / "project.yaml")["state"] == "awaiting_medical_review"


def test_m65_production_records_visual_qa_and_reuses_valid_promoted_cache(
    tmp_path: Path,
) -> None:
    project = _m65_project(tmp_path)
    revision = project / "revisions/001"
    tts = CountingSilent()
    render_calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        render_calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    first = produce_project(project, tts, runner)
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    assert qa["visual_budget"] == {
        "profile": "m6_5_v1",
        "override_active": False,
        "total_frames": 1000,
        "category_frames": {
            "whiteboard_svg": 750,
            "chart_crop": 250,
            "ai_clip": 0,
        },
        "category_basis_points": {
            "whiteboard_svg": 7500,
            "chart_crop": 2500,
            "ai_clip": 0,
        },
        "effective_bounds": {
            "whiteboard_svg": {"min_percent": 65, "max_percent": 75},
            "chart_crop": {"min_percent": 15, "max_percent": 25},
            "ai_clip": {"min_percent": 0, "max_percent": 10},
        },
        "passed": True,
    }
    assert produce_project(
        project, NoSynthesis(), lambda _: pytest.fail("renderer invoked on retry")
    ) == first
    project_data = read_yaml(project / "project.yaml")
    project_data["state"] = "medically_approved"
    write_yaml_atomic(project / "project.yaml", project_data)
    assert produce_project(
        project, NoSynthesis(), lambda _: pytest.fail("renderer invoked on recovery")
    ) == first
    assert tts.calls == 1 and len(render_calls) == 1


@pytest.mark.parametrize(
    "tamper",
    [
        "missing",
        "total_frames",
        "category_frames",
        "category_basis_points",
        "effective_bounds",
        "override_active",
        "profile",
        "passed",
        "extra_field",
        "total_frames_as_float",
        "override_active_as_int",
    ],
)
def test_m65_cache_rejects_each_tampered_visual_qa_field(
    tmp_path: Path, tamper: str
) -> None:
    project = _m65_project(tmp_path)
    revision = project / "revisions/001"

    def runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    produce_project(project, SilentTTS(), runner)
    qa_path = revision / "reviews/video-qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    replacements = {
        "total_frames": ("total_frames", 1001),
        "override_active": ("override_active", True),
        "profile": ("profile", "legacy"),
        "passed": ("passed", False),
        "extra_field": ("rounded_percent", 75),
        "total_frames_as_float": ("total_frames", 1000.0),
        "override_active_as_int": ("override_active", 0),
    }
    if tamper == "missing":
        del qa["visual_budget"]
    elif tamper in replacements:
        field, value = replacements[tamper]
        qa["visual_budget"][field] = value
    elif tamper == "effective_bounds":
        qa["visual_budget"][tamper]["whiteboard_svg"]["min_percent"] = 64
    else:
        qa["visual_budget"][tamper]["whiteboard_svg"] += 1
    qa_path.write_text(json.dumps(qa), encoding="utf-8")

    with pytest.raises(ValueError, match="medically_approved"):
        produce_project(
            project,
            NoSynthesis(),
            lambda _: pytest.fail("renderer invoked for tampered cache"),
        )


@pytest.mark.parametrize("tampered", [False, True])
def test_m65_recovery_verifies_staged_visual_qa_before_promotion(
    tmp_path: Path, tampered: bool
) -> None:
    project = _m65_project(tmp_path)
    revision = project / "revisions/001"
    tts = CountingSilent()
    render_calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        render_calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    produce_project(project, tts, runner)
    promoted = revision / "reviews/video-qa.json"
    expected = json.loads(promoted.read_text(encoding="utf-8"))["visual_budget"]
    staged = revision / "renders/video-qa.json"
    qa = json.loads(promoted.read_text(encoding="utf-8"))
    if tampered:
        qa["visual_budget"]["category_frames"]["chart_crop"] = 0
    staged.write_text(json.dumps(qa), encoding="utf-8")
    promoted.unlink()
    project_data = read_yaml(project / "project.yaml")
    project_data["state"] = "medically_approved"
    write_yaml_atomic(project / "project.yaml", project_data)

    produce_project(project, tts, runner)

    assert json.loads(promoted.read_text(encoding="utf-8"))["visual_budget"] == expected
    assert (tts.calls, len(render_calls)) == ((2, 2) if tampered else (1, 1))
    assert read_yaml(project / "project.yaml")["state"] == "awaiting_video_review"


AI_CLIP = "assets/ai-clips/S04.mp4"


def _m66_approved_ai_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = _create_ai_project(tmp_path)
    _author_ai_clip(project)
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)

    def no_provider(*_args: object, **_kwargs: object) -> None:
        pytest.fail("production called the AI provider")

    monkeypatch.setattr(ai_clips_module, "generate_ai_clip", no_provider)
    monkeypatch.setattr(ai_clips_module, "probe_ai_clip_media", no_provider)
    monkeypatch.setattr(GoogleVeoTransport, "generate", no_provider)
    return project


def test_m66_production_stages_one_approved_ai_clip_without_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _m66_approved_ai_project(tmp_path, monkeypatch)
    revision = project / "revisions/001"
    clip = revision / AI_CLIP
    tts = CountingSilent()
    render_inputs: list[dict] = []

    def runner(argv: list[str]) -> int:
        props = Path(argv[argv.index("--props") + 1])
        render_inputs.append(json.loads(props.read_text(encoding="utf-8")))
        assert (props.parent / AI_CLIP).read_bytes() == clip.read_bytes()
        _write_synthetic_output(argv)
        return 0

    first = produce_project(project, tts, runner)

    assert [
        (scene["id"], ref)
        for scene in render_inputs[0]["scenes"]
        for ref in scene["visual_assets"]
        if ref["role"] == "ai_clip"
    ] == [("S04", {"path": AI_CLIP, "role": "ai_clip", "pose": None})]
    manifest = json.loads(
        (revision / "renders/render-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["asset_sha256"][AI_CLIP] == sha256_file(clip)
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    assert qa["visual_budget"]["category_frames"]["ai_clip"] == 120
    assert produce_project(
        project, NoSynthesis(), lambda _: pytest.fail("renderer invoked on retry")
    ) == first
    project_data = read_yaml(project / "project.yaml")
    project_data["state"] = "medically_approved"
    write_yaml_atomic(project / "project.yaml", project_data)
    assert produce_project(
        project, NoSynthesis(), lambda _: pytest.fail("renderer invoked on recovery")
    ) == first
    assert tts.calls == 1 and len(render_inputs) == 1


def _resign_medical_approval(revision: Path) -> None:
    approval_path = revision / "reviews/medical-approval.yaml"
    approval = read_yaml(approval_path)
    approval["artifact_hashes"] = hash_reviewed_artifacts(medical_reviewed_paths(revision))
    write_yaml_atomic(approval_path, approval)


def _edit_yaml(path: Path, edit: Callable[[dict], object]) -> None:
    data = read_yaml(path)
    edit(data)
    write_yaml_atomic(path, data)


def _tamper_ai_bytes(revision: Path) -> None:
    (revision / AI_CLIP).write_bytes(b"tampered-ai-clip")


def _delete_ai_bytes(revision: Path) -> None:
    (revision / AI_CLIP).unlink()


def _edit_ai_rights(revision: Path) -> None:
    _edit_yaml(
        revision / "assets/license-ledger.yaml",
        lambda data: data["entries"][-1].update(rights_basis="edited after approval"),
    )


def _edit_ai_provenance(revision: Path) -> None:
    _edit_yaml(
        revision / "assets/asset-manifest.yaml",
        lambda data: data["assets"][-1]["ai_provenance"].update(prompt="edited"),
    )


def _leave_pending_ai_intent(revision: Path) -> None:
    write_yaml_atomic(revision / ai_clips_module.AI_CLIP_INTENT, {"schema_version": "1.0"})


def _wrong_ai_role(revision: Path) -> None:
    _edit_yaml(
        revision / "storyboard/storyboard.yaml",
        lambda data: data["scenes"][-1]["visual_assets"][0].update(role="whiteboard"),
    )
    _resign_medical_approval(revision)


def _mismatched_ai_duration(revision: Path) -> None:
    def rescale(data: dict) -> None:
        whiteboard, highlight, clip = data["scenes"]
        whiteboard["duration_frames"] = 1260
        highlight["start_frame"], highlight["duration_frames"] = 1260, 360
        clip["start_frame"], clip["duration_frames"] = 1620, 180

    _edit_yaml(revision / "storyboard/storyboard.yaml", rescale)
    _resign_medical_approval(revision)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (_tamper_ai_bytes, "current medical approval"),
        (_delete_ai_bytes, "current medical approval"),
        (_edit_ai_rights, "current medical approval"),
        (_edit_ai_provenance, "current medical approval"),
        (_leave_pending_ai_intent, "cannot recover after medical review"),
        (_wrong_ai_role, "does not match asset kind"),
        (_mismatched_ai_duration, "duration does not match AI clip provenance"),
    ],
)
def test_m66_production_rejects_invalid_ai_clip_before_tts_or_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[Path], None],
    match: str,
) -> None:
    project = _m66_approved_ai_project(tmp_path, monkeypatch)
    mutate(project / "revisions/001")
    tts = CountingSilent()
    render_calls: list[list[str]] = []

    with pytest.raises((ValueError, FileNotFoundError), match=match):
        produce_project(project, tts, lambda argv: render_calls.append(argv) or 0)

    assert tts.calls == 0 and render_calls == []
    assert read_yaml(project / "project.yaml")["state"] == "medically_approved"


def test_v2_produce_stages_declared_mascot_asset(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    revision = project_dir / "revisions" / "001"
    storyboard_path = revision / "storyboard" / "storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    storyboard["scenes"][0]["duration_frames"] = 1350
    write_yaml_atomic(storyboard_path, storyboard)
    source_asset = create_mascot_reaction_asset(
        project_dir,
        scene_id="S01",
        asset_name="pyh-welcome",
        pose=MascotPose.WELCOME,
    )
    approve_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer="BS Nguyễn Văn An",
        now=V2_REVIEWED_AT,
    )

    render_inputs: list[dict] = []

    def runner(argv: list[str]) -> int:
        props = Path(argv[argv.index("--props") + 1])
        render_inputs.append(json.loads(props.read_text(encoding="utf-8")))
        assert (props.parent / "assets" / "pyh-welcome.svg").read_bytes() == source_asset.read_bytes()
        _write_synthetic_output(argv)
        return 0

    produce_project(project_dir, SilentTTS(), runner)

    assert render_inputs[0]["scenes"][0]["visual_assets"] == [
        {"path": "assets/pyh-welcome.svg", "role": "mascot", "pose": "welcome"}
    ]
    manifest = json.loads(
        (revision / "renders" / "render-manifest.json").read_text(encoding="utf-8")
    )
    assert "assets/pyh-welcome.svg" in manifest["asset_sha256"]


def test_v2_provider_identity_changes_cache_with_same_provider_name(tmp_path: Path) -> None:
    project_dir = _v2_medically_approved_project(tmp_path)
    revision = project_dir / "revisions" / "001"
    calls: list[list[str]] = []

    class NamedSilent(SilentTTS):
        def __init__(self, voice: str) -> None:
            self.voice = voice

        def cache_identity(self) -> dict[str, str]:
            return {"provider": "silent", "voice_id": self.voice}

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    produce_project(project_dir, NamedSilent("a"), runner)
    first = json.loads((revision / "renders" / "render-manifest.json").read_text(encoding="utf-8"))
    project = read_yaml(project_dir / "project.yaml")
    project["state"] = "medically_approved"
    write_yaml_atomic(project_dir / "project.yaml", project)
    produce_project(project_dir, NamedSilent("b"), runner)
    second = json.loads((revision / "renders" / "render-manifest.json").read_text(encoding="utf-8"))
    assert first["input_hash"] != second["input_hash"]
    assert second["provider_identity"]["voice_id"] == "b"
    assert len(calls) == 2


def test_v2_renderer_identity_changes_cache_and_render_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = _v2_medically_approved_project(tmp_path)
    revision = project_dir / "revisions" / "001"
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    monkeypatch.setattr(
        produce_workflow,
        "renderer_identity",
        lambda: {"name": "remotion", "package_version": "4.0.522", "source_sha256": "a" * 64},
    )
    produce_project(project_dir, SilentTTS(), runner)
    first = json.loads((revision / "renders" / "render-manifest.json").read_text(encoding="utf-8"))
    project = read_yaml(project_dir / "project.yaml")
    project["state"] = "medically_approved"
    write_yaml_atomic(project_dir / "project.yaml", project)

    monkeypatch.setattr(
        produce_workflow,
        "renderer_identity",
        lambda: {"name": "remotion", "package_version": "4.0.523", "source_sha256": "b" * 64},
    )
    produce_project(project_dir, SilentTTS(), runner)
    second = json.loads((revision / "renders" / "render-manifest.json").read_text(encoding="utf-8"))

    assert first["input_hash"] != second["input_hash"]
    assert second["renderer_identity"] == {
        "name": "remotion",
        "package_version": "4.0.523",
        "source_sha256": "b" * 64,
    }
    assert len(calls) == 2


def test_v2_rejects_bad_staged_audio_before_render(tmp_path: Path) -> None:
    project_dir = _v2_medically_approved_project(tmp_path)
    before = (project_dir / "project.yaml").read_bytes()

    class BadTTS:
        provider_name = "bad"
        require_signal = True

        def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"not wav")
            return TTSResult(provider="bad", audio_file=output, duration_ms=1000)

    with pytest.raises(ValueError, match="WAV"):
        produce_project(project_dir, BadTTS(), lambda _: pytest.fail("render called"))
    assert (project_dir / "project.yaml").read_bytes() == before


def test_v2_pronunciation_is_cache_bound_and_preserves_approved_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    revision = project_dir / "revisions" / "001"
    script_path = revision / "script" / "script.yaml"
    script_before = script_path.read_bytes()
    storyboard_path = revision / "storyboard" / "storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    storyboard["scenes"][0]["duration_frames"] = 1350
    write_yaml_atomic(storyboard_path, storyboard)
    profile = tmp_path / "pronunciation.vi.yaml"
    monkeypatch.setattr(pronunciation_module, "PRONUNCIATION_PROFILE_PATH", profile)
    profile.write_text(
        "schema_version: '1.0'\nlanguage: vi\nversion: '1'\n"
        "entries:\n  - written: huyết áp\n    spoken: áp huyết\n",
        encoding="utf-8",
    )
    approve_gate(project_dir, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=V2_REVIEWED_AT)
    requests: list[TTSRequest] = []

    class SpyTTS(SilentTTS):
        def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
            requests.append(request)
            return super().synthesize(request, output)

    def fake_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    approved_project = (project_dir / "project.yaml").read_bytes()
    profile.write_text(
        profile.read_text(encoding="utf-8").replace("version: '1'", "version: '2'"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="current medical approval"):
        produce_project(project_dir, SpyTTS(), fake_runner)
    assert requests == []
    assert (project_dir / "project.yaml").read_bytes() == approved_project
    profile.write_text(
        profile.read_text(encoding="utf-8").replace("version: '2'", "version: '1'"),
        encoding="utf-8",
    )

    first = produce_project(project_dir, SpyTTS(), fake_runner)
    first_manifest = json.loads((revision / "renders" / "render-manifest.json").read_text(encoding="utf-8"))
    assert first == revision / "renders" / "video.mp4"
    assert first_manifest["pronunciation_version"] == "1"
    assert first_manifest["pronunciation_sha256"]
    assert "áp huyết" in requests[0].text
    assert "huyết áp" in script_before.decode("utf-8")
    assert script_path.read_bytes() == script_before
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"

    video_approval = approve_gate(
        project_dir, GateKind.VIDEO,
        reviewer="BS Nguyễn Văn An", now=V2_REVIEWED_AT,
    )
    assert "renders/render-manifest.json" in video_approval.artifact_hashes
    assert set(video_approval.artifact_hashes) == set(video_reviewed_paths(revision))

    profile.write_text(profile.read_text(encoding="utf-8").replace("version: '1'", "version: '2'"), encoding="utf-8")
    with pytest.raises(ValueError, match="current medical approval"):
        package_project(project_dir)
    assert len(requests) == 1


def test_v2_invalid_pronunciation_fails_before_tts_and_state_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = _v2_medically_approved_project(tmp_path)
    profile = tmp_path / "pronunciation.vi.yaml"
    profile.write_text("schema_version: '1.0'\nlanguage: en\nversion: '1'\nentries: []\n", encoding="utf-8")
    monkeypatch.setattr(pronunciation_module, "PRONUNCIATION_PROFILE_PATH", profile)
    before = (project_dir / "project.yaml").read_bytes()
    with pytest.raises(ValueError):
        produce_project(project_dir, SilentTTS(), lambda _: pytest.fail("render invoked"))
    assert (project_dir / "project.yaml").read_bytes() == before


def test_produce_reuses_matching_artifact_hash(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    calls: list[list[str]] = []

    def fake_runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    first = produce_project(project_dir, SilentTTS(), fake_runner)
    second = produce_project(project_dir, SilentTTS(), fake_runner)

    assert second == first
    assert first == _active_run(project_dir) / "video.mp4"
    assert len(calls) == 1
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


def test_v2_produce_refuses_before_medical_approval(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    calls: list[list[str]] = []

    with pytest.raises(ValueError, match="medically_approved|medical approval"):
        produce_project(project_dir, SilentTTS(), calls.append)

    assert calls == []


def test_v2_produce_requires_current_medical_approval(tmp_path: Path) -> None:
    project_dir = _v2_medically_approved_project(tmp_path)
    script_path = project_dir / "revisions" / "001" / "script" / "script.yaml"
    script = read_yaml(script_path)
    script["lines"][0]["text"] = "Nội dung đã đổi sau khi bác sĩ duyệt."
    write_yaml_atomic(script_path, script)
    calls: list[list[str]] = []

    with pytest.raises(ValueError, match="medical approval"):
        produce_project(project_dir, SilentTTS(), calls.append)

    assert calls == []


def test_v2_produce_uses_active_revision_and_reuses_its_cache(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = _v2_medically_approved_project(tmp_path)
    calls: list[list[str]] = []
    resolutions = 0
    real_resolve = produce_workflow.resolve_project_layout

    def counting_resolve(path: Path):
        nonlocal resolutions
        resolutions += 1
        return real_resolve(path)

    def fake_runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    monkeypatch.setattr(produce_workflow, "resolve_project_layout", counting_resolve)

    first = produce_project(project_dir, SilentTTS(), fake_runner)
    second = produce_project(project_dir, SilentTTS(), fake_runner)

    revision_root = project_dir / "revisions" / "001"
    assert first == second == revision_root / "renders" / "video.mp4"
    assert len(calls) == 1
    assert resolutions == 2
    assert (revision_root / "renders" / "render-manifest.json").is_file()
    assert (revision_root / "reviews" / "video-qa.json").is_file()
    assert read_yaml(project_dir / "project.yaml")["state"] == (
        WorkflowState.AWAITING_VIDEO_REVIEW.value
    )


@pytest.mark.parametrize("dry_run", [False, True])
def test_produce_requires_a_present_medical_approval_before_any_work(
    tmp_path, dry_run: bool
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    for record in (project_dir / "reviews").glob("medical-*.yaml"):
        record.unlink()
    calls: list[list[str]] = []

    with pytest.raises(FileNotFoundError, match="medical approval record"):
        produce_project(
            project_dir, SilentTTS(), calls.append, dry_run=dry_run
        )

    assert calls == []


def test_produce_rejects_reviewed_project_when_cached_output_is_missing(
    tmp_path,
) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), lambda argv: 0)


def test_produce_dry_run_does_not_mutate_project_or_call_renderer(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    original_manifest = (project_dir / "project.yaml").read_bytes()
    calls: list[list[str]] = []

    output = produce_project(project_dir, SilentTTS(), calls.append, dry_run=True)

    assert output.name == "video.mp4"
    assert output.parent.parent == project_dir / "renders"
    assert calls == []
    assert not output.exists()
    assert not (project_dir / "audio" / "narration.wav").exists()
    assert not (project_dir / "render-input.json").exists()
    assert (project_dir / "project.yaml").read_bytes() == original_manifest


def test_produce_dry_run_cache_hit_does_not_call_renderer_or_mutate_project(
    tmp_path,
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")

    def successful_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    original_manifest = (project_dir / "project.yaml").read_bytes()
    original_output = output.read_bytes()
    calls: list[list[str]] = []

    assert (
        produce_project(project_dir, SilentTTS(), calls.append, dry_run=True) == output
    )
    assert calls == []
    assert (project_dir / "project.yaml").read_bytes() == original_manifest
    assert output.read_bytes() == original_output


def test_produce_writes_render_input_and_manifest_with_canonical_hash(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")

    def fake_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project_dir, SilentTTS(), fake_runner)

    render_input = json.loads(
        (output.parent / "render-input.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((output.parent / "manifest.json").read_text(encoding="utf-8"))
    assert render_input["audio_file"] == "audio/narration.wav"
    assert len(manifest["input_hash"]) == 64
    assert manifest["provider"] == "silent"


def test_produce_rejects_cached_reviewed_video_after_author_profile_changes(
    tmp_path, monkeypatch
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    profile = tmp_path / "author-voice.vi.yaml"
    profile.write_text("language: vi\ndirectness: clear_and_calm\n", encoding="utf-8")
    monkeypatch.setattr(
        "healthvideo.workflows.produce.AUTHOR_PROFILE_PATH", profile, raising=False
    )

    def fake_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    produce_project(project_dir, SilentTTS(), fake_runner)
    profile.write_text("language: vi\ndirectness: direct\n", encoding="utf-8")

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), fake_runner)


class ExplodingTTS:
    provider_name = "exploding"

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        raise RuntimeError("synthetic TTS failure")


@pytest.mark.parametrize(
    ("label", "tts", "runner", "error"),
    [
        (
            "tts",
            ExplodingTTS(),
            lambda argv: 0,
            RuntimeError,
        ),
        (
            "runner",
            SilentTTS(),
            lambda argv: 9,
            RuntimeError,
        ),
        (
            "output",
            SilentTTS(),
            lambda argv: 0,
            FileNotFoundError,
        ),
    ],
)
def test_produce_failure_preserves_project_and_allows_retry(
    tmp_path,
    label: str,
    tts: SilentTTS | ExplodingTTS,
    runner: Callable[[list[str]], int],
    error: type[Exception],
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    old_run = _write_existing_production_run(project_dir)
    original_manifest = (project_dir / "project.yaml").read_bytes()
    original_artifacts = _run_artifacts(old_run)

    with pytest.raises(error):
        produce_project(project_dir, tts, runner)

    assert (project_dir / "project.yaml").read_bytes() == original_manifest
    assert _run_artifacts(old_run) == original_artifacts
    assert list((project_dir / "renders").glob(".*.produce-*")) == []
    assert list((project_dir / "renders").iterdir()) == [old_run], label
    assert not (project_dir / "audio" / "narration.wav").exists(), label
    assert not (project_dir / "render-input.json").exists(), label

    def successful_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    assert output.is_file(), label
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


def test_promotion_failure_preserves_active_run_and_allows_retry(
    tmp_path, monkeypatch
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    old_run = _write_existing_production_run(project_dir)
    original_manifest = (project_dir / "project.yaml").read_bytes()
    original_run = _run_artifacts(old_run)

    def successful_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    def fail_promotion(staging_dir: Path, run_dir: Path) -> None:
        raise OSError("synthetic promotion failure")

    monkeypatch.setattr(produce_workflow, "_promote_run", fail_promotion, raising=False)
    with pytest.raises(OSError, match="promotion"):
        produce_project(project_dir, SilentTTS(), successful_runner)

    assert (project_dir / "project.yaml").read_bytes() == original_manifest
    assert _run_artifacts(old_run) == original_run
    assert list((project_dir / "renders").glob(".*.produce-*")) == []
    monkeypatch.undo()

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    assert output.is_file()
    assert _run_artifacts(old_run) == original_run


def test_manifest_write_failure_leaves_recoverable_run_for_retry(
    tmp_path, monkeypatch
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    old_run = _write_existing_production_run(project_dir)
    original_manifest = (project_dir / "project.yaml").read_bytes()
    original_run = _run_artifacts(old_run)
    calls: list[list[str]] = []

    def successful_runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    def fail_manifest_write(path: Path, data: object) -> None:
        raise OSError("synthetic manifest write failure")

    monkeypatch.setattr(produce_workflow, "write_yaml_atomic", fail_manifest_write)
    with pytest.raises(OSError, match="manifest write"):
        produce_project(project_dir, SilentTTS(), successful_runner)

    assert (project_dir / "project.yaml").read_bytes() == original_manifest
    assert _run_artifacts(old_run) == original_run
    assert (
        len([path for path in (project_dir / "renders").iterdir() if path.is_dir()])
        == 2
    )
    monkeypatch.undo()

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    assert output.is_file()
    assert len(calls) == 1
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


@pytest.mark.parametrize("state", ["idea", "awaiting_medical_review"])
def test_produce_dry_run_rejects_invalid_state_without_calling_renderer(
    tmp_path, state
) -> None:
    project_dir = create_project_fixture(tmp_path, state=state)
    calls: list[list[str]] = []

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), calls.append, dry_run=True)

    assert calls == []


def test_produce_dry_run_rejects_reviewed_project_with_cache_miss(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")
    calls: list[list[str]] = []

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), calls.append, dry_run=True)

    assert calls == []


RUN_ARTIFACT_NAMES = frozenset(
    {"audio/narration.wav", "render-input.json", "video.mp4", "manifest.json"}
)


def test_produce_publishes_a_populated_run_in_one_rename(tmp_path, monkeypatch) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    real_promote = produce_workflow._promote_run
    observed: list[tuple[frozenset[str], bool]] = []

    def observing_promote(staging_dir: Path, run_dir: Path) -> None:
        observed.append((frozenset(_run_artifacts(staging_dir)), run_dir.exists()))
        real_promote(staging_dir, run_dir)

    def successful_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    monkeypatch.setattr(produce_workflow, "_promote_run", observing_promote)
    output = produce_project(project_dir, SilentTTS(), successful_runner)

    assert len(observed) == 1
    staged_names, destination_existed = observed[0]
    assert not destination_existed
    assert RUN_ARTIFACT_NAMES <= staged_names
    assert RUN_ARTIFACT_NAMES <= frozenset(_run_artifacts(output.parent))
    assert not (project_dir / "audio" / "narration.wav").exists()
    assert not (project_dir / "render-input.json").exists()
    assert not (project_dir / "renders" / "video.mp4").exists()
    assert not (project_dir / "renders" / "manifest.json").exists()


def test_produce_republishes_over_a_damaged_published_run(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    calls: list[list[str]] = []

    def successful_runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    output.unlink()
    project = read_yaml(project_dir / "project.yaml")
    project["state"] = "script_approved"
    write_yaml_atomic(project_dir / "project.yaml", project)

    republished = produce_project(project_dir, SilentTTS(), successful_runner)

    assert republished == output
    assert len(calls) == 2
    assert RUN_ARTIFACT_NAMES <= frozenset(_run_artifacts(republished.parent))
    assert list((project_dir / "renders").iterdir()) == [republished.parent]
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


def test_input_hash_changes_for_every_declared_input(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    script_data = read_yaml(project_dir / "script" / "script.yaml")
    storyboard_data = read_yaml(project_dir / "storyboard" / "storyboard.yaml")

    script = Script.model_validate(script_data)
    storyboard = Storyboard.model_validate(storyboard_data)
    profile = {"language": "vi", "directness": "clear_and_calm"}
    renderer = {
        "name": "remotion",
        "package_version": "4.0.522",
        "source_sha256": "c" * 64,
    }
    baseline = _input_hash(
        script,
        storyboard,
        profile,
        "silent",
        {"assets/evidence-r01.svg": "a" * 64},
        renderer,
    )

    changed_script = script.model_copy(
        update={"title": "Ăn mặn và tăng huyết áp — cập nhật"}
    )
    changed_storyboard = storyboard.model_copy(
        update={"title": "Ăn mặn và tăng huyết áp — cập nhật"}
    )

    assert (
        _input_hash(
            changed_script,
            storyboard,
            profile,
            "silent",
            {"assets/evidence-r01.svg": "a" * 64},
            renderer,
        )
        != baseline
    )
    assert (
        _input_hash(
            script,
            changed_storyboard,
            profile,
            "silent",
            {"assets/evidence-r01.svg": "a" * 64},
            renderer,
        )
        != baseline
    )
    assert (
        _input_hash(
            script,
            storyboard,
            {"language": "vi", "directness": "direct"},
            "silent",
            {"assets/evidence-r01.svg": "a" * 64},
            renderer,
        )
        != baseline
    )
    assert (
        _input_hash(
            script,
            storyboard,
            profile,
            "other",
            {"assets/evidence-r01.svg": "a" * 64},
            renderer,
        )
        != baseline
    )
    assert (
        _input_hash(
            script,
            storyboard,
            profile,
            "silent",
            {"assets/evidence-r01.svg": "b" * 64},
            renderer,
        )
        != baseline
    )
    assert (
        _input_hash(
            script,
            storyboard,
            profile,
            "silent",
            {"assets/evidence-r01.svg": "a" * 64},
            {**renderer, "source_sha256": "d" * 64},
        )
        != baseline
    )


def test_produce_invalidates_cache_after_approved_evidence_asset_is_replaced(
    tmp_path,
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    calls: list[list[str]] = []

    def fake_runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    first = produce_project(project_dir, SilentTTS(), fake_runner)
    first_hash = first.parent.name
    asset = project_dir / "assets" / "evidence-r01.svg"
    asset.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg'><text>replacement</text></svg>",
        encoding="utf-8",
    )
    project = read_yaml(project_dir / "project.yaml")
    project["state"] = "awaiting_medical_review"
    write_yaml_atomic(project_dir / "project.yaml", project)
    from healthvideo.workflows.review import approve_medical

    approve_medical(project_dir, reviewer="BS An")

    second = produce_project(project_dir, SilentTTS(), fake_runner)

    assert len(calls) == 2
    assert second.parent.name != first_hash


def _run_artifacts(run_dir: Path) -> dict[str, bytes]:
    paths = tuple(path for path in run_dir.rglob("*") if path.is_file())
    return {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in paths
        if path.is_file()
    }


def _write_synthetic_output(argv: list[str]) -> None:
    output = Path(argv[argv.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"synthetic-mp4")


def _v2_medically_approved_project(tmp_path: Path) -> Path:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    storyboard_path = (
        project_dir / "revisions" / "001" / "storyboard" / "storyboard.yaml"
    )
    storyboard = read_yaml(storyboard_path)
    storyboard["scenes"][0]["duration_frames"] = 1350
    write_yaml_atomic(storyboard_path, storyboard)
    approve_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer="BS Nguyễn Văn An",
        now=V2_REVIEWED_AT,
    )
    return project_dir


def _active_run(project_dir: Path) -> Path:
    input_hash = read_yaml(project_dir / "project.yaml")["artifact_hashes"][
        "production"
    ]
    return project_dir / "renders" / input_hash


def _write_existing_production_run(project_dir: Path) -> Path:
    old_hash = "previous-run"
    project = read_yaml(project_dir / "project.yaml")
    project["artifact_hashes"]["production"] = old_hash
    write_yaml_atomic(project_dir / "project.yaml", project)
    run_dir = project_dir / "renders" / old_hash
    artifacts = {
        run_dir / "audio" / "narration.wav": b"old-audio",
        run_dir / "render-input.json": b'{"old":"input"}',
        run_dir / "manifest.json": b'{"old":"manifest"}',
        run_dir / "video.mp4": b"old-video",
    }
    for path, contents in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    return run_dir
