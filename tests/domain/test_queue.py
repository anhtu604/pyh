from datetime import date

import pytest
from pydantic import ValidationError

from healthvideo.domain.queue import QueueEntry


@pytest.mark.parametrize("bad_slug", ["AB", "co dau", "x" * 81])
def test_bad_slug_rejected(bad_slug: str) -> None:
    with pytest.raises(ValidationError):
        QueueEntry(
            slug=bad_slug,
            title="Ăn mặn và huyết áp",
            question="Ăn mặn ảnh hưởng thế nào đến huyết áp?",
            added=date(2026, 10, 22),
        )
