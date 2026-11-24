"""Pre-TTS Vietnamese medical pronunciation & pacing prep (`voice_prep`)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.pronunciation import PronunciationEntry, PronunciationLexicon
from healthvideo.domain.script import Script
from healthvideo.storage.files import (
    AgentEncodingError,
    canonical_json_hash,
    read_agent_yaml,
    read_yaml,
    sha256_file,
    validate_agent_text,
    write_yaml_atomic,
)
from healthvideo.storage.revision_lock import revision_lock
from healthvideo.tts import pronunciation as pronunciation_module
from healthvideo.tts.pronunciation import load_pronunciation_lexicon, pronunciation_hash
from healthvideo.workflows.draft import _project

VOICE_PREP_ARTIFACT = "script/voice-prep.yaml"
VOICE_PREP_CACHE_FILENAME = "voice-prep-cache.yaml"

_VI_DIACRITICS = frozenset(
    "ăâđêôơưĂÂĐÊÔƠƯ"
    "àáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
    "òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
    "ÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊ"
    "ÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ"
)
_VI_RHYME = (
    r"(?:ieu|yeu|uoi|uou|oai|oay|uay|uya|uye|oeo|"
    r"ia|ie|iu|oa|oe|oi|oo|ua|ue|ui|uo|uu|uy|ai|ao|au|ay|eo|eu|ye|[aeiouy])"
)
_VI_CODA = r"(?:ch|ng|nh|[cmnpt])?"
_VI_PLAIN_SYLLABLE_RE = re.compile(
    rf"^(?:(?:ngh|gh)[eiy]{_VI_CODA}"
    rf"|k[eiy]{_VI_CODA}"
    rf"|qu[aeioy][a-z]*{_VI_CODA}"
    rf"|gi(?:[aeouy][a-z]*{_VI_CODA}|{_VI_CODA})"
    rf"|(?:ng|g|c)[aou][a-z]*{_VI_CODA}"
    rf"|(?:nh|ch|kh|ph|th|tr|[bdhlmnprstvx])?{_VI_RHYME}{_VI_CODA})$"
)
_UNIT_OR_NUMERIC_RE = re.compile(
    r"(?:<=|>=|≤|≥|<|>)\s*\d+(?:[.,]\d+)?(?:\s*[%°]|[A-Za-zµμ/]+)?"
    r"|(?<!\w)\d+(?:[.,]\d+)?\s*[–-]\s*\d+(?:[.,]\d+)?(?:\s*%)?"
    r"|(?<!\w)\d+(?:[.,]\d+)?\s*/\s*\d+(?:[.,]\d+)?"
    r"|(?<!\w)\d+(?:[.,]\d+)?\s*(?:%|°[CF]?)(?!\w)"
    r"|(?<!\w)[A-Za-zµμ]+(?:/[A-Za-zµμ]+)+(?!\w)"
    r"|(?<!\w)(?:µg|μg|mg|kg|g|mL|ml|mmol|mol|mmHg|cm|mm|kcal|IU)(?!\w)"
)
_HYPHEN_TECH_RE = re.compile(
    r"(?<!\w)[A-Za-z0-9α-ωΑ-Ωµμ]+(?:-[A-Za-z0-9α-ωΑ-Ωβµμ]+)+(?!\w)"
)
_SINGLE_LETTER_AFTER_TAG_RE = re.compile(
    r"\b(?:vitamin|gan|nhóm|týp|type)\s+([A-HK])\b",
    re.IGNORECASE,
)
_WORD_TOKEN_RE = re.compile(r"(?<!\w)[A-Za-zÀ-ỹα-ωΑ-Ωµμ0-9]+(?!\w)")


class VoicePrepSheet(BaseModel):
    """Per-project pronunciation extensions and delivery pacing notes before TTS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    script_hash: str = ""
    pronunciations: tuple[PronunciationEntry, ...] = ()
    pacing_notes: tuple[str | dict[str, Any], ...] = ()
    notes: str = Field(default="")

    @model_validator(mode="after")
    def _unique_written(self) -> VoicePrepSheet:
        seen: set[str] = set()
        for entry in self.pronunciations:
            key = entry.written.strip().casefold()
            if key in seen:
                raise ValueError(f"duplicate voice_prep pronunciation term: {entry.written}")
            seen.add(key)
        return self


