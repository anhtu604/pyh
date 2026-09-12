---
name: pyh
description: Operate one revisioned preventive-health video project from topic selection through manual posting package.
---

# /pyh

Interpret `discover`, `new`, `select`, `continue`, `edit`, `review`, `package`, and `status` (and their Vietnamese equivalents). Resolve the project path from the user's request or current project context. If ambiguous, list local projects or ask which project the user means.

Read `AGENTS.md` and the required design/plan before changing workflow or schema. Use existing M1–M3 artifacts and commands. Load only references needed for the current topic. Never invent a source, DOI, PMID, medical result, number, or doctor's experience.

For an existing project, call `healthvideo operator status <project> --json` first. Treat its state and action as the authority for the next step. Perform one deterministic operation or continue through existing steps until a human boundary. Recheck status after each operation. If the project is v1, present the existing migration command and wait for an explicit migration choice. `status` is read-only. `edit` uses the existing invalidation policy and revision service; any semantic medical change returns to the medical gate.

For discovery, use local `healthvideo topic list` and `healthvideo topic create` or existing M3 source search only when needed. Do not claim a topic is trending without evidence. `new` calls `healthvideo operator new <root> --slug <slug> --title <title>` and creates v2. `select` calls `healthvideo operator select <project> --file <card.yaml>`.

If the doctor says `/pyh chọn chủ đề <n>` after discovery and **chưa có project**, resolve `<n>` against the displayed local topic cards, create a v2 project with `healthvideo operator new`, then call `healthvideo operator select` with that card. If a project already exists, select into that project. For a direct `/pyh làm video ... về <topic>` request, create or reuse a local card using only the user-stated topic, create a v2 project if needed, select the card, and stop at `confirm_brief`. If the topic wording does not specify a research question, keep that field as a neutral copy of the stated topic; do not invent a trend, medical claim, or doctor's position. Resolve slug/path collisions with the doctor before overwriting anything.

Draft an author brief from the doctor's actual words, show it, and call `healthvideo operator brief <project> --title ...` without `--confirm` until the doctor confirms that specific brief is **ổn**. Then use `--confirm` and recheck status. This confirms the brief only: **không tự chốt brief**, **không tạo approval** for either gate.

For research and drafting, use the existing evidence commands, schemas, revision paths and review packet. At `awaiting_medical_review`, present `healthvideo review open <project> --gate medical` and stop. After medical approval, `healthvideo produce <project>` may run. At `awaiting_video_review`, present `healthvideo review open <project> --gate video` and stop again. After explicit video approval, `healthvideo package <project>` creates the local `publish/` bundle. Show its path and checklist for manual upload; **không tự động xuất bản**.

Generic “ổn”, “tiếp tục”, or “render đi” **không tạo medical/video approval**. For `/pyh duyệt nội dung` or `/pyh duyệt video`, first identify the relevant packet, gate and **active revision** and present them to the doctor. Require the doctor's explicit decision to approve that gate and a user-supplied **reviewer identity**; note is optional. Then invoke the existing `healthvideo review approve <project> --gate medical|video --reviewer <name>` confirmation workflow. **Không suy đoán reviewer**, never reuse brief confirmation as gate approval, and never generate, forge, or infer a gate record from conversation. A rejection uses the existing review rejection workflow and records the doctor's reason.

When waiting for browser login, second-model review, revision, or blocker resolution, explain the exact action from operator status and pause. Use existing CLI and files; do not add an approval layer, workflow engine, renderer, registry, or publishing API.
