"""Tests for voice_prep candidate extraction, content cache reuse, and delta context."""

from __future__ import annotations

import time
from pathlib import Path

from healthvideo.domain.pronunciation import PronunciationEntry, PronunciationLexicon
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.pronunciation import apply_pronunciation
from healthvideo.workflows.voice_prep import (
    build_voice_prep_delta_context,
    extract_pronunciation_candidates,
    load_voice_prep_lexicon,
    save_voice_prep,
    try_auto_voice_prep,
    try_reuse_cached_voice_prep,
    voice_prep_ready,
)
from tests.helpers import create_v2_project_fixture


def _lexicon_file(tmp_path: Path, entries: list[dict] | None = None) -> Path:
    path = tmp_path / "pronunciation.vi.yaml"
    write_yaml_atomic(
        path,
        {
            "schema_version": "1.0",
            "language": "vi",
            "version": "3",
            "entries": entries
            if entries is not None
            else [
                {"written": "gout", "spoken": "gút"},
                {"written": "acid uric", "spoken": "a-xít u-ríc"},
            ],
        },
    )
    return path


def test_extract_pronunciation_candidates_filters_base_lexicon_and_plain_vietnamese() -> None:
    base = PronunciationLexicon(
        schema_version="1.0",
        language="vi",
        version="3",
        entries=(
            PronunciationEntry(written="gout", spoken="gút"),
            PronunciationEntry(written="acid uric", spoken="a-xít u-ríc"),
        ),
    )
    script = {
        "schema_version": "1.0",
        "title": "Test",
        "lines": [
            {
                "id": "L01",
                "text": "Men gan tăng không có nghĩa là bạn bị gout hay tăng acid uric ngay.",
            },
            {
                "id": "L02",
                "text": "Xét nghiệm HbA1c < 7% và c-AST trên 140/90 mg/dL, kèm purin.",
            },
            {
                "id": "L03",
                "text": "Ăn nhiều rau xanh và uống đủ nước mỗi ngày để gan khỏe.",
            },
        ],
    }
    res = extract_pronunciation_candidates(script, base)
    terms_cf = {t.casefold() for t in res["terms"]}
    assert "hba1c" in terms_cf
    assert "c-ast" in terms_cf
    assert "mg/dl" in terms_cf
    assert "140/90" in terms_cf
    assert "< 7%" in terms_cf
    assert "purin" in terms_cf
    # Covered by base_lexicon:
    assert "gout" not in terms_cf
    assert "acid" not in terms_cf
    assert "uric" not in terms_cf
    # Plain Vietnamese words/lines excluded:
    assert "men" not in terms_cf
    assert "gan" not in terms_cf
    assert "ngay" not in terms_cf
    assert [row["id"] for row in res["lines"]] == ["L02"]


def test_try_reuse_cached_voice_prep_on_unchanged_terms_and_invalidates_on_lexicon_or_new_term(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path / "projects")
    rev = project_dir / "revisions/001"
    lex_path = _lexicon_file(tmp_path)

    script_path = rev / "script/script.yaml"
    script_data = read_yaml(script_path)
    script_data["lines"] = [
        {"id": "L01", "text": "Chỉ số ALT tăng nhẹ khi tế bào gan tổn thương."},
        {"id": "L02", "text": "Hãy đi khám sớm khi có dấu hiệu bất thường."},
    ]
    write_yaml_atomic(script_path, script_data)

    vp_input = tmp_path / "vp-input.yaml"
    write_yaml_atomic(
        vp_input,
        {
            "schema_version": "1.0",
            "pronunciations": [{"written": "ALT", "spoken": "a-lờ-tê"}],
            "pacing_notes": ["Ngắt nhẹ sau ALT"],
        },
    )
    save_voice_prep(project_dir, vp_input, base_lexicon_path=lex_path)
    assert voice_prep_ready(project_dir)

    cache_path = tmp_path / "topics/logs/muoi-va-huyet-ap/voice-prep-cache.yaml"
    assert cache_path.is_file()
    cache_data = read_yaml(cache_path)
    assert cache_data["base_lexicon_sha256"] == sha256_file(lex_path)

    # 1. Edit plain Vietnamese wording without adding/changing candidate terms -> 100% cache reuse!
    script_data["lines"][1]["text"] = "Bạn nên đi khám sớm để bác sĩ kiểm tra kỹ hơn."
    write_yaml_atomic(script_path, script_data)
    assert not voice_prep_ready(project_dir)

    reused = try_reuse_cached_voice_prep(project_dir, base_lexicon_path=lex_path)
    assert reused == rev / "script/voice-prep.yaml"
    assert voice_prep_ready(project_dir)

    # 2. Introducing a new candidate term invalidates reuse and builds compact delta context.
    script_data["lines"][1]["text"] = "Cần kiểm tra thêm chỉ số HbA1c dưới < 7% và 126 mg/dL."
    write_yaml_atomic(script_path, script_data)
    assert try_reuse_cached_voice_prep(project_dir, base_lexicon_path=lex_path) is None

    delta = build_voice_prep_delta_context(project_dir, base_lexicon_path=lex_path)
    assert delta["mode"] == "delta"
    assert delta["cache_hit"] is False
    assert [row["id"] for row in delta["changed_lines"]] == ["L02"]
    new_terms_cf = {t.casefold() for t in delta["new_terms"]}
    assert {"hba1c", "< 7%", "mg/dl"}.issubset(new_terms_cf)
    assert "alt" not in new_terms_cf
    assert "L01" not in delta["prompt_context"]
    assert "L02" in delta["prompt_context"]

    # 3. Changing pronunciation.vi.yaml SHA-256 invalidates cache even if script is unchanged.
    save_voice_prep(project_dir, vp_input, base_lexicon_path=lex_path)
    assert try_reuse_cached_voice_prep(project_dir, base_lexicon_path=lex_path) is not None
    _lexicon_file(
        tmp_path,
        entries=[
            {"written": "gout", "spoken": "gút"},
            {"written": "acid uric", "spoken": "a-xít u-ríc"},
            {"written": "ALT", "spoken": "a-lờ-tê"},
        ],
    )
    assert try_reuse_cached_voice_prep(project_dir, base_lexicon_path=lex_path) is None
    full_delta = build_voice_prep_delta_context(project_dir, base_lexicon_path=lex_path)
    assert full_delta["mode"] == "full_candidates"


