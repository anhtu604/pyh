import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "src/healthvideo/cli.py": {
        "ai_clip_generate",
        "outro_author",
        "agent_review_request",
        "agent_review_complete",
        "produce",
        "package",
        "migrate_project_command",
        "review_medical",
        "review_video",
        "review_approve",
        "review_reject",
        "review_resume",
        "revision_create",
        "topic_select",
        "evidence_search",
        "evidence_ingest",
        "evidence_build_ledger",
    },
    "src/healthvideo/commands/operator.py": {
        "select",
        "orientation",
        "brief",
        "draft",
        "submit_medical",
    },
}
READ_ONLY = {
    "src/healthvideo/cli.py": {"status", "lease_inspect", "review_open", "security_audit"},
    "src/healthvideo/commands/operator.py": {"status"},
}
LEASE_CONTROL = {
    # backup_create holds the write lease inside create_backup, not via the decorator.
    "src/healthvideo/cli.py": {"lease_recover", "backup_create"},
    "src/healthvideo/commands/operator.py": set(),
}


def test_every_project_cli_command_is_classified_and_mutations_are_guarded() -> None:
    for relative, expected_mutations in EXPECTED.items():
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        commands = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and any(".command(" in ast.unparse(item) for item in node.decorator_list)
            and any(arg.arg == "project_dir" for arg in node.args.args)
        }
        assert set(commands) == (
            expected_mutations | READ_ONLY[relative] | LEASE_CONTROL[relative]
        )
        for name in expected_mutations:
            decorators = {ast.unparse(item) for item in commands[name].decorator_list}
            assert any(item.startswith("project_mutation(") for item in decorators), name
        for name in READ_ONLY[relative]:
            calls = {
                ast.unparse(node.func)
                for node in ast.walk(commands[name])
                if isinstance(node, ast.Call)
            }
            assert not calls.intersection(
                {"write_text_atomic", "write_yaml_atomic", "write_json_atomic"}
            ), name
