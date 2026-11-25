import wave

from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.input import build_render_input
from healthvideo.render.timing import (
    concat_scene_audio,
    restore_timed_storyboard,
    retime_storyboard,
)
from healthvideo.render.word_timing import apply_alignment


def board():
    scenes = tuple(Scene(id=ident, start_frame=start, duration_frames=duration,
                         narration=ident, script_line_id=line, visual="whiteboard", on_screen_text="Synthetic")
                   for ident, start, duration, line in (
                       ("S1", 0, 9000, "L1"), ("S2", 9000, 9000, "L2"),
                       ("H1", 0, 60, "H"), ("O1", 0, 60, "O")))
    scenes = (*scenes[:2], *(s.model_copy(update={"clip_only": "CL01"}) for s in scenes[2:]))
    return Storyboard(title="Standalone", scenes=scenes).model_copy(update={"format_profile": "youtube_long"})


def test_clip_speech_has_local_timing_and_roundtrips_without_entering_long_audio(tmp_path):
    approved = board()
    timed, record = retime_storyboard(approved, {"L1": 1000, "L2": 2000, "H": 500, "O": 700})
    assert [s.start_frame for s in timed.scenes] == [0, 39, 0, 0]
    wavs = {}
    for line, samples in (("L1", 1000), ("L2", 2000), ("H", 500), ("O", 700)):
        path = tmp_path / f"{line}.wav"
        with wave.open(str(path), "wb") as stream:
            stream.setparams((1, 2, 1000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\x01\0" * samples)
        wavs[line] = path
    long_board = timed.model_copy(update={"scenes": timed.scenes[:2]})
    record["audio_alignment"] = concat_scene_audio(long_board, {k: wavs[k] for k in ("L1", "L2")}, tmp_path / "long.wav")
    assert [row["scene_id"] for row in record["audio_alignment"]] == ["S1", "S2"]
    assert restore_timed_storyboard(approved, record) == timed
    assert len(record["scenes"]) == 4


def test_long_render_input_excludes_clip_only_scenes(monkeypatch):
    monkeypatch.setattr("healthvideo.render.beats.visual_rhythm_qa", lambda scene: None)
    result = build_render_input(board(), "audio/narration.wav")
    assert [s.id for s in result.scenes] == ["S1", "S2"]


def test_clip_hook_and_outro_receive_their_own_caption_words():
    timed, _ = retime_storyboard(board(), {"L1": 1000, "L2": 2000, "H": 500, "O": 700})
    aligned = apply_alignment(timed, {"H": [{"word": "Hook", "start": 0, "end": .4}],
                                      "O": [{"word": "Outro", "start": 0, "end": .6}]})
    assert [s.words[0].text for s in aligned.scenes[2:]] == ["Hook", "Outro"]




def test_production_synthesizes_clip_lines_but_keeps_long_track_and_cache_separate(tmp_path, monkeypatch):
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    from healthvideo.domain.gate_review import GateKind
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.tts.silent import SilentTTS
    from healthvideo.workflows.gate_review import approve_gate
    from healthvideo.workflows.produce import produce_project
    from tests.helpers import (
        create_long_form_project_fixture,
        write_critic_review_fixture,
    )

    def align(wavs, scripts, *, out_dir, **kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        result = {}
        for line, text in scripts.items():
            with wave.open(str(wavs[line]), "rb") as source:
                seconds = source.getnframes() / source.getframerate()
            tokens = text.split()
            result[line] = [{"word": token, "start": i * seconds / len(tokens),
                             "end": (i + 1) * seconds / len(tokens), "matched": True}
                            for i, token in enumerate(tokens)]
            (out_dir / f"{line}.json").write_text(json.dumps(result[line]), encoding="utf-8")
        return result

    monkeypatch.setattr("healthvideo.workflows.produce.align_lines", align)

    project = create_long_form_project_fixture(tmp_path)
    revision = project / "revisions/001"
    script_path = revision / "script/script.yaml"
    script = read_yaml(script_path)
    script["lines"].extend([
        {"id": "CH", "text": "Bạn ăn mặn?", "purpose": "clip_hook", "clip_id": "CL01"},
        {"id": "CO", "text": "Hãy giảm muối dần.", "purpose": "clip_outro", "clip_id": "CL01"},
    ])
    write_yaml_atomic(script_path, script)
    board_path = revision / "storyboard/storyboard.yaml"
    storyboard = read_yaml(board_path)
    storyboard["scenes"].extend([
        {"id": "CH", "start_frame": 0, "duration_frames": 60, "narration": "Bạn ăn mặn?",
         "script_line_id": "CH", "clip_only": "CL01", "visual": "whiteboard", "on_screen_text": "Ăn mặn?"},
        {"id": "CO", "start_frame": 0, "duration_frames": 60, "narration": "Hãy giảm muối dần.",
         "script_line_id": "CO", "clip_only": "CL01", "visual": "whiteboard", "on_screen_text": "Giảm muối dần"},
    ])
    write_yaml_atomic(board_path, storyboard)
    plan_path = revision / "script/clip-plan.yaml"
    plan = read_yaml(plan_path)
    plan["clips"][0].update(hook_scene_id="CH", outro_scene_id="CO")
    write_yaml_atomic(plan_path, plan)
    write_critic_review_fixture(project)
    approve_gate(project, GateKind.MEDICAL, reviewer="Doctor", now=datetime(2026, 11, 20, tzinfo=UTC))

    class CountingTTS(SilentTTS):
        def __init__(self):
            self.calls = []

        def synthesize(self, request, output):
            self.calls.append(request.text)
            return super().synthesize(request, output)

    def runner(argv):
        output = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4-" + output.name.encode())
        return 0

    tts = CountingTTS()
    produce_project(project, tts, runner, music=False)
    renders = revision / "renders"
    long_input = json.loads((renders / "render-input.json").read_text(encoding="utf-8"))
    assert {s["id"] for s in long_input["scenes"]}.isdisjoint({"CH", "CO"})
    clip_input = json.loads((renders / "clips/CL01.render-input.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in clip_input["scenes"]] == ["CH", "S01", "S02", "CO"]
    assert [word["text"] for word in clip_input["scenes"][0]["words"]] == ["Bạn", "ăn", "mặn?"]
    assert [word["text"] for word in clip_input["scenes"][-1]["words"]] == ["Hãy", "giảm", "muối", "dần."]
    timing = json.loads((renders / "scene-timing.json").read_text(encoding="utf-8"))
    assert {r["scene_id"] for r in timing["audio_alignment"]}.isdisjoint({"CH", "CO"})
    assert (renders / "audio/lines/CH.wav").is_file()
    assert (renders / "audio/lines/CO.wav").is_file()
    with wave.open(str(renders / "audio/narration.wav"), "rb") as source:
        seconds = source.getnframes() / source.getframerate()
    assert abs(seconds - sum(s["duration_frames"] for s in long_input["scenes"]) / 30) < .001
    calls = len(tts.calls)
    produce_project(project, tts, runner, music=False)
    assert len(tts.calls) == calls

