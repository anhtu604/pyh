---
name: pyh
description: Operate the preventive-health video factory through its public CLI and two doctor gates.
---

# /pyh

Run `healthvideo` from the repo root using the installed local executable; if missing, use `install/install.ps1`.
Read `AGENTS.md` and the required design/plan before changing workflow or schema.
Never invent a source, DOI, PMID, medical number, result, or doctor's experience.

Start with `healthvideo status`; for a known project use `healthvideo status <project> --json`.
Resolve the project from the user's request or current context; ask only if ambiguous.
Use `healthvideo topic discover --query <query> [--title <title> --question <question> --layers a,b]` for discovery.
Show recorded signals and source failures; never call a topic hot when heat is absent.
Use `healthvideo topic list` to inspect the queue.
For “làm video” or a selected discovery card, use `healthvideo topic add --slug <slug> --title <title> --question <question> [--note <doctor-note>]`.
If chưa có project, queue the topic; do not fabricate a question, trend, or doctor's position.
Use a neutral copy of the user's topic as the question if none was supplied.
Do not overwrite slug collisions.

Use `healthvideo run` to continue the factory to a doctor gate; it currently exits 2 with the Task 3.5 stub message.
Report that limitation when encountered; do not claim production ran.
Recheck `status` after each operation and respect the reported next action.
At a gate, show `healthvideo review open <project> --gate medical|video` and stop.
Show the packet, gate and active revision to the doctor.
Only the doctor may type `healthvideo review approve <project> --gate medical|video --reviewer <name> [--note <note>]` and enter PIN in their own terminal.
Never execute approval or `review set-pin` for the doctor, create approval files, or accept a PIN through chat.
Generic “ổn”, “tiếp tục”, or “render đi” không tạo medical/video approval; research không tạo approval.
Không suy đoán reviewer; reviewer identity must come from the doctor.
Use `healthvideo review reject <project> --gate medical|video --reviewer <name> --reason <reason> --resume-to <state>` for an explicit rejection.
For approved medical changes, use `healthvideo review reopen <project> --gate medical --reviewer <name> --reason <reason> --changed <revision-relative-path> --resume-to draft_ready|research_in_progress`.

Use `healthvideo preview <project>` for viewing; Studio edits do not save or approve anything.
After video approval, `healthvideo package <project>` creates the local posting bundle.
Show its path for manual upload; không tự động xuất bản.
