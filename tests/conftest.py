from hashlib import sha256

import pytest

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from tests.brand_artwork import png_bytes


@pytest.fixture(scope='session')
def brand_profile_path(tmp_path_factory):
    from pathlib import Path

    data = read_yaml(Path('profiles/brand.vi.yaml'))
    data['mascot'].pop('artwork', None)
    path = tmp_path_factory.mktemp('brand-fixture') / 'brand.yaml'
    write_yaml_atomic(path, data)
    return path


@pytest.fixture(autouse=True)
def synthetic_workflow_brand(brand_profile_path, monkeypatch):
    from healthvideo.workflows import long_form, produce, visual_assets

    monkeypatch.setattr(visual_assets, 'BRAND_PROFILE_PATH', brand_profile_path)
    monkeypatch.setattr(long_form, 'BRAND_PROFILE_PATH', brand_profile_path)
    monkeypatch.setattr(produce, 'BRAND_PROFILE_PATH', brand_profile_path)


@pytest.fixture
def artwork_brand(tmp_path, monkeypatch):
    from healthvideo.domain import brand

    data = read_yaml(brand.Path("profiles/brand.vi.yaml"))
    artwork = {}
    for pose in ("welcome", "explain", "caution"):
        path = f"assets/brand/mascot/{pose}.png"
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = png_bytes()
        target.write_bytes(content)
        artwork[pose] = {"path": path, "sha256": sha256(content).hexdigest()}
    data["mascot"]["artwork"] = artwork
    monkeypatch.setattr(brand, "REPO_ROOT", tmp_path, raising=False)
    return data, tmp_path
