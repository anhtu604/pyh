---
name: motion-design
description: Taste rules for Remotion motion graphics — timing, easing, springs, typography, color, and anti-patterns, aligned with PYH anatomy and scene-timing contracts.
---

# Motion Design (PYH-Scoped)

## Ràng buộc PYH (bắt buộc)
- **Không** tìm `timeline.json` hay `src/lib.ts`, **không** chạy `npm run sfx`, `review-loop`, hay `sound-design`.
- Thời gian và nhịp của PYH nằm ở `renders/scene-timing.json`, `beats`, `FOCUS_REGIONS`, `CUE_ACTIONS` và `video/src/motion/` (`docs/reference/motion-vocabulary.md`). Python đảm nhận việc dựng lại video.
- Kỷ luật thợ dựng (`2026-11-17-pyh-style-a-mascot-host.md` mục 5): chỉ sửa đúng lỗi được giao; không tự thêm bounce/hiệu ứng ngoài bộ động tác nhận diện để "cho sinh động".

## 1. Frame-Pure Timing

- Every animation must be a pure function of `useCurrentFrame()` (no CSS transitions/keyframes, no `Math.random()`, no `Date`).
- Offset entrances/cues relative to scene `beats` / `CUE_ACTIONS` rather than arbitrary wall-clock timers.

## 2. Easing

| Curve | Use |
|---|---|
| `bezier(0.16, 1, 0.3, 1)` (`easeOut`) | entrances, reveals, anything arriving |
| `bezier(0.6, 0, 0.9, 0.35)` (`easeIn`) | exits — leaves fast, doesn't linger |
| `bezier(0.65, 0, 0.35, 1)` (`easeInOut`) | smooth state transitions |

Use linear motion only for continuous drift or steady rotation.

## 3. Springs

- Default settle (`damping: 14, stiffness: 140, mass: 0.8`) for panels and diagrams.
- Calm/heavy (`damping: 15–20, stiffness: 140–240`) for large medical stages.
- Callout pop (`damping: 10–12, stiffness: 200`) only when matching a `CUE_ACTIONS` highlight—never spam bounce across every element.

## 4. Timing

- **Stagger** list items/labels by ~0.15–0.25s; keep SVG stroke reveals crisp (`0.3–0.8s`).
- **Exits** take ~0.35–0.5s (`easeIn`), faster than entrances.
- **Reading holds**: leave at least 1–2s hold after a label or diagram settles so viewers can read it at 720p.

## 5. Typography & 6. Color

- Use PYH brand font `Be Vietnam Pro` and palette tokens from `profiles/brand.vi.yaml` (`off_white #F7F4EC`, `navy #12304A`, `teal #18A6A6`, `yellow #F4B942`, `night #0A1C2E`; max 3 accent colors, no alarm red).
- Ensure labels remain readable on mobile/720p (≤ 6 labels per anatomy diagram, no overlap or edge clipping).

## Anti-patterns

- Everything fading in at once or with identical timing.
- Linear easing on starts/stops, or text moving while the viewer tries to read it.
- More than one focal point per frame, or placing elements inside the 60px outer margin / 9:16 caption zone.
