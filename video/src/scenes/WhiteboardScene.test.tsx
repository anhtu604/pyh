import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {WhiteboardScene} from './WhiteboardScene';

vi.mock('remotion', () => ({
  interpolate: () => 0,
  useCurrentFrame: () => 0,
}));

describe('WhiteboardScene', () => {
  it('does not route the internal source marker into whiteboard or chart scenes', () => {
    for (const visual of ['whiteboard', 'chart'] as const) {
      const scene = {
        schema_version: '1.0', id: `S-${visual}`, start_frame: 0, duration_frames: 90,
        narration: 'Bằng chứng cần dấu nguồn.', source_marker: '[7]', visual,
      };
      const rendered = WhiteboardScene({scene}) as React.ReactElement<{children: React.ReactNode}>;
      const serialized = JSON.stringify(React.Children.toArray(rendered.props.children));
      expect(serialized).not.toContain('[7]');
    }
  });
});