"""Opt-in, pinned OpenMontage/HyperFrames render boundary (no model calls).

PYH_RENDERER=openmontage selects this adapter. Installation is always explicit.
The upstream orchestration, .env loader and npx downloader are never invoked.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import os
import shutil
import subprocess
import sys
import types
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from healthvideo.process import prepare_subprocess_argv, run_bounded
from healthvideo.storage.files import canonical_json_hash, sha256_file

COMMIT = '2e003e65fa99a0f329478a2c1cdcf26bc481933a'
VERSION = 'pyh-openmontage-1'
HYPERFRAMES_VERSION = '0.9.56'
ROOT = Path(__file__).resolve().parents[3]
REMEDY = 'Chạy healthvideo openmontage-install; hoặc đặt PYH_OPENMONTAGE_PATH tới checkout đã cài đúng commit.'
TIMEOUT = 2 * 60 * 60


def selected_renderer():
    """A single explicit configuration key; absent means the original Remotion."""
    name = os.environ.get('PYH_RENDERER', 'remotion')
    if name == 'remotion':
        from healthvideo.render import remotion

        return remotion
    if name == 'openmontage':
        return sys.modules[__name__]
    raise ValueError(f'PYH_RENDERER không hợp lệ: {name!r}; dùng remotion hoặc openmontage.')


def require_preview_renderer(manifest: Path, name: str) -> None:
    """A pending visual gate must not return another renderer's preview."""
    cached = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else {}
    previous = cached.get('renderer_identity', {}).get('name', 'remotion')
    if previous != name:
        raise ValueError('Không đổi renderer khi đang chờ duyệt hình; hoàn tất visual review trước khi dựng lại.')


def checkout_path() -> Path:
    return Path(os.environ.get('PYH_OPENMONTAGE_PATH', ROOT / 'cache/openmontage' / COMMIT)).resolve()


def runtime_path(checkout: Path) -> Path:
    return Path(os.environ.get('PYH_HYPERFRAMES_PATH', checkout / '.pyh-runtime/node_modules/hyperframes')).resolve()


def _runtime_env() -> dict[str, str]:
    return {**os.environ, 'HYPERFRAMES_NO_AUTO_INSTALL': '1',
            'HYPERFRAMES_NO_UPDATE_CHECK': '1', 'HYPERFRAMES_NO_CAPTURE_DOTENV': '1'}


def _browser_path(runtime: Path) -> Path:
    # This pinned module's findBrowser only discovers installed browsers; unlike
    # `hyperframes browser path`, it never calls ensureBrowser or downloads Chrome.
    module = (runtime / 'dist/chunk-43CQTZGB.js').as_uri()
    script = f'import {{findBrowser}} from {json.dumps(module)}; console.log((await findBrowser())?.executablePath || "");'
    found = run_bounded(['node', '--input-type=module', '-e', script], timeout=30,
                        capture_output=True, text=True, check=True, env=_runtime_env()).stdout.strip()
    if not found or not Path(found).is_file():
        raise FileNotFoundError(f'Chưa có Chrome cho OpenMontage. {REMEDY}')
    return Path(found)


def _git(checkout: Path, *args: str) -> str:
    return run_bounded(['git', '-C', str(checkout), *args], timeout=30,
                       check=True, capture_output=True, text=True, shell=False).stdout.strip()


