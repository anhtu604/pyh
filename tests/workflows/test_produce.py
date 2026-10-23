import json
import wave
from datetime import UTC, datetime
from pathlib import Path

import pytest

import healthvideo.tts.pronunciation as pronunciation_module
import healthvideo.workflows.produce as produce_workflow
from healthvideo.domain.brand import MascotPose
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.script import Script
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.base import TTSRequest, TTSResult
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import (
    approve_gate,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
    video_reviewed_paths,
)
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.visual_assets import (
    create_mascot_reaction_asset,
)
from tests.helpers import align_fixture_script, create_v2_project_fixture

V2_REVIEWED_AT = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


def test_m64_production_records_measured_audio_and_rejects_stale_qa(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    write_yaml_atomic(board_path, board)
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)

    def runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    produce_project(project, SilentTTS(), runner)
    qa_path = revision / "reviews/video-qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    assert qa["audio_duration_ms"] > 0
    timing = json.loads((revision / "renders/scene-timing.json").read_text(encoding="utf-8"))
    assert qa["composition_duration_ms"] == round(sum(
        scene["duration_frames"] for scene in timing["scenes"]
    ) * 1000 / timing["fps"])
    assert qa["composition_duration_ms"] > 0
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
    write_yaml_atomic(board_path, board)
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


def _m65_project(tmp_path: Path) -> Path:
    project = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    highlight = dict(board["scenes"][0])
    highlight["id"] = "S02"
    whiteboard_frames, highlight_frames = 750, 250
    board["visual_budget_profile"] = "m6_5_v1"
    board["scenes"] = [
        {
            "id": "S01",
            "start_frame": 0,
            "duration_frames": whiteboard_frames,
            "narration": "Whiteboard synthetic.",
            "script_line_id": "L01",
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "whiteboard", "on_screen_text": "Synthetic illustration.",
        },
        {
            **highlight,
            "start_frame": whiteboard_frames,
            "duration_frames": highlight_frames,
        },
    ]
    highlight["script_line_id"] = "L02"
    align_fixture_script(revision, board)
    write_yaml_atomic(board_path, board)
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)
    return project


class CountingSilent(SilentTTS):
    def __init__(self, project: Path | None = None) -> None:
        self.calls = 0
        self.line_frames: dict[str, int] | None = None
        if project is not None:
            root = project / "revisions/001"
            script = read_yaml(root / "script/script.yaml")
            board = read_yaml(root / "storyboard/storyboard.yaml")
            self.line_frames = {
                line["text"]: sum(s["duration_frames"] for s in board["scenes"]
                                  if s.get("script_line_id") == line["id"]) - 9
                for line in script["lines"]
            }

    def synthesize(self, request: TTSRequest, output_path: Path) -> TTSResult:
        self.calls += 1
        if self.line_frames is not None:
            frames = self.line_frames[request.text]
            assert frames > 0
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(output_path), "wb") as output:
                output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                output.writeframes(b"\0\0" * (frames * 800))
            return TTSResult(provider=self.provider_name, audio_file=output_path,
                             duration_ms=round(frames * 1000 / 30))
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
    board["scenes"][2]["start_frame"] = 1000
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


