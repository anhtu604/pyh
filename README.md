# Protect Your Health

## Mục tiêu

Xây dựng luồng có thể kiểm tra để biến hồ sơ và luận điểm đã được bác sĩ duyệt
thành video y tế dự phòng tiếng Việt dọc 1080 × 1920.

## Trạng thái hiện tại

CLI `healthvideo` có thể cài đặt và hiển thị phiên bản; phần domain và workflow
được triển khai theo các nhiệm vụ tiếp theo.

## Milestone

MVP hoàn thành vertical slice từ author brief, evidence, kịch bản và storyboard
đến TTS giả lập, render, hai cổng duyệt và gói xuất bản.

## Tiến độ nhiệm vụ

| Task | Deliverable | Status | Tests | Commit |
| --- | --- | --- | --- | --- |
| 1 | Bootstrap repo và CLI có thể kiểm thử | complete | `pytest tests/test_cli.py`; `ruff check src tests` | `chore: bootstrap healthvideo CLI` |
| 2 | Domain model, state machine và storage nguyên tử | planned | — | — |
| 3 | Project scaffold và author-owned voice | planned | — | — |
| 4 | Claim ledger, human script và read-aloud QA | planned | — | — |
| 5 | Storyboard, evidence highlight và render contract | planned | — | — |
| 6 | Remotion composition 9:16 và visual regression cơ bản | planned | — | — |
| 7 | TTS giả lập, manifest cache và render workflow | planned | — | — |
| 8 | Hai cổng duyệt có hash và audit trail | planned | — | — |
| 9 | Gói xuất bản và golden end-to-end test | planned | — | — |
| 10 | Installer Windows và environment doctor | planned | — | — |

## Kiến trúc

Python CLI điều phối artifact YAML/JSON theo schema. Domain thuần Python tách
khỏi TTS và renderer; Remotion nhận `render-input.json` bất biến.

## Quick start

```powershell
python -m pip install -e ".[dev]"
healthvideo version
```

## Workflow

Author brief → evidence ledger → medical review → script/storyboard → production
→ video review → publication package. Cả hai cổng duyệt của bác sĩ là bắt buộc.

## Kiểm thử gần nhất

`python -m pytest tests/test_cli.py -v` và `python -m ruff check src tests`.

## Quyết định

Tiếng Việt trước; AI chỉ chấp bút từ ý kiến bác sĩ; mọi claim y khoa cần định
danh và nguồn đã xác minh; không tự động đăng video.

## Giới hạn hiện tại

Chưa có model domain, intake nguồn, TTS, render, review, packaging hay installer.

## Tài liệu

- [Thiết kế hệ thống](docs/superpowers/specs/2026-09-07-preventive-health-video-system-design.md)
- [Kế hoạch MVP](docs/superpowers/plans/2026-09-07-preventive-health-video-mvp.md)
