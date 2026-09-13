"""Explicit local command adapter; no model, voice, or license is assumed."""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from healthvideo.tts.audio_checks import inspect_wav
from healthvideo.tts.base import TTSRequest, TTSResult

Runner = Callable[[list[str]], int]


def _run(argv: list[str]) -> int:
    return subprocess.run(argv, shell=False, check=False).returncode


class CommandTTS:
    provider_name = "command"
    require_signal = True

    def __init__(
        self,
        *,
        executable: str,
        arguments: tuple[str, ...],
        model_id: str,
        voice_id: str,
        runtime_id: str = "operator-configured",
        runner: Runner = _run,
    ) -> None:
        if not all(value.strip() for value in (executable, model_id, voice_id, runtime_id)):
            raise ValueError("Command TTS identity and executable must be nonempty")
        if sum(arg.count("{input}") for arg in arguments) != 1 or sum(
            arg.count("{output}") for arg in arguments
        ) != 1:
            raise ValueError("Command TTS needs one {input} and one {output}")
        if any("{" in arg.replace("{input}", "").replace("{output}", "") for arg in arguments):
            raise ValueError("Command TTS has unknown placeholder")
        self.executable = executable
        self.arguments = arguments
        self.model_id = model_id
        self.voice_id = voice_id
        self.runtime_id = runtime_id
        self.runner = runner

    def cache_identity(self) -> dict[str, str]:
        # No paths, environment, command arguments, or credentials in manifests.
        return {
            "provider": self.provider_name,
            "model_id": self.model_id,
            "voice_id": self.voice_id,
            "runtime_id": self.runtime_id,
        }

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        if request.language != "vi":
            raise ValueError("Command TTS requires Vietnamese text")
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".command-tts-", dir=output.parent) as temporary:
            staging = Path(temporary)
            input_path = staging / "narration.txt"
            staged_output = staging / "narration.wav"
            input_path.write_text(request.text, encoding="utf-8")
            argv = [self.executable] + [
                arg.replace("{input}", str(input_path)).replace("{output}", str(staged_output))
                for arg in self.arguments
            ]
            exit_code = self.runner(argv)
            if exit_code != 0:
                raise RuntimeError(f"Command TTS failed with exit code {exit_code}")
            if not staged_output.is_file():
                raise FileNotFoundError("Command TTS did not produce a WAV file")
            report = inspect_wav(staged_output, require_signal=True)
            os.replace(staged_output, output)
        return TTSResult(
            provider=self.provider_name, audio_file=output, duration_ms=report.duration_ms
        )
