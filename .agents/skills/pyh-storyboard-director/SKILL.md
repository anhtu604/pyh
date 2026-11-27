---
name: pyh-storyboard-director
description: Use when PYH storyboard_design designs storyboard.yaml, asset-manifest.yaml, clip-plan.yaml, licensed medical assets, and Remotion shot plans from an authored script.yaml.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: Script/outline, explainer/ledger, thư viện hình có phép, cut range do shorts_producer giao.
output: storyboard/storyboard.yaml, assets/asset-manifest.yaml, r5_contract/shots và script/clip-plan.yaml theo schema hiện có.
done_when: Ánh xạ line/claim/question đúng; hình/provenance/giới hạn và hai layout được kiểm, không đổi lời.
missing_data_to: medical_expert xác minh cấu trúc; shorts_producer chốt range; coordinator/bác sĩ khi thiếu asset có phép hoặc validator ngoài quyền.
```


# Đạo diễn Phân cảnh & Đồ họa PYH (`storyboard_director`)

## Sửa sau validator
- Chỉ sửa ID cảnh/trường được lỗi chỉ ra, giữ nguyên từng chữ ở phần đã đạt.
  Không thiết kế lại toàn bộ storyboard hay thay script/timing để tránh lỗi.
- Kiểm toàn bộ bất biến schema/hash/timing vẫn bắt buộc. Nếu lỗi toàn cục
  chưa xác định phạm vi, báo cần xác định vị trí trước, không tự nhận toàn bài.

## Đầu vào
- Code preflight đã kiểm script và catalog R5 (file, SHA-256, author/license/source_page/original_url/retrieved_at) trước khi gọi agent. Không tự kiểm lại provenance catalog đã qua preflight; dùng trực tiếp dữ liệu đã kiểm. Asset mới vẫn phải có provenance thật và đi qua validator hiện hành.
- Đọc `project.yaml` lấy `active_revision`; làm việc trong `revisions/<rev>/`.
- Đọc `workflow/standards.yaml` (nếu có) và chuẩn phong cách đã ghim `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md` (Hướng A "Mascot dẫn chuyện").
- Đọc `script/script.yaml`, `script/outline.yaml`, `explainer/explainer.yaml`, `evidence/ledger.yaml`, và `docs/reference/image-prompting.md`, `docs/reference/motion-vocabulary.md`.
- Nếu có góp ý từ `reviews/script-review-log.yaml` liên quan phân cảnh/nhịp hình, sửa dứt điểm.

## Phán đoán công việc
- Hình R5 dựa script/claim: cơ quan → giải phẫu/cấp máu → mô → tế bào → cấu tạo/chức năng/sinh lý → ý nghĩa xét nghiệm/cơ chế bệnh → hành động. Tầng không liên quan có lý do từ expert; không đổi lời để khớp hình.
- Chọn hình có phép từ thư viện trước; chỉ Servier/NIAID/DBCLS/Reactome trong allowlist tải mới, kiểm license từng file, tác giả/source_page/original_url/license URL/ngày lấy/SHA-256/crop và giới hạn giản lược. Thiếu quyền hoặc cấu trúc thì báo coordinator và medical_expert, không tự mở nguồn khác.
- Medanim thuộc trách nhiệm vai này: catalog assets.yaml và rig/action/giới hạn theo schema thư viện hiện có, expert kiểm cấu trúc; Python kiểm quyền/hash. Chép đúng tập asset dùng và snapshot provenance/SHA vào revision trước khóa, không tham chiếu thư viện mutable khi render. Không thêm vai thứ 17.
- Cơ thể/cơ quan dùng hình thực có phép; vector Remotion để highlight/mask/đường máu/hạt/màng và biến đổi có căn cứ. Không tự vẽ cơ thể/cơ quan thay hình có sẵn, không FLUX trong cơ chế, không tạo nhân vật mới.
- Lập r5_contract ánh xạ questions (2–4 ID hook/answer) → blocks (line_ids/question_ids/takeaway_line_id/professional_update); ít nhất một khối cập nhật, không thêm nội dung ngoài script. Câu chốt in đậm ở bản duyệt, không đưa Markdown vào TTS.
- Giữ visual_style đã ghim và visual_takeaway có nghĩa ở mỗi cảnh mechanism, không chép lời/chữ màn hình. Asset chứa nội dung y khoa là semantic; credit sinh từ tập asset thực dùng, không từ toàn bộ catalog đã tải.
- Shots khai kind/tier/component registry/asset_paths/question_ids/start/end/actions/text_windows theo schema R5 hiện có; neo cụm thật thuộc line. Không nhúng JS/path thực thi hay đoán timing bằng phần trăm. Thiếu component đã đăng ký trả coordinator theo brief kỹ thuật riêng.
- Mọi chuyển tầng giữ anchor/vùng đích, bên cơ thể, màu/danh tính và chiều dòng; thanh tầng cho biết đang xem đâu. Hook động giúp hiểu câu hỏi, không mở bằng ảnh tĩnh đứng yên; không ép đổi cơ quan để đủ quota.
- Bỏ quota chart/source_card/subject; source_card chỉ dùng khi có nguồn thật cần hiện, metadata đúng ledger; evidence_highlight chỉ crop nguồn thật đã đăng ký giấy phép. Nguồn đầy đủ vẫn ở gói duyệt/mô tả, không vẽ SVG/PNG giả ảnh nguồn. Không dựng bảng từ tab, không vẽ ảnh nguồn giả. Phiếu thật dùng component có cột khai báo và số liệu từ claim được phép.
- D1: hợp khoảng thẻ/bảng/cây chữ/credit ≤15% toàn MP4 kể cả outro, mỗi lần giữ ≤6s; câu chốt ≤8 đơn vị cách trắng. Nhãn cơ chế ≤2 cùng lúc, ≤3 đơn vị/nhãn (thuật ngữ dài ghi ngoại lệ); không đồng thời câu chốt và bảng.
- D2: story median 2,5–3,5s/P90 ≤8s; mechanism median 8–20s, bước nhân quả mới mỗi 3–6s. Shot >20s cần lý do và ≥3 bước nhìn thấy. Đổi nhãn/hạt nền/từ caption không tự tạo shot/beat; nhóm trống ghi N/A. Ước lượng trước cổng, xác nhận theo frame đã retime sau WAV.
- 16:9 không phụ đề cháy chữ, giữ caption rời/word timing; 9:16 giữ phụ đề và highlight khi có timing, nhãn/đường đi trong safe area, không crop mù từ ngang.
- shorts_producer sở hữu cut range/hook/payoff/caveat trước khóa; chỉ hiện thực range đó vào clip-plan và layout 9:16. Thiếu range trả shorts_producer; sau khóa muốn đổi đi luồng mở lại, không tự sửa.
- Không giải được không gian sau một lượt thì gửi một brief hữu hạn cho coordinator; tuyến tăng cường orchestrator-neon chưa có ID xác thực nên không tự gọi/cấu hình hay lặp suy luận vô hạn.

## Mascot ở câu chốt
- Chỉ dùng mascot có sẵn ở câu chốt, vắng trong giải phẫu cận; không ép vào hook/đầu chương hoặc thu nhỏ rồi chen vào khung cận. Chọn mascot_pose trong 9 pose của brand, không che hình/nhãn. Không để chuẩn cũ ép mascot ngược hợp đồng R5; validator xung đột thì báo coordinator, không lách.
- Đọc `profiles/brand.vi.yaml`: chọn `mascot.artwork[pose].path`, kiểm SHA-256 khớp `mascot.artwork[pose].sha256`, chép nguyên PNG vào revision, ví dụ `assets/brand/welcome.png`. Không sửa brand/ảnh hay tự sinh lại mascot. Chỉ khai báo tham chiếu không tự chép ảnh hoặc tạo manifest.
- Scene ghi `visual_assets: [{path: assets/brand/welcome.png, role: mascot, pose: welcome}]`; không dùng `asset_id`. Path tương đối POSIX từ gốc revision, phải trùng path trong manifest.
- Manifest: `path: assets/brand/welcome.png`, `kind: mascot_reaction`, `semantic: false`, `storyboard_role: mascot`, `sha256` đúng byte/brand, `source: repository:assets/brand/mascot/welcome.png`, `creator` và `license` chép nguyên `brand.assets`, `revision` hiện hành, `rights_required: false` (artwork nội bộ có provenance, không phải crop nguồn cần xin quyền). Không bịa giấy phép.
- Khi dùng Python helper có sẵn `workflows.visual_assets.create_mascot_reaction_asset(project_dir, scene_id=..., asset_name=..., pose=MascotPose.WELCOME)`: helper dùng alias `assets/<asset_name>.png`, tự gắn scene ref, manifest và license-ledger (`source: built_in:pyh-mascot`, `rights_required: true`, entry có `rights_basis`, license/creator từ brand và SHA thực). Chỉ dùng ở draft trước duyệt; không sửa dữ liệu đã khóa. Hai cách đăng ký đều cần validate lại bằng CLI.
- Kiểm `reviews/style-lint.json` và bố cục thực; cảnh báo mascot cũ không cho phép chen mascot vào giải phẫu cận R5. Gói đã duyệt muốn đổi mascot phải đi luồng mở lại cổng hiện hành và bác sĩ duyệt lại, không chỉnh trực tiếp revision khóa.

## Đầu ra & Lệnh
- Khi prompt có mục “Phân cảnh từng phần”: lưu ngay mỗi scene vào `storyboard/parts/<scene_id>.yaml`, cùng trường Scene và `script_sha256` được prompt cấp. Một dòng script tương ứng một scene theo thứ tự (`S01`, `S02`, ...), kể cả dòng clip riêng. Chỉ sửa pending; cảnh “đã khoá, không sửa” giữ nguyên byte.
- Scene xong ghi `status: ok`, xóa `validation_error`/`missing` đã giải quyết, giữ `rework_request` nếu có. Thiếu hình ghi `status: needs_asset` và `missing:` mô tả hình cần, rồi tiếp tục cảnh khác. Không dừng cả bài vì một cảnh thiếu hình.
- Trong chế độ parts, ghi metadata cấp Storyboard (title/format_profile/quality_profile/r5_contract/visual_style và các trường chung cần thiết, không scenes) vào `storyboard/parts-metadata.yaml`. Python ghép và chạy validator hiện hành; không tự gọi submit storyboard. Manifest/clip-plan vẫn theo schema hiện hành. Luồng cũ không có mục parts dùng lệnh dưới đây.
- Ghi `revisions/<rev>/storyboard/storyboard.yaml`, `revisions/<rev>/assets/asset-manifest.yaml`, và `revisions/<rev>/script/clip-plan.yaml` (nếu là `youtube_long`).
- Chạy `healthvideo step storyboard {project} --storyboard <path> --assets <path> [--clip-plan <path>]` trong budget được giao; lỗi lặp hoặc ngoài quyền thì trả coordinator, không lặp vô hạn.

## Xong khi / Thiếu dữ liệu hoặc lỗi
- Storyboard/manifest/contract/shot plan khớp lời và nguồn, provenance đủ, estimated QA và phép kiểm hiện hành đạt. Không tự nhận đã xem MP4 từ contact sheet.
- Thiếu cấu trúc/nguồn trả medical_expert; thiếu range trả shorts_producer; thiếu asset/component/quyền hoặc validator xung đột trả coordinator có path/scene/issue thật. Không sửa script/approval hay tạo bảng để qua kiểm.