def renderer_identity() -> dict[str, str]:
    checkout = checkout_path()
    source = checkout / 'tools/video/hyperframes_compose.py'
    if not source.is_file():
        raise FileNotFoundError(f'Chưa có OpenMontage tại {checkout}. {REMEDY}')
    if _git(checkout, 'rev-parse', 'HEAD') != COMMIT:
        raise ValueError(f'OpenMontage phải ở commit {COMMIT}. {REMEDY}')
    if _git(checkout, 'diff', 'HEAD', '--name-only'):
        raise ValueError(f'Checkout OpenMontage có thay đổi tracked; cần checkout sạch. {REMEDY}')
    runtime = runtime_path(checkout)
    package = runtime / 'package.json'
    if not package.is_file() or not (runtime / 'bin/hyperframes.mjs').is_file():
        raise FileNotFoundError(f'Chưa cài HyperFrames local. {REMEDY}')
    if json.loads(package.read_text(encoding='utf-8')).get('version') != HYPERFRAMES_VERSION:
        raise ValueError(f'Cần HyperFrames {HYPERFRAMES_VERSION}. {REMEDY}')
    if not shutil.which('node') or not shutil.which('ffmpeg'):
        raise FileNotFoundError('OpenMontage cần Node >=22 và FFmpeg trên PATH.')
    major = int(run_bounded(['node', '--version'], timeout=15, capture_output=True,
                            text=True, check=True).stdout.strip().lstrip('v').split('.')[0])
    if major < 22:
        raise ValueError('OpenMontage cần Node >=22.')
    browser = _browser_path(runtime)
    # Source and packaged runtime bytes, including bundled GSAP/fonts, bind the cache.
    runtime_hashes = {p.relative_to(runtime).as_posix(): sha256_file(p)
                      for folder in ('bin', 'dist') for p in sorted((runtime / folder).rglob('*'))
                      if p.is_file()}
    return {'name': 'openmontage', 'commit': COMMIT, 'version': VERSION,
            'tool_version': '0.2.0',
            'hyperframes_version': HYPERFRAMES_VERSION,
            'runtime_sha256': canonical_json_hash(runtime_hashes),
            'browser_sha256': sha256_file(browser),
            'fonts_sha256': canonical_json_hash({p.name: sha256_file(p) for p in sorted((ROOT / 'video/public/fonts').iterdir()) if p.is_file()}),
            'adapter_sha256': sha256_file(Path(__file__))}


def install(checkout: Path | None = None) -> Path:
    """Explicit network operation; never called from identity, doctor or produce."""
    checkout = (checkout or checkout_path()).resolve()
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        run_bounded(['git', 'clone', '--no-checkout', 'https://github.com/calesthio/OpenMontage', str(checkout)],
                    timeout=600, check=True, shell=False)
        _git(checkout, 'checkout', '--detach', COMMIT)
    if _git(checkout, 'rev-parse', 'HEAD') != COMMIT or _git(checkout, 'diff', 'HEAD', '--name-only'):
        raise ValueError('Không ghi đè checkout OpenMontage khác commit hoặc có thay đổi.')
    runtime = checkout / '.pyh-runtime'
    run_bounded([*_npm_argv(), 'install', '--prefix', str(runtime),
                 '--save-exact', f'hyperframes@{HYPERFRAMES_VERSION}'],
                timeout=600, check=True, shell=False)
    run_bounded(['node', str(runtime / 'node_modules/hyperframes/bin/hyperframes.mjs'), 'browser', 'ensure'],
                timeout=600, check=True, shell=False, env=_runtime_env())
    return checkout


def _npm_argv() -> list[str]:
    """npm.cmd cannot be launched safely without a shell; use its JS entrypoint."""
    node, npm = shutil.which('node'), shutil.which('npm')
    if node:
        roots = [Path(node).parent, *([Path(npm).parent] if npm else [])]
        for root in roots:
            script = root / 'node_modules/npm/bin/npm-cli.js'
            if script.is_file():
                return [node, str(script)]
    return prepare_subprocess_argv(['npm'])


def build_render_argv(render_input: Path, output: Path, public_dir: Path) -> list[str]:
    renderer_identity()  # Fail before any rendering or implicit download.
    return [sys.executable, '-m', 'healthvideo.render.openmontage',
            '--props', str(render_input.resolve()), '--output', str(output.resolve()),
            '--public-dir', str(public_dir.resolve())]


def run_render_argv(argv: list[str]) -> int:
    log_dir = ROOT / 'topics/logs/render'
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f'openmontage-{datetime.now().astimezone():%Y%m%dT%H%M%S%f}.log'
    with log.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps(argv, ensure_ascii=False) + '\n')
        stream.flush()
        try:
            return run_bounded(argv, timeout=TIMEOUT, shell=False, check=False,
                               stdout=stream, stderr=subprocess.STDOUT).returncode
        except BaseException as error:
            stream.write(f'\n{type(error).__name__}: OpenMontage interrupted\n')
            raise


