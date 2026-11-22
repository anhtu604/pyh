---
name: visual-style
description: Apply PYH pinned visual style specifications consistently across storyboard scenes, FLUX prompts, and SVG/Remotion components.
---

# Visual Style (PYH-Scoped)

## Ràng buộc PYH (bắt buộc)
- Chỉ dùng phần **Apply** để ánh xạ chuẩn phong cách đã ghim của PYH sang `profiles/brand.vi.yaml`, `storyboard.yaml`, `image-prompting.md`, và component Remotion hiện có; **không** tạo schema mới hay dùng connector HeyGen / Figma / paper.design.
- Tài liệu chuẩn PYH: `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md` (Style A) và `docs/superpowers/specs/2026-11-21-visual-style-set-design.md` (`scale_zoom`, `iso_infographic`, `whiteboard`).

## Apply

1. **Load the pinned PYH style**: check `workflow/standards.yaml` in the active revision and read the pinned spec (`scale_zoom`, `iso_infographic`, or `whiteboard` + Style A mascot host rules).
2. **Map palette & typography**: enforce `off_white #F7F4EC`, `night #0A1C2E`, `navy #12304A`, `teal #18A6A6`, `yellow #F4B942` (≤ 3 accent colors, no alarm red) and `Be Vietnam Pro`.
3. **Map scene craft**:
   - FLUX illustrations: 2D matte flat editorial style, clean English prompt, no text/numbers/labels inside generated images; life/context scenes only (never medical anatomy via FLUX).
   - Medical diagrams: registered `video/src/anatomy/` SVG / `ScaleZoomStage` / `IsoInfographicStage` / progressive `WhiteboardScene` with ≤ 6 crisp Vietnamese labels.
   - Mascot host: valid 9 poses from `profiles/brand.vi.yaml`, matched to narration meaning, ≤ 28% width in 9:16 and never blocking anatomy or captions.
4. **Verify both aspect ratios**: confirm readability and safe zones for both 16:9 and 9:16 before locking storyboard or submitting review.
