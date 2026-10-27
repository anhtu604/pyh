# Quy tắc viết prompt ảnh FLUX.2 klein & Hook chuyển động

Tài liệu này đúc kết quy tắc viết prompt cho ảnh minh họa y khoa phẳng (`FLUX.2-klein-4B`, chạy qua `tools/flux/generate.py`) và quy tắc dựng cảnh mở đầu (hook), tổng hợp và viết lại cho bối cảnh giải thích y khoa từ kinh nghiệm thực nghiệm của bộ `shuohao-skills` (Apache-2.0, eternityspring).

---

## 1. Câu đầu tiên quyết định khung hình (Framing First)

Mô hình sinh ảnh và sửa ảnh theo tham chiếu ưu tiên tuyệt đối câu đầu tiên cho bố cục. Nếu chỉ viết chung chung (`close-up`, `front view`), mô hình dễ lùi máy ra góc trung cảnh hoặc xoay nghiêng 20–30°.

- **Đặt khung hình có thể đo được ngay câu mở đầu**: nêu rõ cỡ cảnh, góc máy, tỉ lệ chủ thể chiếm khung và vị trí mép cắt (vd: *"Extreme close-up top-down view of a right foot: the big toe joint fills two-thirds of the frame, cropped just above the ankle"*).
- **Lượng hóa góc nhìn hình học**: thay vì chỉ viết *"nhìn thẳng"*, hãy chỉ rõ dấu hiệu hình học (*"camera level with the joint, both sides of the foot contour equally visible"*).
- **Nhắc lại mép cắt ở câu cuối nếu prompt dài**: khi phần tả chi tiết ở giữa dài hơn 2–3 câu, mô hình dễ quên lệnh phóng gần ở đầu. Chốt lại bằng một câu ngắn (*"Framing reminder: cropped at the ankle, no lower leg or background room in frame"*).

---

## 2. Tả hiệu ứng ánh sáng, không gọi tên nguồn sáng

Mọi danh từ chỉ vật thể xuất hiện trong prompt đều có nguy cơ bị vẽ vào khung hình.

- **Không gọi tên nguồn sáng hay đạo cụ ánh sáng**: tránh viết *"ánh sáng từ cửa sổ"*, *"đèn phòng khám"*, *"đèn bàn"* — mô hình sẽ vẽ thêm khung cửa sổ hoặc bóng đèn làm rối nền.
- **Chỉ tả hiệu ứng ánh sáng trên bề mặt chủ thể**: viết hướng sáng, độ mềm và vùng chuyển tông (vd: *"soft directional key light from the upper left with gentle fill, clean flat cel-shading and crisp contour lines on a plain warm cream background"*).

---

## 3. Một chủ thể mỗi ảnh & danh sách đồng nhất ngắn

- **Một chủ thể / một ý mỗi ảnh**: ảnh minh họa `whiteboard` chỉ phục vụ đúng 1 trạng thái lâm sàng hoặc 1 hành động đời thường. Không ghép nhiều cảnh hay nhiều bước cơ chế vào một ảnh (tránh các từ `turnaround`, `character sheet`, `multiple views`, `split screen`).
- **Danh sách đồng nhất ngắn khi dùng ảnh tham chiếu (`--ref`)**: chỉ viết câu lệnh thay đổi ở đầu + một câu giữ nhận diện cốt lõi (*"Keep the exact same character as the reference: round glasses, parted black hair, teal jacket with yellow badge"*).
- **Không liệt kê bộ phận nằm ngoài khung cắt**: nếu vẽ cận cảnh bàn tay hoặc cổ áo mà liệt kê cả quần và giày trong câu đồng nhất, mô hình sẽ tự kéo lùi camera để vẽ đủ giày.

---

## 4. Từ khóa phong cách phẳng & chống "mùi AI"

- **Hậu tố cấm chữ đã tự động gắn**: `tools/flux/generate.py` luôn tự nối câu `"Unlabeled illustration only. No text, letters, numbers, anatomical labels or captions."` vào cuối mọi prompt. Khi viết prompt trong `asset-manifest.yaml`, vẫn nên giữ cụm ngắn `no text` và tuyệt đối không yêu cầu vẽ nhãn, con số hay mũi tên chữ.
- **Định hướng phong cách phẳng 2D sạch**: dùng cụm *"clean 2D flat medical vector illustration, bold uniform dark-navy outline, 4-tone cel shading, warm cream background"*.
- **Từ khóa tránh cảm giác CG / "mùi AI"**: tránh các từ kéo ảnh về 3D bóng nhựa hoặc ảnh chụp gắt (`photorealistic`, `3D render`, `plastic skin`, `waxy skin`, `hyper-symmetry`, `HDR`, `oversaturated neon glow`, `shallow depth of field`, `skin pores`). Trong prompt FLUX, diễn đạt trực tiếp bằng cụm khẳng định cuối câu: *"flat matte colors, no 3D render, no plastic sheen, no HDR or oversaturation"*.

---

## 5. Ngoại hóa triệu chứng và cảm xúc bằng hành vi cơ thể

