"""Frame-only, offline examples; synthetic action labels are not medical evidence."""
import hashlib
from pathlib import Path

import pytest

from healthvideo.domain.storyboard import Storyboard
from healthvideo.render.quality import (
    R5RuntimeStoryboard,
    measure_r5_quality,
    resolve_r5_shots,
    validate_r5_quality,
)
from healthvideo.render.timing import retime_storyboard
from healthvideo.render.word_timing import apply_alignment
from healthvideo.storage.files import read_yaml


def anchor(frame):
    return {"kind": "phrase", "line_id": "L1", "phrase": f"w{frame}"}


def shot(start, end, *, id="SH1", kind="recap", windows=(), actions=(), reason=None):
    return {"id": id, "kind": kind, "tier": None, "component": "ZoomChain", "asset_paths": [],
                "question_ids": ["Q1"], "start": anchor(start), "end": anchor(end),
                "actions": list(actions), "text_windows": list(windows), "long_shot_reason": reason}


def window(start, end, kind="table"):
    return {"kind": kind, "text": "Synthetic", "start": anchor(start), "end": anchor(end)}


def action(start, end, index=0, actor="cell"):
    return {"actor": actor, "compartment": "inside", "change": f"change{index}",
                "outcome": f"outcome{index}", "start": anchor(start), "end": anchor(end)}


def board(shots, frames=1000):
    points = {0, frames}
    for s in shots:
        for item in (s, *s["actions"], *s["text_windows"]):
            for key in ("start", "end"):
                points.add(int(item[key]["phrase"][1:]))
    # The final boundary is the scene end, not a word outside the scene.
    for s in shots:
        for item in (s, *s["actions"], *s["text_windows"]):
            for key in ("start", "end"):
                if item[key] == anchor(frames):
                    item[key] = {"kind": "scene_end"}
    words = [{"text": f"w{i}", "start_frame": i, "end_frame": i+1}
             for i in sorted(points) if i < frames]
    contract = {"questions": [{"id": f"Q{i}", "text": f"Question{i}?", "hook_line_id": "L1",
                                    "answer_line_ids": ["L1"]} for i in (1, 2)],
                    "blocks": [{"id": "B1", "line_ids": ["L1"], "question_ids": ["Q1", "Q2"],
                                 "takeaway_line_id": "L1", "professional_update": True}]}
    return Storyboard(title="Synthetic", quality_profile="r5_v1", r5_contract=contract,
                      scenes=[{"id": "S1", "start_frame": 0, "duration_frames": frames,
                                   "narration": " ".join(w["text"] for w in words),
                                   "visual": "whiteboard", "on_screen_text": "Synthetic", "script_line_id": "L1",
                                   "words": words, "shots": shots}])


def test_text_union_exact_threshold_and_separate_labels():
    b = board([shot(0, 1000, windows=[window(0, 100), window(50, 150, "credit"),
                                     window(0, 1000, "label"), window(0, 1000, "scale_bar")])])
    report = measure_r5_quality(b)
    assert report.numerator_frames == 150
    assert report.denominator_frames == 1000
    assert [(i.start_frame, i.end_frame) for i in report.text_union_intervals] == [(0, 150)]
    assert len(report.source_intervals) == 4
    assert report.manual_review == "pending"
    validate_r5_quality(report, estimated=False)
    b2 = board([shot(0, 1000, windows=[window(0, 151)])])
    with pytest.raises(ValueError, match="15%"):
        validate_r5_quality(measure_r5_quality(b2), estimated=False)


@pytest.mark.parametrize("kind", ["question", "takeaway", "worksheet", "source_card", "table",
                                  "lab_sheet", "text_tree", "credit"])
def test_all_large_text_counts_and_six_second_limit(kind):
    report = measure_r5_quality(board([shot(0, 2000, windows=[window(0, 181, kind)])], 2000))
    assert report.numerator_frames == 181
    with pytest.raises(ValueError, match="S1.*SH1.*frame.*6s.*storyboard_director"):
        validate_r5_quality(report, estimated=False)