def _resolve_workspace_root(project_dir: Path, root: Path | None = None) -> Path:
    if root is not None:
        return root
    return project_dir.parent.parent if project_dir.parent.name == "projects" else project_dir.parent


def _resolve_lexicon_and_hash(
    base_lexicon: PronunciationLexicon | None = None,
    base_lexicon_path: Path | None = None,
) -> tuple[PronunciationLexicon, str]:
    if base_lexicon is not None:
        if base_lexicon_path is not None and base_lexicon_path.is_file():
            return base_lexicon, sha256_file(base_lexicon_path)
        return base_lexicon, pronunciation_hash(base_lexicon)
    path = base_lexicon_path or pronunciation_module.PRONUNCIATION_PROFILE_PATH
    if path.is_file():
        return load_pronunciation_lexicon(path), sha256_file(path)
    empty = PronunciationLexicon(schema_version="1.0", language="vi", version="0", entries=())
    return empty, pronunciation_hash(empty)


def _current_script_hash(revision: Path) -> str:
    script_path = revision / "script/script.yaml"
    if not script_path.is_file():
        raise ValueError("voice_prep requires script/script.yaml")
    data = read_yaml(script_path)
    Script.model_validate(data)
    return canonical_json_hash(data)


def _load_script(revision: Path) -> tuple[Script, str]:
    script_path = revision / "script/script.yaml"
    if not script_path.is_file():
        raise ValueError("voice_prep requires script/script.yaml")
    data = read_yaml(script_path)
    return Script.model_validate(data), canonical_json_hash(data)


def _mask_span(chars: list[str], start: int, end: int) -> None:
    for idx in range(start, end):
        chars[idx] = " "


def _looks_like_candidate_word(token: str) -> bool:
    if not token:
        return False
    if token.isdigit():
        return False
    if any(ch.isdigit() for ch in token):
        return True
    if any(ch in {"µ", "μ", "α", "β", "γ", "δ"} for ch in token):
        return True
    if any(ch in _VI_DIACRITICS for ch in token):
        return False
    if not token.isascii() or not token.isalpha():
        return True
    if len(token) >= 2 and (token.isupper() or any(ch.isupper() for ch in token[1:])):
        return True
    if len(token) == 1:
        return False
    lowered = token.lower()
    if any(ch in {"f", "j", "w", "z"} for ch in lowered):
        return True
    # Strict Vietnamese orthography check prevents multi-vowel non-VI words from slipping past.
    if not _VI_PLAIN_SYLLABLE_RE.match(lowered):
        return True
    if lowered.startswith(('ch', 'gh', 'ngh')):
        return False
    # Disallow invalid `qu`/`gi`/`c`/`g`/`ng` internal clusters caught by `[a-z]*` above.
    rhyme_part = lowered
    for onset in ("ngh", "qu", "gi", "ng", "c", "g"):
        if lowered.startswith(onset):
            rhyme_part = lowered[len(onset):]
            break
    if lowered.startswith(("qu", "gi", "ng", "c", "g")) and rhyme_part:
        if lowered.startswith("gi"):
            return not bool(re.fullmatch(rf"(?:{_VI_RHYME})?{_VI_CODA}", rhyme_part))
        return not bool(re.fullmatch(rf"{_VI_RHYME}{_VI_CODA}", rhyme_part))
    return False


def _scan_line_candidates(text: str, base_pattern: re.Pattern[str] | None) -> list[str]:
    chars = list(text)
    if base_pattern is not None:
        for match in base_pattern.finditer(text):
            _mask_span(chars, match.start(), match.end())

    found: list[str] = []
    seen_cf: set[str] = set()

    def _record(raw_term: str) -> None:
        term = " ".join(raw_term.strip().split())
        if not term:
            return
        cf = term.casefold()
        if cf not in seen_cf:
            seen_cf.add(cf)
            found.append(term)

    masked = "".join(chars)
    for match in _UNIT_OR_NUMERIC_RE.finditer(masked):
        _record(match.group(0))
        _mask_span(chars, match.start(), match.end())

    masked = "".join(chars)
    for match in _HYPHEN_TECH_RE.finditer(masked):
        token = match.group(0)
        if not token.replace("-", "").isdigit():
            _record(token)
            _mask_span(chars, match.start(), match.end())

    masked = "".join(chars)
    for match in _SINGLE_LETTER_AFTER_TAG_RE.finditer(masked):
        letter = match.group(1)
        if letter.isupper():
            _record(letter)
            _mask_span(chars, match.start(1), match.end(1))

    masked = "".join(chars)
    for match in _WORD_TOKEN_RE.finditer(masked):
        token = match.group(0)
        if _looks_like_candidate_word(token):
            _record(token)

    return found


