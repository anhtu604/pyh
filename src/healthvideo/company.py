"""Company roles and model tiers: which (cli, model) chain runs each factory step."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPANY_PATH = REPO_ROOT / 'profiles/company.yaml'

# A critic must not start on the same (cli, model) as the role whose work it grades.
CRITIC_OF = {'script_critic': 'writer', 'product_critic': 'editor'}


class ModelSlot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    cli: Literal['claude', 'codex', 'agy']
    model: str


class Role(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str
    name: str
    skill: str | None = None
    steps: list[str]
    tier: Literal['hard', 'medium', 'bulk']
    models: list[ModelSlot] | None = None


class Company(BaseModel):
    model_config = ConfigDict(extra='forbid')

    tiers: dict[str, list[ModelSlot]]
    roles: dict[str, Role]

    def chain(self, role_id: str) -> list[ModelSlot]:
        role = self.roles[role_id]
        return list(role.models if role.models is not None else self.tiers[role.tier])

    def role_for_step(self, step: str) -> Role:
        for role in self.roles.values():
            if step in role.steps:
                return role
        raise KeyError(f'Không có vai nào làm bước {step!r}')


def load_company(path: Path = COMPANY_PATH) -> Company:
    """Load and validate the company file; any problem is a Vietnamese ValueError."""
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        for role_id, role in (data.get('roles') or {}).items():
            role.setdefault('id', role_id)
        company = Company.model_validate(data)
    except (OSError, yaml.YAMLError, AttributeError, ValidationError) as exc:
        raise ValueError(f'{path.name} không hợp lệ: {exc}') from exc
    owner: dict[str, str] = {}
    for role_id, role in company.roles.items():
        if role.id != role_id:
            raise ValueError(f'{path.name}: vai {role_id!r} ghi id {role.id!r}')
        if role.tier not in company.tiers:
            raise ValueError(f'{path.name}: vai {role_id!r} dùng bậc chưa khai báo {role.tier!r}')
        if not company.chain(role_id):
            raise ValueError(f'{path.name}: vai {role_id!r} không có model nào')
        for step in role.steps:
            if step in owner:
                raise ValueError(f'{path.name}: bước {step!r} thuộc cả {owner[step]!r} và {role_id!r}')
            owner[step] = role_id
    # Import at load time to avoid the runner/company module import cycle.
    from healthvideo.workflows.runner import AGENT_STEPS

    missing = AGENT_STEPS - owner.keys()
    if missing:
        raise ValueError(f'{path.name}: các bước chưa có vai: {", ".join(sorted(missing))}')
    for critic, maker in CRITIC_OF.items():
        if (critic in company.roles and maker in company.roles
                and company.chain(critic)[0] == company.chain(maker)[0]):
            raise ValueError(f'{path.name}: {critic!r} không được bắt đầu cùng model với {maker!r}')
    return company
