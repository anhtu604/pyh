# Quy tắc viết prompt ảnh FLUX.2 klein & Hook chuyển động

Tài liệu này quy định cách viết prompt cho ảnh minh họa đời sống phẳng (`FLUX.2-klein-4B`, chạy qua `tools/flux/generate.py`) theo **Chuẩn phong cách PYH — Hướng A** (`docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md`) và hướng dẫn viết prompt khẳng định của Black Forest Labs, kèm quy tắc dựng cảnh mở đầu (hook).

> **Phạm vi dùng FLUX:** FLUX **chỉ dùng cho cảnh đời sống** minh họa bối cảnh thường ngày, đồng bộ nét và bảng màu Style A. **Không dùng FLUX cho hình y khoa / giải phẫu / mô phôi** — hình y khoa dùng SVG trong `video/src/anatomy/` hoặc nguồn khoa học có giấy phép theo mục 3 của chuẩn Style A.

---

## 1. Công thức prompt khẳng định theo FLUX & Style A

Theo hướng dẫn chính thức của Black Forest Labs, FLUX **không hỗ trợ negative prompt** (câu lệnh phủ định). Khi viết từ khóa phủ định, mô hình vẫn có xu hướng vẽ chính vật thể được nhắc đến. Vì vậy, mọi prompt cần viết bằng **văn xuôi tiếng Anh khẳng định**, mô tả cụ thể điều muốn thấy, dùng **tên màu kèm mã hex `#RRGGBB`** và nêu rõ ánh sáng phẳng.

### Công thức chuẩn

```text
[Chủ thể + tư thế/hành động, màu bằng TÊN] + [Phong cách] + [Bối cảnh] + [Ánh sáng] + [Bảng màu hex Style A, một câu ở cuối]
```

### Cụm phong cách, ánh sáng và bảng màu bắt buộc (Style A)

- **Phong cách phẳng 2D chuẩn Style A:**
  `"flat 2D vector editorial illustration, solid flat color fills, uniform navy #12304A outlines, plain flat #F7F4EC background"`
- **Ánh sáng khẳng định:**
  `"flat even lighting with solid color fills"` — mô tả ánh sáng đều, không khối nổi, không chuyển sắc gradient, không đổ bóng, không hiệu ứng hạt/nhiễu.
- **Bảng màu hex Style A (tối đa 3 màu nổi không tính nền, không dùng đỏ báo động):**
  - Nền: `off_white #F7F4EC` (cảnh tối kịch tính duy nhất khi cần: `night #0A1C2E`)
  - Nét và chi tiết tối: `navy #12304A`
  - Màu nhấn chính: `teal #18A6A6`
  - Màu điểm chốt / lưu ý: `yellow #F4B942`
- **Chỗ được đặt mã hex (đo ngày 2026-11-19):** mã hex chỉ đặt trong câu phong cách và câu bảng màu ở cuối prompt. KHÔNG đặt mã hex trong phần mô tả vật thể: đo 15 ảnh cho thấy khi hex đứng cạnh danh từ như `header bars`, FLUX in chính chuỗi mã (vd `F46BDA`, biến thể của `#F4B942`) thành chữ rác lên tờ giấy (3/3 ảnh `lab-slip`). Ở phần vật thể dùng tên màu bằng chữ (`teal`, `navy`, `warm yellow`).

---

## 2. Câu đầu tiên quyết định khung hình (Framing First)

Mô hình sinh ảnh ưu tiên tuyệt đối câu đầu tiên cho bố cục. Nếu chỉ viết chung chung (`close-up`, `front view`), mô hình dễ lùi máy ra góc trung cảnh hoặc xoay nghiêng 20–30°.

- **Đặt khung hình có thể đo được ngay câu mở đầu:** nêu rõ cỡ cảnh, góc máy, tỉ lệ chủ thể chiếm khung và vị trí mép cắt (vd: *"Top-down close-up of a wooden desk surface filling the lower two-thirds of the frame, cropped cleanly along the desk edges, with a blank folded paper sheet centered in view"*).
- **Lượng hóa góc nhìn hình học:** thay vì chỉ viết *"nhìn thẳng"*, hãy chỉ rõ dấu hiệu hình học (*"straight-on eye-level view aligned with the tabletop, both sides of the mug symmetrical in the frame"*).
- **Nhắc lại mép cắt ở câu cuối nếu prompt dài:** khi phần tả chi tiết ở giữa dài hơn 2–3 câu, chốt lại bằng một câu khẳng định ngắn (*"Framing reminder: tight tabletop crop showing only the glass and saucer against the plain flat #F7F4EC background"*).

---

## 3. Ánh sáng đều, không gọi tên nguồn sáng

Mọi danh từ chỉ vật thể xuất hiện trong prompt đều có nguy cơ bị vẽ vào khung hình.

