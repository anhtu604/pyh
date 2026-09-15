import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {AiClipScene} from './AiClipScene';

const {staticFile} = vi.hoisted(() => ({staticFile: vi.fn((path: string) => path)}));
vi.mock('remotion', () => ({OffthreadVideo: 'video', staticFile}));

describe('AiClipScene', () => {
  it('plays the declared clip once, muted, without loop, trim or rate change', () => {
    const scene = {
      id: 'S04', start_frame: 0, duration_frames: 120, narration: 'Minh họa đã duyệt',
      source_marker: '[1]', visual: 'ai_clip' as const,
      visual_assets: [{path: 'assets/ai-clips/S04.mp4', role: 'ai_clip' as const}],
    };

    const root = AiClipScene({scene}) as React.ReactElement<{children: React.ReactNode}>;
    const videos = React.Children.toArray(root.props.children).filter(
      (child) => React.isValidElement(child) && child.type === 'video',
    ) as React.ReactElement<Record<string, unknown>>[];

    expect(videos).toHaveLength(1);
    expect(videos[0].props.src).toBe('assets/ai-clips/S04.mp4');
    expect(videos[0].props.muted).toBe(true);
    for (const prop of ['loop', 'playbackRate', 'trimBefore', 'trimAfter', 'volume']) {
      expect(videos[0].props).not.toHaveProperty(prop);
    }
    expect(staticFile).toHaveBeenCalledTimes(1);
  });
});
