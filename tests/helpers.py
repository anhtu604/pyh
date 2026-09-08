from pathlib import Path
from typing import Any

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.base import TTSRequest
from healthvideo.tts.silent import SilentTTS


def create_project_fixture(root: Path, state: str) -> Path:
    """Create a complete synthetic project that is safe for offline tests."""
    project_dir = root / "muoi-va-huyet-ap"
    for directory in ("audio", "assets", "evidence", "renders", "script", "storyboard"):
        (project_dir / directory).mkdir(parents=True, exist_ok=True)

    project: dict[str, Any] = {
        "schema_version": "1.0",
        "slug": "muoi-va-huyet-ap",
        "language": "vi",
        "state": state,
        "artifact_hashes": {},
    }
    brief = {
        "schema_version": "1.0",
        "title": "Ăn mặn và tăng huyết áp",
        "personal_position": "Giảm muối là một bước thực tế.",
        "reasoning": "Huyết áp thường đáp ứng với lượng muối.",
        "emotion": "bình tĩnh",
        "audience_concern": "Người trưởng thành quan tâm huyết áp.",
        "phrases_to_keep": [],
    }
    lines = [
        {
            "id": f"L{index:02}",
            "text": text,
            "claim_id": "C01",
            "source_marker": "[1]",
            "delivery": {"intent": "explain"},
        }
        for index, text in enumerate(
            (
                "Ăn mặn có thể làm huyết áp tăng.",
                "Điều này không có nghĩa là bạn phải bỏ hết gia vị.",
                "Bằng chứng cho thấy giảm muối giúp hạ huyết áp.",
                "Hiệu quả khác nhau giữa mỗi người.",
                "Quan điểm của tôi là giảm dần sẽ dễ duy trì hơn.",
                "Hãy trao đổi với bác sĩ nếu bạn đang điều trị huyết áp.",
            ),
            start=1,
        )
    ]
    script = {
        "schema_version": "1.0",
        "title": brief["title"],
        "language": "vi",
        "lines": lines,
    }
    scenes = []
    for index, line in enumerate(lines):
        scene: dict[str, Any] = {
            "id": f"S{index + 1:02}",
            "start_frame": index * 225,
            "duration_frames": 225,
            "narration": line["text"],
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "whiteboard",
        }
        scenes.append(scene)
    storyboard = {"schema_version": "1.0", "title": brief["title"], "scenes": scenes}
    ledger = {
        "schema_version": "1.0",
        "records": [{"id": "R01", "synthetic_test_record": True}],
        "claims": [{"id": "C01", "synthetic_test_record": True}],
    }

    write_yaml_atomic(project_dir / "project.yaml", project)
    write_yaml_atomic(project_dir / "author-brief.yaml", brief)
    write_yaml_atomic(project_dir / "evidence" / "ledger.yaml", ledger)
    write_yaml_atomic(project_dir / "script" / "script.yaml", script)
    write_yaml_atomic(project_dir / "storyboard" / "storyboard.yaml", storyboard)
    return project_dir


def synthesize_fixture_audio(project_dir: Path) -> Path:
    """Create a local silent WAV for a copied fixture without tracking generated audio."""
    script = read_yaml(project_dir / "script" / "script.yaml")
    narration = " ".join(line["text"] for line in script["lines"])
    output = project_dir / "audio" / "narration.wav"
    return (
        SilentTTS()
        .synthesize(TTSRequest(text=narration, language=script["language"]), output)
        .audio_file
    )
