import contextvars
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

from healthvideo.process import resolve_pnpm_argv, run_with_deadline
from healthvideo.storage.files import canonical_json_hash, rmtree_long_path, sha256_file

RemotionRunner = Callable[[list[str]], int]
BUNDLE_TIMEOUT_SECONDS = 300
DEFAULT_WINDOWS_GL = "angle"
FALLBACK_GL = "swiftshader"
_SKIP_PUBLIC_ROOTS = frozenset({".remotion-bundle", "renders"})
_MEDANIM_MEDIA_SUFFIXES = frozenset({".svg", ".png", ".jpg", ".jpeg", ".webp"})

_ACTIVE_BUNDLE_STATE: contextvars.ContextVar[dict[str, object] | None] = contextvars.ContextVar(
    "pyh_remotion_active_bundle", default=None,
)


def _fs_path(path: Path) -> str:
    """Return an extended-length Windows path when approaching MAX_PATH."""
    resolved = str(path.resolve())
    if os.name == "nt" and len(resolved) >= 240 and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\UNC\\" + resolved[2:] if resolved.startswith("\\\\") else "\\\\?\\" + resolved
    return resolved


def _copy_if_newer(src: Path, dst: Path) -> None:
    """Copy ``src`` to ``dst`` only when missing, size differs, or ``src`` is newer."""
    dst_fs = _fs_path(dst)
    src_fs = _fs_path(src)
    if os.path.isfile(dst_fs):
        try:
            src_stat = os.stat(src_fs)
            dst_stat = os.stat(dst_fs)
            if src_stat.st_size == dst_stat.st_size and dst_stat.st_mtime_ns >= src_stat.st_mtime_ns:
                return
        except OSError:
            pass
    os.makedirs(os.path.dirname(dst_fs), exist_ok=True)
    shutil.copy2(src_fs, dst_fs)


def _iter_medanim_assets(repository_root: Path) -> Iterator[tuple[str, Path, Path]]:
    """Yield ``(anim_id, assets_dir, asset_path)`` for non-symlink media under ``library/medanim``."""
    medanim_root = repository_root / "library" / "medanim"
    if not medanim_root.is_dir() or medanim_root.is_symlink():
        return
    for anim_dir in sorted(medanim_root.iterdir(), key=lambda p: p.name):
        if anim_dir.name.startswith(".") or anim_dir.is_symlink() or not anim_dir.is_dir():
            continue
        assets_dir = anim_dir / "assets"
        if assets_dir.is_symlink() or not assets_dir.is_dir():
            continue
        for asset in sorted(assets_dir.rglob("*"), key=lambda p: p.as_posix()):
            if asset.is_symlink() or not asset.is_file():
                continue
            rel_parts = asset.relative_to(assets_dir).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
            if asset.suffix.lower() not in _MEDANIM_MEDIA_SUFFIXES:
                continue
            yield anim_dir.name, assets_dir, asset


def stage_medanim_assets(repository_root: Path, public_dir: Path) -> None:
    """Stage open medical animation media from ``library/medanim/*/assets`` into ``public_dir/medanim``."""
    resolved_public = public_dir.resolve()
    for anim_id, assets_dir, asset in _iter_medanim_assets(repository_root):
        rel = asset.relative_to(assets_dir)
        _copy_if_newer(asset, resolved_public / "medanim" / anim_id / rel)


def _stage_public_assets(repository_root: Path, public_dir: Path) -> None:
    resolved_public = public_dir.resolve()
    builtin_public = (repository_root / "video" / "public").resolve()
    fonts_dir = repository_root / "video" / "public" / "fonts"
    target_fonts = resolved_public / "fonts"
    if fonts_dir.is_dir() and target_fonts != fonts_dir.resolve():
        shutil.copytree(fonts_dir, target_fonts, dirs_exist_ok=True)
    if resolved_public != builtin_public:
        stage_medanim_assets(repository_root, resolved_public)


def renderer_identity() -> dict[str, str]:
    """Return the version and source fingerprint of the active Remotion renderer."""
    repository_root = Path(__file__).resolve().parents[3]
    video_dir = repository_root / "video"
    package_path = video_dir / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package_version = package.get("dependencies", {}).get("remotion")
    if not isinstance(package_version, str) or not package_version:
        raise ValueError("video/package.json must declare a Remotion version")

    source_dir = video_dir / "src"
    source_hashes = {
        path.relative_to(source_dir).as_posix(): sha256_file(path)
        for path in sorted(source_dir.rglob("*"))
        if path.is_file()
    }
    if not source_hashes:
        raise FileNotFoundError("Remotion renderer source is missing")
    for anim_id, assets_dir, asset in _iter_medanim_assets(repository_root):
        source_hashes[f"medanim/{anim_id}/{asset.relative_to(assets_dir).as_posix()}"] = sha256_file(asset)
    fonts_dir = video_dir / "public" / "fonts"
    font_hashes = {
        path.relative_to(fonts_dir).as_posix(): sha256_file(path)
        for path in sorted(fonts_dir.rglob("*"))
        if path.is_file()
    }
    return {
        "name": "remotion",
        "package_version": package_version,
        "source_sha256": canonical_json_hash(source_hashes),
        "fonts_sha256": canonical_json_hash(font_hashes),
    }


