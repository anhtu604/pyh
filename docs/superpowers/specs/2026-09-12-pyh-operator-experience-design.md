# Thiết kế trải nghiệm vận hành `/pyh`

**Ngày:** 12-09-2026  
**Trạng thái:** Implemented (offline operator milestone, 12-09-2026)
**Phạm vi:** Tối giản cách vận hành Protect Your Health trên Codex và Claude Code, tận dụng M1–M3

## 1. Mục tiêu

Protect Your Health là một xưởng sản xuất video y khoa dự phòng local-first. Bác sĩ điều khiển xưởng bằng một lệnh `/pyh`, chọn chủ đề, chốt thông điệp, duyệt nội dung y khoa và duyệt video. Python và Remotion thực hiện những bước xác định; Codex hoặc Claude Code hiểu yêu cầu, điều phối và trình bày kết quả.

Thay đổi này tối giản trải nghiệm, không viết lại hệ thống. Nó giữ topic discovery, evidence ledger, provenance, revision, hash, invalidation, render cache và hai cổng duyệt đã hoàn thành trong M1–M3.

## 2. Kết quả cần đạt

Một người dùng mới có thể bắt đầu bằng:

```text
/pyh tìm chủ đề cho tuần này
```

hoặc:

```text
/pyh làm video 60 giây về ăn mặn và tăng huyết áp
```

Sau đó người dùng chỉ cần chọn chủ đề, thống nhất brief, duyệt nội dung và duyệt video. Người dùng không phải biết schema version, revision ID, state graph hay các lệnh Python nội bộ.

Luồng chuẩn:

```text
Khám phá chủ đề hoặc nhập chủ đề
  -> bác sĩ chọn chủ đề
  -> bác sĩ chốt editorial/author brief
  -> tìm và tổng hợp bằng chứng
  -> soạn kịch bản và storyboard
  -> bác sĩ duyệt y khoa
  -> tạo audio, phụ đề và video từ template
  -> bác sĩ duyệt video
  -> tạo gói đăng thủ công
```

## 3. Nguyên tắc

1. `/pyh` là cửa vào duy nhất cho hoạt động hằng ngày.
2. Artifact trong repo là nguồn sự thật; lịch sử chat không phải nguồn sự thật.
3. Agent điều phối nhưng không tự duyệt, tự xác minh nguồn thiếu bằng chứng hay tự xuất bản.
4. Project mới dùng schema v2. Khả năng đọc và migrate v1 được giữ trong đường bảo trì.
5. Template mặc định phải tạo được video hoàn chỉnh trước khi hệ thống thêm template hoặc provider mới.
6. Một trạng thái, schema hay abstraction mới chỉ được thêm khi đường chạy nghiệm thu cần nó.
7. Mọi chỉnh sửa sau duyệt phải dùng invalidation hiện có để quay lại đúng cổng.

## 4. Giao diện `/pyh`

### 4.1 Một workflow chuẩn, hai adapter mỏng

Repo lưu một workflow chuẩn cho `pyh`. Adapter Codex và adapter Claude Code chỉ chuyển yêu cầu vào workflow này. Chúng không nhân đôi quy tắc nghiệp vụ. Cả hai gọi chung Python core và đọc cùng artifact project.

Các cách gọi chính:

```text
/pyh tìm chủ đề
/pyh tìm chủ đề về tăng huyết áp
/pyh chọn chủ đề 3
/pyh làm video về ăn mặn và tăng huyết áp
/pyh tiếp tục
/pyh sửa câu kết ngắn và ít tuyệt đối hơn
/pyh mở bản duyệt y khoa
/pyh duyệt nội dung
/pyh duyệt video
/pyh tạo gói đăng
```

`/pyh` diễn giải ngôn ngữ tự nhiên, tìm project phù hợp và chọn hành động hợp lệ tiếp theo. Khi có nhiều project đang hoạt động, nó trình bày danh sách ngắn để người dùng chọn. Nó không đoán project.

### 4.2 Quy tắc approval

Các câu như “ổn”, “tiếp tục” hoặc “render đi” không tạo approval. Trước khi ghi approval, `/pyh` phải:

- mở hoặc chỉ rõ packet đang được duyệt;
- nêu loại duyệt và revision hoặc hash rút gọn;
- nhận quyết định rõ ràng từ người dùng;
- ghi reviewer, thời điểm và ghi chú;
- dùng workflow approval hiện có.

Agent không đứng tên bác sĩ. Hệ thống không gộp bước chốt brief với medical approval.

## 5. Khám phá, chọn và chốt chủ đề

