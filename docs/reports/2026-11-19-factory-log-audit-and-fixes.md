# Báo cáo Pháp y Log, Dự báo Rủi ro & Vá lỗi Dừng xưởng — 2026-11-19

Người kiểm & tổng hợp: `verifier` (độc lập với `fix-daemon`, `fix-media`, `fix-pipeline`). Mọi số liệu dưới đây đối chiếu trực tiếp từ log, file dự án và lệnh chạy trên `E:\Protect Your Health` (`master`).

## 1. Bức tranh pháp y log & sự cố dừng xưởng lúc 15:53:58

### 1.1. Thống kê log thực tế (`topics/logs/`)
- `topics/logs/xuong.log` (`407` dòng):
  - `18` lần lỗi bước `produce` (`bước produce`), `4` lần `visual_review`, `18` lần thông báo mù `agent không làm đổi trạng thái`, `4` lần `storyboard.yaml chưa hợp lệ`, `3` lần `Estimated layout precheck failed`, `2` lần `Không còn model độc lập nào cho critic`.
  - Lỗi hệ thống/Windows/GPU: `2` lần `WinError 5` (`write_text_atomic` -> `topics/code-review.yaml`), `2` lần `WinError 32` (`.agent-running` ở `script_review`), `4` lần `os error 1455` (ACE-Step/pagefile), `2` lần `exit 3221225477` (ACE-Step CUDA), `2` lần `Cannot allocate memory` (FFmpeg contact sheet >100 nhánh `select`), `1` lần `vibi connection failed`, `3` lần `Clip CL01 render failed`, `1` lần `Generated illustration sha256 mismatch: assets/illustrations/lab-slip.png` (`2026-11-19 15:50:58`).
- `topics/logs/activity.jsonl` (`470` dòng): `237` sự kiện `start`, `229` sự kiện `end` (`173` `ok=True`, `56` `ok=False`), `4` sự kiện `quota`.
- `176` log con (`topics/logs/**/*.log`, trừ `xuong.log`): `4` file rỗng `0 byte`, `22` log bắt đầu bằng `TimeoutExpired:`, `83` log dính `UnicodeEncodeError: 'charmap' codec` (`cp1252`), `2` log `503` hết tải (`capacity`).
- `topics/logs/station-telemetry.jsonl` (`4` bản ghi ngày `2026-11-19`): `produce` / `flux` chạy trên `PID 13064` từ `15:33:54` tới `15:50:56` (**`1022.032s` ≈ 17 phút GPU**) rồi ngã `ValueError` vì `lab-slip.png`.

### 1.2. Chuỗi tự dừng kép `repair_service` + `factory` (`2026-11-19 15:50:58 -> 15:53:58`)
1. Lượt `produce` trên `thay-men-gan-...` nổ `Generated illustration sha256 mismatch: assets/illustrations/lab-slip.png` lúc `15:50:58`. Nguyên nhân gốc: bỏ `product-choice.png` và thêm `clinic-preparation.png` / `urgent-care-call.png` làm đổi `recipes_sha256`, khiến `ensure_candidates()` reset index về `round-0`, `selected: null` và chép đè `candidate-1.png` (`06d8e5a9...`) lên ảnh đã khóa `dda04433...` (bytes gốc vẫn còn tại `reviews/visual/asset-00/round-0/candidate-2.png`; lỗi tương tự cũng rình rập `prescription-review.png` khóa `a54b2067...` đang bị đè bởi `58b047e1...` trong khi bytes gốc còn ở `reviews/visual/asset-02/round-1/candidate-3.png`).
2. `repair_service` chẩn đoán xong ở `attempt 10` (`15:53:41`) và gọi `_maintenance()` -> `factory.stop_background(root)` (`TerminateProcess` giết `PID 13064`, để lại `topics/.xuong.lock` mồ côi).
3. Ngay khi `running_pid` về `None`, `_lock_factory_for_maintenance()` chỉ thử `msvcrt.locking(..., LK_NBLCK, 1)` **1 lần** trong lúc Windows chưa giải phóng xong file handle -> ném `FactoryAlreadyRunning: Xưởng đang chạy (PID đang khởi động).`.
4. Do `_lock_factory_for_maintenance` nằm ngoài khối `try: ... finally:` bật lại `xuong`, `factory.start_background(root)` không bao giờ chạy; `repair_once()` đốt `attempts: 10` thành `phase: repair_failed` và `repair_service.main()` tự thoát khi thấy xưởng tắt.

## 2. Chi tiết các bản vá đã triển khai & kiểm chứng

