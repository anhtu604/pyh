from pathlib import Path


def test_claude_adapter_points_to_one_canonical_workflow() -> None:
    canonical = Path(".agents/skills/pyh/SKILL.md").read_text(encoding="utf-8")
    shim = Path(".claude/commands/pyh.md").read_text(encoding="utf-8")
    assert "healthvideo operator status" in canonical
    assert ".agents/skills/pyh/SKILL.md" in shim
    assert "ổn" in canonical and "không tạo approval" in canonical
    assert "không tự động xuất bản" in canonical