def render_bundle_ready(bundle_dir: Path | None) -> bool:
    """Return True when ``bundle_dir`` contains a built Remotion bundle (``index.html``)."""
    return bundle_dir is not None and bundle_dir.is_dir() and (bundle_dir / "index.html").is_file()


def chunk_renderer_identity() -> dict[str, object]:
    """Private cache identity; never changes the existing review-gate identity.

    Hash executable bundle bytes separately from per-chunk public assets. When
    no bundle was built (e.g. injected runners), hash renderer sources/configs.
    Fonts and built-in media remain conservative shared dependencies.
    """
    root = Path(__file__).resolve().parents[3]
    state = _ACTIVE_BUNDLE_STATE.get() or {}
    bundle = state.get("bundle_dir")
    files: dict[str, str] = {}
    # Remotion 4.0.522 embeds public file sizes/mtimes in index.html. Those
    # describe media, not executable code, and fresh TTS changes them on every
    # run. Media bytes are hashed per chunk. Keep the entire inventory if a
    # future renderer actually reads it (current R5 uses staticFile only).
    uses_inventory = any(
        any(token in p.read_text(encoding="utf-8")
            for token in ("getStaticFiles", "remotion_staticFiles"))
        for p in (root / "video/src").rglob("*")
        if p.is_file() and p.suffix in {".ts", ".tsx", ".js", ".jsx"}
    )
    if isinstance(bundle, Path) and render_bundle_ready(bundle):
        for p in sorted(bundle.rglob("*")):
            if not p.is_file() or p.relative_to(bundle).parts[0] == "public":
                continue
            digest = sha256_file(p)
            if p == bundle / "index.html" and not uses_inventory:
                html = p.read_text(encoding="utf-8")
                marker = "window.remotion_staticFiles = "
                prefix, present, tail = html.partition(marker)
                if present:
                    try:
                        inventory, end = json.JSONDecoder().raw_decode(tail)
                        if isinstance(inventory, list):
                            digest = sha256((prefix + marker + "[]" + tail[end:]).encode()).hexdigest()
                    except ValueError:
                        pass  # Unknown bundle format: hash all bytes conservatively.
            files["bundle/" + p.relative_to(bundle).as_posix()] = digest
    for directory in ("src", "public/fonts"):
        base = root / "video" / directory
        files.update({"video/" + p.relative_to(root / "video").as_posix(): sha256_file(p)
                      for p in sorted(base.rglob("*")) if p.is_file()})
    for name in ("package.json", "pnpm-lock.yaml", "remotion.config.ts", "tsconfig.json"):
        path = root / "video" / name
        if path.is_file():
            files["video/" + name] = sha256_file(path)
    for name in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
        path = root / name
        if path.is_file():
            files[name] = sha256_file(path)
    for anim_id, assets_dir, asset in _iter_medanim_assets(root):
        files[f"medanim/{anim_id}/{asset.relative_to(assets_dir).as_posix()}"] = sha256_file(asset)
    return {"bundle_sha256": canonical_json_hash(files)}


def sync_bundle_public(public_dir: Path, bundle_dir: Path, *, verify_bytes: bool = False) -> None:
    """Copy new or updated static assets/audio from ``public_dir`` into ``bundle_dir/public``."""
    src_root = public_dir.resolve()
    dst_root = (bundle_dir / "public").resolve()
    if not src_root.is_dir():
        return
    dst_root.mkdir(parents=True, exist_ok=True)
    for item in src_root.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(src_root)
        if not rel.parts or rel.parts[0] in _SKIP_PUBLIC_ROOTS or rel.parts[0].startswith("."):
            continue
        if item.suffix.lower() in {".mp4", ".tmp"}:
            continue
        target = dst_root / rel
        if verify_bytes and (not target.is_file() or sha256_file(item) != sha256_file(target)):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        else:
            _copy_if_newer(item, target)


def build_bundle_argv(
    public_dir: Path,
    out_dir: Path,
    *,
    stage_fonts: bool = True,
) -> list[str]:
    """Build the argv to bundle the Remotion composition once for reuse across clips/chapters."""
    repository_root = Path(__file__).resolve().parents[3]
    if stage_fonts:
        _stage_public_assets(repository_root, public_dir)
    return [
        "pnpm",
        "--dir",
        str(repository_root / "video"),
        "exec",
        "remotion",
        "bundle",
        "src/index.ts",
        "--public-dir",
        str(public_dir.resolve()),
        "--out-dir",
        str(out_dir.resolve()),
    ]