def test_load_voice_prep_lexicon_merges_over_base(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path / "projects")
    rev = project_dir / "revisions/001"
    vp_input = tmp_path / "vp.yaml"
    write_yaml_atomic(
        vp_input,
        {
            "schema_version": "1.0",
            "pronunciations": [{"written": "HbA1c", "spoken": "hát-bê-a-một-xê"}],
        },
    )
    save_voice_prep(project_dir, vp_input)
    base = PronunciationLexicon(
        schema_version="1.0",
        language="vi",
        version="3",
        entries=(PronunciationEntry(written="gout", spoken="gút"),),
    )
    merged = load_voice_prep_lexicon(rev, base)
    assert apply_pronunciation("HbA1c và gout", merged) == "hát-bê-a-một-xê và gút"


def test_scanner_catches_percentages_and_non_vi_orthography_but_skips_plain_vi() -> None:
    base = PronunciationLexicon(
        schema_version="1.0",
        language="vi",
        version="3",
        entries=(
            PronunciationEntry(written="gout", spoken="gút", needs_doctor_review=False),
            PronunciationEntry(written="enzyme", spoken="en-zim", needs_doctor_review=True),
        ),
    )
    script = {
        "schema_version": "1.0",
        "title": "Test",
        "lines": [
            {
                "id": "L01",
                "text": "Gan, men, giêng, giường, quốc, quyết, nghiêng, chuyển, khuya, khoeo 2024.",
            },
            {
                "id": "L02",
                "text": "Nguy cơ liên quan gen, gout, enzyme, giảm 20% và sốt 37°C.",
            },
        ],
    }
    res = extract_pronunciation_candidates(script, base)
    terms_cf = {t.casefold() for t in res["terms"]}
    assert {"gen", "enzyme", "20%", "37°c"} <= terms_cf
    # Confirmed dictionary entry is excluded; pending needs_doctor_review entry stays candidate.
    assert "gout" not in terms_cf
    assert [row["written"] for row in res["needs_doctor_review_terms"]] == ["enzyme"]
    assert [row["id"] for row in res["lines"]] == ["L02"]


def test_try_auto_voice_prep_zero_token_fast_path_and_delta_fallback(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path / "projects")
    rev = project_dir / "revisions/001"
    lex_path = _lexicon_file(
        tmp_path,
        entries=[
            {"written": "gout", "spoken": "gút", "needs_doctor_review": False},
            {"written": "ALT", "spoken": "a-lờ-tê", "needs_doctor_review": False},
            {"written": "enzyme", "spoken": "en-zim", "needs_doctor_review": True},
        ],
    )

    # Case 1: 100% terms covered by confirmed lexicon entries + plain Vietnamese -> 0-token auto-gen!
    script_path = rev / "script/script.yaml"
    script_data = read_yaml(script_path)
    script_data["lines"] = [
        {"id": "L01", "text": "Chỉ số ALT tăng nhẹ khi gan quá tải và dễ gặp ở người bị gout."},
        {"id": "L02", "text": "Uống đủ nước mỗi ngày 2 lần để hỗ trợ chuyển hóa tự nhiên."},
    ]
    write_yaml_atomic(script_path, script_data)
    assert not voice_prep_ready(project_dir)

    t0 = time.perf_counter()
    auto_path = try_auto_voice_prep(project_dir, base_lexicon_path=lex_path)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert auto_path == rev / "script/voice-prep.yaml"
    assert elapsed_ms < 250  # deterministic fast-path well under budget
    assert voice_prep_ready(project_dir)
    saved_vp = read_yaml(auto_path)
    assert saved_vp["pronunciations"] == []
    assert "0-token" in saved_vp["notes"]

    # Case 2: needs_doctor_review=True term -> fast-path returns None and builds compact delta context.
    script_data["lines"].append({"id": "L03", "text": "Cơ thể cần enzyme để tiêu hóa thức ăn."})
    write_yaml_atomic(script_path, script_data)
    assert try_auto_voice_prep(project_dir, base_lexicon_path=lex_path) is None

    delta = build_voice_prep_delta_context(project_dir, base_lexicon_path=lex_path)
    assert delta["new_terms"] == ["enzyme"]
    assert [row["id"] for row in delta["changed_lines"]] == ["L03"]
    assert [row["written"] for row in delta["needs_doctor_review_terms"]] == ["enzyme"]
    assert "L01" not in delta["prompt_context"]
    assert "L02" not in delta["prompt_context"]
    assert "L03" in delta["prompt_context"]

    # Case 3: Corrupt '?' lossy cache is rejected safely.
    cache_path = tmp_path / "topics/logs/muoi-va-huyet-ap/voice-prep-cache.yaml"
    cache_data = read_yaml(cache_path)
    cache_data["sheet"]["notes"] = "Ti?ng Vi?t m?t d?u"
    write_yaml_atomic(cache_path, cache_data)
    assert try_reuse_cached_voice_prep(project_dir, base_lexicon_path=lex_path) is None