def test_nearest_rank_groups_and_empty_na():
    shots = [shot(i*90, (i+1)*90, id=f"T{i}", kind="story") for i in range(9)]
    shots += [shot(810, 1020, id="T9", kind="story", actions=[action(900, 1020)]), shot(1020, 1320, id="M", kind="mechanism",
              actions=[action(1020, 1170), action(1170, 1320, 1)])]
    report = measure_r5_quality(board(shots, 1320))
    assert (report.story.count, report.story.median_seconds, report.story.p90_seconds) == (10, 3, 3)
    assert (report.mechanism.count, report.mechanism.median_seconds) == (1, 10)
    validate_r5_quality(report, estimated=False)
    empty = measure_r5_quality(board([shot(0, 1000)]))
    assert empty.story.count == 0 and empty.story.median_seconds is None
    assert empty.mechanism.p90_seconds is None


@pytest.mark.parametrize("durations,median,p90", [([60, 120], 2, 4), ([90, 120, 300], 4, 10)])
def test_statistics_use_shots_and_hard_limits(durations, median, p90):
    start, shots = 0, []
    for i, duration in enumerate(durations):
        shots.append(shot(start, start+duration, id=str(i), kind="story"))
        start += duration
    report = measure_r5_quality(board(shots, start))
    assert report.story.median_seconds == median
    assert report.story.p90_seconds == p90
    with pytest.raises(ValueError, match="story.*median"):
        validate_r5_quality(report, estimated=False)


def test_long_mechanism_requires_reason_and_causal_steps():
    def sample(reason, actor):
        return board([shot(0, 750, kind="mechanism", reason=reason,
                           actions=[action(i, i+150, i, actor) for i in range(0, 750, 150)]),
                      shot(750, 1050, id="M2", kind="mechanism",
                           actions=[action(750, 900), action(900, 1050, 1)]),
                      shot(1050, 1350, id="M3", kind="mechanism",
                           actions=[action(1050, 1200), action(1200, 1350, 1)])], 1350)
    validate_r5_quality(measure_r5_quality(sample("Follow the same entity", "cell")), estimated=False)
    for reason, actor in [(None, "cell"), ("Follow entity", "background")]:
        with pytest.raises(ValueError, match="long shot"):
            validate_r5_quality(measure_r5_quality(sample(reason, actor)), estimated=False)


@pytest.mark.parametrize("failure", ["missing", "repeated", "outside", "line", "gap", "overlap"])
def test_resolution_errors_have_location_and_owner(failure):
    b = board([shot(0, 150), shot(150, 300, id="SH2")], 300)
    s = b.scenes[0]
    if failure in {"gap", "overlap"}:
        second = s.shots[1].model_copy(update={"start": s.shots[0].start if failure == "overlap"
                                                       else s.shots[1].end})
        s = s.model_copy(update={"shots": (s.shots[0], second)})
    else:
        words = list(s.words)
        if failure == "missing":
            words = words[1:]
        elif failure == "repeated":
            words.append(words[0].model_copy(update={"start_frame": 10, "end_frame": 11}))
        elif failure == "outside":
            words[0] = words[0].model_copy(update={"start_frame": 301, "end_frame": 302})
        else:
            first = s.shots[0].model_copy(update={"start": s.shots[0].start.model_copy(update={"line_id": "L2"})})
            s = s.model_copy(update={"shots": (first, *s.shots[1:])})
        s = s.model_copy(update={"words": tuple(words)})
    with pytest.raises(ValueError, match="S1.*SH.*frame.*storyboard_director"):
        resolve_r5_shots(b.model_copy(update={"scenes": (s,)}))


def test_full_phrase_no_first_token_fallback_and_explicit_estimate():
    b = board([shot(0, 300)], 300)
    s = b.scenes[0]
    first = s.shots[0].model_copy(update={"start": s.shots[0].start.model_copy(update={"phrase": "w0 absent"})})
    with pytest.raises(ValueError, match="anchor"):
        resolve_r5_shots(b.model_copy(update={"scenes": (s.model_copy(update={"shots": (first,)}),)}))
    unaligned = b.model_copy(update={"scenes": (s.model_copy(update={"words": ()}),)})
    with pytest.raises(ValueError, match="alignment"):
        resolve_r5_shots(unaligned)
    runtime = R5RuntimeStoryboard.model_validate({**unaligned.model_dump(), "estimated": True})
    report = measure_r5_quality(resolve_r5_shots(runtime))
    assert report.estimated
    with pytest.raises(ValueError, match="estimated"):
        validate_r5_quality(report, estimated=False)


