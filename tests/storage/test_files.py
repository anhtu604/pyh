from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic


def test_yaml_round_trip_and_hash(tmp_path) -> None:
    path = tmp_path / "project.yaml"

    write_yaml_atomic(path, {"slug": "muoi-va-huyet-ap", "state": "idea"})

    assert read_yaml(path)["state"] == "idea"
    assert len(sha256_file(path)) == 64
    assert not (tmp_path / "project.yaml.tmp").exists()
