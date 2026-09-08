from datetime import UTC, date, datetime

import pytest

from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)


def test_yaml_round_trip_and_hash(tmp_path) -> None:
    path = tmp_path / "project.yaml"

    write_yaml_atomic(path, {"slug": "muoi-va-huyet-ap", "state": "idea"})

    assert read_yaml(path)["state"] == "idea"
    assert len(sha256_file(path)) == 64
    assert not (tmp_path / "project.yaml.tmp").exists()


def test_canonical_json_hash_keeps_dates_deterministic() -> None:
    """YAML dates stay hashable, and hash by their value."""
    published = canonical_json_hash({"published": date(2026, 9, 7)})

    assert published == canonical_json_hash({"published": date(2026, 9, 7)})
    assert published != canonical_json_hash({"published": date(2026, 9, 8)})
    assert len(canonical_json_hash({"at": datetime(2026, 9, 7, 8, 30, tzinfo=UTC)})) == 64


def test_canonical_json_hash_refuses_values_it_cannot_hash_deterministically() -> None:
    """A YAML !!set stringifies in an order that varies with PYTHONHASHSEED."""
    with pytest.raises(TypeError):
        canonical_json_hash({"tags": {"muoi", "huyet-ap"}})
