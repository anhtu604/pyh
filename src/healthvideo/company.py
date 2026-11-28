"""Company roles and model tiers: which (cli, model) chain runs each factory step."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPANY_PATH = REPO_ROOT / 'profiles/company.yaml'
SKILLS_DIR = Path('.agents/skills')
SKILL_RULE = (
    'Đọc các skill trên trước khi làm; chỉ áp dụng phần hợp với kênh sức khoẻ tiếng Việt. '
    'Khi skill mâu thuẫn với prompt bước hoặc quy tắc cứng, prompt bước và quy tắc cứng thắng.'
)

# Concise reading scope for long general skills so roles skip non-PYH workflows.
SKILL_SECTION_GUIDES: dict[str, str] = {
    'content-strategy': (
        'Chỉ đọc "Searchable vs Shareable" và "Content Ideation Sources"; '
        'bỏ Buyer Stage, Scoring Template, Calendar Split 60/30/10 và link-building; '
        'dùng rubric THANG_DIEM của PYH.'
    ),
    'copy-editing': (
        'Chỉ đọc Clarity, Voice and Tone, Specificity và AI-Tell Check; '
        'bỏ bổ sung proof/testimonial (Sweep 4) và không đổi mức chắc chắn của claim '
        '(lỗi claim chuyển expert/writer).'
    ),
    'social': (
        'Chỉ đọc Hook Formulas, No AI Tells và caption ngắn gọn; '
        'bỏ Engagement Strategy, Scheduling/Publishing và B2B calendar; '
        'đầu ra duy nhất theo schema PostSet/ShortsPlan.'
    ),
    'youtube-scriptwriting': (
        'Chỉ đọc hook/through-line/payoff (Checkpoint 3–5); '
        'bỏ tự research (Checkpoint 2), lời khuyên lặp ý, Binge Loop và không dừng hỏi duyệt checkpoint trong bước batch.'
    ),
    'short-form-video': (
        'Chỉ áp dụng hook, nhịp cắt, loop và 9:16 safe areas cho tác vụ clip từ cảnh đã duyệt; '
        'không trì hoãn caveat/cảnh báo an toàn, không tạo composition hay tự render.'
    ),
    'scripting-and-storyboarding': (
        'Đọc bảng audio–visual và intent từng shot (SCENE); '
        'thay Read these first bằng script/outline, profiles/brand.vi.yaml và style PYH đã pin; '
        'bỏ lịch quay thật và publish/WoopSocial.'
    ),
    'visual-style': (
        'Chỉ đọc phần Apply để ánh xạ style PYH đã pin '
        '(docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md) sang brand/storyboard/motion hiện có; '
        'không tự tạo schema hay connector ngoài.'
    ),
    'motion-design': (
        'Chỉ đọc Easing/Timing/Typography/Anti-patterns khi sửa hình; '
        'thay mục timeline.json/src/lib.ts bằng scene-timing/beats/FOCUS_REGIONS/CUE_ACTIONS của repo, '
        'bỏ npm run sfx và để Python dựng lại.'
    ),
    'remotion-best-practices': (
        'Chỉ đọc Preserve user changes và React Markup Best Practices cho component được giao; '
        'bỏ Open the preview (Studio), New project setup, Render the video và không nạp cây references mặc định.'
    ),
    'character-animation-qa': (
        'Chỉ đọc Review Layers và Pass/Revise/Fail để kiểm qua review-frames/index.json và video-qa.json có sẵn; '
        'bỏ Playwright Pattern và không nhận đã xem chuyển động liên tục từ frame mẫu.'
    ),
}

# A critic must not start on the same (cli, model) as the role(s) whose work it grades.
CRITIC_OF: dict[str, tuple[str, ...]] = {
    'script_critic': ('writer', 'storyboard_director'),
    'product_critic': ('editor',),
}

# A skill is a folder name under .agents/skills/, never a path.
SkillName = Annotated[str, StringConstraints(pattern=r'^[a-z0-9][a-z0-9-]*$')]


class ModelSlot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    cli: Literal['claude', 'codex', 'agy', 'omniroute']
    model: str

    @model_validator(mode='after')
    def explicit_router_model(self):
        # Bác sĩ 2026-11-28: xưởng không gọi Claude trực tiếp — nó ăn hạn mức của điều phối tổng.
        if self.cli == 'claude' or (self.cli == 'omniroute'
                                    and self.model.partition('/')[0] in ('claude', 'cc')):
            raise ValueError('Xưởng không được gọi Claude trực tiếp; dùng agy (claude-sonnet-5-5-medium) hoặc codex.')
        if self.cli == 'omniroute':
            provider, _, model = self.model.partition('/')
            if provider not in ('codex', 'cx', 'agy', 'antigravity', 'claude', 'cc',
                                'ds-web', 'deepseek-web') or not model:
                raise ValueError('OmniRoute cần provider/model cụ thể để giữ critic độc lập.')
        return self

    @property
    def model_identity(self) -> tuple[str, str]:
        """Routing through a proxy does not make the maker a different critic."""
        if self.cli == 'omniroute':
            provider, _, model = self.model.partition('/')
            provider = {'cx': 'codex', 'cc': 'claude', 'antigravity': 'agy',
                        'ds-web': 'deepseek-web'}.get(provider, provider)
            return provider, model
        return self.cli, self.model


class Role(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str
    name: str
    skills: list[SkillName] = Field(default_factory=list, max_length=3)
    steps: list[str]
    tier: Literal['hard', 'medium', 'bulk']
    models: list[ModelSlot] | None = None
    rework_models: list[ModelSlot] | None = Field(default=None, min_length=1)


class Company(BaseModel):
    model_config = ConfigDict(extra='forbid')

    tiers: dict[str, list[ModelSlot]]
    roles: dict[str, Role]

    def chain(self, role_id: str, *, rework: bool = False) -> list[ModelSlot]:
        role = self.roles[role_id]
        if rework and role.rework_models is not None:
            return list(role.rework_models)
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
    for critic, makers in {**CRITIC_OF, 'art_director': ('storyboard_director',)}.items():
        if critic not in company.roles:
            continue
        maker_ids = (makers,) if isinstance(makers, str) else tuple(makers)
        for maker in maker_ids:
            if (maker in company.roles and company.chain(critic)[0].model_identity
                    == company.chain(maker)[0].model_identity):
                raise ValueError(f'{path.name}: {critic!r} không được bắt đầu cùng model với {maker!r}')
            if maker in company.roles and company.roles[maker].rework_models is not None:
                critic_models = {slot.model_identity for slot in company.chain(critic)}
                if critic_models & {slot.model_identity for slot in company.chain(maker, rework=True)}:
                    raise ValueError(f'{path.name}: {critic!r} trùng model sửa của {maker!r}')
    return company


def role_skill_block(role_id: str, company: Company | None = None) -> str:
    """Prompt section pointing the role at its SKILL.md files; empty when it has none."""
    role = (company or load_company()).roles[role_id]
    if not role.skills:
        return ''
    lines = []
    for name in role.skills:
        path = (SKILLS_DIR / name / 'SKILL.md').as_posix()
        guide = SKILL_SECTION_GUIDES.get(name)
        lines.append(f'- {path} — {guide}' if guide else f'- {path}')
    paths = '\n'.join(lines)
    return f'## Skill của vai: {role.name}\n{paths}\n\n{SKILL_RULE}\n'
