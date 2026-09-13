# M5.3 — Xác minh VieNeu-TTS v3 Turbo và benchmark khách quan

Ngày: 13-09-2026. Phạm vi: nối provider thật vào `CommandTTS` (M5.2) qua một
wrapper cục bộ, chạy benchmark có tiêu chí đo được, ghi kết quả thật. Không đổi
`healthvideo produce` (vẫn `--tts silent`), không thêm ASR, chuẩn hóa audio,
ElevenLabs, workflow engine, approval hay auto-publish.

## 1. Môi trường máy (kiểm tra 13-09-2026)

| Hạng mục | Kết quả |
|---|---|
| GPU | NVIDIA GeForce RTX 3060, 12288 MiB, driver 610.74 |
| Python dự án | `.venv` Python 3.11.15 (hệ thống có 3.14.3) |
| FFmpeg | 8.1.1-full_build (gyan.dev) |
| Trình quản lý gói | `uv` tại `~/.local/bin/uv` |
| Đã có sẵn | Không có torch, vieneu, cache Hugging Face hay biến môi trường ElevenLabs |

## 2. Nguồn và giấy phép ứng viên (kiểm tra 13-09-2026)

| Thành phần | Định danh đã ghim | Giấy phép | Ghi chú |
|---|---|---|---|
| Source SDK | GitHub `pnnbao97/VieNeu-TTS`, tag `v3.6.4` (commit `4d61586`) | Apache-2.0 (`LICENSE` repo) | README gọi v3 Turbo là bản open-source mới nhất; v4 proprietary chỉ qua vieneu.io |
| PyPI | `vieneu==3.6.4`, `requires-python >=3.10` | Apache-2.0 | Core torch-free: `sea-g2p`, `onnxruntime`, `numpy`, `soundfile`, `soxr`, `kaldi-native-fbank`, `tokenizers`, `huggingface_hub`, `PyYAML`, `gradio`, `librosa` |
| Model | HF `pnnbao-ump/VieNeu-TTS-v3-Turbo`, revision `8b7e9cffb4b41918cb638b9f62f0a751184d14a6` (cập nhật 05-09-2026) | `license: apache-2.0` trong model card | FAQ của model card ghi rõ: Apache-2.0 áp cho weights, ONNX, tokenizer và preset voices; audio tạo từ preset voice được dùng cho nội dung thương mại/kiếm tiền; người nói preset đã đồng ý. Voice clone từ clip riêng là trách nhiệm người dùng |
| Codec | `OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano` | Apache-2.0 (theo model card VieNeu) | Giữ notice khi phân phối lại |

Điểm cần lưu ý: README source gọi v3 Turbo là "on-device version for personal
use" (câu marketing phân biệt với bản server), nhưng cả LICENSE và model card
đều là Apache-2.0 không giới hạn mục đích. Ghi lại để bác sĩ/chủ kênh cân nhắc;
không phải rào cản pháp lý theo văn bản giấy phép hiện hành. Đầu ra 48 kHz mono
đã nằm trong tập `inspect_wav` chấp nhận.

## 3. Cách nối (không thêm adapter mới)

- Môi trường TTS tách khỏi `.venv` dự án: `cache/tts-venv` (đã gitignore),
  `uv pip install vieneu==3.6.4` (ONNX/CPU, không torch). GPU/PyTorch để sau
  nếu RTF CPU không đạt.
- `tools/tts/vieneu_synth.py --input {input} --output {output} [--voice Adam]
  [--backend onnx|auto]`: đọc UTF-8, gọi `Vieneu().infer`, ghi PCM16 48 kHz mono.
  Phần thuần (`write_pcm16_wav`, `synthesize_file`) có test trong `.venv` dự án.
- Chạy qua `CommandTTS(executable=<tts-venv python>, arguments=(..., "{input}",
  ..., "{output}"), model_id="vieneu-v3-turbo", voice_id=<preset>,
  runtime_id="onnx-cpu")` — định danh cache/manifest chỉ là alias công khai.

## 4. Tiêu chí đo khách quan (gate M5.3)

`healthvideo tts-benchmark tests/fixtures/tts-benchmark-cases.yaml --output cache/tts-benchmark ...`
ghi `benchmark.json` và trả exit 1 nếu bất kỳ case nào trượt:

