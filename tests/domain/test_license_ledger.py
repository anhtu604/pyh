import pytest
from pydantic import ValidationError

from healthvideo.domain.license_ledger import LicenseEntry, LicenseLedger


def entry(**changes: object) -> LicenseEntry:
    data = {
        "path": "assets/chart.svg",
        "source": "R01",
        "creator": "operator",
        "license": "explicit-rights",
        "rights_basis": "operator supplied permission",
        "revision": "001",
        "sha256": "a" * 64,
    }
    data.update(changes)
    return LicenseEntry.model_validate(data)


@pytest.mark.parametrize("field", ["source", "creator", "license", "rights_basis"])
def test_provenance_must_be_supplied(field: str) -> None:
    with pytest.raises(ValidationError):
        entry(**{field: " "})


@pytest.mark.parametrize(
    "path", ["../outside.svg", "C:/secret.svg", "/root/x.svg", "assets\\x.svg"]
)
def test_unsafe_path_is_rejected(path: str) -> None:
    with pytest.raises(ValidationError):
        entry(path=path)


def test_duplicate_or_invalid_hash_and_revision_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LicenseLedger(entries=(entry(), entry()))
    with pytest.raises(ValidationError):
        entry(sha256="bad")
    with pytest.raises(ValidationError):
        entry(revision="../")


def test_schema_omits_runtime_configuration() -> None:
    serialized = LicenseLedger(entries=(entry(),)).model_dump(mode="json")
    assert set(serialized["entries"][0]) == {
        "path",
        "source",
        "creator",
        "license",
        "rights_basis",
        "revision",
        "sha256",
    }
