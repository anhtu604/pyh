import {describe, expect, it} from 'vitest';
import {metadataFromProps, verticalClipDefaults} from './Root';
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

describe('vertical clip', () => {
  it('defaults to a 30 s 9:16 clip', () => {
    expect(metadataFromProps(verticalClipDefaults))
      .toEqual({durationInFrames: 900, width: 1080, height: 1920});
  });

  it('accepts a Python clip render input (re-timed, no chapter)', () => {
    const clip = {title: 'T', audio_file: 'audio/clips/CL01.wav', format_profile: 'vertical_clip',
      width: 1080, height: 1920, scenes: [
        {id: 'S01', start_frame: 0, duration_frames: 900, narration: 'A', visual: 'whiteboard'},
        {id: 'S02', start_frame: 900, duration_frames: 600, narration: 'B', visual: 'whiteboard'},
      ]};
    expect(metadataFromProps(clip)).toEqual({durationInFrames: 1500, width: 1080, height: 1920});
  });
});
