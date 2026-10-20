import json
import shutil
from collections.abc import Callable
from pathlib import Path

from healthvideo.storage.files import canonical_json_hash, sha256_file

RemotionRunner = Callable[[list[str]], int]


def renderer_identity() -> dict[str, str]:
    """Return the version and source fingerprint of the active Remotion renderer."""
    repository_root = Path(__file__).resolve().parents[3]
    video_dir = repository_root / "video"
    package_path = video_dir / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package_version = package.get("dependencies", {}).get("remotion")
    if not isinstance(package_version, str) or not package_version:
        raise ValueError("video/package.json must declare a Remotion version")

    source_dir = video_dir / "src"
    source_hashes = {
        path.relative_to(source_dir).as_posix(): sha256_file(path)
        for path in sorted(source_dir.rglob("*"))
        if path.is_file()
    }
    if not source_hashes:
        raise FileNotFoundError("Remotion renderer source is missing")
    fonts_dir = video_dir / "public" / "fonts"
    font_hashes = {
        path.relative_to(fonts_dir).as_posix(): sha256_file(path)
        for path in sorted(fonts_dir.rglob("*"))
        if path.is_file()
    }
    return {
        "name": "remotion",
        "package_version": package_version,
        "source_sha256": canonical_json_hash(source_hashes),
        "fonts_sha256": canonical_json_hash(font_hashes),
    }


def build_render_argv(
    render_input: Path,
    output: Path,
    public_dir: Path,
    *,
    frames: tuple[int, int] | None = None,
    muted: bool = False,
    stage_fonts: bool = True,
) -> list[str]:
    """Build the cross-platform argv used to render the HealthVideo composition.

    Paths are absolute because ``pnpm --dir`` runs Remotion from ``video/``.
    Stage renderer-owned fonts (and their license) before any runner is invoked.
    Command previews can disable staging to keep dry runs read-only.
    """
    repository_root = Path(__file__).resolve().parents[3]
    fonts_dir = repository_root / "video" / "public" / "fonts"
    target_fonts = public_dir.resolve() / "fonts"
    if stage_fonts and target_fonts != fonts_dir.resolve():
        shutil.copytree(fonts_dir, target_fonts, dirs_exist_ok=True)
    argv = [
        "pnpm",
        "--dir",
        str(repository_root / "video"),
        "render",
        "--props",
        str(render_input.resolve()),
        "--output",
        str(output.resolve()),
        "--public-dir",
        str(public_dir.resolve()),
    ]
    if frames is not None:
        argv.append(f"--frames={frames[0]}-{frames[1]}")
    if muted:
        argv.append("--muted")
    return argv


def build_concat_argv(concat_list: Path, audio: Path, output: Path) -> list[str]:
    """Join muted chapter parts losslessly, then mux the reviewed narration once."""
    return [
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list.resolve()),
        "-i", str(audio.resolve()),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(output.resolve()),
    ]