def render(render_input: Path, output: Path, public_dir: Path, *,
           runner: Callable[[list[str]], int] | None = None,
           assets: Sequence[Mapping[str, Any]] = ()) -> None:
    argv = build_render_argv(render_input, output, public_dir)
    if assets:
        rights = public_dir / 'openmontage-assets.json'
        rights.write_text(json.dumps(list(assets), ensure_ascii=False), encoding='utf-8')
        argv += ['--assets', str(rights.resolve())]
    output.unlink(missing_ok=True)
    try:
        code = (runner or run_render_argv)(argv)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    if code != 0:
        output.unlink(missing_ok=True)
        raise RuntimeError(f'OpenMontage render failed with exit code {code}; xem topics/logs/render/.')
    if not output.is_file():
        raise FileNotFoundError(f'OpenMontage render did not create output: {output}')


def _local(public_dir: Path, relative: str) -> Path:
    path = (public_dir / relative).resolve()
    if not path.is_relative_to(public_dir.resolve()) or Path(relative).is_absolute():
        raise ValueError(f'OpenMontage asset phải nằm trong staged public dir: {relative}')
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def materialize_workspace(render_input: Path, public_dir: Path, *,
                          assets: Sequence[Mapping[str, Any]] = ()) -> Path:
    """Preserve frame times; reject unsupported visual semantics instead of dropping them."""
    props = json.loads(render_input.read_text(encoding='utf-8'))
    fps = props['fps']
    if fps != 30 or not props['scenes']:
        raise ValueError('OpenMontage cần timeline 30 fps có scene.')
    if props.get('youtube_cta'):
        raise ValueError('OpenMontage chưa hỗ trợ youtube_cta.')
    workspace = public_dir / 'openmontage-workspace'
    workspace.mkdir(exist_ok=True)
    shutil.copytree(ROOT / 'video/public/fonts', workspace / 'fonts', dirs_exist_ok=True)
    rights = {a['path']: a for a in assets}

    def stage(relative: str, *, require_rights: bool = True) -> str:
        source = _local(public_dir, relative)
        if require_rights:
            record = rights.get(relative, {})
            if not all(record.get(k) for k in ('source', 'license', 'sha256')):
                raise ValueError(f'OpenMontage cần license/source/SHA: {relative}')
            if sha256_file(source) != record['sha256']:
                raise ValueError(f'OpenMontage asset SHA không khớp: {relative}')
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return html.escape(relative, quote=True)

    body = []
    expected_start = 0
    for scene_index, scene in enumerate(props['scenes']):
        # These fields require renderer-specific design and independent visual QA.
        if scene['visual'] not in {'whiteboard', 'chart'} or any(scene.get(k) for k in (
            'anatomy', 'evidence_highlight', 'source_card', 'stat_gauge', 'kinetic_term',
            'motion', 'labels', 'annotations', 'beats', 'entrances', 'explainer_layer_id',
        )):
            raise ValueError(f"OpenMontage chưa hỗ trợ đầy đủ scene {scene['id']}: {scene['visual']}; dùng remotion.")
        start, frames = scene['start_frame'], scene['duration_frames']
        if start != expected_start or frames <= 0:
            raise ValueError('OpenMontage cần timeline liên tục, duration dương.')
        expected_start = start + frames
        timing = f'data-start="{start / fps}" data-duration="{frames / fps}"'
        text = html.escape(scene.get('on_screen_text') or '')
        body.append(f'<section id="scene-{scene_index}" class="scene" {timing} data-track-index="1"><h1>{text}</h1>')
        for asset in scene.get('visual_assets', []):
            if asset.get('role') not in {'whiteboard', 'chart'}:
                raise ValueError(f"OpenMontage chưa hỗ trợ asset role: {asset.get('role')}")
            if Path(asset['path']).suffix.lower() not in {'.svg', '.png', '.jpg', '.jpeg', '.webp'}:
                raise ValueError('OpenMontage hiện chỉ hỗ trợ asset ảnh/SVG tĩnh.')
            body.append(f'<img src="{stage(asset["path"])}" alt="">')
        body.append('</section>')
        words = scene.get('words', [])
        if scene.get('narration') and not words:
            raise ValueError(f"OpenMontage cần phụ đề có timing thật: {scene['id']}")
        for word_index, word in enumerate(words):
            if not 0 <= word['start_frame'] < word['end_frame'] <= frames:
                raise ValueError('OpenMontage caption nằm ngoài scene.')
            body.append(f'<div id="caption-{scene_index}-{word_index}" class="caption" data-start="{(start + word["start_frame"]) / fps}" '
                        f'data-duration="{(word["end_frame"] - word["start_frame"]) / fps}" '
                        f'data-track-index="2">{html.escape(word["text"])}</div>')
    duration = expected_start / fps
    audio = stage(props['audio_file'], require_rights=False)  # factory-reviewed mixed narration
    body.append(f'<audio id="narration" src="{audio}" data-start="0" data-duration="{duration}" '
                'data-track-index="3" data-volume="1"></audio>')
    width, height = props['width'], props['height']
    if (width, height) not in {(1920, 1080), (1080, 1920)}:
        raise ValueError('OpenMontage cần kích thước 1920x1080 hoặc 1080x1920.')
    document = f'''<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<style>@font-face{{font-family:PYHLocal;src:url('fonts/BeVietnamPro-SemiBold.woff2') format('woff2');font-weight:100 900}}
body{{margin:0;background:#102330;color:#fff;font-family:PYHLocal,sans-serif}}
[data-composition-id]{{position:relative;width:{width}px;height:{height}px;overflow:hidden}}
.scene{{position:absolute;inset:0;box-sizing:border-box;padding:80px;text-align:center}}
h1{{font-size:54px}}img{{width:85%;height:65%;object-fit:contain}}
.caption{{position:absolute;bottom:80px;left:80px;right:80px;text-align:center;font-size:48px;background:#102330;color:#fff}}
</style><script src="gsap.min.js"></script></head><body>
<div data-composition-id="root" data-start="0" data-duration="{duration}" data-width="{width}" data-height="{height}">
{''.join(body)}<script>window.__timelines={{root:gsap.timeline({{paused:true}})}};
window.__timelines.root.to({{}},{{duration:{duration}}});</script></div></body></html>'''
    (workspace / 'index.html').write_text(document, encoding='utf-8')
    (workspace / 'hyperframes.json').write_text('{}', encoding='utf-8')
    return workspace


