from pathlib import Path

import pytest

from healthvideo.approver_pin import PinError, pin_path, set_pin, verify_pin


def test_verify_after_set(tmp_path: Path) -> None:
    target = tmp_path / "approver-pin.json"
    set_pin("123456", old_pin=None, path=target)

    assert verify_pin("123456", path=target) is True


def test_wrong_pin_rejected(tmp_path: Path) -> None:
    target = tmp_path / "approver-pin.json"
    set_pin("123456", old_pin=None, path=target)

    assert verify_pin("654321", path=target) is False


def test_reset_requires_old_pin(tmp_path: Path) -> None:
    target = tmp_path / "approver-pin.json"
    set_pin("123456", old_pin=None, path=target)

    with pytest.raises(PinError):
        set_pin("654321", old_pin=None, path=target)

    with pytest.raises(PinError):
        set_pin("654321", old_pin="000000", path=target)

    assert verify_pin("123456", path=target) is True

    set_pin("654321", old_pin="123456", path=target)

    assert verify_pin("654321", path=target) is True
    assert verify_pin("123456", path=target) is False


def test_short_pin_rejected(tmp_path: Path) -> None:
    target = tmp_path / "approver-pin.json"

    with pytest.raises(PinError):
        set_pin("12345", old_pin=None, path=target)

    assert not target.exists()


def test_verify_without_pin_file_is_false(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "approver-pin.json"

    assert verify_pin("123456", path=target) is False


def test_corrupt_file_is_false(tmp_path: Path) -> None:
    target = tmp_path / "approver-pin.json"
    target.write_text("{not-valid-json", encoding="utf-8")

    assert verify_pin("123456", path=target) is False

    target.write_text('{"version": 1, "salt": "zz", "hash": "00"}', encoding="utf-8")
    assert verify_pin("123456", path=target) is False


def test_file_never_contains_raw_pin(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "approver-pin.json"
    raw_pin = "doctor-secret-pin-987654"
    set_pin(raw_pin, old_pin=None, path=target)

    content = target.read_text(encoding="utf-8")
    assert raw_pin not in content


def test_pin_path_is_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert pin_path() == tmp_path / ".healthvideo" / "approver-pin.json"