def extract_pronunciation_candidates(
    script: Script | Mapping[str, Any],
    base_lexicon: PronunciationLexicon | None = None,
) -> dict[str, Any]:
    """Extract pronunciation-sensitive terms and candidate lines absent from confirmed ``base_lexicon``."""
    validated_script = script if isinstance(script, Script) else Script.model_validate(dict(script))
    lexicon, lexicon_sha256 = _resolve_lexicon_and_hash(base_lexicon)

    confirmed_entries = [entry for entry in lexicon.entries if not entry.needs_doctor_review]
    review_pending_by_cf = {
        entry.written.strip().casefold(): entry
        for entry in lexicon.entries
        if entry.needs_doctor_review
    }

    base_pattern: re.Pattern[str] | None = None
    if confirmed_entries:
        choices = sorted(confirmed_entries, key=lambda entry: -len(entry.written))
        base_pattern = re.compile(
            r"(?<!\w)(?:" + "|".join(re.escape(e.written) for e in choices) + r")(?!\w)",
            flags=re.IGNORECASE | re.UNICODE,
        )

    canonical_by_cf: dict[str, str] = {}
    by_term_lines: dict[str, list[str]] = {}
    candidate_lines: list[dict[str, Any]] = []
    all_lines: list[dict[str, Any]] = []

    for line in validated_script.lines:
        clean_text = line.tts_text(expressive=False)
        line_terms = _scan_line_candidates(clean_text, base_pattern)
        normalized_terms: list[str] = []
        for term in line_terms:
            cf = term.casefold()
            canonical = canonical_by_cf.setdefault(cf, term)
            if canonical not in normalized_terms:
                normalized_terms.append(canonical)
            line_list = by_term_lines.setdefault(canonical, [])
            if line.id not in line_list:
                line_list.append(line.id)

        line_record = {
            "id": line.id,
            "text": clean_text,
            "line_hash": canonical_json_hash({"text": clean_text, "terms": [t.casefold() for t in normalized_terms]}),
            "terms": normalized_terms,
        }
        all_lines.append(line_record)
        if normalized_terms:
            candidate_lines.append(line_record)

    sorted_terms = sorted(canonical_by_cf.values(), key=str.casefold)
    sorted_by_term = {term: by_term_lines[term] for term in sorted_terms}
    needs_doctor_review_terms = [
        {
            "written": review_pending_by_cf[term.casefold()].written,
            "spoken": review_pending_by_cf[term.casefold()].spoken,
            "note": review_pending_by_cf[term.casefold()].note,
        }
        for term in sorted_terms
        if term.casefold() in review_pending_by_cf
    ]
    term_set_hash = canonical_json_hash([term.casefold() for term in sorted_terms])
    candidates_hash = canonical_json_hash({
        "terms": [term.casefold() for term in sorted_terms],
        "lines": [
            {"id": row["id"], "line_hash": row["line_hash"], "terms": [t.casefold() for t in row["terms"]]}
            for row in candidate_lines
        ],
    })
    return {
        "terms": sorted_terms,
        "by_term": sorted_by_term,
        "lines": candidate_lines,
        "all_lines": all_lines,
        "needs_doctor_review_terms": needs_doctor_review_terms,
        "term_set_hash": term_set_hash,
        "candidates_hash": candidates_hash,
        "base_lexicon_sha256": lexicon_sha256,
    }


def _cache_file_path(project_dir: Path, slug: str, *, root: Path | None = None) -> Path:
    return _resolve_workspace_root(project_dir, root) / "topics" / "logs" / slug / VOICE_PREP_CACHE_FILENAME


