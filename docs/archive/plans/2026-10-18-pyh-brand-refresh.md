# Plan: làm mới nhận diện PYH

Spec: `docs/superpowers/specs/2026-10-18-pyh-brand-refresh-design.md` (đã duyệt 18-10-2026).
Thực hiện: Codex CLI, TDD; Claude review và commit.

Không sửa: `.agents/`, `.claude/`, `skills-lock.json`, `.gitignore`, `src/healthvideo/cli.py`,
`src/healthvideo/workflows/review_html.py`, `tests/contracts/test_cli_mutation_inventory.py`
(session khác đang sửa). Vì vậy cảnh báo placeholder ở cổng 2 (spec §5.3) **hoãn** sang việc
sau; chỉ đổi `aria-label`.

## B1. Brand profile

- `profiles/brand.vi.yaml`: thêm `colors.night: "#0A1C2E"`.
- `src/healthvideo/domain/brand.py`: `BrandColors.night` bắt buộc; `MascotIdentity.artwork`
  tùy chọn (map đủ 3 pose → `{path, sha256}`); validator stdlib: path POSIX tương đối, file
  có thật (tính từ thư mục gốc repo), SHA-256 khớp, chữ ký PNG, IHDR color type 6 (RGBA),
  ba file cùng kích thước, cạnh ngắn ≥ 768.
- Test: thiếu `night`; artwork thiếu pose / sai hash / không phải PNG / không RGBA / lệch
  kích thước / quá nhỏ; artwork hợp lệ (PNG RGBA tạo bằng `zlib`+`struct` trong test).
- Test đồng bộ: object `brand` trong `video/src/anatomy/palette.ts` khớp `colors` của YAML.

## B2. Logo

- `src/healthvideo/visuals/brand.py`: vẽ lại theo spec §2 (tham khảo
  `.tmp/brand-sketch/sketch.py`); thêm `LogoVariant.REVERSE`; xóa `render_phy_logo`.
- Chỉ dùng lệnh path tuyệt đối `M L H V Q Z`, rect/circle nguyên.
- Test: lặp byte; mọi tọa độ ± nửa `stroke-width` nằm trong lề 40 của `viewBox`; màu từng
  biến thể; monogram có `rect` nền navy; bản một màu chỉ một màu; không `filter`, `gradient`,
  `<text>`, `href`, `<image>`.
- Đổi fixture `assets/phy.svg` → `assets/pyh.svg` trong `video/src/types.test.ts`,
  `video/src/HealthVideo.test.tsx`. Giữ test tương thích `phy-logo` trong `tests/test_assets.py`.
- Schema export nếu enum đổi.

## B3. Mascot

- `src/healthvideo/visuals/mascot.py`: `mascot_asset(brand, pose) -> tuple[bytes, str]`
  (`(png, ".png")` khi có artwork, ngược lại `(render_mascot(...), ".svg")`); placeholder
  đổi `aria-label` thành `PYH guide placeholder <pose>`.
- `create_mascot_reaction_asset` (`workflows/visual_assets.py`) và `_register_clip_mascot`
  (`workflows/long_form.py`) dùng `mascot_asset`; đường dẫn theo suffix. Mở các kiểm tra đuôi
  `.svg` ở manifest/preflight/render input để nhận `.png` **chỉ** cho `mascot_reaction`.
- `create_mascot_annotation_asset` từ chối khi profile có artwork (thông báo: dùng
  `medical_text` cạnh mascot).
- Test cho cả hai nhánh có/không artwork (monkeypatch profile).

## B4. Thẻ cuối: logo

- Python: đăng ký `clips/cta/logo.svg` (logo `reverse`, kind `FLOURISH`, `semantic: false`,
  role `brand`) cùng chỗ đăng ký mascot clip; `YouTubeCTA` (render/input.py) thêm
  `logo_path` mặc định `clips/cta/logo.svg`, validate như `mascot_path`.
- Zod (`video/src/types.ts`) thêm `logo_path` có default; `Root.tsx` default props.
- `YouTubeEndCard.tsx`: logo cao 64 (9:16) / 48 (16:9) dưới mascot, cách 32; cập nhật
  `endCardGeometry` và test.

## B5. Font

- Tải Be Vietnam Pro SemiBold (600) và ExtraBold (800) từ repo chính thức
  `github.com/google/fonts` (`ofl/bevietnampro`), kèm `OFL.txt`, vào `video/public/fonts/`.
- `video/src/fonts.ts`: nạp bằng `FontFace` + `staticFile` + `delayRender/continueRender`,
  xuất `FONT_FAMILY = "'Be Vietnam Pro', Arial, sans-serif"`; nạp một lần ở module root.
- Thay mọi `'Arial, sans-serif'` trong `video/src` bằng `FONT_FAMILY`.

## B6. Mascot trong khung

- `MascotGuide`: lật `scaleX(-1)` khi tâm hộp ở nửa phải khung; test.
- Kiểm tra `layout.ts`: hộp mascot thường ≤ 30% chiều cao ở 16:9, ≤ 24% ở 9:16 (không áp
  cho thẻ cuối); thêm test, chỉnh nếu vượt.

## B7. Ảnh nghiệm thu

Xuất ra `.tmp/brand-review/`: 4 SVG logo, 3 SVG placeholder, và Remotion still (log ghi ra
file) cho: thẻ cuối 9:16 và 16:9, một cảnh có mascot 16:9 và 9:16 (dùng fixture/default
props có sẵn).

## Kiểm tra cuối

`python -m pytest -q`; `python -m ruff check src tests tools`; schema export rồi `git diff`
chỉ đổi dự kiến; `pnpm --dir video test`; `pnpm --dir video typecheck`; `git diff --check`.