### 2.1. Daemon, khóa Windows & UTF-8 (`fix-daemon`)
- `src/healthvideo/workflows/repair_service.py`: bọc toàn bộ `_maintenance()` từ trước `stop_background` vào `try: ... finally:` để luôn bật lại `factory.start_background(root)` khi `was_running == True`; thêm backoff tối đa `5.0s` (`_MAINTENANCE_LOCK_RETRY_DELAYS`) trong `_lock_factory_for_maintenance` khi `running_pid` là `None`; hoàn trả `attempts` nếu lỗi hạ tầng trước khi gọi agent; cập nhật `(parent_pid, parent_token)` và giữ grace restart (`RESTARTING_STATE`, 15s) trong `main()`.
- `src/healthvideo/workflows/factory.py`: đóng stream lock an toàn trong `FactoryLock.__exit__`, chịu được tiến trình vừa thoát trong `stop_background`.
- `src/healthvideo/storage/files.py`: retry `PermissionError` (`winerror in {5, 32}`) quanh `os.replace` trong `write_text_atomic` và `read_yaml`.
- `src/healthvideo/agents.py`: mở rộng retry `_remove_job_marker` (`winerror in {5, 32, 33}`), dùng chung cho `.cancelled-*`, `.job-*.json`, `.agent-running`, `waiting-model*`.
- `src/healthvideo/env.py`: `child_env()` luôn đặt `PYTHONUTF8=1` và `PYTHONIOENCODING=utf-8`.
- `src/healthvideo/workflows/production_retry.py`: `_is_transient_production_error` nhận diện `os error 1455`, `Cannot allocate memory`, `vibi connection failed`, `3221225477`, `3221226505`, `502/503/504`, `timed out` là `transient` ngay cả khi bị bọc thành `ValueError`.

### 2.2. Bảo toàn ảnh khóa, Shorts & GPU/FFmpeg (`fix-media`)
- `src/healthvideo/workflows/visual_review.py` & `produce.py`: bổ sung `restore_locked_illustrations` chạy **trước** `referenced_storyboard_assets` & FLUX để xác minh hoặc khôi phục nguyên tử ảnh khóa `sha256` từ `reviews/visual/**/candidate-*.png` và `assets/imported/*.png`, fail closed ở `0s` nếu không tìm thấy bytes khớp, không bao giờ gọi FLUX lại hay chép đè ảnh khóa; thu hẹp `_illustrated_recipes_hash` chỉ theo các cảnh dùng minh họa và giữ ứng viên cho asset giữ nguyên `(prompt, width, height, seed)`.
- `src/healthvideo/workflows/shorts_plan.py`, `long_form.py`, `src/healthvideo/prompts/shorts_plan.md`: giữ biên `1800..2700` frames (`60–90s` gồm CTA `90f`); `save_shorts_plan` khóa dưới `revision_tx_lock` và chạy `validate_clip_plan` ngay khi lưu; `load_effective_clip_specs` kiểm `revision_hash` và fallback về `script/clip-plan.yaml` khi revision cũ chưa tương thích; `produce.py` tái kiểm clip payload trước `render_clips`.
- `src/healthvideo/workflows/produce.py`, `review_frames.py`, `tools/music/generate.py`: bọc `flux`, `Whisper`, `ACE-Step`, `Remotion` trong `gpu_mutex` kèm `gc.collect()` và dọn VRAM ở `try...finally`; chia batch FFmpeg `select` `<= 50` frame mỗi lệnh.

### 2.3. Chuẩn Style A ở Trạm 12, xóa mù lỗi & Maker/Critic (`fix-pipeline`)
- `src/healthvideo/workflows/product_review.py` & `runner.py`: bổ sung `criteria_for_revision(root)` — chỉ bắt buộc tiêu chí thứ 7 `dung_phong_cach_pyh >= 7` khi `style_a_active(revision) == True`; với revision cũ (`style_a_active == False`, gồm cả 4 dự án hiện có), `dung_phong_cach_pyh` chỉ mang tính tham khảo và không chặn Trạm 12 khi 6 tiêu chí gốc `LEGACY_CRITERIA >= 7`.
- `src/healthvideo/workflows/storyboard_design.py`, `script_review.py`, `runner.py`: tách `storyboard_validation_error` trả lỗi chi tiết; chuẩn hóa thông báo vượt `MAX_CYCLES` của Trạm 07; ghi rõ nguyên nhân gốc vào `blocked.txt` / `agent-retry.yaml` thay cho `"agent không làm đổi trạng thái"`; hỗ trợ `gpu_mutex` tái nhập cùng thread (`threading.local()`); bảo toàn lỗi nhánh song song và cô lập `waiting-model-step.yaml` trong fan-out; `_maker_slots_for_critic` chỉ loại slot vừa tạo bản nháp hiện hành.