def _compose(workspace: Path, output: Path) -> None:
    """Isolated child: use upstream checks/render, replace only unsafe launcher/probes.

    base_tool automatically reads .env at import. Remove that one call from its
    AST in memory, leaving the checkout untouched and never opening any .env.
    """
    renderer_identity()
    checkout = checkout_path()
    runtime = runtime_path(checkout)
    browser = _browser_path(runtime)
    gsap = runtime / 'dist/vendor/npm/gsap@3.15.0/dist/gsap.min.js'
    shutil.copyfile(gsap, workspace / 'gsap.min.js')
    sys.path.insert(0, str(checkout))
    base_path = checkout / 'tools/base_tool.py'
    tree = ast.parse(base_path.read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name) and node.value.func.id == '_load_dotenv')]
    base = types.ModuleType('tools.base_tool')
    base.__file__ = str(base_path)
    sys.modules[base.__name__] = base
    exec(compile(tree, str(base_path), 'exec'), base.__dict__)  # noqa: S102 - pinned local source; suppress .env side effect
    from tools.video.hyperframes_compose import HyperFramesCompose

    class LocalCompose(HyperFramesCompose):
        def _runtime_check(self):
            # Already checked without upstream npm registry/.env probes.
            return {'runtime_available': True, 'reasons': []}

        def _run_hf(self, args, *, cwd, timeout, check):
            env = {**_runtime_env(), 'HYPERFRAMES_BROWSER_PATH': str(browser)}
            return run_bounded(['node', str(runtime / 'bin/hyperframes.mjs'), *args],
                               cwd=str(cwd), timeout=timeout, check=check, shell=False,
                               env=env,
                               capture_output=True, text=True, encoding='utf-8', errors='replace')

    result = LocalCompose().execute({'operation': 'render_existing', 'workspace_path': str(workspace),
                                     'output_path': str(output), 'fps': 30, 'quality': 'standard'})
    print(json.dumps({'success': result.success, 'error': result.error, 'data': result.data}))
    if not result.success:
        raise RuntimeError(f'OpenMontage: {result.error}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--props', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-dir', type=Path, required=True)
    parser.add_argument('--assets', type=Path)
    args = parser.parse_args()
    assets = json.loads(args.assets.read_text(encoding='utf-8')) if args.assets else []
    workspace = materialize_workspace(args.props, args.public_dir, assets=assets)
    _compose(workspace, args.output)


if __name__ == '__main__':
    main()
