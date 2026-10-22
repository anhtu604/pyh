import pytest
from pydantic import ValidationError

from healthvideo.domain.posts import (
    ClipCaptions,
    PostSet,
    iter_texts,
    validate_posts,
)

CHAPTERS = ("Mở đầu", "Cơ chế tăng huyết áp", "Khi nào cần đo lại")
SOURCES = ("Tạp chí Tim mạch Việt Nam", "Hướng dẫn ESC về tăng huyết áp")
APPROVED_CLAIMS = {"C01", "C02", "C03.1"}


def _valid_post_set(**overrides: object) -> PostSet:
    data: dict[str, object] = {
        "youtube_titles": [
            "Vì sao tăng huyết áp thường không có triệu chứng?",
            "Huyết áp cao âm thầm làm tổn thương thành mạch thế nào?",
        ],
        "youtube_description": (
            "Tìm hiểu cơ chế tăng huyết áp và cách theo dõi tại nhà.\n"
            "0:00 Mở đầu\n"
            "2:15 Cơ chế tăng huyết áp\n"
            "12:34 Khi nào cần đo lại\n"
            "Giảm ăn mặn giúp hạ trung bình 5 mmHg tâm thu [claim:C01].\n"
            "Nguồn tham khảo:\n"
            "- Tạp chí Tim mạch Việt Nam\n"
            "- Hướng dẫn ESC về tăng huyết áp"
        ),
        "youtube_tags": ["tăng huyết áp", "tim mạch", "sức khỏe"],
        "clip_captions": {
            "CL01": {
                "tiktok": "Huyết áp 140/90 mmHg cần được đo đúng tư thế [claim:C02].",
                "shorts": "Đo huyết áp nghỉ ngơi 5 phút trước khi bấm máy [claim:C02].",
                "reels": "Cơ chế thành mạch chịu áp lực cao kéo dài.",
            }
        },
        "facebook_post": (
            "Nhiều người nghĩ phải đau đầu mới là tăng huyết áp. "
            "Thực tế khoảng 46% người lớn mắc bệnh không hề biết [claim:C03.1]."
        ),
        "youtube_community": "Bạn thường đo huyết áp vào thời điểm nào trong ngày?",
    }
    data.update(overrides)
    return PostSet.model_validate(data)


def test_valid_posts_pass() -> None:
    posts = _valid_post_set()
    errors = validate_posts(
        posts,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=CHAPTERS,
        source_labels=SOURCES,
    )
    assert errors == []


def test_number_without_claim_ref_blocks() -> None:
    posts = _valid_post_set(
        facebook_post=(
            "Nhiều người chủ quan với huyết áp. "
            "Giảm muối giúp hạ 10 mmHg huyết áp tâm thu! "
            "Hãy đo huyết áp định kỳ."
        ),
        clip_captions={
            "CL01": ClipCaptions(
                tiktok="Uống đủ 2 lít nước mỗi ngày.",
                shorts="Đo huyết áp nghỉ ngơi 5 phút trước khi bấm máy [claim:C02].",
                reels="Cơ chế thành mạch chịu áp lực cao kéo dài.",
            )
        },
    )
    errors = validate_posts(
        posts,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=CHAPTERS,
        source_labels=SOURCES,
    )
    assert any(
        err.startswith("facebook_post: câu có số liệu thiếu [claim:…]:")
        and "10 mmHg" in err
        for err in errors
    )
    assert any(
        err.startswith("clip_captions[CL01].tiktok: câu có số liệu thiếu [claim:…]:")
        and "2 lít" in err
        for err in errors
    )


def test_claim_ref_must_be_medically_approved() -> None:
    posts = _valid_post_set(
        youtube_community="Giảm 20% biến cố tim mạch khi kiểm soát tốt [claim:C99]."
    )
    errors = validate_posts(
        posts,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=CHAPTERS,
        source_labels=SOURCES,
    )
    assert errors == ["youtube_community: claim chưa duyệt y khoa: C99"]


def test_chapter_timestamps_not_treated_as_numbers() -> None:
    posts = _valid_post_set(
        youtube_description=(
            "0:00 Mở đầu\n"
            "03:45 Cơ chế tăng huyết áp\n"
            "12:34 Khi nào cần đo lại\n"
            "Nguồn: Tạp chí Tim mạch Việt Nam; Hướng dẫn ESC về tăng huyết áp"
        )
    )
    errors = validate_posts(
        posts,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=CHAPTERS,
        source_labels=SOURCES,
    )
    assert errors == []

    # A timestamp-like number in non-description fields or with extra unreferenced digits still blocks.
    posts_with_unclaimed_number = _valid_post_set(
        youtube_description=(
            "0:00 Mở đầu với 3 lưu ý quan trọng\n"
            "12:34 Cơ chế tăng huyết áp\n"
            "20:00 Khi nào cần đo lại\n"
            "Nguồn: Tạp chí Tim mạch Việt Nam; Hướng dẫn ESC về tăng huyết áp"
        )
    )
    desc_errors = validate_posts(
        posts_with_unclaimed_number,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=CHAPTERS,
        source_labels=SOURCES,
    )
    assert len(desc_errors) == 1
    assert desc_errors[0].startswith(
        "youtube_description: câu có số liệu thiếu [claim:…]:"
    )
    assert "3 lưu ý" in desc_errors[0]


