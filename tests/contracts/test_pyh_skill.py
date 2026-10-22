from pathlib import Path


def test_claude_adapter_points_to_one_canonical_workflow():
    skill = Path(".agents/skills/pyh/SKILL.md").read_text(encoding="utf-8")
    shim = Path(".claude/commands/pyh.md").read_text(encoding="utf-8")
    assert ".agents/skills/pyh/SKILL.md" in shim
    assert len(skill.splitlines()) <= 40
    for command in ("status", "topic discover", "topic add", "topic list", "run", "review open", "review approve", "review reject", "review reopen", "preview", "package"):
        assert f"healthvideo {command}" in skill
    assert "healthvideo operator" not in skill


def test_pyh_approval_requires_doctor_pin_in_own_terminal():
    skill = Path(".agents/skills/pyh/SKILL.md").read_text(encoding="utf-8")
    for phrase in ("active revision", "reviewer identity", "PIN in their own terminal", "Never execute approval", "không tạo approval", "không tự động xuất bản", "không suy đoán reviewer"):
        assert phrase in skill or phrase in skill.lower()
    assert "Task 3.5 stub" in skill
