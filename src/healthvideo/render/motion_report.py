"""Measured whole-frame motion evidence, independent of review/approval decisions."""

import math
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from healthvideo.storage.files import sha256_file

SAMPLE_INTERVAL_S = 0.5
# Initial design threshold: tolerates compression noise on 160x90 grayscale.
# Keep conservative: whole-frame changes cannot prove meaningful medical motion.
# PYH-003 calibration: 1..3 still split reviewer S08 into runs <=5s while
# flagging many more scenes. Retain 0.6; document that semantic blind spot
# rather than inflate the threshold to classify genuine frame changes as static.
STATIC_THRESHOLD = 0.6
STATIC_LIMIT_S = 6.0
DATA_LIMIT_S = 10.0
OUTRO_LIMIT_S = 15.0
DATA_VISUALS = frozenset({"source_card", "evidence_highlight", "chart", "stat_gauge"})
OUTRO_VISUALS = frozenset({"brand_outro"})
WIDTH, HEIGHT = 160, 90


def find_static_runs(
    differences: Iterable[float], *, sample_interval_s: float = SAMPLE_INTERVAL_S,
    threshold: float = STATIC_THRESHOLD,
) -> list[dict[str, float]]:
    """Each delta covers [i * interval, (i + 1) * interval]; keep all runs."""
    if not math.isfinite(sample_interval_s) or sample_interval_s <= 0:
        raise ValueError("sample_interval_s must be positive and finite")
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError("threshold must be nonnegative and finite")
    runs = []
    start = None
    end = 0.0
    for index, difference in enumerate(differences):
        if not math.isfinite(difference) or not 0 <= difference <= 255:
            raise ValueError("pixel difference must be finite and in 0..255")
        if difference <= threshold:
            if start is None:
                start = index * sample_interval_s
            end = (index + 1) * sample_interval_s
        elif start is not None:
            runs.append({"start_s": start, "end_s": end, "duration_s": end - start})
            start = None
    if start is not None:
        runs.append({"start_s": start, "end_s": end, "duration_s": end - start})
    return runs


def build_motion_report(
    differences: Iterable[float], timing: Mapping[str, Any], visuals: Mapping[str, str], *,
    video_sha256: str, sample_interval_s: float = SAMPLE_INTERVAL_S,
    threshold: float = STATIC_THRESHOLD,
) -> dict[str, Any]:
    """Apply limits to each run's overlap with each runtime scene (not approved timing)."""
    fps = timing.get("fps", 30)
    if not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("scene timing fps must be positive and finite")
    scenes = []
    for row in timing["scenes"]:
        sid = row["scene_id"]
        start, duration = row["start_frame"], row["duration_frames"]
        if not math.isfinite(start) or not math.isfinite(duration) or start < 0 or duration <= 0:
            raise ValueError("invalid scene timing")
        scenes.append((sid, start / fps, (start + duration) / fps, visuals[sid]))
    runs = find_static_runs(differences, sample_interval_s=sample_interval_s, threshold=threshold)
    violations: set[str] = set()
    for run in runs:
        overlaps = []
        for sid, start, end, visual in scenes:
            left, right = max(run["start_s"], start), min(run["end_s"], end)
            if right <= left:
                continue
            limit = (
                OUTRO_LIMIT_S
                if visual in OUTRO_VISUALS
                else DATA_LIMIT_S
                if visual in DATA_VISUALS
                else STATIC_LIMIT_S
            )
            exceeded = right - left > limit
            if exceeded:
                violations.add(sid)
            overlaps.append({
                "scene_id": sid, "visual": visual, "start_s": left, "end_s": right,
                "duration_s": right - left, "limit_s": limit, "exceeded": exceeded,
            })
        run.update({
            "scene_ids": [item["scene_id"] for item in overlaps],
            "visual": {item["scene_id"]: item["visual"] for item in overlaps},
            "scene_overlaps": overlaps,
        })
    return {
        "schema_version": "1.0", "video_sha256": video_sha256,
        "sample_interval_s": sample_interval_s, "threshold": threshold,
        "limits": {"default_s": STATIC_LIMIT_S, "data_s": DATA_LIMIT_S,
                   "outro_s": OUTRO_LIMIT_S, "data_visuals": sorted(DATA_VISUALS)},
        "static_runs": runs,
        "max_static_s": max((run["duration_s"] for run in runs), default=0.0),
        "passed": not violations, "scenes_with_violation": sorted(violations),
    }


def measure_video(
    video: Path, timing: Mapping[str, Any], visuals: Mapping[str, str], *,
    ffmpeg: str = "ffmpeg",
) -> dict[str, Any]:
    """Stream small grayscale frames through a pipe; retain deltas, never full video."""
    differences = []
    # Only stderr uses a temporary file, so a failing decoder cannot fill a pipe.
    with tempfile.TemporaryFile() as errors, subprocess.Popen([
        ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(video),
        "-an", "-vf", f"fps=2,scale={WIDTH}:{HEIGHT},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ], stdout=subprocess.PIPE, stderr=errors) as process:
        assert process.stdout is not None
        previous = None
        try:
            while True:
                frame = bytearray()
                while len(frame) < WIDTH * HEIGHT:
                    part = process.stdout.read(WIDTH * HEIGHT - len(frame))
                    if not part:
                        break
                    frame.extend(part)
                if not frame:
                    break
                if len(frame) != WIDTH * HEIGHT:
                    raise RuntimeError("ffmpeg returned an incomplete raw frame")
                if previous is not None:
                    differences.append(sum(abs(a - b) for a, b in zip(previous, frame))
                                       / len(frame))
                previous = frame
            code = process.wait()
            if code:
                errors.seek(max(0, errors.tell() - 4000))
                raise RuntimeError(f"ffmpeg exited {code}: "
                                   + errors.read().decode("utf-8", errors="replace"))
            if not differences:
                raise RuntimeError("ffmpeg returned fewer than two samples")
        finally:
            if process.poll() is None:
                process.kill()
            process.stdout.close()
    return build_motion_report(differences, timing, visuals, video_sha256=sha256_file(video))