## 3. Hiện trạng & dự báo rủi ro trên 4 dự án thật (`projects/`)

Cả 4 dự án đều có `style_a_active == False` (`LEGACY_CRITERIA` có hiệu lực tại Trạm 12). Các `paused.yaml` của 3 dự án tạm dừng vẫn giữ nguyên, xưởng đang **dừng** (`running_pid=None`, `PID 13064` đã chết).

1. **`thay-men-gan-tang-lien-voi-mua-thuoc-bo-gan-mat-gan-uong-coi`** (`medically_approved` -> `produce`, không tạm dừng):
   - `reviews/medical-approval.yaml` khớp **9/9 hash** (`reviewer: Tu`, `2026-11-19T15:33:48+07:00`).
   - Kiểm tra trên bản sao `TemporaryDirectory`: `restore_locked_illustrations` khôi phục đúng `lab-slip.png` (`dda04433...` từ `asset-00/round-0/candidate-2.png`) và `prescription-review.png` (`a54b2067...` từ `asset-02/round-1/candidate-3.png`), giữ `keep-packaging.png` (`b818a668...`), không chạm 2 ảnh chưa khóa.
   - `load_effective_clip_specs` + `load_clip_scenes` nạp sạch `posts/shorts-plan.yaml`: `CL01` (`4` cảnh, `2396f` + `90f` CTA = `2486f`), `CL02` (`4` cảnh, `1936f` + `90f` = `2026f`), `CL03` (`6` cảnh, `2258f` + `90f` = `2348f`). Lưu ý rủi ro: `CL01` (`2486f` ≈ 82.9s) gần ngưỡng 90s (`2700f`) nếu TTS thật đọc chậm hơn ước lượng.
   - Đã dọn cờ kẹt cũ (`topics/.xuong.lock`, `blocked.txt`, `production-retry.yaml`) và đặt `leader-repair.yaml` về `phase: validated` (giữ `attempts: 10`).
2. **`hoc-xuong-ca-nuot-ngay-nam-com-to-cach-chua-meo-hay-tu-day-x`** (`medically_approved`, đang `paused.yaml`): `medical-approval.yaml` khớp **9/9 hash** (`reviewer: Tu`, `2026-11-19T15:34:11+07:00`), `storyboard_validation_error == None`. Khi mở lại sẽ cần chạy FLUX + `visual_review` cho 2 minh họa chưa khóa và tạo `posts/posts.yaml` / `posts/shorts-plan.yaml`.
3. **`an-gao-lut-muoi-me-de-bo-doi-ung-thu-tu-chua-lanh-hay-tu-day`** (`draft_ready`, đang `paused.yaml`): `storyboard_validation_error == None`, có `voice-prep.yaml`; khi mở lại tiếp tục `script_review` -> cổng y khoa.
4. **`uong-1-vien-c-sui-moi-ngay-tang-de-khang-hay-tu-nuoi-soi-can`** (`draft_ready`, đang `paused.yaml`): đang vướng `storyboard_validation_error` (`whiteboard_svg=1312/9091 frames outside 11-14%`), cần `storyboard_design` sửa ngân sách hình khi mở lại.

## 4. Kết quả kiểm định sau chỉnh sửa cuối

- `ruff check src tests tools`: `All checks passed!` (exit `0`).
- `pytest tests/storage/test_files.py -q` lặp **5 lần liên tiếp**: `10 passed` cả 5 lần (`0.74s`, `0.76s`, `1.55s`, `0.49s`, `0.50s`).
- `pytest -q --tb=short -rs` (toàn bộ suite): **`2304 passed, 2 skipped, 0 failed`** (`318.07s`, exit `0`).
  - 2 test skipped có điều kiện opt-in: `tests/e2e/test_real_production_smoke.py:27` (`PYH_REAL_RENDER_SMOKE=1`) và `tests/render/test_openmontage.py:230` (OpenMontage runtime smoke).
- `git diff --check`: exit `0`; `git status --short tests/fixtures`: trống; `healthvideo status`: báo `Xưởng nền: không chạy` và đủ 4 dự án.
- Không chạy lại FLUX/ACE-Step/Vibi TTS thật hoặc bật `xuong` trong phiên kiểm định.
