"""Resolve R5 anchors and measure half-open frame intervals without touching sources.

Phrase anchors denote the onset of the COMPLETE phrase for both boundaries, so
adjacent shots can share an anchor. Runtime estimation is explicit and never
serialized back into the approved storyboard. Semantic/pixel review stays pending.
"""
from __future__ import annotations

import itertools
from math import ceil

from pydantic import Field

from healthvideo.audio.align import normalize_word
from healthvideo.domain.long_form import long_form_storyboard
from healthvideo.domain.quality_standards import (
    D1_MAX_TEXT_PERCENT,
    D1_MAX_TEXT_SECONDS,
    D2_ACTION_STEP_SECONDS,
    D2_LONG_SHOT_MIN_STEPS,
    D2_LONG_SHOT_SECONDS,
    D2_MECHANISM_MEDIAN_SECONDS,
    D2_STORY_MEDIAN_SECONDS,
    D2_STORY_P90_MAX_SECONDS,
    FrameInterval,
    QualityReport,
    QualityShotInterval,
    QualitySourceInterval,
    R5Anchor,
    ResolvedR5Action,
    ResolvedR5Shot,
    ResolvedR5TextWindow,
    ShotStatistics,
)
from healthvideo.domain.storyboard import CaptionWord, Scene, Storyboard


class R5RuntimeStoryboard(Storyboard):
    """Transient timing provenance, local to R5; never write this to a revision.

    Pass estimated=True explicitly before resolving estimated timing. A plain
    Storyboard requires scene-local word alignment, even when anchors use only
    scene boundaries. This prevents missing alignment from becoming an estimate.
    """

    estimated: bool = Field(default=False, strict=True)


def _issue(scene: Scene, shot: str, start: int, end: int, message: str) -> str:
    return (f"Scene {scene.id} shot {shot} frame [{start},{end}): {message}; "
            "owner=storyboard_director")


def _estimated_words(board: Storyboard) -> dict[str, tuple[CaptionWord, ...]]:
    """Estimate each shared line once, then slice by the retimed scene boundaries."""
    result = {}
    groups: list[list[Scene]] = []
    for scene in board.scenes:
        if groups and scene.script_line_id is not None and groups[-1][0].script_line_id == scene.script_line_id:
            groups[-1].append(scene)
        else:
            groups.append([scene])
    for group in groups:
        narrations = [s.narration for s in group]
        text = narrations[0] if len(set(narrations)) == 1 else " ".join(narrations)
        tokens = text.split()
        total = sum(s.duration_frames for s in group)
        words = [CaptionWord(text=t, start_frame=round(i*total/len(tokens)),
                             end_frame=round((i+1)*total/len(tokens)))
                 for i, t in enumerate(tokens)]
        offset = 0
        for scene in group:
            result[scene.id] = tuple(CaptionWord(text=w.text,
                start_frame=max(0, w.start_frame-offset),
                end_frame=min(scene.duration_frames, w.end_frame-offset))
                for w in words if w.end_frame > offset and w.start_frame < offset+scene.duration_frames)
            offset += scene.duration_frames
    return result


def _anchor(anchor: R5Anchor, scene: Scene, words: tuple[CaptionWord, ...]) -> int:
    if anchor.kind == "scene_start":
        return 0
    if anchor.kind == "scene_end":
        return scene.duration_frames
    if anchor.line_id != scene.script_line_id:
        raise ValueError(f"anchor line {anchor.line_id} outside scene line {scene.script_line_id}")
    tokens = [normalize_word(t) for t in anchor.phrase.split()]
    normalized = [normalize_word(w.text) for w in words]
    matches = [i for i in range(len(words)-len(tokens)+1)
               if normalized[i:i+len(tokens)] == tokens]
    if len(matches) != 1:
        raise ValueError(f"anchor {anchor.phrase!r} requires exactly one complete match, found {len(matches)}")
    selected = words[matches[0]:matches[0]+len(tokens)]
    if any(not 0 <= w.start_frame < w.end_frame <= scene.duration_frames for w in selected):
        raise ValueError(f"anchor {anchor.phrase!r} outside scene")
    return selected[0].start_frame