| Tiêu chí | Ngưỡng | Lý do |
|---|---|---|
| Tổng hợp thành công | 12/12 case `ok` | Lỗi runtime/WAV hỏng là loại ngay |
| Định dạng WAV | PCM 16-bit, 24 hoặc 48 kHz, có tín hiệu | `inspect_wav` với `require_signal` |
| Realtime factor | `elapsed_ms / duration_ms ≤ 1.0` | Một video 60 s phải tổng hợp dưới 60 s trên máy này |
| Tốc độ đọc | 1,5–5,0 từ/giây | Phát hiện cắt cụt hoặc im lặng kéo dài |

Không đo và không suy ra: phát âm đúng tên thuốc/số, tự nhiên, cảm xúc. Việc đó
cần ASR back-check (M5.4) và bác sĩ nghe duyệt; không ghi bất kỳ điểm chất lượng
nào vào repo cho đến khi có.

## 5. Kết quả thật (13-09-2026, i5-13500, ONNX CPU, `vieneu==3.6.4`, voice preset `Adam`)

Lệnh đã chạy (từ gốc worktree, `HF_HUB_DISABLE_SYMLINKS_WARNING=1`):

```powershell
& .venv\Scripts\healthvideo.exe tts-benchmark tests\fixtures\tts-benchmark-cases.yaml `
  --output cache\tts-benchmark-fp32 `
  --command (Resolve-Path cache\tts-venv\Scripts\python.exe) `
  --arg (Resolve-Path tools\tts\vieneu_synth.py) --arg --input --arg "{input}" `
  --arg --output --arg "{output}" --arg --backend --arg onnx --arg --precision --arg fp32 `
  --model-id vieneu-v3-turbo --voice-id adam --runtime-id onnx-cpu-fp32 --max-rtf 1.0
```

Bộ case có 12 câu lẻ (7–41 từ) và `bai-ghep` = 12 câu ghép lại (185 từ), gần với
cách `produce` gọi TTS một lần cho cả bài (`workflows/produce.py`).

| Chỉ số | fp32 | int8 |
|---|---|---|
| Tổng hợp thành công / WAV PCM16 48 kHz có tín hiệu | 13/13 | 13/13 |
| Tốc độ đọc (từ/giây), min–max | 2,73–4,49 | 2,89–4,76 |
| Chi phí cố định mỗi lần gọi (câu 1,4–1,6 s audio) | ≈8,5 s | ≈7,8 s |
| RTF câu lẻ, min–max | 1,25–5,31 | 1,10–5,72 |
| `bai-ghep`: thời lượng audio / thời gian tổng hợp / RTF | 49,2 s / 27,1 s / **0,55** | 46,1 s / 21,0 s / **0,46** |
| Case đạt gate `--max-rtf 1.0` | 1/13 | 1/13 |

Đọc kết quả:

- Gate RTF ≤ 1,0 theo từng lần gọi **trượt** với câu lẻ vì mỗi lần `CommandTTS`
  khởi động tiến trình Python mới và nạp model (~8 s); RTF biên khi đã nạp ≈ 0,39
  (fp32) / 0,28 (int8), suy từ chênh lệch giữa `bai-ghep` và câu ngắn nhất.
- Với hình dạng production hiện tại (một lần gọi cho cả bài), VieNeu v3 Turbo
  ONNX/CPU **đạt** ngưỡng đo được: một bài ~50 s tổng hợp trong 21–27 s.
- Thời lượng cùng một câu lệch giữa hai lần chạy (vd. `so-huyet-ap` 3840 ↔ 4080 ms)
  vì `infer` lấy mẫu với `temperature=0.8`; audio không bit-identical nên mọi lần
  tổng hợp lại đều phải qua lại cổng duyệt video (invalidation `audio/` → `video`).
- Chưa đo và chưa kết luận: phát âm tên thuốc/số/viết tắt, độ tự nhiên. Cần ASR
  back-check và bác sĩ nghe (M5.4) trước khi chọn voice chính thức.

Không commit WAV, model, `cache/tts-venv` hay `benchmark.json`.

## 6. Ngoài phạm vi M5.3

`produce --tts vieneu`, chọn preset voice chính thức, ASR mismatch, loudness/khoảng
lặng FFmpeg, ElevenLabs fallback, GPU backend, engine thường trú để bỏ chi phí nạp
model mỗi lần gọi (chỉ cần nếu production chuyển sang gọi TTS theo câu).
