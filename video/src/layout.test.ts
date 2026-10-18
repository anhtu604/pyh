import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {visualAssetBox} from './components/VisualAsset';
import {LAYOUTS, LayoutContext} from './layout';
import {WhiteboardScene} from './scenes/WhiteboardScene';
import type {Box} from './layout';

vi.mock('remotion', () => ({interpolate: () => 1, useCurrentFrame: () => 0}));

const inside = (box: Box, frame: {width: number; height: number}) =>
  box.left >= 0 && box.top >= 0 && box.left + box.width <= frame.width && box.top + box.height <= frame.height;

describe('layouts', () => {
  it('keeps vertical captions and narrative geometry', () => {
    const v = LAYOUTS.vertical_clip;
    expect(v.frame).toEqual({width: 1080, height: 1920});
    expect(v.captions).toMatchObject({left: 72, bottom: 174, width: 936, height: 136, fontSize: 48, maxWords: 6});
    expect(v.narration).toEqual({left: 96, right: 96, top: 760, fontSize: 72});

  });

  it('every landscape box fits in 1920x1080', () => {
    const l = LAYOUTS.youtube_long;
    const boxes = [l.chart.image, ...Object.values(l.assets)];
    boxes.forEach((box) => expect(inside(box, l.frame)).toBe(true));
    expect(l.captions.left + l.captions.width).toBeLessThanOrEqual(1920);
  });

  it('visualAssetBox uses the given layout', () => {
    const asset = {path: 'a.svg', role: 'mascot' as const, pose: 'explain' as const};
    expect(visualAssetBox(asset, false, LAYOUTS.youtube_long)).toEqual(LAYOUTS.youtube_long.assets.explain);
    expect(visualAssetBox(asset)).toEqual(LAYOUTS.vertical_clip.assets.explain);
  });

  it('WhiteboardScene renders landscape values inside the youtube_long provider', () => {
    const scene = {id: 'S01', start_frame: 0, duration_frames: 90, narration: 'Noi dung', visual: 'whiteboard' as const, visual_assets: []};
    const html = (layout: typeof LAYOUTS.vertical_clip) => renderToStaticMarkup(
      React.createElement(LayoutContext.Provider, {value: layout}, React.createElement(WhiteboardScene, {scene})),
    );
    const landscape = html(LAYOUTS.youtube_long);
    expect(landscape).toContain('viewBox="0 0 1200 120"');
    expect(landscape).toContain('width:1200px');
    expect(landscape).toContain('top:380px');
    expect(html(LAYOUTS.vertical_clip)).toContain('viewBox="0 0 936 136"');
  });
});


it('limits all regular mascot boxes to 24% vertical and 30% landscape', () => {
  for (const layout of Object.values(LAYOUTS)) {
    const limit = layout.frame.height * (layout.frame.height > layout.frame.width ? 0.24 : 0.30);
    for (const box of [layout.mechanism.mascot, layout.assets.standard, layout.assets.explain, layout.assets.outroMascot]) {
      expect(box.height).toBeLessThanOrEqual(limit);
      expect(inside(box, layout.frame)).toBe(true);
    }
  }
});
