import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {HealthVideo} from './HealthVideo';
import {VisualAsset} from './components/VisualAsset';

vi.mock('remotion', () => ({
  AbsoluteFill: 'div',
  Audio: 'audio',
  Sequence: 'section',
  staticFile: (path: string) => path,
}));

const input = (visual: 'whiteboard' | 'evidence_highlight') => ({
  schema_version: '1.0',
  title: 'PHY',
  audio_file: 'audio/silence.wav',
  scenes: [{
    schema_version: '1.0',
    id: 'S01', start_frame: 0, duration_frames: 90, narration: 'Nội dung', visual,
    source_marker: visual === 'evidence_highlight' ? '[1]' : undefined,
    evidence_highlight: visual === 'evidence_highlight' ? {
      schema_version: '1.0',
      image: 'assets/evidence.svg', quote: 'Trích dẫn', x: 0, y: 0,
      width: 0.5, height: 0.5,
    } : undefined,
    visual_assets: [{path: 'assets/guide.svg', role: 'mascot' as const, pose: 'welcome' as const}],
  }],
  width: 1080 as const, height: 1920 as const, fps: 30 as const,
});

describe('HealthVideo visual asset layer', () => {
  it.each(['whiteboard', 'evidence_highlight'] as const)(
    'renders one declared asset for a %s scene',
    (visual) => {
      const root = HealthVideo(input(visual)) as React.ReactElement<{children: React.ReactNode}>;
      const sequence = React.Children.toArray(root.props.children)[1] as React.ReactElement<{
        children: React.ReactNode;
      }>;
      const assets = React.Children.toArray(sequence.props.children).filter(
        (child) => React.isValidElement(child) && child.type === VisualAsset,
      );
      expect(assets).toHaveLength(1);
    },
  );
});
