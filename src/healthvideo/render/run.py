"""Layout of a published production run under ``renders/<input_hash>/`` and media stream probing."""

import json
import math
import subprocess
from pathlib import Path
from typing import Any

RENDERS_DIRECTORY = "renders"
OUTPUT_NAME = "video.mp4"
RENDER_INPUT_NAME = "render-input.json"
MANIFEST_NAME = "manifest.json"
PRODUCTION_ARTIFACT = "production"
"""Key in ``project.yaml.artifact_hashes`` selecting the active run."""


def renders_directory(project_dir: Path) -> Path:
    return project_dir / RENDERS_DIRECTORY


def production_run_dir(project_dir: Path, input_hash: str) -> Path:
    return renders_directory(project_dir) / input_hash


def is_mp4_container(path: Path) -> bool:
    """Return True when ``path`` begins with an ISO BMFF ``ftyp`` box (not a tiny test stub)."""
    try:
        with path.open("rb") as stream:
            header = stream.read(12)
    except OSError:
        return False
    return len(header) >= 12 and header[4:8] == b"ftyp"


def probe_video_streams(
    video_path: Path,
    *,
    expected_duration_ms: int | None = None,
    max_duration_drift_ms: int = 500,
    require_audio: bool = True,
    ffprobe: str = "ffprobe",
    runner=subprocess.run,
) -> dict[str, Any]:
    """Verify via ffprobe that ``video_path`` has valid video/audio streams and matching duration."""
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise RuntimeError(f"Rendered MP4 is missing or empty: {video_path}")
    argv = [
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(video_path),
    ]
    try:
        result = runner(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        raise RuntimeError(f"ffprobe could not inspect {video_path}: {error}") from None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"ffprobe failed on {video_path}: {detail}")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"ffprobe returned invalid JSON for {video_path}: {error}") from None
    streams = payload.get("streams") if isinstance(payload, dict) and isinstance(payload.get("streams"), list) else []
    fmt = payload.get("format") if isinstance(payload, dict) and isinstance(payload.get("format"), dict) else {}
    if not streams or not fmt:
        raise RuntimeError(f"ffprobe missing streams/format metadata for {video_path}")
    video_streams = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"]
    if not video_streams:
        raise RuntimeError(f"Rendered MP4 has no video stream: {video_path}")
    if require_audio and not audio_streams:
        raise RuntimeError(f"Rendered MP4 has no audio stream: {video_path}")

    raw_dur = fmt.get("duration") or video_streams[0].get("duration")
    try:
        duration_s = float(raw_dur)
    except (TypeError, ValueError):
        duration_s = 0.0
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise RuntimeError(f"Rendered MP4 has invalid duration ({raw_dur!r}): {video_path}")
    duration_ms = round(duration_s * 1000)
    drift_ms = abs(duration_ms - expected_duration_ms) if expected_duration_ms is not None else 0
    if expected_duration_ms is not None and drift_ms > max_duration_drift_ms:
        raise RuntimeError(
            f"Rendered MP4 duration {duration_ms}ms differs from expected {expected_duration_ms}ms "
            f"(drift {drift_ms}ms > {max_duration_drift_ms}ms)"
        )
    return {
        "passed": True,
        "has_video": True,
        "has_audio": bool(audio_streams),
        "video_codec": str(video_streams[0].get("codec_name") or ""),
        "audio_codec": str(audio_streams[0].get("codec_name") or "") if audio_streams else "",
        "width": int(video_streams[0].get("width") or 0),
        "height": int(video_streams[0].get("height") or 0),
        "duration_ms": duration_ms,
        "duration_drift_ms": drift_ms,
    }
