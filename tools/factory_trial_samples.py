"""Build offline nonmedical evidence without creating projects or approvals."""
from pathlib import Path

from healthvideo.workflows.factory_trials import build_stage_sample, trial_root


def build_samples(root: Path) -> dict[int, list[Path]]:
    return {stage: build_stage_sample(trial_root(root) / 'samples' / f'stage-{stage}', stage)
            for stage in range(1, 5)}