def _write_voice_prep_cache(
    cache_path: Path,
    *,
    slug: str,
    script_hash: str,
    base_lexicon_sha256: str,
    candidates: Mapping[str, Any],
    sheet: VoicePrepSheet,
) -> None:
    payload = {
        "version": 1,
        "slug": slug,
        "script_hash": script_hash,
        "base_lexicon_sha256": base_lexicon_sha256,
        "term_set_hash": candidates["term_set_hash"],
        "candidates_hash": candidates["candidates_hash"],
        "candidate_terms": list(candidates["terms"]),
        "lines": list(candidates["lines"]),
        "all_lines": list(candidates["all_lines"]),
        "sheet": sheet.model_dump(mode="json"),
    }
    write_yaml_atomic(cache_path, payload)


def _read_valid_cache(cache_path: Path) -> tuple[dict[str, Any], VoicePrepSheet] | None:
    if not cache_path.is_file():
        return None
    try:
        data = read_yaml(cache_path)
        if data.get("version") != 1:
            return None
        validate_agent_text(data, cache_path.name)
        sheet = VoicePrepSheet.model_validate(data.get("sheet"))
    except (AgentEncodingError, OSError, TypeError, ValueError):
        return None
    return data, sheet


def save_voice_prep(
    project_dir: Path,
    file_path: Path,
    *,
    root: Path | None = None,
    base_lexicon: PronunciationLexicon | None = None,
    base_lexicon_path: Path | None = None,
) -> Path:
    """Validate and save ``script/voice-prep.yaml`` stamped to current script_hash and cache it."""
    project = _project(project_dir)
    revision = project_dir / "revisions" / project.active_revision
    with revision_lock(revision):
        script, script_hash = _load_script(revision)
        sheet = VoicePrepSheet.model_validate(read_agent_yaml(file_path)).model_copy(
            update={"script_hash": script_hash}
        )
        target = revision / VOICE_PREP_ARTIFACT
        target.parent.mkdir(parents=True, exist_ok=True)
        write_yaml_atomic(target, sheet.model_dump(mode="json"))

        lexicon, lexicon_sha256 = _resolve_lexicon_and_hash(base_lexicon, base_lexicon_path)
        candidates = extract_pronunciation_candidates(script, lexicon)
        cache_path = _cache_file_path(project_dir, project.slug, root=root)
        _write_voice_prep_cache(
            cache_path,
            slug=project.slug,
            script_hash=script_hash,
            base_lexicon_sha256=lexicon_sha256,
            candidates=candidates,
            sheet=sheet,
        )
        if pronunciation_gate_active(revision):
            require_doctor_pronunciations(_resolve_workspace_root(project_dir, root), project.slug, script, lexicon)
        return target


def try_reuse_cached_voice_prep(
    project_dir: Path,
    *,
    root: Path | None = None,
    base_lexicon: PronunciationLexicon | None = None,
    base_lexicon_path: Path | None = None,
) -> Path | None:
    """Reuse cached voice-prep and stamp the new ``script_hash`` when candidate terms are 100% unchanged."""
    project = _project(project_dir)
    revision = project_dir / "revisions" / project.active_revision
    cache_path = _cache_file_path(project_dir, project.slug, root=root)
    loaded = _read_valid_cache(cache_path)
    if loaded is None:
        return None
    cache, cached_sheet = loaded

    lexicon, lexicon_sha256 = _resolve_lexicon_and_hash(base_lexicon, base_lexicon_path)
    if cache.get("base_lexicon_sha256") != lexicon_sha256:
        return None

    with revision_lock(revision):
        script, script_hash = _load_script(revision)
        current_candidates = extract_pronunciation_candidates(script, lexicon)
        cached_terms_cf = {
            str(term).strip().casefold()
            for term in (cache.get("candidate_terms") or [])
            if str(term).strip()
        }
        current_terms_cf = {
            str(term).strip().casefold()
            for term in current_candidates["terms"]
            if str(term).strip()
        }
        if not current_terms_cf.issubset(cached_terms_cf):
            return None

        reused_sheet = cached_sheet.model_copy(update={"script_hash": script_hash})
        target = revision / VOICE_PREP_ARTIFACT
        target.parent.mkdir(parents=True, exist_ok=True)
        write_yaml_atomic(target, reused_sheet.model_dump(mode="json"))
        _write_voice_prep_cache(
            cache_path,
            slug=project.slug,
            script_hash=script_hash,
            base_lexicon_sha256=lexicon_sha256,
            candidates=current_candidates,
            sheet=reused_sheet,
        )
        return target


