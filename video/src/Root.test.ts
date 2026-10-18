import {describe, expect, it} from 'vitest';
import {metadataFromProps} from './Root';
import {parseRenderInput} from './types';

const scene = {id: 'S01', start_frame: 0, duration_frames: 1800, narration: 'N',
  visual: 'whiteboard' as const, chapter_id: 'CH01'};

describe('format profile', () => {
  it('keeps legacy input vertical', () => {
    expect(metadataFromProps({title: 'T', audio_file: 'a.wav', scenes: [scene]}))
      .toEqual({durationInFrames: 1800, width: 1080, height: 1920});
  });

  it('renders youtube_long landscape', () => {
    expect(metadataFromProps({title: 'T', audio_file: 'a.wav', scenes: [scene],
      format_profile: 'youtube_long', width: 1920, height: 1080}))
      .toEqual({durationInFrames: 1800, width: 1920, height: 1080});
  });

  it('rejects size that mismatches the profile', () => {
    expect(() => parseRenderInput({title: 'T', audio_file: 'a.wav',
      format_profile: 'youtube_long', width: 1080, height: 1920}))
      .toThrow(/youtube_long requires 1920x1080/);
  });

  it('rejects malformed chapter ids', () => {
    expect(() => parseRenderInput({title: 'T', audio_file: 'a.wav',
      scenes: [{...scene, chapter_id: 'one'}]})).toThrow();
  });
});
