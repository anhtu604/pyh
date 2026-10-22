from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from healthvideo.domain.queue import QueueEntry, QueueError
from healthvideo.storage.files import read_yaml
from healthvideo.storage.queue import add_to_queue, load_queue, queue_path


def test_add_then_load_roundtrip(tmp_path: Path) -> None:
    entry = QueueEntry(
        slug="an-man-va-huyet-ap",
        title="Ăn mặn và huyết áp cao",
        question="Vì sao ăn mặn làm tăng huyết áp ở người trưởng thành?",
        doctor_note="Nhấn mạnh cơ chế giữ nước và natri.",
        added=date(2026, 10, 22),
    )

    add_to_queue(tmp_path, entry)

    loaded = load_queue(tmp_path)
    assert loaded == [entry]
    raw_text = queue_path(tmp_path).read_text(encoding="utf-8")
    assert "Ăn mặn và huyết áp cao" in raw_text
    assert "Nhấn mạnh cơ chế giữ nước và natri." in raw_text
    raw_yaml = read_yaml(queue_path(tmp_path))
    assert raw_yaml["version"] == 1
    assert raw_yaml["entries"][0]["added"] == "2026-10-22"


def test_duplicate_slug_rejected(tmp_path: Path) -> None:
    first = QueueEntry(
        slug="an-man-va-huyet-ap",
        title="Ăn mặn và huyết áp",
        question="Ăn mặn làm tăng huyết áp như thế nào?",
        added=date(2026, 10, 22),
    )
    duplicate = QueueEntry(
        slug="an-man-va-huyet-ap",
        title="Chủ đề trùng slug",
        question="Câu hỏi khác nhưng trùng slug?",
        added=date(2026, 10, 23),
    )

    add_to_queue(tmp_path, first)
    with pytest.raises(QueueError):
        add_to_queue(tmp_path, duplicate)

    assert load_queue(tmp_path) == [first]


def test_existing_project_slug_rejected(tmp_path: Path) -> None:
    (tmp_path / "projects" / "do-huyet-ap").mkdir(parents=True)
    entry = QueueEntry(
        slug="do-huyet-ap",
        title="Đo huyết áp tại nhà",
        question="Đo huyết áp tại nhà sao cho đúng?",
        added=date(2026, 10, 22),
    )

    with pytest.raises(QueueError):
        add_to_queue(tmp_path, entry)

    assert not queue_path(tmp_path).exists()


def test_missing_queue_file_is_empty(tmp_path: Path) -> None:
    assert load_queue(tmp_path) == []


@pytest.mark.parametrize("bad_slug", ["AB", "co dau", "x" * 81])
def test_bad_slug_rejected(bad_slug: str) -> None:
    with pytest.raises(ValidationError):
        QueueEntry(
            slug=bad_slug,
            title="Ăn mặn và huyết áp",
            question="Ăn mặn ảnh hưởng thế nào đến huyết áp?",
            added=date(2026, 10, 22),
        )


def test_order_preserved(tmp_path: Path) -> None:
    entries = [
        QueueEntry(
            slug="chu-de-mot",
            title="Chủ đề 1",
            question="Câu hỏi 1?",
            added=date(2026, 10, 20),
        ),
        QueueEntry(
            slug="chu-de-hai",
            title="Chủ đề 2",
            question="Câu hỏi 2?",
            added=date(2026, 10, 21),
        ),
        QueueEntry(
            slug="chu-de-ba",
            title="Chủ đề 3",
            question="Câu hỏi 3?",
            added=date(2026, 10, 22),
        ),
    ]

    for entry in entries:
        add_to_queue(tmp_path, entry)

    assert [item.slug for item in load_queue(tmp_path)] == [
        "chu-de-mot",
        "chu-de-hai",
        "chu-de-ba",
    ]
