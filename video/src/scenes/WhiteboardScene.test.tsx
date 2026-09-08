import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {SourceMarker, WhiteboardScene} from './WhiteboardScene';

vi.mock('remotion', () => ({
  interpolate: () => 0,
  useCurrentFrame: () => 0,
}));

describe('WhiteboardScene', () => {
  it('renders the scene source marker visibly for whiteboard and chart scenes', () => {
    for (const visual of ['whiteboard', 'chart'] as const) {
      const scene = {
        schema_version: '1.0',
        id: `S-${visual}`,
        start_frame: 0,
        duration_frames: 90,
        narration: 'Bằng chứng cần dấu nguồn.',
        source_marker: '[7]',
        visual,
      };
      const marker = SourceMarker({sourceMarker: scene.source_marker});
      const rendered = WhiteboardScene({scene}) as React.ReactElement<{
        children: React.ReactNode;
      }>;
      const routedMarker = React.Children.toArray(rendered.props.children).find(
        (child) => React.isValidElement(child) && child.type === SourceMarker,
      ) as React.ReactElement<{sourceMarker: string}> | undefined;

      expect(marker.props['aria-label']).toBe('Nguồn [7]');
      expect(marker.props.children).toBe('[7]');
      expect(marker.props.style.position).toBe('absolute');
      expect(routedMarker?.props.sourceMarker).toBe('[7]');
    }
  });
});
