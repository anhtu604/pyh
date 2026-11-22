import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile, mkdtemp
from typing import Any

import yaml

AGENT_UTF8_RULE = (
    "Mọi tệp kết quả phải giữ nguyên tiếng Việt UTF-8. Dùng công cụ Write/Edit/apply_patch "
    "hoặc tệp Python UTF-8 chạy trực tiếp với open(..., encoding='utf-8'). "
    "Cấm Set-Content, Out-File, shell redirect > và here-string/pipe chứa tiếng Việt "
    "đưa vào Python hay CLI; encoding='utf-8' ở đầu ra không cứu được pipe đã mất dấu. "
    "Không truyền nội dung tiếng Việt qua tham số CLI; nộp bằng tệp. "
    "Nếu buộc dùng PowerShell pipe cho mã Python, chỉ dùng mã ASCII và Unicode escapes. "
    "Đọc lại và kiểm nội dung tiếng Việt trước khi nộp."
)


class AgentEncodingError(ValueError):
    """An agent must resubmit its output without lossy text conversion."""


_URL_RE = re.compile(r'https?://[^\s<>]+')
_LOSSY_WORD_RE = re.compile(r'[A-Za-zÀ-ỹ]+(?:\?+[A-Za-zÀ-ỹ]+)+')


def validate_agent_text(value: Any, location: str = 'result') -> None:
    """Check incoming content only, never rewrite or revalidate historical logs.

    A damaged syllable of at least three characters indicates loss.
    URLs, sentence-final questions and A?B choices remain legal.
    This is a conservative heuristic, not a Vietnamese language detector.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            validate_agent_text(item, f'{location}.{key}')
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            validate_agent_text(item, f'{location}[{index}]')
    elif isinstance(value, str):
        cleaned = _URL_RE.sub('', value)
        words = [word for word in _LOSSY_WORD_RE.findall(cleaned)
                 if not re.fullmatch(r'[A-Z]\?[A-Z]', word)]
        if '\ufffd' in cleaned or any(len(word) >= 3 for word in words):
            raise AgentEncodingError(
                f'Đầu ra agent: văn bản bị mất dấu (mã hóa) tại {location}. '
                "Hãy nộp lại tệp bằng Write/Edit/apply_patch hoặc tệp Python encoding='utf-8'; "
                'không đưa tiếng Việt qua PowerShell pipe/redirect.'
            )


def read_agent_text(path: Path) -> str:
    try:
        text = path.read_text(encoding='utf-8-sig')
    except UnicodeError as exc:
        raise AgentEncodingError(
            f'Đầu ra agent: văn bản bị mất dấu (mã hóa) tại {path.name}; hãy nộp lại UTF-8.'
        ) from exc
    validate_agent_text(text, path.name)
    return text


def read_agent_yaml(path: Path) -> dict[str, Any]:
    """Read a fresh agent submission, rejecting loss before it can be persisted."""
    try:
        data = read_yaml(path)
    except UnicodeError as exc:
        raise AgentEncodingError(
            f'Đầu ra agent: văn bản bị mất dấu (mã hóa) tại {path.name}; hãy nộp lại UTF-8.'
        ) from exc
    validate_agent_text(data, path.name)
    return data


class DirectoryPromotionError(OSError):
    """A replacement failed and the recoverable previous directory was retained."""

    def __init__(
        self,
        promotion_error: Exception,
        restore_error: Exception,
        backup_dir: Path,
    ) -> None:
        super().__init__(
            "Directory promotion failed "
            f"({promotion_error}); restoring the previous directory also failed "
            f"({restore_error}). Recoverable backup retained at: {backup_dir}"
        )
        self.promotion_error = promotion_error
        self.restore_error = restore_error
        self.backup_dir = backup_dir


def read_yaml(path: Path) -> dict[str, Any]:
    raw = ""
    for index, delay in enumerate((0.0, 0.005, 0.015, 0.03)):
        if delay:
            time.sleep(delay)
        try:
            with path.open(encoding="utf-8") as stream:
                raw = stream.read()
            break
        except PermissionError:
            if sys.platform != "win32" or index == 3:
                raise
    data = yaml.safe_load(raw)
    if not isinstance(data, Mapping):
        raise TypeError(f"YAML root must be a mapping: {path}")
    return dict(data)


_WINDOWS_TRANSIENT_REPLACE_ERRORS = frozenset({5, 32})
_REPLACE_RETRY_DELAYS = (0.0, 0.005, 0.015, 0.03, 0.06, 0.15, 0.25, 0.35, 0.5, 0.5)


def _replace_with_retry(source: Path, destination: Path) -> None:
    """Retry transient Windows access/sharing locks during atomic file replacement."""
    for index, delay in enumerate(_REPLACE_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            os.replace(source, destination)
            return
        except PermissionError as error:
            if (
                getattr(error, "winerror", None) not in _WINDOWS_TRANSIENT_REPLACE_ERRORS
                or index == len(_REPLACE_RETRY_DELAYS) - 1
            ):
                raise


def write_text_atomic(path: Path, text: str) -> None:
    """Write UTF-8 text through a sibling temporary file and one rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        _replace_with_retry(temporary_path, path)
        temporary_path = None
        _fsync_directory(path.parent)
    finally:
        if temporary_path is not None:
            for delay in (0.0, 0.01, 0.03):
                if delay:
                    time.sleep(delay)
                try:
                    temporary_path.unlink(missing_ok=True)
                    break
                except PermissionError as error:
                    if getattr(error, "winerror", None) not in _WINDOWS_TRANSIENT_REPLACE_ERRORS:
                        raise


