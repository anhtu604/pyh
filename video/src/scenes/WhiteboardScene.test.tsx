import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext} from '../layout';
import {
  WHITEBOARD_REVEAL_MAX_FRAMES,
  WHITEBOARD_REVEAL_MIN_FRAMES,
  whiteboardInkReveal,
  WhiteboardScene,
} from './WhiteboardScene';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', () => ({
  interpolate: (frame: number, [start, end]: [number, number], [outStart, outEnd]: [number, number]) => {
    const t = Math.max(0, Math.min(1, (frame - start) / Math.max(1, end - start)));
    return outStart + (outEnd - outStart) * t;
  },
  useCurrentFrame: () => clock.frame,
}));

describe('WhiteboardScene', () => {
  it('does not route the internal source marker into whiteboard or chart scenes', () => {
    clock.frame = 0;
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

  it('reveals ink progressively per term within 0.3-0.8s (9-24 frames) using 3 brand colors + 1 accent', () => {
    expect(WHITEBOARD_REVEAL_MIN_FRAMES).toBe(9);
    expect(WHITEBOARD_REVEAL_MAX_FRAMES).toBe(24);
    expect(whiteboardInkReveal(10, 10).progress).toBe(0);
    expect(whiteboardInkReveal(17.5, 10, 15).progress).toBeCloseTo(0.5, 5);
    expect(whiteboardInkReveal(25, 10, 15).progress).toBe(1);
    // Clamps out-of-range reveal durations to [9, 24]
    expect(whiteboardInkReveal(9, 0, 2).progress).toBe(1);
    expect(whiteboardInkReveal(24, 0, 60).progress).toBe(1);

    const scene = {
      schema_version: '1.0',
      id: 'S-WB-01',
      start_frame: 0,
      duration_frames: 150,
      narration: 'Bước một kiểm tra phiếu; bước hai hỏi bác sĩ.',
      on_screen_text: 'Kiểm tra phiếu; hỏi bác sĩ',
      visual: 'whiteboard' as const,
      entrances: [
        {text: 'Kiểm tra phiếu; ', start_frame: 0},
        {text: 'hỏi bác sĩ', start_frame: 60},
      ],
    };

    clock.frame = 67;
    const midHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <WhiteboardScene scene={scene} />
      </LayoutContext.Provider>,
    );
    expect(midHtml).toContain('data-whiteboard-palette="brand-3plus1"');
    expect(midHtml).toContain('data-ink-progress="1.00"');
    expect(midHtml).toContain('data-ink-progress="0.47"');
    expect(midHtml).toContain('#12304A');
    expect(midHtml).toContain('#18A6A6');
    expect(midHtml).toContain('#F4B942');
  });
});