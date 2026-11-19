# Benchmark Ollama ~4B Local Router (R3.4 / 4b)

- Thời điểm đo: `2026-11-19T12:48:33+07:00`
- Ollama CLI: `C:\Users\anhtu\AppData\Local\Programs\Ollama\ollama.EXE` (`Warning: could not connect to a running Ollama instance
Warning: client version is 0.23.1`)
- Endpoint headless: `http://127.0.0.1:11434`
- Model được đo: `qwen2.5:3b`

## Phần cứng đo thực tế

| Chỉ số | Giá trị đo thực |
|---|---|
| VRAM tổng (`nvidia-smi`) | `12288` MiB |
| VRAM rảnh nền (`nvidia-smi`) | `10658` MiB |
| VRAM đang dùng nền (`nvidia-smi`) | `1456` MiB |
| RAM trống nền (`GlobalMemoryStatusEx`) | `16415` MiB |

## Tổng hợp đo 6 mẫu tiếng Việt (`num_ctx: 4096`, `keep_alive: 0`)

| Chỉ số | Giá trị |
|---|---|
| Mẫu đạt schema Pydantic | `6/6` (`1.0`) |
| Tốc độ trung bình | `123.8` tok/s |
| VRAM tổng đỉnh lúc chạy | `3984` MiB |
| VRAM model theo `/api/ps` | `2279.6` MiB (`size_vram=2390300672`, `size=2390300672`) |
| VRAM rảnh tối thiểu | `8130` MiB |
| RAM trống tối thiểu | `15711` MiB |
| CPU offload ngầm (`/api/ps`) | `False` |
| Đã unload sạch (`keep_alive: 0`) | `False` |

## Chi tiết 6 mẫu tiếng Việt

| ID | Task | Schema Pass | Latency (s) | Prompt Tok | Eval Tok | tok/s | Lỗi |
|---|---|---|---:|---:|---:|---:|---|
| `FB-01` | `feedback_inbox` | `True` | `38.3` | `101` | `97` | `132.73` | `—` |
| `FB-02` | `feedback_inbox` | `True` | `3.404` | `93` | `124` | `113.03` | `—` |
| `FB-03` | `feedback_inbox` | `True` | `5.176` | `90` | `123` | `121.0` | `—` |
| `CS-01` | `chat_status_summary` | `True` | `4.05` | `109` | `79` | `123.54` | `—` |
| `CS-02` | `chat_status_summary` | `True` | `2.098` | `113` | `73` | `129.54` | `—` |
| `CS-03` | `chat_status_summary` | `True` | `3.082` | `92` | `43` | `122.94` | `—` |

## Ghi chú trung thực

- `unloaded_cleanly=False`: /api/ps còn model ngay sau lệnh unload (kiểm sau 0,5 s). Sau khi benchmark tắt `ollama serve` tạm, `nvidia-smi` đo VRAM dùng 1453 MiB (nền, không còn tiến trình ollama) nên VRAM đã giải phóng.
- `qwen3:4b` không kéo được trong 240 s (kết nối Cloudflare R2 bị ngắt/stall nhiều lần); đo bằng `qwen2.5:3b`. Chưa đo `qwen3:4b`.
- Mẫu nhỏ (6 mẫu, 1 lần chạy); chưa đánh giá chất lượng ngữ nghĩa so với cloud, chỉ schema pass. `profiles/local-llm.yaml` chưa tạo nên routing local vẫn TẮT mặc định (`enabled: false`); bật cần quyết định của bác sĩ/dev lead, đề xuất `model: qwen2.5:3b`, `peak_vram_mib` ~2600 (delta đo 2528).