- **Không gọi tên nguồn sáng hay đạo cụ ánh sáng:** tránh viết *"ánh sáng từ cửa sổ"*, *"đèn phòng khám"*, *"đèn bàn"* — mô hình sẽ vẽ thêm khung cửa sổ hoặc bóng đèn làm rối nền.
- **Chỉ tả ánh sáng phẳng đều chuẩn Style A:** dùng cụm khẳng định `"flat even lighting with solid color fills"` thay cho mọi mô tả đổ bóng theo hướng, đổ bóng nhiều mảng tông hay ánh sáng tạo khối 3D.

---

## 4. Một chủ thể mỗi ảnh, hạn chế bàn tay & đồng nhất tham chiếu

- **Một chủ thể / một ý mỗi ảnh:** ảnh minh họa `whiteboard` chỉ phục vụ đúng 1 tình huống đời sống. Không ghép nhiều cảnh hay nhiều bước vào một ảnh (tránh các từ như `turnaround`, `character sheet`, `multiple views`, `split screen`).
- **Ưu tiên bố cục không có bàn tay (tránh lỗi `style_hands`):** FLUX thường vẽ sai số ngón hoặc làm ngón tay dính vào giấy/vật nhỏ.
  - Ưu tiên đặt vật dụng lên mặt bàn, cắt khung trước tay, hoặc dùng góc nhìn từ xa.
  - Nếu cảnh bắt buộc có người và tay, đặt tay ở xa hoặc che một phần / khuất ngoài mép khung (vd: `"distant full-body view"`, `"arms resting behind the desk edge"`, `"hands tucked out of frame"`), tránh cận cảnh bàn tay cầm vật nhỏ.
- **Danh sách đồng nhất ngắn khi dùng ảnh tham chiếu (`--ref`):** chỉ viết câu lệnh thay đổi ở đầu + một câu giữ nhận diện cốt lõi (*"Keep the exact same character as the reference: round glasses, parted black hair, teal jacket with warm yellow badge"*).
- **Không liệt kê bộ phận nằm ngoài khung cắt:** nếu vẽ bán thân từ thắt lưng trở lên mà liệt kê cả quần và giày, mô hình sẽ tự kéo lùi camera để vẽ đủ giày.

---

## 5. Diễn đạt khẳng định & hạn chế đã biết

Thay vì liệt kê điều cấm bằng câu phủ định, hãy diễn đạt bằng trạng thái bề mặt và bố cục muốn thấy:

| Ý định | Cách viết khẳng định nên dùng |
| --- | --- |
| Không bóng nhựa / không dựng 3D | `"matte solid fills, crisp uniform navy #12304A vector outlines, completely flat 2D surface"` |
| Không nền rườm rà | `"plain flat #F7F4EC background with a single clean desk surface"` |
| Không chữ / số trên giấy, nhãn, màn hình | `"empty blank paper surfaces, plain unmarked bottle labels, blank solid-color screen"` |
| Không quá nhiều màu chói | `"limited matte palette using off-white #F7F4EC, navy #12304A, teal #18A6A6, and yellow #F4B942"` |

- **Hạn chế đã biết về chữ/số trong ảnh:** Yêu cầu "tuyệt đối không có chữ, số hay nhãn" không thể đảm bảo 100% chỉ bằng câu khẳng định. Để giảm tối đa nguy cơ mô hình tự vẽ chữ giả:
  1. Luôn mô tả khẳng định các bề mặt trống (`empty blank paper surfaces`, `unmarked plain label`, `blank display screen`).
  2. Tránh nhắc các danh từ dễ gợi ký tự (như chữ viết, bảng số liệu, tiêu đề, logo, tem chữ).
  3. Lưu ý tầng sinh ảnh `tools/flux/generate.py` vẫn có bước xử lý riêng cho ảnh không nhãn; trong prompt ở `asset-manifest.yaml`, tập trung mô tả khẳng định bề mặt trống thay vì nhồi cụm phủ định.

---

## 6. Ngoại hóa cảm xúc và thói quen bằng tư thế & vật dụng (không cận cảnh tay)

Mô hình không vẽ được tính từ trừu tượng; hãy đổi thành tư thế vai, đầu, dáng người hoặc bố cục vật dụng dễ nhìn mà không cần cận cảnh bàn tay:

- **Không viết trừu tượng:** *"người bệnh rất mệt mỏi"*, *"lo lắng về kết quả xét nghiệm"*, *"thói quen uống nhiều đường"*.
- **Đổi thành hình ảnh cụ thể, an toàn bố cục:**
  - Mệt mỏi / thiếu ngủ → *"distant side-angle view of an adult sitting on the edge of a tidy bed with slumped shoulders and head tilted gently downward, arms resting loosely out of frame behind the blanket fold"*.
  - Lo lắng trước giấy khám sức khỏe → *"top-down tabletop view of an empty blank folded paper sheet resting beside a pair of navy eyeglasses and a ceramic cup on a clean flat desk, completely empty space around the desk"*.
  - Thói quen đồ uống ngọt → *"eye-level tabletop close-up of a tall clear glass filled with amber-yellow iced tea and a teal straw resting on a coaster beside a plain glass of water"*.