### 5.1 Khám phá

`/pyh tìm chủ đề` dùng topic inbox và nguồn được phép, khả dụng. Nó khử trùng lặp và trình bày mỗi topic card bằng:

- câu hỏi hoặc hiểu nhầm của công chúng;
- giá trị dự phòng;
- nhóm khán giả;
- nguy cơ nếu truyền đạt sai;
- mức sẵn sàng của bằng chứng;
- độ mới và hạn sử dụng;
- góc video đề xuất;
- lý do đề xuất.

Triage score sắp xếp đề xuất nhưng không thay người dùng chọn chủ đề. Hệ thống không phụ thuộc vào scraping dễ vỡ làm đường chính.

### 5.2 Chọn chủ đề

`/pyh chọn chủ đề <số hoặc slug>` tạo hoặc cập nhật project v2 bằng topic card đã chọn. Agent không tự chọn topic có điểm cao nhất và không tự chuyển thẳng sang sản xuất.

### 5.3 Chốt nội dung

Trước khi nghiên cứu sâu, `/pyh` cùng bác sĩ chốt một editorial/author brief ngắn:

- câu hỏi chính;
- đối tượng xem;
- lập trường hoặc điểm bác sĩ muốn phản biện;
- thông điệp cần nhớ;
- hành động an toàn;
- phạm vi và điều không được nói;
- thời lượng và phong cách.

Agent tận dụng dữ liệu người dùng đã cung cấp và chỉ hỏi từng câu còn thiếu có ảnh hưởng đáng kể. Nó không tự thêm trải nghiệm, cảm xúc hay quan điểm cá nhân của bác sĩ. Brief được lưu thành artifact và phải được người dùng xác nhận trước bước nghiên cứu sâu.

## 6. Điều phối nội bộ

Một coordinator mỏng nối các workflow hiện có. Nó không tái cài đặt nghiệp vụ.

Giao diện dự kiến:

```python
get_next_action(project_dir)
run_next(project_dir)
summarize_status(project_dir)
```

Coordinator ánh xạ trạng thái kỹ thuật sang hành động dễ hiểu:

| Tình trạng | Hành động hiển thị |
|---|---|
| Chưa có project | Tạo video hoặc tìm chủ đề |
| Có topic, brief chưa chốt | Thống nhất nội dung |
| Brief đã chốt, evidence chưa đủ | Nghiên cứu và kiểm tra nguồn |
| Chờ medical gate | Bác sĩ duyệt nội dung |
| Đã duyệt y khoa | Sản xuất video |
| Chờ video gate | Bác sĩ xem và duyệt video |
| Đã duyệt video | Tạo gói đăng |
| Artifact đổi hoặc bước lỗi | Sửa đúng artifact hoặc quay lại đúng gate |

`run_next` chạy đến điểm dừng tự nhiên kế tiếp, không chạy xuyên qua quyết định của bác sĩ. Mỗi lần chạy phải idempotent khi đầu vào và artifact hash không đổi.

## 7. Dữ liệu người dùng nhìn thấy

Mỗi project có một `STATUS.md` được sinh từ artifact chuẩn. File này không trở thành nguồn trạng thái mới. Nó chỉ trình bày:

- tên và chủ đề video;
- tiến độ bằng ngôn ngữ thông thường;
- artifact gần nhất để xem;
- việc đang chờ người dùng hoặc hệ thống;
- ví dụ lệnh `/pyh` phù hợp tiếp theo;
- lỗi và cách xử lý nếu có.

Các đầu ra thuận tiện:

```text
projects/<slug>/
├── STATUS.md
├── review/
│   ├── medical.html
│   └── video.html
├── preview/
│   └── video.mp4
└── publish/
    ├── video.mp4
    ├── caption.txt
    ├── sources.md
    └── manifest.json
```

Schema, revision, manifest và audit record vẫn nằm trong layout v2 hiện có. Các đường dẫn tiện dụng trên có thể là bản sao dẫn xuất hoặc chỉ mục; chúng không được tạo hai nguồn sự thật.

## 8. Evidence và biên tập

Sau khi brief được xác nhận, workflow:

1. chuyển câu hỏi thành PICO khi phù hợp;
2. tìm guideline, systematic review và nghiên cứu then chốt qua nguồn cho phép;
3. kiểm tra định danh và trạng thái rút bài;
4. ghi search log, nguồn chọn và nguồn loại;
5. lập evidence ledger;
6. tạo kịch bản và storyboard từ ledger cùng brief;
7. kiểm tra claim–citation trước medical gate.

