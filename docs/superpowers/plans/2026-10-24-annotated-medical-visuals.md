# Annotated medical visuals implementation plan

**Goal:** Implement the doctor's supplied A–D brief in the current worktree.
**Architecture:** Keep approved project artifacts immutable. Add component metadata and deterministic scene beats; review generated candidate images before the video gate. Runtime choices belong to derived production artifacts.
**Tech stack:** Pydantic/Python, React/Remotion, Vitest, pytest, FFmpeg.
**Spec:** User brief, plus `2026-10-22-video-factory-restructure-design.md`.

## Global constraints

- No fabricated medical facts, sources, numbers or doctor experience; no approval bypass or publishing.
- No changes to projects/, topics/, root README progress, TTS, pronunciation, delivery or draft voice instructions.
- No commit, push or branch switch. Generated review images stay in ignored cache/visual2/.
- Read source evidence only; local paths use pathlib.Path in Python.

## Tasks

- [ ] Anatomy: named focus regions and label metadata; shared contrast labels/leader lines; five gout views with state/action tests and bounded nonoverlapping labels.
- [ ] Beats: scene beat schema, keyword alignment, eased camera and label selection; draft and timed-input rhythm checks; subject diversity tests.
- [ ] Whiteboard: dedicated image/text boxes for both aspect ratios; rendered-layout regression tests.
- [ ] FLUX review: three seeds, contact sheets, agent review, bounded retries and derived SVG fallback; hash-bound review packet and gate integration tests.
- [ ] Prompts: edit visual requirements only, keep each agent prompt at most 60 lines.
- [ ] Verification: view evidence frames, render both aspect ratios with normal/diseased and focus samples, inspect sheets, run all requested checks and report evidence mapping.

## Review focus

- Repeated identical beats must not satisfy a visual-change check.
- Camera focus must not clip labels; phone-size label readability matters.
- Retry/resume cannot select a stale candidate or invalidate medical approval silently.
- Whiteboard text and illustration must have disjoint boxes, including long text.
- Candidate selection must be reflected in final render and video packet.
