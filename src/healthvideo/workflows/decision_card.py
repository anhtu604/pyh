"""Read critic decision cards and compose the doctor's choices; never approve gates."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic

MAX_DECISIONS = 5


class DecisionOption(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    effect: str = Field(min_length=1)
    recommended: bool = False
    keep: bool = False


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(min_length=1)
    where: str = Field(min_length=1)
    question: str = Field(min_length=1)
    why_hard: str = Field(min_length=1)
    options: list[DecisionOption] = Field(min_length=2, max_length=3)

    @model_validator(mode='after')
    def validate_options(self) -> 'Decision':
        if len({option.id for option in self.options}) != len(self.options):
            raise ValueError('ID phương án không được trùng.')
        if sum(option.keep for option in self.options) != 1:
            raise ValueError('Mỗi điểm khó phải có đúng một phương án keep.')
        if sum(option.recommended for option in self.options) > 1:
            raise ValueError('Chỉ được khuyến nghị tối đa một phương án.')
        return self


def validate_decisions(decisions: list[Decision], line_ids: set[str] | None = None) -> None:
    if len({item.id for item in decisions}) != len(decisions):
        raise ValueError('ID điểm khó không được trùng.')
    if line_ids is not None:
        for item in decisions:
            if item.where not in line_ids:
                raise ValueError(f'Dòng không có trong kịch bản: {item.where}')


def _log(root: Path, gate: str) -> dict:
    path = root / f'reviews/{"script" if gate == "medical" else "product"}-review-log.yaml'
    return read_yaml(path) if path.is_file() else {}


def _receipt(root: Path, gate: str) -> Path:
    return root / 'reviews' / gate / 'decision-card-fix.yaml'


def remember_fix(root: Path, gate: str, choices: dict[str, str], other: str) -> None:
    """Record a PIN-authorized send-fix only after the existing rejection succeeds."""
    write_yaml_atomic(_receipt(root, gate), {
        'rounds': len(_log(root, gate).get('rounds', [])),
        'choices': choices, 'other': other.strip(),
    })


def card(project_dir: Path) -> dict | None:
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / 'project.yaml'))
    gates = {WorkflowState.AWAITING_MEDICAL_REVIEW: 'medical',
             WorkflowState.AWAITING_VIDEO_REVIEW: 'video'}
    gate = gates.get(project.state)
    if gate is None:
        return None
    root = project_dir / 'revisions' / project.active_revision
    rounds = _log(root, gate).get('rounds', [])
    latest = rounds[-1] if rounds else {}
    decisions = [Decision.model_validate(item) for item in latest.get('decisions', [])]
    validate_decisions(decisions)
    shown = []
    for item in decisions[:MAX_DECISIONS]:
        default = next((option for option in item.options if option.recommended), None)
        shown.append({**item.model_dump(mode='json'),
                      'selected': default.id if default else None})
    followup = None
    receipt = _receipt(root, gate)
    if receipt.is_file() and not decisions and latest.get('passed'):
        previous = read_yaml(receipt)
        if len(rounds) > previous['rounds']:
            choices = ' · '.join(f'{key}={value}' for key, value in previous['choices'].items())
            followup = f'Đã sửa theo {choices or "ý khác"} · agent kiểm ✓'
    return {
        'gate': gate, 'revision': project.active_revision,
        'title': 'Duyệt y khoa' if gate == 'medical' else 'Duyệt video',
        'checked': latest.get('checked', []), 'decisions': shown,
        'more': max(0, len(decisions) - MAX_DECISIONS), 'followup': followup,
    }


def compose(card: dict, choices: dict[str, str], other: str) -> tuple[Literal['approve', 'send_fix'], str]:
    """Require an explicit valid choice for every visible decision, fail closed on stale IDs."""
    decisions = [Decision.model_validate({key: value for key, value in item.items()
                                         if key != 'selected'}) for item in card['decisions']]
    validate_decisions(decisions)
    if not isinstance(choices, dict) or set(choices) != {item.id for item in decisions}:
        raise ValueError('Chọn một phương án cho mỗi điểm khó; tải lại thẻ nếu đã thay đổi.')
    if not isinstance(other, str):
        raise TypeError('Ý khác phải là văn bản.')
    rows = []
    send_fix = bool(other.strip())
    for item in decisions:
        option = next((option for option in item.options if option.id == choices[item.id]), None)
        if option is None:
            raise ValueError(f'Phương án không hợp lệ: {item.id}')
        rows.append(f'{item.id} ({item.where}) → {option.id}: {option.label}')
        send_fix = send_fix or not option.keep
    if other.strip():
        rows.append('Ý khác: ' + other.strip())
    return ('send_fix' if send_fix else 'approve', '\n'.join(rows))
