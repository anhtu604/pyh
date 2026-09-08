import {describe, expect, it} from 'vitest';
import {activeSceneIndex} from './HealthVideo';

describe('activeSceneIndex', () => {
  it('selects the scene that owns the current frame', () => {
    const scenes = [
      {id: 'S01', start_frame: 0, duration_frames: 90},
      {id: 'S02', start_frame: 90, duration_frames: 60},
    ];
    expect(activeSceneIndex(scenes, 0)).toBe(0);
    expect(activeSceneIndex(scenes, 89)).toBe(0);
    expect(activeSceneIndex(scenes, 90)).toBe(1);
  });
});