def _fsync_directory(path: Path) -> None:
    """Persist a directory entry where the platform permits directory handles."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_yaml_atomic(path: Path, data: Mapping[str, Any]) -> None:
    write_text_atomic(
        path, yaml.safe_dump(dict(data), allow_unicode=True, sort_keys=False)
    )


def replace_directory_atomic(source_dir: Path, destination_dir: Path) -> None:
    """Publish a staged directory with one rename, replacing what is there.

    ``os.replace`` refuses a non-empty destination directory on Windows, so an
    existing destination is renamed aside first and deleted only once the new
    directory is in place; a failed rename puts the old directory back.
    """
    recover_directory_promotion(destination_dir)
    if not destination_dir.exists():
        os.replace(source_dir, destination_dir)
        return
    superseded = Path(
        mkdtemp(
            prefix=f".{destination_dir.name}.superseded-", dir=destination_dir.parent
        )
    )
    superseded.rmdir()
    os.replace(destination_dir, superseded)
    try:
        os.replace(source_dir, destination_dir)
    except Exception as promotion_error:
        try:
            os.replace(superseded, destination_dir)
        except OSError as restore_error:
            raise DirectoryPromotionError(
                promotion_error, restore_error, superseded
            ) from promotion_error
        raise
    shutil.rmtree(superseded, ignore_errors=True)


def recover_directory_promotion(destination_dir: Path) -> None:
    """Restore the one preserved predecessor after an interrupted promotion."""
    """Restore the one preserved predecessor before attempting a new promotion."""
    if destination_dir.exists():
        return
    backups = sorted(
        destination_dir.parent.glob(f".{destination_dir.name}.superseded-*")
    )
    if not backups:
        return
    if len(backups) != 1:
        raise FileExistsError(
            "Cannot recover missing directory with multiple preserved backups: "
            + ", ".join(str(backup) for backup in backups)
        )
    os.replace(backups[0], destination_dir)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(64 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _hashable_date(value: Any) -> str:
    """Encode YAML dates, and refuse every other value JSON cannot represent.

    Narrow on purpose: a blanket `default=str` would also stringify values with
    no stable text form (a `set` from YAML `!!set` iterates in an order that
    varies with PYTHONHASHSEED), turning "not hashable" into a wrong hash.
    """
    if isinstance(value, datetime.date):  # datetime.datetime is a date subclass
        return str(value)
    raise TypeError(
        f"canonical_json_hash cannot hash {type(value).__name__} deterministically"
    )


def canonical_json_hash(payload: Any) -> str:
    """Hash a payload by meaning: canonical JSON with sorted keys, then SHA-256.

    Dates parsed from YAML are hashed as their string form so a document stays
    hashable without a second scheme; anything else JSON cannot represent
    raises `TypeError` rather than hashing to a value that may not repeat.
    """
    canonical = json.dumps(
        payload,
        default=_hashable_date,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
