from pathlib import Path

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
    try:
        project_dir.mkdir()
    except FileExistsError as error:
        raise FileExistsError(f"Project already exists: {project_dir}") from error

    for directory in PROJECT_DIRECTORIES:
        (project_dir / directory).mkdir()

    brief = AuthorBrief(title=title)
    write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))
    write_yaml_atomic(project_dir / "author-brief.yaml", brief.model_dump(mode="json"))
    return project_dir
