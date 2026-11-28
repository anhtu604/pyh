"""Measure black, frozen and silent intervals and loudness in a rendered MP4."""

import re
import subprocess
from pathlib import Path
from typing import Any

_NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_BLACK = re.compile(rf"lavfi\.black_(start|end)=({_NUMBER})")
_FREEZE = re.compile(rf"lavfi\.freezedetect\.freeze_(start|end):\s*({_NUMBER})")
_SILENCE = re.compile(rf"silence_(start|end):\s*({_NUMBER})")
_OUT_TIME = re.compile(r"^out_time_us=(\d+)\s*$", re.MULTILINE)
_LOUDNESS = re.compile(rf"^\s*I:\s*({_NUMBER}|-inf) LUFS", re.MULTILINE)
# R5 already treats a visual gap > 6 s as a fault; shorter holds are normal mascot/still beats
# (PYH-003 trial: 73 holds >= 3 s in a 13-min video would drown the critic).
FREEZE_WARN_SECONDS = 6
_TRUE_PEAK = re.compile(rf"True peak:\s*Peak:\s*({_NUMBER}|-inf) dB(?:FS|TP)")


def _stream_end(stderr: str) -> float:
    times = _OUT_TIME.findall(stderr)
    if not times:
        raise ValueError("FFmpeg did not report the decoded stream end")
    return int(times[-1]) / 1_000_000


def _intervals(stderr: str, pattern: re.Pattern[str], stream_end: float) -> list[list[float]]:
    intervals = []
    start = None
    for event, timestamp in pattern.findall(stderr):
        time = float(timestamp)
        if event == "start":
            start = time
        elif start is not None:
            intervals.append([start, time])
            start = None
    if start is not None:
        intervals.append([start, stream_end])
    return intervals


def parse_frame_qa(
    black_log: str, freeze_log: str, silence_log: str, loudness_log: str,
) -> dict[str, Any]:
    video_end = _stream_end(black_log)
    audio_end = _stream_end(silence_log)
    duration = max(video_end, audio_end)
    black = _intervals(black_log, _BLACK, video_end)
    freeze = _intervals(freeze_log, _FREEZE, video_end)
    silence = _intervals(silence_log, _SILENCE, audio_end)
    loudness = _LOUDNESS.search(loudness_log)
    peak = _TRUE_PEAK.search(loudness_log)
    if loudness is None or peak is None:
        raise ValueError("FFmpeg ebur128 summary is missing integrated loudness or true peak")
    integrated_lufs = None if loudness[1] == "-inf" else float(loudness[1])
    true_peak_db = None if peak[1] == "-inf" else float(peak[1])

    issues = []
    for start, end in black:
        start, end = max(start, 0.3), min(end, duration - 0.3)
        if round(end - start, 6) >= 0.5:
            issues.append(_issue("block", "black", [start, end], "Black frames for at least 0.5 s"))
    for start, end in freeze:
        if round(end - start, 6) >= FREEZE_WARN_SECONDS:
            issues.append(_issue("warn", "freeze", [start, end],
                                 f"Frozen image for at least {FREEZE_WARN_SECONDS} s"))
    for start, end in silence:
        if round(end - start, 6) >= 3:
            # A silent tail is the end screen (PYH-003 trial: 5 s after the outro), not a dropout.
            tail = end >= duration - 0.5
            issues.append(_issue("warn" if tail else "block", "silence", [start, end],
                                 "Silent tail (end screen)" if tail else "Silent audio for at least 3 s"))
    if true_peak_db is not None and true_peak_db > -0.5:
        issues.append(_issue("block", "true_peak", [0.0, duration], f"True peak {true_peak_db:g} dBTP"))
    if integrated_lufs is None or not -16 <= integrated_lufs <= -12:
        level = "-inf" if integrated_lufs is None else f"{integrated_lufs:g}"
        issues.append(_issue("warn", "integrated_lufs", [0.0, duration], f"Integrated loudness {level} LUFS"))

    return {
        "black": black,
        "freeze": freeze,
        "silence": silence,
        "integrated_lufs": integrated_lufs,
        "true_peak_db": true_peak_db,
        "issues": issues,
    }


def _issue(severity: str, kind: str, at: list[float], message: str) -> dict[str, Any]:
    return {"severity": severity, "kind": kind, "at": at, "message": message}


def measure_frame_qa(
    video_path: Path, *, ffmpeg: str = "ffmpeg", runner=subprocess.run,
) -> dict[str, Any]:
    # Black metadata records both transitions, including ranges shorter than d
    # and starts still open when blackdetect logs the last frame at EOF.
    filters = (
        ("v", "blackdetect=d=0.5:pix_th=0.10,metadata=mode=print"),
        ("v", "freezedetect=n=-60dB:d=3"),
        ("a", "silencedetect=n=-50dB:d=3"),
        ("a", "ebur128=peak=true:framelog=verbose"),
    )
    logs = []
    for stream, filter_expr in filters:
        argv = [
            ffmpeg, "-hide_banner", "-loglevel", "info", "-nostdin", "-nostats",
            "-i", str(video_path), "-map", f"0:{stream}:0", f"-{stream}f", filter_expr,
            "-progress", "pipe:2", "-f", "null", "-",
        ]
        try:
            result = runner(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        except OSError as error:
            raise RuntimeError(f"FFmpeg could not inspect {video_path}: {error}") from None
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg {filter_expr} failed on {video_path}: {result.stderr.strip()}")
        logs.append(result.stderr)
    try:
        return parse_frame_qa(*logs)
    except ValueError as error:
        raise RuntimeError(f"FFmpeg Frame QA could not parse {video_path}: {error}") from None
