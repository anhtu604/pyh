---
name: pyh
description: Operate one revisioned preventive-health video project from topic selection through manual posting package.
---

# /pyh

In this repo, every `healthvideo ...` command means `.venv\Scripts\healthvideo.exe ...` run from the repo root. If that executable is missing, stop and tell the user to run `powershell -NoProfile -ExecutionPolicy Bypass -File install/install.ps1`.

Interpret `discover`, `new`, `select`, `continue`, `edit`, `review`, `package`, `preview` (`xem`), and `status` (and their Vietnamese equivalents). Resolve the project path from the user's request or current project context. If ambiguous, list local projects or ask which project the user means.

`/pyh xem` runs `healthvideo preview <project>` in the background as a long-running server, then tells the user to open the printed URL: in Antigravity IDE via its built-in browser, in Claude Code via a browser/preview pane. Studio is for viewing; changes made in Studio are not saved to the project and never count as video approval.

Read `AGENTS.md` and the required design/plan before changing workflow or schema. Use existing M1–M3 artifacts and commands. Load only references needed for the current topic. Never invent a source, DOI, PMID, medical result, number, or doctor's experience.

For an existing project, call `healthvideo operator status <project> --json` first. Treat its state and action as the authority for the next step. Perform one deterministic operation or continue through existing steps until a human boundary. Recheck status after each operation. If the project is v1, present the existing migration command and wait for an explicit migration choice. `status` is read-only. `edit` uses the existing invalidation policy and revision service; any semantic medical change returns to the medical gate.

For discovery, use local `healthvideo topic list` and `healthvideo topic create` or existing M3 source search only when needed. Do not claim a topic is trending without evidence. `new` calls `healthvideo operator new <root> --slug <slug> --title <title>` and creates v2. `select` calls `healthvideo operator select <project> --file <card.yaml>`.

If the doctor says `/pyh chọn chủ đề <n>` after discovery and **chưa có project**, resolve `<n>` against the displayed local topic cards, create a v2 project with `healthvideo operator new`, then call `healthvideo operator select` with that card. If a project already exists, select into that project. For a direct `/pyh làm video ... về <topic>` request, create or reuse a local card using only the user-stated topic, create a v2 project if needed, select the card, and continue with evidence search. If the topic wording does not specify a research question, keep that field as a neutral copy of the stated topic; do not invent a trend, medical claim, or doctor's position. Resolve slug/path collisions with the doctor before overwriting anything.

From `topic_selected`, run `healthvideo evidence search <project> --query <English-query>`; repeat `--query` for multiple English queries. Inspect the per-query search log and provider failures, screen recorded candidates, and build the evidence ledger. Use only recorded sources; never invent sources or a doctor's views. Research must **không tạo approval** for either gate.

For research and drafting, use the existing evidence commands, schemas, revision paths and review packet. At `evidence_ready`, author `script.yaml`, `storyboard.yaml`, and `asset-manifest.yaml` from the verified ledger and selected topic; never invent a claim or source. Put referenced asset files in the active revision, then call `healthvideo operator draft <project> --script <file> --storyboard <file> --assets <file>`. Check status and call `healthvideo operator submit-medical <project>` only after the complete draft validates. At `awaiting_medical_review`, present `healthvideo review open <project> --gate medical` and stop. After medical approval, `healthvideo produce <project>` may run. At `awaiting_video_review`, present `healthvideo review open <project> --gate video` and stop again. After explicit video approval, `healthvideo package <project>` creates the local `publish/` bundle. Show its path and checklist for manual upload; **không tự động xuất bản**.

Generic “ổn”, “tiếp tục”, or “render đi” **không tạo medical/video approval**. For `/pyh duyệt nội dung` or `/pyh duyệt video`, first identify the relevant packet, gate and **active revision** and present them to the doctor. Require the doctor's explicit decision to approve that gate and a user-supplied **reviewer identity**; note is optional. Then invoke the existing `healthvideo review approve <project> --gate medical|video --reviewer <name>` confirmation workflow. **Không suy đoán reviewer**, never generate, forge, or infer a gate record from conversation. A rejection uses the existing review rejection workflow and records the doctor's reason. After medical approval, use `healthvideo review reopen <project> --gate medical --reviewer <name> --reason <text> --changed <revision-relative-path> --resume-to draft_ready|research_in_progress` (`REOPEN` confirmation); it preserves prior approvals as history and creates no approval. Then `review resume --gate medical --to draft_ready` and `operator draft` can submit the revised draft.

When waiting for revision or blocker resolution, explain the exact action from operator status and pause. Use existing CLI and files; do not add an approval layer, workflow engine, renderer, registry, or publishing API.
