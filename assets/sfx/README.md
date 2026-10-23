# SFX tiết chế (CC0)

Nguồn: [Kenney Interface Sounds 1.0](https://kenney.nl/assets/interface-sounds).
Tác giả: Kenney. Giấy phép CC0-1.0; bản giấy phép gốc: `LICENSE-Kenney.txt`.
`catalog.yaml` lưu file gốc trong archive, URL nguồn và SHA-256 của WAV đã xử lý.

| ID | File gốc |
|---|---|
| whoosh-soft | open_001.ogg |
| chime-soft | glass_001.ogg |
| pop-soft | drop_001.ogg |
| tick | tick_001.ogg |
| swell-low | maximize_001.ogg |
| chime-warm | confirmation_001.ogg |
| tap-soft | select_001.ogg |

Đây là các bản xử lý từ âm gốc: hạ cao độ/tốc độ, low-pass 2.4 kHz,
fade đầu/cuối, chuẩn hóa RMS -26 dBFS (giới hạn peak -12 dBFS), PCM16 WAV
48 kHz stereo, mỗi file dưới 2 giây. Không chọn âm error/alarm/glitch.
Tái tạo bằng `python tools/sfx/prepare.py` (cần FFmpeg; chỉ tải các âm CC0).

Mix hạ nhạc -20 dB trước khi cộng SFX ở volume 0.15–0.4, rồi sidechain duck
toàn bộ nền theo giọng; giữ nguyên gain giọng. Cache theo hash giọng, nhạc,
lịch cue, byte SFX và phiên bản mix. `--no-music` vẫn giữ SFX; muốn bỏ cả SFX
thì dùng `sfx_defaults: false` và không khai báo cue riêng.

`audio/alignment/LNxx.json` được đọc khi có; từ khóa khớp không phân biệt hoa
thường/dấu câu và hỗ trợ cụm từ. Thiếu file hoặc không khớp thì cue ở đầu cảnh.
Clip dọc dùng lại cue đã giải theo cảnh, chuyển thời điểm sang timeline của clip.