@pytest.mark.parametrize("wav_ms", [9000, 11000])
def test_shared_line_wav_changes_resolve_again_without_rewriting(wav_ms):
    from healthvideo.domain.quality_standards import R5Shot
    b = board([shot(0, 150)], 150)
    first = b.scenes[0].model_copy(update={"narration": "alpha beta gamma delta", "words": (),
        "shots": (R5Shot(**dict(shot(0, 150), start={"kind": "scene_start"}, end={"kind": "scene_end"})),)})
    second = first.model_copy(update={"id": "S2", "start_frame": 150,
                                       "shots": (first.shots[0].model_copy(update={"id": "SH2"}),)})
    b = b.model_copy(update={"scenes": (first, second)})
    before = b.model_dump_json()
    timed, _ = retime_storyboard(b, {"L1": wav_ms})
    duration = wav_ms/1000
    aligned = apply_alignment(timed, {"L1": [{"word": w, "start": i*duration/4,
                        "end": (i+1)*duration/4} for i, w in enumerate(first.narration.split())]})
    resolved = resolve_r5_shots(aligned)
    assert [w.text for w in resolved.scenes[0].words] == ['alpha', 'beta', 'gamma']
    assert [w.text for w in resolved.scenes[1].words] == ['gamma', 'delta']
    assert sum(s.duration_frames for s in resolved.scenes) == wav_ms*30//1000+9
    assert all(s.resolved_shots[0].end_frame == s.duration_frames for s in resolved.scenes)
    assert not measure_r5_quality(resolved).estimated
    assert b.model_dump_json() == before


def test_legacy_identity_and_golden_hash():
    path = Path("tests/fixtures/golden-project-v2/revisions/001/storyboard/storyboard.yaml")
    b = Storyboard.model_validate(read_yaml(path))
    before = b.model_dump_json().encode()
    assert resolve_r5_shots(b) is b
    assert hashlib.sha256(before).hexdigest() == "e5a6365206b4912c8767a4dbca4755469446c8600f7414361a0660aed82b72e0"
    assert b.model_dump_json().encode() == before



def test_complete_phrase_disambiguates_repeated_first_token_and_round_trips():
    from healthvideo.domain.quality_standards import R5Anchor
    from healthvideo.domain.storyboard import CaptionWord

    b = board([shot(0, 300), shot(300, 600, id="SH2")], 600)
    s = b.scenes[0]
    boundary = R5Anchor(kind="phrase", line_id="L1", phrase="alpha two")
    words = tuple(CaptionWord(text=text, start_frame=start, end_frame=start+10)
                  for text, start in [("w0", 0), ("alpha", 100), ("one", 110),
                                      ("alpha", 300), ("two", 310)])
    shots = (s.shots[0].model_copy(update={"end": boundary}),
             s.shots[1].model_copy(update={"start": boundary}))
    b = b.model_copy(update={"scenes": (s.model_copy(update={"words": words, "shots": shots}),)})
    runtime = resolve_r5_shots(b)
    assert runtime.scenes[0].resolved_shots[0].end_frame == 300
    report = measure_r5_quality(runtime)
    assert type(report).model_validate_json(report.model_dump_json()) == report
    assert runtime.scenes[0].words == words


def test_shared_line_phrase_anchors_use_scene_offsets_at_both_wav_lengths():
    from healthvideo.domain.quality_standards import R5Anchor, R5Shot

    b = board([shot(0, 150)], 150)
    start = R5Anchor(kind="scene_start")
    end = R5Anchor(kind="scene_end")
    def split(prefix, phrase):
        boundary = R5Anchor(kind="phrase", line_id="L1", phrase=phrase)
        data = shot(0, 150)
        return (R5Shot(**{**data, "id": prefix+"a", "start": start, "end": boundary}),
                R5Shot(**{**data, "id": prefix+"b", "start": boundary, "end": end}))
    first = b.scenes[0].model_copy(update={"narration": "alpha beta gamma delta", "words": (),
                                           "shots": split("A", "beta")})
    second = first.model_copy(update={"id": "S2", "start_frame": 150, "shots": split("B", "delta")})
    b = b.model_copy(update={"scenes": (first, second)})
    for ms in (9000, 11000):
        timed, _ = retime_storyboard(b, {"L1": ms})
        aligned = apply_alignment(timed, {"L1": [
            {"word": word, "start": i*ms/4000, "end": (i+1)*ms/4000}
            for i, word in enumerate(first.narration.split())]})
        runtime = resolve_r5_shots(aligned)
        assert runtime.scenes[0].resolved_shots[0].end_frame == round(ms*30/4000)
        assert runtime.scenes[1].resolved_shots[0].end_frame == round(3*ms*30/4000)-timed.scenes[1].start_frame
        assert not measure_r5_quality(runtime).estimated


