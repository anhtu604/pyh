import pytest
from pydantic import ValidationError

from healthvideo.domain.storyboard import Scene, SceneBeat, Storyboard
from healthvideo.render.beats import resolve_scene_beats, visual_rhythm_qa


def scene(**updates):
    data = {"id": "S01", "visual": "process_animation", "narration": "Tinh thể lớn rồi lắng đọng",
                "start_frame": 0, "duration_frames": 600,
                "anatomy": {"subject": "joint_fluid_urate_to_inflammation", "state": "diseased",
                             "severity": 1, "motion": "grow"}}
    data.update(updates)
    return Scene.model_validate(data)


def test_beats_focus_must_exist():
    with pytest.raises(ValidationError, match="beat focus must exist"):
        scene(beats=[{"at": 2, "focus": "missing"}])


def test_visual_gap_over_6s_rejected():
    with pytest.raises(ValueError, match="visual gap.*exceeds 6"):
        visual_rhythm_qa(scene(duration_frames=270))


def test_long_scene_needs_two_beats():
    with pytest.raises(ValueError, match="over 12 seconds needs at least 2"):
        visual_rhythm_qa(scene())


def test_long_video_needs_four_subjects():
    scenes = [scene(id=f"S{i}", start_frame=i*600, chapter_id="CH01",
                    anatomy={"subject": subject, "state": "diseased", "severity": 1, "motion": "grow"})
              for i, subject in enumerate(["joint_fluid_urate_to_inflammation", "immune_cell_alarm",
                                           "heart", "heart"])]
    with pytest.raises(ValidationError, match="at least 4 anatomy.subject"):
        Storyboard(title="Gout", format_profile="youtube_long", scenes=scenes)


def test_clip_needs_two_subjects():
    with pytest.raises(ValidationError, match="at least 2 anatomy.subject"):
        Storyboard(title="Gout", scenes=[scene(), scene(id="S02", start_frame=600)])


def test_keyword_beat_uses_existing_whisper_words():
    item = scene(beats=[{"at": "lắng đọng", "action": "deposit"}], words=[
        {"text": "lắng", "start_frame": 310, "end_frame": 325},
        {"text": "đọng", "start_frame": 326, "end_frame": 340}])
    assert resolve_scene_beats(item).beats[0].start_frame == 310


def test_seconds_rechecked_after_timing():
    with pytest.raises(ValueError, match="outside timed scene"):
        resolve_scene_beats(scene(duration_frames=90, beats=[{"at": 3, "action": "grow"}]))


def test_identical_focus_and_labels_do_not_hide_static_gap():
    item = scene(duration_frames=350).model_copy(update={"beats": (
        SceneBeat(at=1, start_frame=30), SceneBeat(at=5, start_frame=150))})
    with pytest.raises(ValueError, match="visual gap"):
        visual_rhythm_qa(item)


def test_two_process_events_and_cut_meet_rhythm():
    item = resolve_scene_beats(scene(duration_frames=390, beats=[
        {"at": 4, "action": "grow"}, {"at": 9, "action": "deposit"}]))
    visual_rhythm_qa(item)


@pytest.mark.parametrize("at", [float("inf"), float("nan"), -1, " "])
def test_beat_time_finite_nonnegative_nonblank(at):
    with pytest.raises(ValidationError):
        SceneBeat(at=at)


def test_keyword_must_belong_to_narration():
    with pytest.raises(ValidationError, match="beat keyword must be in narration"):
        scene(beats=[{"at": "Không có", "action": "grow"}])


def test_repeated_completed_action_does_not_count_as_second_beat():
    item = resolve_scene_beats(scene(beats=[
        {"at": 2, "action": "grow"}, {"at": 8, "action": "grow"}]))
    with pytest.raises(ValueError, match="needs at least 2 visual beats"):
        visual_rhythm_qa(item)


def test_unknown_label_rejected():
    with pytest.raises(ValidationError, match="beat label must exist"):
        scene(beats=[{"at": 1, "labels": ["missing"]}])


def test_beats_carry_no_more_than_six_labels():
    with pytest.raises(ValidationError):
        SceneBeat(at=1, labels=[f"label{i}" for i in range(7)])


def test_duplicate_beat_times_rejected():
    with pytest.raises(ValueError, match="distinct increasing"):
        resolve_scene_beats(scene(beats=[{"at": 1, "action": "grow"},
                                         {"at": 1, "action": "deposit"}]))
