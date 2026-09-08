from collections.abc import Callable
from pathlib import Path

RemotionRunner = Callable[[list[str]], int]


def build_render_argv(render_input: Path, output: Path, public_dir: Path) -> list[str]:
    """Build the cross-platform argv used to render the HealthVideo composition."""
    repository_root = Path(__file__).resolve().parents[3]
    return [
        "pnpm",
        "--dir",
        str(repository_root / "video"),
        "render",
        "--props",
        str(render_input),
        "--output",
        str(output),
        "--public-dir",
        str(public_dir),
    ]
