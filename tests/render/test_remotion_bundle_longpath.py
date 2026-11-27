"""PYH-001 2026-11-28: chunked render copies public assets into a bundle past MAX_PATH."""
import os

from healthvideo.render.remotion import _fs_path, sync_bundle_public


def test_verified_public_sync_survives_paths_past_max_path(tmp_path):
    public = tmp_path / "public"
    asset = public / "assets" / "r5" / "reactome-muscle-icon.svg"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"<svg/>")
    bundle = tmp_path / ("b" * 120) / ("c" * 120)
    os.makedirs(_fs_path(bundle), exist_ok=True)
    sync_bundle_public(public, bundle, verify_bytes=True)
    target = bundle / "public" / "assets" / "r5" / "reactome-muscle-icon.svg"
    assert len(str(target)) > 260
    with open(_fs_path(target), "rb") as stream:
        assert stream.read() == b"<svg/>"