def test_m65_production_records_visual_qa_and_reuses_valid_promoted_cache(
    tmp_path: Path,
) -> None:
    project = _m65_project(tmp_path)
    revision = project / "revisions/001"
    tts = CountingSilent(project)
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
        "mascot_frames": 0,
        "mascot_basis_points": 0,
        "warnings": [],
        "total_frames": 1000,
        "category_frames": {
            "whiteboard_svg": 750,
            "chart_crop": 250,
        },
        "category_basis_points": {
            "whiteboard_svg": 7500,
            "chart_crop": 2500,
        },
        "effective_bounds": {
            "whiteboard_svg": {"min_percent": 65, "max_percent": 75},
            "chart_crop": {"min_percent": 15, "max_percent": 25},
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
    assert tts.calls == 3 and len(render_calls) == 1


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

    produce_project(project, CountingSilent(project), runner)
    qa_path = revision / "reviews/video-qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    replacements = {
        "total_frames": ("total_frames", 1001),
        "override_active": ("override_active", True),
        "profile": ("profile", "explain_first_v1"),
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
    tts = CountingSilent(project)
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
    assert (tts.calls, len(render_calls)) == ((6, 2) if tampered else (3, 1))
    assert read_yaml(project / "project.yaml")["state"] == "awaiting_video_review"


def _resign_medical_approval(revision: Path) -> None:
    approval_path = revision / "reviews/medical-approval.yaml"
    approval = read_yaml(approval_path)
    approval["artifact_hashes"] = hash_reviewed_artifacts(medical_reviewed_paths(revision))
    write_yaml_atomic(approval_path, approval)


def test_v2_produce_stages_declared_mascot_asset(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    revision = project_dir / "revisions" / "001"
    storyboard_path = revision / "storyboard" / "storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
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
    write_yaml_atomic(storyboard_path, storyboard)
    profile = tmp_path / "pronunciation.vi.yaml"
    monkeypatch.setattr(pronunciation_module, "PRONUNCIATION_PROFILE_PATH", profile)
    profile.write_text(
        "schema_version: '1.0'\nlanguage: vi\nversion: '1'\n"
        "entries:\n  - written: evidence\n    spoken: proof\n",
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
    assert "proof" in requests[0].text
    assert "evidence" in script_before.decode("utf-8")
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
    assert len(requests) == 6


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


class ExplodingTTS:
    provider_name = "exploding"

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        raise RuntimeError("synthetic TTS failure")


RUN_ARTIFACT_NAMES = frozenset(
    {"audio/narration.wav", "render-input.json", "video.mp4", "manifest.json"}
)


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


def test_v2_runtime_timing_is_hash_bound_and_preserves_approved_content(tmp_path):
    project = _v2_medically_approved_project(tmp_path)
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    approved_bytes = board_path.read_bytes()
    script = read_yaml(revision / "script/script.yaml")
    requests: list[TTSRequest] = []

    class Spy(SilentTTS):
        def synthesize(self, request, output):
            requests.append(request)
            return super().synthesize(request, output)

    def runner(argv):
        _write_synthetic_output(argv)
        return 0

    produce_project(project, Spy(), runner)
    timing_path = revision / "renders/scene-timing.json"
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    manifest = json.loads((revision / "renders/render-manifest.json").read_text(encoding="utf-8"))
    assert manifest["scene_timing_sha256"] == sha256_file(timing_path)
    assert len(manifest["line_audio_sha256"]) == len(script["lines"])
    assert len(requests) == len(script["lines"])
    assert [request.delivery_beats for request in requests] == [
        (line.delivery.model_dump(mode="json"),)
        for line in Script.model_validate(script).lines
    ]
    assert board_path.read_bytes() == approved_bytes
    assert timing["scenes"][0]["duration_frames"] != 1350
    timing["scenes"][0]["duration_frames"] += 1
    timing_path.write_text(json.dumps(timing), encoding="utf-8")
    with pytest.raises(ValueError, match="medically_approved"):
        produce_project(project, NoSynthesis(), lambda _: pytest.fail("render called"))


@pytest.mark.parametrize("field", ["audio_duration_ms", "composition_duration_ms",
                                   "trailing_visual_ms", "max_scene_drift_ms"])
def test_v2_all_profiles_refuse_missing_or_changed_timing_qa(tmp_path, field):
    project = _v2_medically_approved_project(tmp_path)
    revision = project / "revisions/001"

    def runner(argv):
        _write_synthetic_output(argv)
        return 0

    produce_project(project, SilentTTS(), runner)
    qa_path = revision / "reviews/video-qa.json"
    original = json.loads(qa_path.read_text(encoding="utf-8"))
    for missing in (True, False):
        qa = dict(original)
        if missing:
            del qa[field]
        else:
            qa[field] += 151
        qa_path.write_text(json.dumps(qa), encoding="utf-8")
        with pytest.raises(ValueError, match="medically_approved"):
            produce_project(project, NoSynthesis(), lambda _: pytest.fail("render called"))


@pytest.mark.parametrize("fault", ["tail", "drift"])
def test_v2_fresh_timing_failure_blocks_before_render(tmp_path, monkeypatch, fault):
    project = _v2_medically_approved_project(tmp_path)
    original_project = (project / "project.yaml").read_bytes()
    real_concat = produce_workflow.concat_scene_audio

    def inject_fault(board, lines, output, *args, **kwargs):
        alignment = real_concat(board, lines, output, *args, **kwargs)
        if fault == "drift":
            alignment[0]["audio_start_ms"] += 121
        else:
            with wave.open(str(output), "rb") as stream:
                params = stream.getparams()
                data = stream.readframes(stream.getnframes() - 48000)
            with wave.open(str(output), "wb") as stream:
                stream.setparams(params)
                stream.writeframes(data)
        return alignment

    monkeypatch.setattr(produce_workflow, "concat_scene_audio", inject_fault)
    with pytest.raises(ValueError, match="silence|drift|speech end"):
        produce_project(project, SilentTTS(), lambda _: pytest.fail("render called"))
    assert (project / "project.yaml").read_bytes() == original_project
    assert not (project / "revisions/001/renders/video.mp4").exists()


def test_v2_measured_runtime_visual_budget_blocks_before_render(tmp_path):
    project = _m65_project(tmp_path)
    revision = project / "revisions/001"
    script_path = revision / "script/script.yaml"
    script = read_yaml(script_path)
    script["lines"][1]["text"] = "Synthetic long chart narration. " * 100
    write_yaml_atomic(script_path, script)
    board_path = revision / "storyboard/storyboard.yaml"
    data = read_yaml(board_path)
    data["scenes"][1]["narration"] = script["lines"][1]["text"]
    write_yaml_atomic(board_path, data)
    _resign_medical_approval(revision)
    before = (project / "project.yaml").read_bytes()
    tts = CountingSilent()
    with pytest.raises(ValueError, match="visual budget failed"):
        produce_project(project, tts, lambda _: pytest.fail("render called"))
    assert tts.calls == 3
    assert (project / "project.yaml").read_bytes() == before


def test_v2_unbound_tail_is_rejected_before_synthesis(tmp_path):
    project = _v2_medically_approved_project(tmp_path)
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    data = read_yaml(board_path)
    data["scenes"].append({
        "id": "SILENT-TAIL", "start_frame": sum(s["duration_frames"] for s in data["scenes"]),
        "duration_frames": 300, "narration": "", "visual": "whiteboard", "on_screen_text": "Synthetic illustration.",
    })
    write_yaml_atomic(board_path, data)
    _resign_medical_approval(revision)
    before = (project / "project.yaml").read_bytes()
    tts = CountingSilent()
    with pytest.raises(ValueError, match="visual budget failed|outro|align"):
        produce_project(project, tts, lambda _: pytest.fail("render called"))
    assert tts.calls == 0
    assert (project / "project.yaml").read_bytes() == before
    assert not (revision / "renders/video.mp4").exists()


def test_v2_cache_tail_qa_uses_speech_end_despite_full_length_padded_wav(tmp_path):
    project = _v2_medically_approved_project(tmp_path)
    revision = project / "revisions/001"

    def runner(argv):
        _write_synthetic_output(argv)
        return 0

    produce_project(project, SilentTTS(), runner)
    qa_path = revision / "reviews/video-qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    assert abs(qa["composition_duration_ms"] - qa["audio_duration_ms"]) <= 1
    timing = json.loads((revision / "renders/scene-timing.json").read_text(encoding="utf-8"))
    speech_end = max(item["speech_end_ms"] or 0 for item in timing["audio_alignment"])
    assert qa["trailing_visual_ms"] == qa["composition_duration_ms"] - speech_end
    assert 300 <= qa["trailing_visual_ms"] <= 334
    qa["trailing_visual_ms"] = 0
    qa_path.write_text(json.dumps(qa), encoding="utf-8")
    with pytest.raises(ValueError, match="medically_approved"):
        produce_project(project, NoSynthesis(), lambda _: pytest.fail("render called"))


def _v2_medically_approved_project(tmp_path: Path) -> Path:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    storyboard_path = (
        project_dir / "revisions" / "001" / "storyboard" / "storyboard.yaml"
    )
    storyboard = read_yaml(storyboard_path)
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


def test_production_carries_alignment_and_reuses_it_on_retry(tmp_path, monkeypatch):
    from healthvideo.audio.align import map_words
    from healthvideo.tts.audio_checks import inspect_wav
    from healthvideo.workflows import produce

    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / 'revisions/001'
    # This fixture's repeated narration starts with Synthetic. Its text entrance
    # uses a different keyword so the independent front-loading QA does not fire.
    board_path = revision/'storyboard/storyboard.yaml'
    board = read_yaml(board_path)
    for scene in board['scenes']:
        if scene.get('on_screen_text'):
            scene['on_screen_text'] = 'Overview'
    write_yaml_atomic(board_path, board)
    approve_gate(project, GateKind.MEDICAL, reviewer='doctor', now=V2_REVIEWED_AT)
    calls = []

    def fake_align(line_wavs, scripts, *, out_dir):
        calls.append('align')
        result = {}
        out_dir.mkdir(parents=True)
        for line, text in scripts.items():
            tokens = text.split()
            seconds = inspect_wav(line_wavs[line]).duration_ms / 1000
            raw = [{'word': token, 'start': seconds*i/len(tokens),
                    'end': seconds*(i+1)/len(tokens), 'prob': .9} for i, token in enumerate(tokens)]
            result[line] = map_words(text, raw, duration=seconds)
            (out_dir/f'{line}.json').write_text(json.dumps(result[line]), encoding='utf-8')
        return result

    monkeypatch.setattr(produce, 'align_lines', fake_align)

    def runner(argv):
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project, SilentTTS(), runner)
    rendered = read_yaml(revision/'renders/render-input.json')
    assert any(scene.get('words') for scene in rendered['scenes'])
    qa = read_yaml(revision/'reviews/pronunciation-qa.json')
    assert qa['status'] == 'aligned' and not qa['flags']
    assert all(line['match_ratio'] == 1 for line in qa['lines'])
    assert produce_project(project, SilentTTS(), lambda _: pytest.fail('render on cache hit')) == output
    assert calls == ['align']
    (revision/'reviews/pronunciation-qa.json').unlink()
    produce_project(project, SilentTTS(), lambda _: pytest.fail('render on cache hit'))
    assert read_yaml(revision/'reviews/pronunciation-qa.json') == qa
    path = next((revision/'renders/audio/alignment').glob('*.json'))
    path.write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError, match='medically_approved'):
        produce_project(project, SilentTTS(), runner)