def create_bundle(
    public_dir: Path,
    out_dir: Path,
    *,
    runner: RemotionRunner | None = None,
    stage_fonts: bool = True,
) -> Path | None:
    """Build a reusable Remotion bundle in ``out_dir``; return ``out_dir`` when valid."""
    if out_dir.exists():
        rmtree_long_path(out_dir)
    argv = build_bundle_argv(public_dir, out_dir, stage_fonts=stage_fonts)
    if runner is not None:
        code = runner(argv)
    else:
        resolved = resolve_pnpm_argv(argv[1:])
        result = run_with_deadline(
            resolved,
            timeout=BUNDLE_TIMEOUT_SECONDS,
            runner=subprocess.run,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        code = result.returncode
    if code == 0 and render_bundle_ready(out_dir):
        return out_dir
    if out_dir.is_file():
        out_dir.unlink(missing_ok=True)
    elif out_dir.is_dir():
        rmtree_long_path(out_dir)
    return None


@contextmanager
def active_bundle(
    bundle_dir: Path | None,
    *,
    gl: str | None = None,
    hardware_acceleration: str | None = None,
) -> Iterator[None]:
    """Scope pre-built Remotion bundle and Chromium/GPU options to ``build_render_argv`` calls."""
    token = _ACTIVE_BUNDLE_STATE.set({
        "bundle_dir": bundle_dir,
        "gl": gl,
        "hardware_acceleration": hardware_acceleration,
    })
    try:
        yield
    finally:
        _ACTIVE_BUNDLE_STATE.reset(token)


def render_gl_fallback_argv(argv: list[str]) -> list[str] | None:
    """Return a CPU SwiftShader fallback argv when a GPU ANGLE render command fails."""
    if not any(arg.startswith(("--gl=", "--hardware-acceleration=")) for arg in argv):
        return None
    updated = [
        arg for arg in argv
        if not arg.startswith(("--gl=", "--hardware-acceleration="))
    ]
    if f"--gl={FALLBACK_GL}" in argv and "--hardware-acceleration=disable" in argv:
        return None
    updated.extend([f"--gl={FALLBACK_GL}", "--hardware-acceleration=disable"])
    return updated


def build_render_argv(
    render_input: Path,
    output: Path,
    public_dir: Path,
    *,
    frames: tuple[int, int] | None = None,
    muted: bool = False,
    stage_fonts: bool = True,
    bundle_dir: Path | None = None,
    gl: str | None = None,
    hardware_acceleration: str | None = None,
    verify_public: bool = False,
) -> list[str]:
    """Build the cross-platform argv used to render the HealthVideo composition.

    Paths are absolute because ``pnpm --dir`` runs Remotion from ``video/``.
    Stage renderer-owned fonts (and their license) before any runner is invoked.
    Command previews can disable staging to keep dry runs read-only.
    """
    state = _ACTIVE_BUNDLE_STATE.get()
    if bundle_dir is None and state is not None:
        raw_bundle = state.get("bundle_dir")
        bundle_dir = raw_bundle if isinstance(raw_bundle, Path) else None
    if gl is None and state is not None:
        raw_gl = state.get("gl")
        gl = raw_gl if isinstance(raw_gl, str) and raw_gl else None
    if hardware_acceleration is None and state is not None:
        raw_hw = state.get("hardware_acceleration")
        hardware_acceleration = raw_hw if isinstance(raw_hw, str) and raw_hw else None

    repository_root = Path(__file__).resolve().parents[3]
    if stage_fonts:
        _stage_public_assets(repository_root, public_dir)
    if render_bundle_ready(bundle_dir):
        assert bundle_dir is not None
        sync_bundle_public(public_dir, bundle_dir, verify_bytes=verify_public)
        argv = [
            "pnpm",
            "--dir",
            str(repository_root / "video"),
            "exec",
            "remotion",
            "render",
            str(bundle_dir.resolve()),
            "HealthVideo",
            "--props",
            str(render_input.resolve()),
            "--output",
            str(output.resolve()),
            "--public-dir",
            str(public_dir.resolve()),
        ]
    else:
        argv = [
            "pnpm",
            "--dir",
            str(repository_root / "video"),
            "render",
            "--props",
            str(render_input.resolve()),
            "--output",
            str(output.resolve()),
            "--public-dir",
            str(public_dir.resolve()),
        ]
    if frames is not None:
        argv.append(f"--frames={frames[0]}-{frames[1]}")
    if muted:
        argv.append("--muted")
    if gl:
        argv.append(f"--gl={gl}")
    if hardware_acceleration:
        argv.append(f"--hardware-acceleration={hardware_acceleration}")
    return argv


def default_windows_gl_options() -> tuple[str | None, str | None]:
    """Return configured or default Windows GPU/ANGLE Chromium options for Remotion."""
    gl = os.environ.get("PYH_REMOTION_GL", "").strip() or (DEFAULT_WINDOWS_GL if os.name == "nt" else None)
    hwaccel = os.environ.get("PYH_REMOTION_HWACCEL", "").strip() or ("if-possible" if os.name == "nt" else None)
    return gl, hwaccel


def build_concat_argv(concat_list: Path, audio: Path, output: Path) -> list[str]:
    """Join muted chapter parts losslessly, then mux the reviewed narration once."""
    return [
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list.resolve()),
        "-i", str(audio.resolve()),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output.resolve()),
    ]