def test_report_source_intervals_are_composition_relative_and_touching_merge():
    b = board([shot(0, 300, windows=[window(250, 300, "credit")])], 300)
    other = board([shot(0, 300, id="SH2", windows=[window(0, 50, "lab_sheet")])], 300).scenes[0]
    b = b.model_copy(update={"scenes": (*b.scenes, other.model_copy(update={"id": "S2", "start_frame": 300}))})
    report = measure_r5_quality(b)
    assert [(i.start_frame, i.end_frame) for i in report.source_intervals] == [(250, 300), (300, 350)]
    assert [(i.start_frame, i.end_frame) for i in report.text_union_intervals] == [(250, 350)]
    assert report.numerator_frames == 100


def test_nested_intervals_outside_shot_and_multiple_scene_errors_collected():
    b = board([shot(0, 100, windows=[window(0, 150)]), shot(100, 300, id="SH2")], 300)
    other = b.scenes[0].model_copy(update={"id": "S2", "start_frame": 300})
    b = b.model_copy(update={"scenes": (*b.scenes, other)})
    with pytest.raises(ValueError) as exc:
        resolve_r5_shots(b)
    assert "S1" in str(exc.value) and "S2" in str(exc.value)
    assert "contained in shot" in str(exc.value)


def test_six_second_text_exact_boundary_passes():
    report = measure_r5_quality(board([shot(0, 1200, windows=[window(0, 180)])], 1200))
    validate_r5_quality(report, estimated=False)


def test_long_shot_cannot_reuse_one_transition_as_three_steps():
    actions = [action(i, i+150) for i in range(0, 750, 150)]
    b = board([shot(0, 750, kind="mechanism", reason="Same entity", actions=actions)], 750)
    with pytest.raises(ValueError, match="long shot.*3 causal steps"):
        validate_r5_quality(measure_r5_quality(b), estimated=False)


def test_continuous_same_card_cannot_reset_six_seconds_by_splitting_window():
    b = board([shot(0, 2000, windows=[window(0, 120), window(90, 210)])], 2000)
    with pytest.raises(ValueError, match="continuous.*6s"):
        validate_r5_quality(measure_r5_quality(b), estimated=False)


def test_causal_step_onsets_cannot_be_one_second_apart():
    b = board([shot(0, 300, kind="mechanism", actions=[action(0, 150), action(30, 180, 1),
                                                             action(150, 300, 2)])], 300)
    with pytest.raises(ValueError, match="step onsets"):
        validate_r5_quality(measure_r5_quality(b), estimated=False)


def test_zero_length_aligned_word_inside_scene_resolves():
    """Forced alignment rounds short words to 0 frames (PYH hóc xương S03 'đến' 182-182)."""
    from healthvideo.domain.quality_standards import R5Anchor
    from healthvideo.domain.storyboard import CaptionWord

    b = board([shot(0, 300), shot(300, 600, id="SH2")], 600)
    s = b.scenes[0]
    boundary = R5Anchor(kind="phrase", line_id="L1", phrase="alpha two")
    words = (CaptionWord(text="w0", start_frame=0, end_frame=10),
             CaptionWord(text="alpha", start_frame=300, end_frame=300),
             CaptionWord(text="two", start_frame=300, end_frame=310))
    shots = (s.shots[0].model_copy(update={"end": boundary}),
             s.shots[1].model_copy(update={"start": boundary}))
    b = b.model_copy(update={"scenes": (s.model_copy(update={"words": words, "shots": shots}),)})
    assert resolve_r5_shots(b).scenes[0].resolved_shots[0].end_frame == 300
