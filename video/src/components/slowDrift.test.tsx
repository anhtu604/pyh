import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext} from '../layout';
import {VisualAsset, visualAssetBox} from './VisualAsset';
import {WhiteboardScene} from '../scenes/WhiteboardScene';
import {DRIFT_MAX_SCALE, LONG_SCENE_SECONDS, slowDriftTransform} from './slowDrift';

const clock = vi.hoisted(() => ({frame: 120}));
vi.mock('remotion', async (original) => ({
  ...await original<typeof import('remotion')>(),
  Img: 'img',
  staticFile: (path: string) => path,
  useCurrentFrame: () => clock.frame,
  useVideoConfig: () => ({fps: 30}),
}));

describe('slowDriftTransform', () => {
  it('is inactive for scenes shorter than 8 seconds', () => {
    for (const duration of [30, 90, 180, LONG_SCENE_SECONDS * 30 - 1]) {
      const state = slowDriftTransform(60, duration, 30);
      expect(state.active).toBe(false);
      expect(state.scale).toBe(1);
      expect(state.transform).toBeUndefined();
    }
  });

  it('activates for scenes >= 8s, stays within 100%..108%, and reverses smoothly every 8s', () => {
    const duration = 900; // 30s
    const start = slowDriftTransform(0, duration, 30);
    const midSeg0 = slowDriftTransform(120, duration, 30);
    const endSeg0 = slowDriftTransform(239, duration, 30);
    const startSeg1 = slowDriftTransform(240, duration, 30);
    const midSeg1 = slowDriftTransform(360, duration, 30);
    const startSeg2 = slowDriftTransform(480, duration, 30);

    expect(start.active).toBe(true);
    expect(start.scale).toBeCloseTo(1, 5);
    expect(midSeg0.scale).toBeGreaterThan(1.03);
    expect(midSeg0.scale).toBeLessThan(DRIFT_MAX_SCALE);
    expect(endSeg0.scale).toBeCloseTo(DRIFT_MAX_SCALE, 3);
    // Continuous across 8s boundary (no sudden jump)
    expect(Math.abs(startSeg1.scale - endSeg0.scale)).toBeLessThan(0.002);
    // Segment 1 reverses direction (zooming back out toward 1.0)
    expect(midSeg1.scale).toBeLessThan(startSeg1.scale);
    expect(startSeg2.scale).toBeCloseTo(1, 5);

    for (let f = 0; f <= duration; f += 15) {
      const s = slowDriftTransform(f, duration, 30);
      expect(s.scale).toBeGreaterThanOrEqual(1);
      expect(s.scale).toBeLessThanOrEqual(DRIFT_MAX_SCALE + 1e-6);
      expect(s.transform).toContain('scale(');
    }
  });
});

describe('slow drift integration in VisualAsset and WhiteboardScene', () => {
  it('clips long whiteboard illustrations inside their safe box and leaves short ones static', () => {
    const asset = {path: 'assets/scene01.png', role: 'whiteboard' as const};
    const box = visualAssetBox(asset, false, LAYOUTS.youtube_long);

    clock.frame = 120;
    const shortHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <VisualAsset asset={asset} durationFrames={180} />
      </LayoutContext.Provider>,
    );
    expect(shortHtml).not.toContain('data-slow-drift');
    expect(shortHtml).not.toContain('scale(');

    const longHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <VisualAsset asset={asset} durationFrames={600} />
      </LayoutContext.Provider>,
    );
    expect(longHtml).toContain('data-slow-drift="true"');
    expect(longHtml).toContain('overflow:hidden');
    expect(longHtml).toContain(`width:${box.width}px`);
    expect(longHtml).toContain(`height:${box.height}px`);
    expect(longHtml).toContain('scale(');
  });

  it('applies slow drift to long text-only WhiteboardScene without moving on_screen_text', () => {
    const baseScene = {
      id: 'S08',
      start_frame: 0,
      duration_frames: 600,
      narration: 'Giải thích cơ chế dài.',
      on_screen_text: 'Ý chính cố định',
      visual: 'whiteboard' as const,
      visual_assets: [],
    };
    clock.frame = 120;
    const longHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <WhiteboardScene scene={baseScene} />
      </LayoutContext.Provider>,
    );
    expect(longHtml).toContain('data-slow-drift="true"');
    expect(longHtml).toContain(`top:${LAYOUTS.youtube_long.whiteboardText.top}px`);

    const shortHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <WhiteboardScene scene={{...baseScene, duration_frames: 120}} />
      </LayoutContext.Provider>,
    );
    expect(shortHtml).not.toContain('data-slow-drift="true"');
  });
});
