---
name: video-understand
description: Optional local video inspection tool using ffmpeg frame extraction and Whisper transcription outside the default product_review path.
---

# video-understand (PYH-Scoped)

## Ràng buộc PYH (bắt buộc)
- Đây chỉ là công cụ điều tra thủ công theo yêu cầu, **không** phải điều kiện tiên quyết của `product_review`.
- Khi `renders/video-qa.json`, `renders/pronunciation-qa.json`, hoặc `review-frames/index.json` đã có sẵn từ Python, **không** tự chạy lại Whisper hay trích khung hình thừa (tránh tranh chấp GPU với FLUX/ACE-Step/Remotion).

## Manual Usage (When Explicitly Requested)

```powershell
# Inspect media metadata via ffprobe
ffprobe -v error -show_format -show_streams video.mp4
```

Only extract key frames or run local Whisper when diagnosing an explicit rendering or audio discrepancy not already covered by `video-qa.json` and `review-frames/index.json`.