def try_auto_voice_prep(
    project_dir: Path,
    *,
    root: Path | None = None,
    base_lexicon: PronunciationLexicon | None = None,
    base_lexicon_path: Path | None = None,
) -> Path | None:
    """Zero-token Python fast-path for ``voice_prep``.

    Reuses a valid cache when 100% of candidate terms are covered, or directly generates
    ``script/voice-prep.yaml`` when 100% of suspicious terms are already confirmed in
    ``profiles/pronunciation.vi.yaml`` (``needs_doctor_review=False``). Returns ``None``
    only when unknown or unconfirmed terms require LLM/agent review.
    """
    reused = try_reuse_cached_voice_prep(
        project_dir,
        root=root,
        base_lexicon=base_lexicon,
        base_lexicon_path=base_lexicon_path,
    )
    if reused is not None:
        return reused

    project = _project(project_dir)
    revision = project_dir / "revisions" / project.active_revision
    lexicon, lexicon_sha256 = _resolve_lexicon_and_hash(base_lexicon, base_lexicon_path)
    with revision_lock(revision):
        script, script_hash = _load_script(revision)
        current_candidates = extract_pronunciation_candidates(script, lexicon)
        if current_candidates["terms"]:
            return None

        sheet = VoicePrepSheet(
            schema_version="1.0",
            script_hash=script_hash,
            pronunciations=(),
            pacing_notes=(),
            notes="0-token Python fast-path: 100% thuật ngữ đã có trong từ điển chuẩn.",
        )
        target = revision / VOICE_PREP_ARTIFACT
        target.parent.mkdir(parents=True, exist_ok=True)
        write_yaml_atomic(target, sheet.model_dump(mode="json"))
        cache_path = _cache_file_path(project_dir, project.slug, root=root)
        _write_voice_prep_cache(
            cache_path,
            slug=project.slug,
            script_hash=script_hash,
            base_lexicon_sha256=lexicon_sha256,
            candidates=current_candidates,
            sheet=sheet,
        )
        return target


