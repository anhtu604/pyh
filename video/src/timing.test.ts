import {describe, expect, it} from 'vitest';
import {activeSceneIndex} from './HealthVideo';
import {durationFromScenes} from './Root';

describe('activeSceneIndex', () => {
  it('uses exact short and long storyboard durations', () => {
    expect(durationFromScenes([{id: 'S01', start_frame: 0, duration_frames: 600,
      narration: 'Hook', visual: 'whiteboard'}])).toBe(600);
    expect(durationFromScenes([{id: 'S01', start_frame: 0, duration_frames: 4200,
      narration: 'Hook', visual: 'whiteboard'}])).toBe(4200);
  });
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
