import json
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
    return {
        "name": "remotion",
        "package_version": package_version,
        "source_sha256": canonical_json_hash(source_hashes),
    }


def build_render_argv(render_input: Path, output: Path, public_dir: Path) -> list[str]:
    """Build the cross-platform argv used to render the HealthVideo composition.

    Paths are absolute because ``pnpm --dir`` runs Remotion from ``video/``.
    """
    repository_root = Path(__file__).resolve().parents[3]
    return [
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
