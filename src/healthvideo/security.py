"""Deterministic, read-only checks for project data that may leave the machine."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from healthvideo.domain.gate_review import GateKind
from healthvideo.storage.backup import is_link_or_reparse
from healthvideo.workflows.backup import is_backup_excluded, validate_project_tree

_SENSITIVE_KEYS = re.compile(
    r"(?:access[_-]?token|api[_-]?key|client[_-]?secret|password|private[_-]?key|"
    r"authorization|raw[_-]?(?:provider[_-]?)?response|cloud[_-]?project[_-]?id|"
    r"(?:^|[_-])(?:token|secret)$)",
    re.IGNORECASE,
)
_RISKY_SUFFIXES = {".mp3", ".mp4", ".wav", ".mov", ".pem", ".key", ".p12", ".pfx", ".safetensors", ".onnx", ".gguf"}
_RISKY_PARTS = {"audio", "renders", "cache", "source-cache", "source-documents", ".healthvideo"}


@dataclass(frozen=True, order=True)
class AuditFinding:
    rule_id: str
    relative_path: str
    reason: str
    remediation: str


def _safe_path(relative: str) -> str:
    return "".join(char if char.isprintable() and char not in "\r\n\t" else "?" for char in relative)


def _entries(root: Path) -> tuple[list[Path], list[AuditFinding]]:
    files: list[Path] = []
    findings: list[AuditFinding] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            findings.append(AuditFinding("unsafe-entry", _safe_path(directory.relative_to(root).as_posix()), "Project directory cannot be inspected", "Check filesystem permissions and retry."))
            continue
        for path in children:
            relative = _safe_path(path.relative_to(root).as_posix())
            try:
                if is_link_or_reparse(path):
                    findings.append(AuditFinding("unsafe-entry", relative, "Link or reparse point in project", "Remove the link and use a regular project file."))
                elif stat.S_ISDIR(os.lstat(path).st_mode):
                    pending.append(path)
                elif stat.S_ISREG(os.lstat(path).st_mode):
                    files.append(path)
                else:
                    findings.append(AuditFinding("unsafe-entry", relative, "Non-regular project entry", "Remove the entry before backup."))
            except OSError:
                findings.append(AuditFinding("unsafe-entry", relative, "Project entry cannot be inspected", "Check filesystem permissions and retry."))
    return files, findings


def _repo_root(project_dir: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


def _is_ignored(repo: Path, path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "--quiet", "--", str(path)],
            capture_output=True, check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_SENSITIVE_KEYS.search(str(key)) or _contains_sensitive_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def audit_project(project_dir: Path) -> tuple[AuditFinding, ...]:
    """Return sorted findings without exposing file contents or absolute paths."""
    try:
        if is_link_or_reparse(project_dir):
            return (AuditFinding("unsafe-entry", ".", "Project root is a link or reparse point", "Use a regular project directory."),)
    except OSError:
        pass
    root = project_dir.resolve()
    if not root.is_dir():
        return (AuditFinding("project-layout", ".", "Project directory is missing", "Provide an existing project directory."),)
    files, findings = _entries(root)
    repo = _repo_root(root)
    if {kind.value for kind in GateKind} != {"medical", "video"}:
        findings.append(AuditFinding("gate-contract", ".", "Unexpected review gate", "Restore the two-gate contract before operating."))
    try:
        validate_project_tree(root)
    except (OSError, TypeError, ValueError):
        findings.append(AuditFinding("backup-binding", ".", "Project layout or authoritative binding is invalid", "Repair the project data before backup."))
    for path in files:
        relative = path.relative_to(root).as_posix()
        display = _safe_path(relative)
        parts = {part.casefold() for part in path.relative_to(root).parts}
        risky = bool(parts & _RISKY_PARTS or path.suffix.casefold() in _RISKY_SUFFIXES or path.name.casefold().startswith(".env"))
        if risky and repo is not None and not _is_ignored(repo, path):
            findings.append(AuditFinding("commit-risk", display, "Sensitive or generated artifact is not confirmed Git-ignored", "Move it outside Git or add a precise ignore rule."))
        if is_backup_excluded(relative) and path.name.casefold().startswith(".env"):
            findings.append(AuditFinding("credential-path", display, "Credential file is present in project", "Keep credentials outside the project directory."))
        if re.search(r"(?:^|[-_])provider[-_]response\.(?:json|ya?ml)$", path.name, re.IGNORECASE):
            findings.append(AuditFinding("raw-provider-response", display, "Raw provider response is present in project", "Remove raw provider output and retain only reviewed typed artifacts."))
        if path.suffix.casefold() not in {".json", ".yaml", ".yml"} or is_backup_excluded(relative):
            continue
        try:
            if path.stat().st_size > 2_000_000:
                findings.append(AuditFinding("typed-artifact", display, "Typed artifact exceeds audit inspection limit", "Review the file size and remove or split the artifact."))
                continue
            content = path.read_text(encoding="utf-8")
            payload = json.loads(content) if path.suffix.casefold() == ".json" else yaml.safe_load(content)
            if _contains_sensitive_key(payload):
                findings.append(AuditFinding("credential-field", display, "Sensitive field in typed artifact", "Remove the field and rotate any exposed credential."))
        except (OSError, UnicodeError, ValueError, yaml.YAMLError):
            findings.append(AuditFinding("typed-artifact", display, "Typed artifact cannot be inspected", "Repair or remove the artifact."))
    return tuple(sorted(set(findings)))
