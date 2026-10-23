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

Daily operation:
1. First time: the doctor runs `healthvideo review set-pin`, then `healthvideo xuong --background`.
2. Add topics using `topic discover` / `topic add` as above.
3. On notification, the doctor runs `healthvideo duyet`: read the packet, choose A/R/B, enter PIN for approval or rejection. Reviewer is asked once and stored outside the repo in `~/.healthvideo/operator.yaml`.
4. The factory continues and packages approved video into `revisions/<rev>/publish/`; upload manually.
Use `healthvideo status` for worker PID and waiting count; `xuong --stop` stops it, `xuong --once` runs one cycle.
Never execute approval, `duyet` or `review set-pin` for the doctor, create approval files, or accept a PIN through chat.
Generic “ổn”, “tiếp tục”, or “render đi” không tạo medical/video approval; research không tạo approval.
Không suy đoán reviewer; reviewer identity must come from the doctor.
Legacy commands: `healthvideo run`, `healthvideo review open <project> --gate medical|video`, `healthvideo package <project>` (see README “Lệnh”); show gate and active revision before review.
Only the doctor executes `healthvideo review approve <project> --gate medical|video --reviewer <name>` and enters PIN in their own terminal (TTY).
Use `healthvideo review reject <project> --gate medical|video --reviewer <name> --reason <reason> --resume-to <state>` only for an explicit rejection.
For approved medical changes, use `healthvideo review reopen <project> --gate medical --reviewer <name> --reason <reason> --changed <revision-relative-path> --resume-to draft_ready|research_in_progress`.

Use `healthvideo preview <project>` for viewing; Studio edits do not save or approve anything.
After video approval, `healthvideo package <project>` creates the local posting bundle.
Show its path for manual upload; không tự động xuất bản.