---

## 7. Năm cặp ví dụ "Prompt cũ → Prompt mới" (cảnh đời sống, chuẩn Style A)

| Tình huống đời sống | Prompt cũ (mơ hồ, lệch phong cách) | Prompt mới (khẳng định, đo được khung hình, đúng Style A, không cận cảnh tay) |
| --- | --- | --- |
| **1. Tờ kết quả khám trên bàn** | `"Patient holding a lab test report with high numbers, worried, medical art"` | `"Top-down close-up of a clean desk filling the lower frame: an empty blank folded medical slip with simple geometric teal header bars rests flat beside a pair of navy eyeglasses and a warm yellow sticky tab, empty blank paper surfaces. Flat 2D vector editorial illustration, solid flat color fills, uniform navy #12304A outlines, plain flat #F7F4EC background. Flat even lighting with solid color fills. Palette limited to off-white #F7F4EC, navy #12304A, teal #18A6A6, and yellow #F4B942."` |
| **2. Thói quen đồ uống nhiều đường** | `"Person drinking sugary iced tea causing fatty liver, photorealistic, 8k"` | `"Eye-level tabletop close-up aligned straight with the table surface: a tall glass of iced tea in soft yellow with a teal straw sits centered beside a smaller plain glass of water on a clean matte table edge, cropped cleanly below the table rim. Flat 2D vector editorial illustration, solid flat color fills, uniform navy #12304A outlines, plain flat #F7F4EC background. Flat even lighting with solid color fills. Matte solid fills using #F7F4EC, #12304A, #18A6A6, and #F4B942."` |
| **3. Ngồi chờ khám buổi sáng** | `"Worried adult sitting in clinic holding medicine bag, detailed shading"` | `"Wide medium shot from head to knees: an adult in a teal shirt sits upright on a simple bench with shoulders slightly tense, arms tucked calmly behind a plain tote bag resting on the lap so hands stay hidden from view. Flat 2D vector editorial illustration, solid flat color fills, uniform navy #12304A outlines, plain flat #F7F4EC background. Flat even lighting with solid color fills. Limited palette of #F7F4EC, #12304A, #18A6A6, and yellow #F4B942 accents."` |
| **4. Góc đo huyết áp đúng tư thế tại nhà** | `"Patient checking blood pressure at home with digital screen numbers, doctor advice"` | `"Side-angle medium shot framed from head to waist: an adult sits upright with back supported against a simple navy chair, upper arm wrapped in a teal fabric cuff while the forearm rests flat on a clean desk edge with the hand extending outside the right frame border; a compact cuff monitor with a blank solid-color screen sits on the desk. Flat 2D vector editorial illustration, solid flat color fills, uniform navy #12304A outlines, plain flat #F7F4EC background. Flat even lighting with solid color fills. Palette of #F7F4EC, #12304A, #18A6A6, and #F4B942."` |
| **5. Thức khuya / giấc ngủ kém** | `"Tired man awake at night by window moonlight, dramatic shadows"` | `"Distant three-quarter wide view of a minimalist bedroom corner: an adult in a plain teal pajama top sits on the edge of a tidy bed with slumped shoulders and bowed head, arms resting out of sight behind a folded off-white blanket, with a simple warm yellow clock silhouette with a blank face on a small nightstand. Flat 2D vector editorial illustration, solid flat color fills, uniform navy #12304A outlines, plain flat #0A1C2E night background. Flat even lighting with solid color fills."` |

---

## 8. Quy tắc Hook: 3 giây đầu phải có chuyển động

Khung hình mở đầu (cảnh đầu tiên của video dài hoặc clip dọc, 3 giây đầu) **không bao giờ được đứng yên như ảnh tĩnh**:

- **Không mở bằng ảnh tĩnh trơ:** tránh để cảnh 1 chỉ chiếu một tấm ảnh `whiteboard` hoặc một sơ đồ giải phẫu đứng im chờ lời đọc.
- **Bắt buộc có chuyển động chủ đạo ngay nhịp mở:**
  1. Cảnh `whiteboard` có minh họa FLUX phải đi kèm thẻ chuyển động trong `Scene.motion` (vd: `emphasis: marker-underline-title` hoặc `lead-word-zoom-assemble`, hoặc `transition_in: crash-zoom-punch` — xem `docs/reference/motion-vocabulary.md`), kết hợp chữ `on_screen_text` vào sớm trong ≤ 10 frame đầu.
  2. Hoặc mở bằng cảnh cơ chế (`process_animation` / `comparison`) có `beats` và `CUE_ACTIONS` kích hoạt ngay từ câu đầu tiên.
  3. Hoặc mở bằng `visual: kinetic_term` / `visual: stat_gauge` (khi có `claim_id` hợp lệ) với chuyển động lắp chữ hoặc kim đo trực tiếp.