Mô hình không vẽ được tính từ trừu tượng hay mức độ nội tâm; phải đổi thành tư thế tay, vai, mặt có thể nhìn thấy:

- **Không viết trừu tượng**: *"bệnh nhân rất đau"*, *"cảm giác mệt mỏi nặng nề"*, *"lo lắng về xét nghiệm"*.
- **Đổi thành hành động cơ thể**:
  - Đau khớp cấp → *"both hands gently cradling the swollen red big toe without touching it directly, shoulders hunched forward, eyebrows drawn together"*.
  - Mệt mỏi / mất ngủ → *"sitting on the edge of the bed with slumped shoulders, one hand rubbing the bridge of the nose, head tilted down"*.
  - Khó thở / tức ngực → *"one open palm pressed flat against the center of the chest, torso leaning slightly forward"*.

---

## 6. Năm cặp ví dụ "Prompt cũ → Prompt mới" (chủ đề y khoa, không chữ/số)

| Chủ đề | Prompt cũ (mơ hồ, dễ lỗi) | Prompt mới (đo được khung hình, 1 chủ thể, phẳng sạch) |
| --- | --- | --- |
| **1. Cơn gout cấp ở ngón chân cái** | `"A very painful gout attack on a big toe with red inflammation and uric acid crystals, medical illustration"` | `"Close-up three-quarter view of a bare foot resting on a white sheet, the big toe joint filling the center of the frame and cropped above the ankle. The first metatarsophalangeal joint is visibly swollen, rounded, and warm coral-red compared to the normal toes. Clean 2D flat medical illustration, bold dark-navy outline, soft directional shading on a plain cream background, flat matte colors, no 3D plastic sheen, no text."` |
| **2. Người bệnh thức giấc vì đau khớp đêm** | `"An adult man in bedroom at night feeling extreme pain in his foot from gout by window moonlight"` | `"Medium shot from the waist to the feet: an adult man sits on the edge of a bed, leaning forward with both hands hovering protectively around his reddened right big toe, brows furrowed and jaw clenched. Cool dim ambient light with a warm highlight on the swollen joint, plain muted background without furniture clutter. Clean 2D flat vector illustration, matte cel-shading, no text."` |
| **3. Gan nhiễm mỡ (bối cảnh đời sống)** | `"Fatty liver disease caused by metabolic syndrome and sugary drinks, photorealistic medical art, 8k HDR"` | `"Medium close-up at table level: a torso-up view of an adult holding a tall glass of iced sweet tea, looking down thoughtfully, cropped at the waist. Soft directional light from the left creating gentle volume on the clothing, plain warm off-white background. Clean 2D flat editorial illustration, uniform line art, matte palette, no 3D render, no oversaturation, no text."` |
| **4. Đo huyết áp đúng tư thế tại nhà** | `"Patient checking blood pressure at home with a monitor on table, doctor advice style"` | `"Side-angle medium shot framed from head to waist: an adult sits upright with back supported against a chair, left forearm resting flat on a table at heart level with a fabric cuff wrapped around the bare upper arm. Calm relaxed posture, shoulders level. Clean 2D flat medical illustration, warm cream background, matte colors, no numbers or screen readouts, no text."` |
| **5. Cận cảnh vùng gót chân / cổ chân sưng** | `"Swollen ankle joint and Achilles tendonitis, close up view"` | `"Extreme close-up profile view of a human ankle and heel filling the frame, cropped at the mid-calf and midfoot so no face or torso is in frame. The posterior heel contour is visibly puffed and shaded in warm coral-red. Clean 2D flat medical illustration, crisp outline, soft two-tone shading on a plain cream background, no text. Framing reminder: only the ankle and heel in frame."` |

---

## 7. Quy tắc Hook: 3 giây đầu phải có chuyển động

Khung hình mở đầu (cảnh đầu tiên của video dài hoặc clip dọc, 3 giây đầu) **không bao giờ được đứng yên như ảnh tĩnh**:

- **Không mở bằng ảnh tĩnh trơ**: tránh để cảnh 1 chỉ chiếu một tấm ảnh `whiteboard` hoặc một sơ đồ giải phẫu đứng im chờ lời đọc.
- **Bắt buộc có chuyển động chủ đạo ngay nhịp mở**:
  1. Cảnh `whiteboard` có minh họa FLUX phải đi kèm thẻ chuyển động trong `Scene.motion` (vd: `emphasis: marker-underline-title` hoặc `lead-word-zoom-assemble`, hoặc `transition_in: crash-zoom-punch` — xem `docs/reference/motion-vocabulary.md`), kết hợp chữ `on_screen_text` vào sớm trong ≤ 10 frame đầu.
  2. Hoặc mở bằng cảnh cơ chế (`process_animation` / `comparison`) có `beats` và `CUE_ACTIONS` kích hoạt ngay từ câu đầu tiên.
  3. Hoặc mở bằng `visual: kinetic_term` / `visual: stat_gauge` (khi có `claim_id` hợp lệ) với chuyển động lắp chữ hoặc kim đo trực tiếp.