def test_chapter_titles_with_digits_are_not_numbers() -> None:
    posts = _valid_post_set(
        youtube_description=(
            "0:00 Chương 1\n"
            "Nguồn: Tạp chí Tim mạch Việt Nam; Hướng dẫn ESC về tăng huyết áp"
        )
    )
    errors = validate_posts(
        posts,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=["Chương 1"],
        source_labels=SOURCES,
    )
    assert errors == []

    posts_with_unclaimed_stat = _valid_post_set(
        youtube_description=(
            "0:00 Chương 1\n"
            "Chương 1 có 30% người bệnh\n"
            "Nguồn: Tạp chí Tim mạch Việt Nam; Hướng dẫn ESC về tăng huyết áp"
        )
    )
    stat_errors = validate_posts(
        posts_with_unclaimed_stat,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=["Chương 1"],
        source_labels=SOURCES,
    )
    assert len(stat_errors) == 1
    assert stat_errors[0].startswith(
        "youtube_description: câu có số liệu thiếu [claim:…]:"
    )
    assert "Chương 1 có 30% người bệnh" in stat_errors[0]


def test_description_has_chapters_and_sources() -> None:
    posts = _valid_post_set(
        youtube_description=(
            "0:00 Mở đầu\n"
            "2:15 Cơ chế tăng huyết áp\n"
            "Nguồn: Tạp chí Tim mạch Việt Nam"
        )
    )
    errors = validate_posts(
        posts,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=CHAPTERS,
        source_labels=SOURCES,
    )
    assert any("Khi nào cần đo lại" in err for err in errors)
    assert any("Hướng dẫn ESC về tăng huyết áp" in err for err in errors)


def test_title_count_bounds() -> None:
    with pytest.raises(ValidationError):
        _valid_post_set(youtube_titles=["Chỉ một tiêu đề duy nhất"])

    with pytest.raises(ValidationError):
        _valid_post_set(
            youtube_titles=["Tiêu đề A", "Tiêu đề B", "Tiêu đề C", "Tiêu đề D"]
        )

    bypassed_one = PostSet.model_construct(
        schema_version="1.0",
        youtube_titles=["Chỉ một tiêu đề duy nhất"],
        youtube_description=_valid_post_set().youtube_description,
        youtube_tags=["tim mạch"],
        clip_captions={},
        facebook_post="Bài đăng không số liệu.",
        youtube_community="Câu hỏi cộng đồng.",
    )
    errors_one = validate_posts(
        bypassed_one,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=CHAPTERS,
        source_labels=SOURCES,
    )
    assert any(err.startswith("youtube_titles:") for err in errors_one)

    bypassed_four = PostSet.model_construct(
        schema_version="1.0",
        youtube_titles=["Tiêu đề A", "Tiêu đề B", "Tiêu đề C", "Tiêu đề D"],
        youtube_description=_valid_post_set().youtube_description,
        youtube_tags=["tim mạch"],
        clip_captions={},
        facebook_post="Bài đăng không số liệu.",
        youtube_community="Câu hỏi cộng đồng.",
    )
    errors_four = validate_posts(
        bypassed_four,
        approved_claim_ids=APPROVED_CLAIMS,
        chapter_titles=CHAPTERS,
        source_labels=SOURCES,
    )
    assert any(err.startswith("youtube_titles:") for err in errors_four)


def test_vietnamese_text_roundtrip() -> None:
    original = _valid_post_set()
    dumped = original.model_dump(mode="json")
    restored = PostSet.model_validate(dumped)
    assert restored == original
    assert "Vì sao tăng huyết áp thường không có triệu chứng?" in restored.youtube_titles
    assert "Đo huyết áp nghỉ ngơi 5 phút trước khi bấm máy [claim:C02]." == (
        restored.clip_captions["CL01"].shorts
    )
    paths = [path for path, _ in iter_texts(restored)]
    assert "youtube_titles[0]" in paths
    assert "youtube_description" in paths
    assert "youtube_tags[0]" in paths
    assert "clip_captions[CL01].tiktok" in paths
    assert "facebook_post" in paths
    assert "youtube_community" in paths


def test_thumbnail_headline_number_needs_claim():
    def errors(headline, chapters=()):
        posts = _valid_post_set(thumbnail={"headline": headline, "background_prompt": "unlabeled heart", "seed": 7})
        return validate_posts(posts, approved_claim_ids=APPROVED_CLAIMS,
                              chapter_titles=chapters, source_labels=())
    assert any("thumbnail.headline" in e for e in errors("5 điều cần biết"))
    assert errors("5 điều cần biết [claim:C01]") == []
    assert any("C99" in e for e in errors("5 điều [claim:C99]"))
    assert any("thumbnail.headline" in e for e in errors("5 điều cần biết", ("5 điều cần biết",)))