def _resolve(board: Storyboard) -> tuple[Storyboard, list[str]]:
    estimated = getattr(board, "estimated", False)
    estimates = _estimated_words(board) if estimated else {}
    scenes, issues, ids = [], [], set()
    cursor = 0
    for scene in board.scenes:
        clip_only = board.format_profile == "youtube_long" and scene.clip_only is not None
        expected_start = 0 if clip_only else cursor
        if scene.start_frame != expected_start or scene.duration_frames <= 0:
            issues.append(_issue(scene, "*", scene.start_frame, cursor, "scene gap/overlap or invalid duration"))
        if not clip_only:
            cursor = scene.start_frame+scene.duration_frames
        words = estimates.get(scene.id, scene.words)
        if not estimated and scene.script_line_id is not None and not words:
            issues.append(_issue(scene, "*", 0, scene.duration_frames, "missing word alignment; estimate must be explicit"))
        if any(a.start_frame > b.start_frame for a, b in itertools.pairwise(words)):
            issues.append(_issue(scene, "*", 0, scene.duration_frames, "word alignment must be ordered"))
        resolved = []
        end = 0
        if not scene.shots:
            issues.append(_issue(scene, "*", 0, scene.duration_frames, "missing R5 shots"))
        for shot in scene.shots:
            if shot.id in ids:
                issues.append(_issue(scene, shot.id, 0, scene.duration_frames, "duplicate shot ID"))
            ids.add(shot.id)
            try:
                start, stop = _anchor(shot.start, scene, words), _anchor(shot.end, scene, words)
                if start != end:
                    issues.append(_issue(scene, shot.id, end, start, "shot gap/overlap"))
                actions, windows = [], []
                for items, target, cls in ((shot.actions, actions, ResolvedR5Action),
                                           (shot.text_windows, windows, ResolvedR5TextWindow)):
                    for item in items:
                        try:
                            first, last = _anchor(item.start, scene, words), _anchor(item.end, scene, words)
                            target.append(cls(**item.model_dump(exclude={"start", "end"}),
                                              start_frame=first, end_frame=last))
                        except ValueError as error:
                            issues.append(_issue(scene, shot.id, start, stop, str(error)))
                resolved.append(ResolvedR5Shot(**shot.model_dump(exclude={"start", "end", "actions", "text_windows"}),
                    start_frame=start, end_frame=stop, actions=tuple(actions), text_windows=tuple(windows)))
                end = stop
            except ValueError as error:
                issues.append(_issue(scene, shot.id, end, scene.duration_frames, str(error)))
        if end != scene.duration_frames:
            issues.append(_issue(scene, scene.shots[-1].id if scene.shots else "*", end,
                                 scene.duration_frames, "shots must cover scene end"))
        scenes.append(scene.model_copy(update={"resolved_shots": tuple(resolved)}))
    return board.model_copy(update={"scenes": tuple(scenes)}), issues


def resolve_r5_shots(board: Storyboard) -> Storyboard:
    """Return a runtime copy; collect every resolvable scene/shot error before raising."""
    if board.quality_profile is None:
        return board
    result, issues = _resolve(board)
    if issues:
        raise ValueError("R5 shot resolution failed:\n" + "\n".join(issues))
    return result


def _statistics(durations: list[int]) -> ShotStatistics:
    values = sorted(durations)
    def rank(fraction: float) -> float | None:
        return values[ceil(len(values)*fraction)-1]/30 if values else None
    return ShotStatistics(count=len(values), median_seconds=rank(.5), p90_seconds=rank(.9))


def causal_actions(shot: ResolvedR5Shot) -> tuple[ResolvedR5Action, ...]:
    """Count authored state transitions once, excluding declared background motion.

    This structural filter is not a medical/visual judgment. A critic still has
    to verify that these distinct transitions are actually visible and causal.
    """
    seen, result = set(), []
    for action in sorted(shot.actions, key=lambda a: a.start_frame):
        identity = tuple(" ".join(v.lower().split()) for v in
                         (action.actor, action.compartment, action.change, action.outcome))
        background = {"background", "background motion", "nền", "chuyển động nền"}
        if identity[0] in background or identity[1] in background or identity[2] == identity[3]:
            continue
        if identity not in seen:
            result.append(action)
            seen.add(identity)
    return tuple(result)


