"""Draft listening and measured timing, without changing scripts or approvals."""

import threading
from pathlib import Path

from healthvideo.domain.script import Script
from healthvideo.storage.files import read_yaml
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.tts import pronunciation
from healthvideo.tts.audio_checks import inspect_wav
from healthvideo.tts.base import TTSRequest, provider_identity
from healthvideo.tts.pronunciation import (
    apply_pronunciation,
    load_pronunciation_lexicon,
)
from healthvideo.tts.vibi import load_voice_profile
from healthvideo.tts.voicestudio import VoiceStudioError, VoiceStudioTTS
from healthvideo.workflows.produce import (
    _synthesize_cached_line,
    _telemetry_root,
    tts_cache_key,
)
from healthvideo.workflows.voice_prep import load_voice_prep_lexicon

_PREVIEW_LOCK = threading.Lock()


def _preview_provider(root: Path) -> VoiceStudioTTS:
    profile_path = root / 'profiles/voice.yaml'
    profile = load_voice_profile(profile_path) if profile_path.is_file() else load_voice_profile()
    if profile.voicestudio is None:
        raise VoiceStudioError('Chưa cấu hình Voice Studio cho nghe thử giọng trên máy.')
    return VoiceStudioTTS(profile.voicestudio, root=root,
                          usage_path=root / 'cache/voicestudio/voicestudio-usage.json')


def voice_preview(project: Path, line_ids: list[str] | None = None) -> dict:
    """Read selected lines (or the entire script), returning audio URLs and measured ms.

    Draft files live in their own render subdirectory and backend cache. No gate,
    script, storyboard, final narration or production manifest is written here.
    """
    return _voice_preview(project, line_ids)


def draft_line_ms(project: Path, script: Script) -> dict[str, int] | None:
    """Opt-in local timing for R5 prechecks; absent settings retain legacy estimates."""
    profile_path = _telemetry_root(project) / 'profiles/voice.yaml'
    if not profile_path.is_file() or load_voice_profile(profile_path).voicestudio is None:
        return None
    from healthvideo.tts.voicestudio import VoiceStudioError

    try:
        result = _voice_preview(project, None, script=script)
    except VoiceStudioError:
        # ponytail: Voice Studio is optional; server off -> legacy character estimate.
        return None
    return {line['id']: line['duration_ms'] for line in result['lines']}


def _voice_preview(project: Path, line_ids: list[str] | None, *, script: Script | None = None) -> dict:
    if line_ids is not None and (not isinstance(line_ids, list) or not line_ids
                                or not all(isinstance(line, str) for line in line_ids)):
        raise ValueError('Danh sách dòng nghe thử không hợp lệ.')
    with _PREVIEW_LOCK:
        layout = resolve_project_layout(project)
        rev = layout.artifact_root
        script = script or Script.model_validate(read_yaml(rev / 'script/script.yaml'))
        if line_ids is not None and set(line_ids) - {line.id for line in script.lines}:
            raise ValueError('Không tìm thấy dòng lời cần nghe thử.')
        lines = [line for line in script.lines if line_ids is None or line.id in line_ids]
        root = _telemetry_root(project)
        tts = _preview_provider(root)
        if provider_identity(tts)['provider'] != 'voicestudio':
            raise ValueError('Nghe thử trên máy cần backend Voice Studio.')
        lexicon = load_pronunciation_lexicon(pronunciation.PRONUNCIATION_PROFILE_PATH)
        if (rev / 'script/voice-prep.yaml').is_file():
            lexicon = load_voice_prep_lexicon(rev, lexicon)
        directory = rev / 'renders/draft-voice'
        if not directory.resolve().is_relative_to(rev.resolve()):
            raise ValueError('Đường dẫn nghe thử không hợp lệ.')
        directory.mkdir(parents=True, exist_ok=True)
        results = []
        for line in lines:
            request = TTSRequest(text=apply_pronunciation(line.text, lexicon), language=script.language)
            key = tts_cache_key(tts, request)
            output = directory / f'{key}.wav'
            _synthesize_cached_line(tts, request, output, cache_dir=root / 'cache/tts/voicestudio')
            results.append({'id': line.id, 'duration_ms': inspect_wav(output).duration_ms,
                            'url': f'/media/{layout.manifest.slug}/draft-voice/{key}.wav'})
        return {'provider': 'voicestudio', 'role': 'draft', 'lines': results,
                'duration_ms': sum(line['duration_ms'] for line in results)}
