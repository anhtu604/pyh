"""Cheap input checks before a paid agent invocation; no retry budget is consumed."""

from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from healthvideo.domain.script import Script
from healthvideo.storage.files import read_yaml
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.visuals.medanim_assets import copy_used_assets, load_asset_catalog
from healthvideo.workflows.adopt_r5 import r5_active


def preflight(step: str, project_dir: Path) -> list[str]:
    if step != 'storyboard_design':
        return []
    errors = []
    try:
        root = resolve_project_layout(project_dir).artifact_root
        script_path = root / 'script/script.yaml'
        if not script_path.is_file():
            errors.append('Thiếu đầu vào script/script.yaml trong revision hiện hành.')
        else:
            try:
                script = Script.model_validate(read_yaml(script_path))
                if not script.lines or len({line.id for line in script.lines}) != len(script.lines):
                    raise ValueError('Các dòng script phải có ID duy nhất và không rỗng.')
            except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
                errors.append(f'Đầu vào script/script.yaml không hợp lệ: {exc}')
        catalog = root / 'assets/r5/catalog.yaml'
        if not r5_active(root) or not catalog.is_file():
            return errors
        # Give field errors an asset identity even when strict catalog loading fails.
        raw = read_yaml(catalog)
        for item in raw.get('assets', []):
            if not isinstance(item, dict):
                continue
            for field in ('author', 'license', 'source_page', 'original_url', 'retrieved_at'):
                if not str(item.get(field) or '').strip():
                    errors.append(f"Hình {item.get('id', '?')}: thiếu trường {field}.")
        records = load_asset_catalog(catalog)
        # Reuse the acquisition boundary's path, size and SHA checks, offline.
        with TemporaryDirectory(prefix='pyh-preflight-') as temporary:
            for record in records:
                try:
                    copy_used_assets(records, [record.id], catalog.parent, Path(temporary))
                except (OSError, ValueError) as exc:
                    errors.append(f'Hình {record.id}: file/SHA-256 không hợp lệ: {exc}')
    except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
        errors.append(f'Đầu vào storyboard_design không hợp lệ: {exc}')
    return errors
