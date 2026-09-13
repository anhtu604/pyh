import inspect
from pathlib import Path

import pytest

from healthvideo.domain.brand import MascotPose, load_brand_profile
from healthvideo.visuals.mascot import render_mascot

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def brand():
    return load_brand_profile(ROOT / "profiles/brand.vi.yaml")


@pytest.mark.parametrize("pose", list(MascotPose))
def test_mascot_pose_is_safe_and_deterministic(brand, pose: MascotPose) -> None:
    svg = render_mascot(brand, pose)
    assert svg == render_mascot(brand, pose)
    assert svg.endswith(b"\n")
    for marker in (b"mascot-p-badge", b"mascot-h-seam", b"mascot-y-check", b"mascot-short-hair"):
        assert marker in svg
    content = svg.replace(b'xmlns="http://www.w3.org/2000/svg"', b"")
    for forbidden in (b"<script", b"<filter", b"href=", b"http:", b"https:", b"foreignObject", b"<image", b"<text"):
        assert forbidden not in content


def test_mascot_poses_differ_but_share_rig(brand) -> None:
    outputs = {pose: render_mascot(brand, pose) for pose in MascotPose}
    assert len(set(outputs.values())) == 3
    for pose, svg in outputs.items():
        assert f'mascot-pose-{pose.value}'.encode() in svg


def test_mascot_api_cannot_accept_semantic_or_arbitrary_content() -> None:
    assert tuple(inspect.signature(render_mascot).parameters) == ("brand", "pose")
    source = inspect.getsource(render_mascot).lower()
    for forbidden in ("stethoscope", "white-coat", "prescription", "patient"):
        assert forbidden not in source
