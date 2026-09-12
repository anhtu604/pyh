from pathlib import Path


def test_claude_adapter_points_to_one_canonical_workflow() -> None:
    canonical = Path(".agents/skills/pyh/SKILL.md").read_text(encoding="utf-8")
    shim = Path(".claude/commands/pyh.md").read_text(encoding="utf-8")
    assert "healthvideo operator status" in canonical
    assert ".agents/skills/pyh/SKILL.md" in shim
    assert "ổn" in canonical and "không tạo approval" in canonical
    assert "không tự động xuất bản" in canonical


def test_pyh_topic_entry_paths_stop_at_brief_confirmation() -> None:
    skill = Path(".agents/skills/pyh/SKILL.md").read_text(encoding="utf-8")
    assert "chưa có project" in skill
    assert "healthvideo operator new" in skill
    assert "healthvideo operator select" in skill
    assert "làm video" in skill
    assert "confirm_brief" in skill
    assert "không tự chốt brief" in skill


def test_pyh_approval_requires_explicit_doctor_decision_and_identity() -> None:
    skill = Path(".agents/skills/pyh/SKILL.md").read_text(encoding="utf-8")
    assert "render đi" in skill
    assert "không tạo medical/video approval" in skill
    assert "active revision" in skill
    assert "reviewer identity" in skill
    assert "healthvideo review approve" in skill
    assert "không suy đoán reviewer" in skill.lower()