Không có DOI, PMID, số liệu hoặc trải nghiệm nghề nghiệp nào được suy đoán. Khi không đủ bằng chứng, `/pyh` báo thiếu gì và đề nghị thu hẹp, đổi góc hoặc loại chủ đề.

## 9. Sản xuất video

Đường chạy đầu tiên dùng một template dọc 9:16 ổn định. Template hỗ trợ lời thoại, phụ đề, evidence marker, whiteboard/SVG và biểu đồ từ dữ liệu đã kiểm tra. Nó tái sử dụng Remotion renderer, TTS adapter và cache hiện có.

Hệ thống chỉ sản xuất sau medical approval hợp lệ. Bản mặc định ưu tiên kết quả nhất quán hơn sự biến đổi hình ảnh. Chế độ custom chỉ cho phép thay giọng, template hoặc một số cảnh; mọi thay đổi vẫn chịu quy tắc invalidation.

## 10. Tương thích và tái cấu trúc

- Project mới luôn dùng v2.
- Project v1 vẫn đọc và chạy được trong giai đoạn chuyển tiếp.
- Migration v1 sang v2 vẫn không ghi đè nguồn và không tự giữ approval khi không chứng minh được equivalence.
- `/pyh` phát hiện v1 và hướng dẫn migration; người dùng hằng ngày không chọn schema.
- Logic compatibility được cô lập dần vào resolver hoặc module migration. Tính năng mới không thêm nhánh v1 trừ khi cần để bảo toàn dữ liệu hiện có.
- `cli.py` được tách thành nhóm lệnh mỏng nhưng giữ entry point và hành vi công khai hiện tại.

Việc tái cấu trúc phải giữ failure behavior, ordering, audit trail và các gate hiện có. Không xóa v1 trong phạm vi này.

## 11. Lỗi và phục hồi

Mỗi lỗi phải trả lời ba câu:

1. Bước nào chưa hoàn thành?
2. Artifact nào thiếu, sai hoặc hết hiệu lực?
3. Người dùng nên gọi `/pyh` thế nào tiếp theo?

Lỗi nguồn, mạng hoặc provider không được làm mất artifact đã xác minh. Workflow tiếp tục từ checkpoint. Unknown change tiếp tục fail closed về medical gate theo policy hiện có.

## 12. Phạm vi triển khai

### Thực hiện

- workflow chuẩn `pyh` và hai adapter Codex/Claude Code;
- coordinator và project resolver;
- hai điểm bắt đầu: discovery hoặc chủ đề trực tiếp;
- bước xác nhận editorial/author brief;
- `STATUS.md` dẫn xuất;
- một template video mặc định;
- chia nhỏ CLI mà không phá giao diện;
- Quick Start không dài quá một màn hình;
- acceptance test cho toàn bộ vòng đời.

### Không thực hiện

- web app hoặc SaaS;
- tự đăng TikTok;
- kho nhiều template;
- framework agent routing M4 tổng quát;
- tích hợp mọi TTS hoặc video provider;
- scraping nguồn bị hạn chế;
- xóa v1 hoặc viết lại toàn bộ core;
- server nhiều người dùng hay tối ưu phân tán.

## 13. Nghiệm thu

Một golden project phải hoàn thành đường chạy:

```text
/pyh tìm chủ đề
  -> chọn chủ đề
  -> chốt brief
  -> tạo evidence ledger và script
  -> mở medical packet
  -> ghi medical approval
  -> tạo video bằng template
  -> mở video packet
  -> ghi video approval
  -> tạo publish package
```

Các bằng chứng bắt buộc:

- Codex và Claude Code có thể tiếp tục cùng một project;
- `/pyh tiếp tục` luôn chọn đúng hành động kế tiếp;
- không có nguồn hoặc số liệu thật bị bịa;
- thay đổi artifact làm approval tương ứng hết hiệu lực;
- không có bước tự duyệt hoặc tự xuất bản;
- CLI cũ vẫn hoạt động;
- focused tests, full Python regression, lint và các kiểm tra video liên quan đều đạt;
- workflow chạy offline với fixture đông lạnh, trừ discovery trực tuyến và TTS thật.

## 14. Tiêu chí dừng

Kết thúc milestone khi một video mẫu đi hết vòng đời bằng `/pyh` và các bằng chứng nghiệm thu đạt. Không thêm abstraction, provider hoặc template chưa cần cho đường chạy này. Mọi mở rộng tiếp theo phải bắt đầu từ vướng mắc quan sát được khi sản xuất video thật.