def build_voice_prep_delta_context(
    project_dir: Path,
    *,
    root: Path | None = None,
    base_lexicon: PronunciationLexicon | None = None,
    base_lexicon_path: Path | None = None,
) -> dict[str, Any]:
    """Build a compact prompt payload containing only changed lines and newly seen candidate terms."""
    project = _project(project_dir)
    revision = project_dir / "revisions" / project.active_revision
    script, script_hash = _load_script(revision)
    lexicon, lexicon_sha256 = _resolve_lexicon_and_hash(base_lexicon, base_lexicon_path)
    current = extract_pronunciation_candidates(script, lexicon)

    cache_path = _cache_file_path(project_dir, project.slug, root=root)
    loaded = _read_valid_cache(cache_path)
    cache_usable = loaded is not None and loaded[0].get("base_lexicon_sha256") == lexicon_sha256

    if cache_usable:
        assert loaded is not None
        cache, cached_sheet = loaded
        cached_terms_cf = {
            str(term).strip().casefold()
            for term in (cache.get("candidate_terms") or [])
            if str(term).strip()
        }
        cached_line_hashes = {
            str(row["id"]): str(row["line_hash"])
            for row in (cache.get("all_lines") or [])
            if isinstance(row, Mapping) and row.get("id") and row.get("line_hash")
        }
        new_terms = [
            term for term in current["terms"]
            if term.strip().casefold() not in cached_terms_cf
        ]
        new_terms_cf = {term.strip().casefold() for term in new_terms}
        changed_lines = [
            row for row in current["all_lines"]
            if row["terms"]
            and (
                any(term.strip().casefold() in new_terms_cf for term in row["terms"])
                or cached_line_hashes.get(row["id"]) != row["line_hash"]
            )
        ]
        cached_pronunciations = [
            entry.model_dump(mode="json") for entry in cached_sheet.pronunciations
        ]
        mode = "reuse" if not new_terms else "delta"
    else:
        new_terms = list(current["terms"])
        changed_lines = list(current["lines"])
        cached_pronunciations = []
        mode = "full_candidates"

    lines_block = "\n".join(
        f"- {row['id']} [{', '.join(row['terms'])}]: {row['text']}"
        for row in changed_lines
    ) or "(không có dòng thay đổi chứa thuật ngữ mới)"
    cached_block = "\n".join(
        f"- {entry['written']} -> {entry['spoken']}"
        for entry in cached_pronunciations
    ) or "(chưa có mục cache)"
    new_terms_cf = {term.strip().casefold() for term in new_terms}
    pending_review = [
        item for item in current.get("needs_doctor_review_terms", [])
        if item["written"].strip().casefold() in new_terms_cf
    ]
    pending_block = "\n".join(
        f"- {item['written']} -> {item['spoken']} ({item['note'] or 'needs_doctor_review'})"
        for item in pending_review
    ) or "(không có)"
    prompt_context = (
        f"mode: {mode}\n"
        f"script_hash: {script_hash}\n"
        f"base_lexicon_sha256: {lexicon_sha256}\n"
        f"new_terms: {new_terms}\n"
        f"needs_doctor_review_terms:\n{pending_block}\n"
        f"changed_lines:\n{lines_block}\n"
        f"cached_pronunciations:\n{cached_block}\n"
    )
    return {
        "mode": mode,
        "cache_hit": cache_usable and mode == "reuse",
        "script_hash": script_hash,
        "base_lexicon_sha256": lexicon_sha256,
        "new_terms": new_terms,
        "needs_doctor_review_terms": pending_review,
        "changed_lines": changed_lines,
        "cached_pronunciations": cached_pronunciations,
        "total_script_lines": len(script.lines),
        "prompt_context": prompt_context,
    }


def voice_prep_ready(project_dir: Path) -> bool:
    """Return True when active revision has a valid voice-prep sheet for the current script."""
    if not (project_dir / "project.yaml").is_file():
        return False
    try:
        project = _project(project_dir)
        revision = project_dir / "revisions" / project.active_revision
        script_hash = _current_script_hash(revision)
        target = revision / VOICE_PREP_ARTIFACT
        if not target.is_file():
            return False
        sheet = VoicePrepSheet.model_validate(read_yaml(target))
    except (OSError, TypeError, ValueError):
        return False
    ready = sheet.script_hash == script_hash
    if ready and project.state.value == 'draft_ready':
        # Factory submissions call the workflow directly, so cover cached sheets
        # at the existing voice-prep readiness boundary as well as the CLI.
        check_before_medical(project_dir)
    return ready


def load_voice_prep_lexicon(
    revision: Path, base_lexicon: PronunciationLexicon
) -> PronunciationLexicon:
    """Merge project ``script/voice-prep.yaml`` entries atop the shared base lexicon."""
    if pronunciation_gate_active(revision):
        # R5 can speak only shared doctor choices. A local agent sheet is a
        # proposal, not approval; retain the legacy merge below unchanged.
        return base_lexicon
    target = revision / VOICE_PREP_ARTIFACT
    if not target.is_file():
        return base_lexicon
    sheet = VoicePrepSheet.model_validate(read_yaml(target))
    if not sheet.pronunciations:
        return base_lexicon
    merged: list[PronunciationEntry] = list(base_lexicon.entries)
    index_by_key = {entry.written.strip().casefold(): idx for idx, entry in enumerate(merged)}
    for entry in sheet.pronunciations:
        key = entry.written.strip().casefold()
        if key in index_by_key:
            merged[index_by_key[key]] = entry
        else:
            index_by_key[key] = len(merged)
            merged.append(entry)
    return PronunciationLexicon(
        schema_version=base_lexicon.schema_version,
        language=base_lexicon.language,
        version=f"{base_lexicon.version}+voiceprep",
        entries=tuple(merged),
    )


