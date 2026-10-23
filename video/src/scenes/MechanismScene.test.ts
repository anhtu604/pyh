import {expect, it} from 'vitest';
import type {Scene} from '../types';
import {anatomyCueProgress} from './MechanismScene';

const scene: Scene = {id: 'S01', visual: 'process_animation', narration: 'Mầm tinh thể lớn rồi lắng đọng',
  start_frame: 600, duration_frames: 300, anatomy: {subject: 'joint_fluid_urate_to_inflammation',
    state: 'diseased', severity: 1, motion: '', cues: [{word: 'Mầm', action: 'seed', start_frame: 30},
      {word: 'lớn', action: 'grow', start_frame: 120}, {word: 'đọng', action: 'deposit', start_frame: 240}]}};
it('runs each action from its local keyword frame and remains seek deterministic', () => {
  expect(anatomyCueProgress(scene, 0)).toEqual({seed: 0, grow: 0, deposit: 0});
  expect(anatomyCueProgress(scene, 75)).toEqual({seed: 1, grow: 0, deposit: 0});
  expect(anatomyCueProgress(scene, 165)).toEqual({seed: 1, grow: 1, deposit: 0});
  expect(anatomyCueProgress(scene, 285)).toEqual({seed: 1, grow: 1, deposit: 1});
  expect(anatomyCueProgress(scene, 75)).toEqual({seed: 1, grow: 0, deposit: 0});
});
it('keeps legacy motion when authored cues have no alignment', () => {
  expect(anatomyCueProgress({...scene, anatomy: {...scene.anatomy!, cues: [{word: 'Mầm', action: 'seed'}]}}, 90)).toBeUndefined();
});
