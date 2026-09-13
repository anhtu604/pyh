"""ASR back-check: objective word error rate between narration text and a transcript.

The ASR itself is an explicit local command (like ``CommandTTS``); no model or
license is assumed. WER flags mismatches for a doctor to listen to; it does not
judge pronunciation quality by itself.
"""

import json
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from healthvideo.tts.command import _run

Runner = Callable[[list[str]], int]

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_transcript(text: str) -> str:
    folded = unicodedata.normalize("NFC", text).casefold()
    return " ".join(_PUNCTUATION.sub(" ", folded).split())


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = normalize_transcript(reference).split()
    hyp = normalize_transcript(hypothesis).split()
    if not ref:
        raise ValueError("WER reference text is empty")
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (ref_word != hyp_word),
                )
            )
        previous = current
    return previous[-1] / len(ref)


class CommandASR:
    """Run a local command reading ``{input}`` WAV and writing ``{output}`` JSON ``{"text"}``."""

    provider_name = "command"

    def __init__(
        self,
        *,
        executable: str,
        arguments: tuple[str, ...],
        model_id: str,
        runner: Runner = _run,
    ) -> None:
        if not executable.strip() or not model_id.strip():
            raise ValueError("Command ASR executable and model_id must be nonempty")
        if sum(arg.count("{input}") for arg in arguments) != 1 or sum(
            arg.count("{output}") for arg in arguments
        ) != 1:
            raise ValueError("Command ASR needs one {input} and one {output}")
        self.executable = executable
        self.arguments = arguments
        self.model_id = model_id
        self.runner = runner

    def identity(self) -> dict[str, str]:
        return {"provider": self.provider_name, "model_id": self.model_id}

    def transcribe(self, wav: Path) -> str:
        with TemporaryDirectory(prefix=".command-asr-", dir=wav.parent) as temporary:
            transcript_path = Path(temporary) / "transcript.json"
            argv = [self.executable] + [
                arg.replace("{input}", str(wav)).replace("{output}", str(transcript_path))
                for arg in self.arguments
            ]
            exit_code = self.runner(argv)
            if exit_code != 0:
                raise RuntimeError(f"Command ASR failed with exit code {exit_code}")
            if not transcript_path.is_file():
                raise FileNotFoundError("Command ASR did not write a transcript")
            data = json.loads(transcript_path.read_text(encoding="utf-8"))
        text = data.get("text") if isinstance(data, dict) else None
        if isinstance(text, str):
            return text
        raise ValueError("Command ASR transcript JSON needs a string `text`")