def require_doctor_pronunciations(
    root: Path, slug: str, script: Script, base_lexicon: PronunciationLexicon,
) -> bool:
    """Open one waiting marker for all unconfirmed terms; never approve agent proposals."""
    from healthvideo.workflows import doctor_questions

    candidates = narration_pronunciation_candidates(script, base_lexicon)
    if not candidates['terms']:
        return doctor_questions.open_question(root, slug) is None
    if doctor_questions.open_question(root, slug) is not None:
        return False
    letters = dict(zip(
        'abcdefghijklmnopqrstuvwxyz0123456789',
        ('a', 'bê', 'xê', 'đê', 'e', 'ép', 'giê', 'hát', 'i', 'giây', 'ca', 'e lờ',
         'em', 'en', 'o', 'pê', 'quy', 'e rờ', 'ét', 'tê', 'u', 'vê', 'vê kép',
         'ích', 'i dài', 'dét', 'không', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu',
         'bảy', 'tám', 'chín'), strict=True,
    ))
    pending = {e.written.casefold(): e.spoken for e in base_lexicon.entries if e.needs_doctor_review}
    terms = []
    for term in candidates['terms']:
        row = next(row for row in candidates['lines'] if term in row['terms'])
        text = row['text']
        at = text.casefold().find(term.casefold())
        excerpt = text[max(0, at - 60):at + len(term) + 60]
        spelling = ' '.join(letters.get(ch.lower(), ch) for ch in term if ch != '-')
        joined = pending.get(term.casefold(), term.lower().replace('-', ' '))
        terms.append({'written': term, 'context': excerpt, 'options': [spelling, joined]})
    doctor_questions.ask(
        root, slug, station='09', kind='pronunciation',
        question='Bác sĩ chọn cách đọc từng từ dưới đây trước khi xưởng đọc giọng.',
        context=[{'code': t['written'], 'summary': t['context']} for t in terms],
        options=[{'id': 'spelling', 'label': 'Đánh vần tất cả'}, {'id': 'joined', 'label': 'Đọc liền tất cả'}],
        allow_free_text=True, pronunciation_terms=terms,
    )
    return False


def check_before_medical(project_dir: Path) -> bool:
    """Ask before submission so the unchanged medical gate hashes the doctor's choices."""
    project = _project(project_dir)
    revision = project_dir / 'revisions' / project.active_revision
    if not pronunciation_gate_active(revision):
        return True
    script, _ = _load_script(revision)
    lexicon = load_pronunciation_lexicon(pronunciation_module.PRONUNCIATION_PROFILE_PATH)
    return require_doctor_pronunciations(_resolve_workspace_root(project_dir), project.slug, script, lexicon)


def pronunciation_gate_active(revision: Path) -> bool:
    path = revision / 'storyboard/storyboard.yaml'
    return path.is_file() and read_yaml(path).get('quality_profile') == 'r5_v1'


# Bác sĩ 2026-11-25: không hỏi phần trăm đơn ("25%") và "video" — đọc thường đã đúng.
_GATE_SKIP_RE = re.compile(r"(?<![\w<>≤≥–/-])\d+(?:[.,]\d+)?\s*%(?!\w)|(?<!\w)video(?!\w)", re.IGNORECASE)


def narration_pronunciation_candidates(script: Script, lexicon: PronunciationLexicon) -> dict[str, Any]:
    """Scan only line.tts_text after confirmed replacements; never storyboard/metadata.

    Confirmed spoken forms are masked too: syllable separators in an approved
    reading are not new foreign terms requiring a second approval.
    """
    confirmed = lexicon.model_copy(update={'entries': tuple(e for e in lexicon.entries if not e.needs_doctor_review)})
    spoken_entries = list(confirmed.entries)
    known = {e.written.casefold() for e in spoken_entries}
    for entry in confirmed.entries:
        if entry.spoken.casefold() not in known:
            spoken_entries.append(PronunciationEntry(written=entry.spoken, spoken=entry.spoken))
            known.add(entry.spoken.casefold())
    masked = confirmed.model_copy(update={'entries': tuple(spoken_entries)})
    lines = [line.model_copy(update={
        'text': _GATE_SKIP_RE.sub(' ', pronunciation_module.apply_pronunciation(
            line.tts_text(expressive=False), confirmed)),
        'delivery': None,
    }) for line in script.lines]
    return extract_pronunciation_candidates(script.model_copy(update={'lines': lines}), masked)
