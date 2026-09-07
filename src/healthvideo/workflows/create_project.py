import shutil
from pathlib import Path
from tempfile import mkdtemp

from healthvideo.domain.author import AuthorBrief
from healthvideo.domain.project import ProjectManifest
from healthvideo.storage.files import write_yaml_atomic

PROJECT_DIRECTORIES = (
    "trend",
    "evidence",
    "script",
    "storyboard",
    "handoffs",
    "audio",
    "assets",
    "renders",
    "reviews",
    "voice-learning",
    "publish",
)


def create_project(root: Path, slug: str, title: str) -> Path:
    """Create a project directory from the doctor's initial author brief."""
    manifest = ProjectManifest(slug=slug)
    project_dir = root / manifest.slug
    root.mkdir(parents=True, exist_ok=True)
    if project_dir.exists():
        raise FileExistsError(f"Project already exists: {project_dir}")

    staging_dir = Path(mkdtemp(prefix=f".{manifest.slug}.tmp-", dir=root))
    try:
        for directory in PROJECT_DIRECTORIES:
            (staging_dir / directory).mkdir()

        brief = AuthorBrief(title=title)
        write_yaml_atomic(staging_dir / "project.yaml", manifest.model_dump(mode="json"))
        write_yaml_atomic(staging_dir / "author-brief.yaml", brief.model_dump(mode="json"))
        staging_dir.rename(project_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    return project_dir