def measure_r5_quality(board: Storyboard) -> QualityReport:
    """Measure the same frame contract before the gate and after measured speech."""
    board = long_form_storyboard(board)
    if board.quality_profile != "r5_v1":
        raise ValueError("R5 measurement requires quality_profile=r5_v1")
    resolved, issues = _resolve(board)
    denominator = sum(s.duration_frames for s in board.scenes)
    if denominator <= 0:
        raise ValueError("Scene * shot * frame [0,0): empty composition; owner=storyboard_director")
    from healthvideo.render.beats import visual_rhythm_qa

    sources, shots, groups = [], [], {"story": [], "mechanism": []}
    appearances: dict[tuple[str, str], list[tuple[int, int, Scene, str]]] = {}
    for scene in resolved.scenes:
        if scene.shots and scene.resolved_shots:
            try:
                visual_rhythm_qa(scene)
            except ValueError as error:
                issues.append(str(error))
        for shot in scene.resolved_shots:
            start, end = scene.start_frame+shot.start_frame, scene.start_frame+shot.end_frame
            if not 0 <= start < end <= denominator:
                issues.append(_issue(scene, shot.id, start, end, "shot outside composition"))
                continue
            shots.append(QualityShotInterval(scene_id=scene.id, shot_id=shot.id, kind=shot.kind,
                                             start_frame=start, end_frame=end))
            if shot.kind in groups:
                groups[shot.kind].append(end-start)
            for window in shot.text_windows:
                sources.append(QualitySourceInterval(scene_id=scene.id, shot_id=shot.id, kind=window.kind,
                    start_frame=scene.start_frame+window.start_frame, end_frame=scene.start_frame+window.end_frame))
                if window.kind not in {"label", "scale_bar"}:
                    appearances.setdefault((window.kind, window.text), []).append((
                        scene.start_frame+window.start_frame, scene.start_frame+window.end_frame,
                        scene, shot.id))
                if window.kind not in {"label", "scale_bar"} and window.end_frame-window.start_frame > D1_MAX_TEXT_SECONDS*30:
                    issues.append(_issue(scene, shot.id, window.start_frame, window.end_frame,
                                         f"D1 {window.kind} exceeds {D1_MAX_TEXT_SECONDS}s"))
            if shot.kind == "mechanism":
                actions = causal_actions(shot)
                if end-start > D2_LONG_SHOT_SECONDS*30 and (
                        not shot.long_shot_reason or len(actions) < D2_LONG_SHOT_MIN_STEPS):
                    issues.append(_issue(scene, shot.id, shot.start_frame, shot.end_frame,
                        f"D2 long shot needs reason and >= {D2_LONG_SHOT_MIN_STEPS} causal steps"))
                for action in actions:
                    if not D2_ACTION_STEP_SECONDS[0]*30 <= action.end_frame-action.start_frame <= D2_ACTION_STEP_SECONDS[1]*30:
                        issues.append(_issue(scene, shot.id, action.start_frame, action.end_frame,
                                             f"D2 action step must last {D2_ACTION_STEP_SECONDS} seconds"))
                for first, last in itertools.pairwise(actions):
                    if not D2_ACTION_STEP_SECONDS[0]*30 <= last.start_frame-first.start_frame <= D2_ACTION_STEP_SECONDS[1]*30:
                        issues.append(_issue(scene, shot.id, first.start_frame, last.start_frame,
                                             f"D2 step onsets must be {D2_ACTION_STEP_SECONDS} seconds apart"))
                changes = sorted({shot.start_frame, shot.end_frame, *(a.start_frame for a in actions)})
                for first, last in itertools.pairwise(changes):
                    if last-first > D2_ACTION_STEP_SECONDS[1]*30:
                        issues.append(_issue(scene, shot.id, first, last, "D2 causal action gap exceeds 6s"))
    # A continuously visible card cannot reset its clock by splitting its data
    # into several overlapping/touching windows or adjacent shots/scenes.
    for intervals in appearances.values():
        first, last, owner, shot_id = -1, -1, None, ""
        for start, end, scene, current_id in sorted(intervals, key=lambda i: (i[0], i[1])):
            if start > last:
                first, last, owner, shot_id = start, end, scene, current_id
            else:
                last = max(last, end)
            if last-first > D1_MAX_TEXT_SECONDS*30:
                issues.append(_issue(owner, shot_id, first-owner.start_frame, last-owner.start_frame,
                                     f"D1 continuous text exceeds {D1_MAX_TEXT_SECONDS}s"))
    union: list[FrameInterval] = []
    for interval in sorted((s for s in sources if s.kind not in {"label", "scale_bar"}),
                           key=lambda s: (s.start_frame, s.end_frame)):
        if union and interval.start_frame <= union[-1].end_frame:
            union[-1] = FrameInterval(start_frame=union[-1].start_frame,
                                     end_frame=max(union[-1].end_frame, interval.end_frame))
        else:
            union.append(FrameInterval(start_frame=interval.start_frame, end_frame=interval.end_frame))
    return QualityReport(estimated=getattr(board, "estimated", False), denominator_frames=denominator,
        numerator_frames=sum(i.end_frame-i.start_frame for i in union),
        shot_intervals=tuple(shots), source_intervals=tuple(sources), text_union_intervals=tuple(union),
        story=_statistics(groups["story"]), mechanism=_statistics(groups["mechanism"]), issues=tuple(issues))


def validate_r5_quality(report: QualityReport, *, estimated: bool) -> None:
    """Raise one actionable packet; manual review remains a separate pending check."""
    issues = list(report.issues)
    if report.estimated != estimated:
        issues.append("Scene * shot * frame [0,0): estimated provenance mismatch; owner=repair_engineer")
    location = ", ".join(f"{s.scene_id}/{s.shot_id}" for s in report.shot_intervals)
    prefix = f"Scene/shot {location} frame [0,{report.denominator_frames}): "
    if report.numerator_frames*100 > report.denominator_frames*D1_MAX_TEXT_PERCENT:
        issues.append(prefix + f"D1 text {report.numerator_frames}/{report.denominator_frames} exceeds "
                      f"{D1_MAX_TEXT_PERCENT}%; owner=storyboard_director")
    for kind, bounds in (("story", D2_STORY_MEDIAN_SECONDS), ("mechanism", D2_MECHANISM_MEDIAN_SECONDS)):
        stats = getattr(report, kind)
        if stats.count and not bounds[0] <= stats.median_seconds <= bounds[1]:
            issues.append(prefix + f"D2 {kind} median {stats.median_seconds}s outside {bounds}; owner=storyboard_director")
        if kind == "story" and stats.count and stats.p90_seconds > D2_STORY_P90_MAX_SECONDS:
            issues.append(prefix + f"D2 story P90 exceeds {D2_STORY_P90_MAX_SECONDS}s; owner=storyboard_director")
    if issues:
        raise ValueError("R5 quality failed (estimated=" + str(estimated) + "):\n" + "\n".join(issues))
