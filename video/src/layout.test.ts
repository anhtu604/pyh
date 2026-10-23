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
const overlaps = (a: Box, b: Box) => a.left < b.left + b.width && b.left < a.left + a.width && a.top < b.top + b.height && b.top < a.top + a.height;

it.each(Object.keys(LAYOUTS) as (keyof typeof LAYOUTS)[])('%s reserves large mechanism and separate whiteboard text areas', format => {
  const l = LAYOUTS[format];
  const caption = {...l.captions, top: l.frame.height - l.captions.bottom - l.captions.height};
  expect(l.mechanism.subject.width).toBeGreaterThanOrEqual(format === 'vertical_clip' ? 1000 : 880);
  expect(l.mechanism.subject.height).toBeGreaterThanOrEqual(format === 'vertical_clip' ? 1100 : 820);
  for (const box of [l.mechanism.subject, ...l.mechanism.comparison]) {
    expect(inside(box, l.frame)).toBe(true);
    expect(overlaps(box, caption)).toBe(false);
    expect(overlaps(box, l.mechanism.mascot)).toBe(false);
  }
  expect(inside(l.whiteboardText, l.frame)).toBe(true);
  for (const reserved of [l.assets.standard, l.assets.explain, caption]) expect(overlaps(l.whiteboardText, reserved)).toBe(false);
});

describe('layouts', () => {
  it.each(Object.keys(LAYOUTS) as (keyof typeof LAYOUTS)[])('%s gives both caption rows room for Vietnamese accents and descenders', (format) => {
    const c = LAYOUTS[format].captions;
    // Bundled Be Vietnam Pro SemiBold: Vietnamese ymax=1215, ymin=-240 / 1000 em.
    const ascender = c.fontSize * 1.215;
    const descender = c.fontSize * 0.24;
    expect(c.rowY[0] - ascender).toBeGreaterThanOrEqual(4);
    expect(c.height - c.rowY[1] - descender).toBeGreaterThanOrEqual(4);
    expect(c.rowY[1] - ascender - c.rowY[0] - descender).toBeGreaterThanOrEqual(4);
  });

  it.each(Object.keys(LAYOUTS) as (keyof typeof LAYOUTS)[])('%s enlarges the chart into the space above captions', (format) => {
    const l = LAYOUTS[format];
    const image = l.chart.image;
    expect(image.width).toBeGreaterThan(format === 'vertical_clip' ? 940 : 1400);
    expect(image.height).toBeGreaterThan(format === 'vertical_clip' ? 1040 : 700);
    expect(image.top + image.height + 24).toBeLessThanOrEqual(l.frame.height - l.captions.bottom - l.captions.height);
    expect(inside(image, l.frame)).toBe(true);
  });

  it('gives a landscape 3:2 chart at least 15% more display area in each dimension', () => {
    const image = LAYOUTS.youtube_long.chart.image;
    const scale = Math.min(image.width / 1080, image.height / 720);
    // The previous 1400x700 contain box was height limited at 700/720.
    expect(scale).toBeGreaterThanOrEqual((700 / 720) * 1.15);
    expect(image.top).toBeLessThanOrEqual(60);
  });
  it('keeps vertical captions and narrative geometry', () => {
    const v = LAYOUTS.vertical_clip;
    expect(v.frame).toEqual({width: 1080, height: 1920});
    expect(v.captions).toMatchObject({left: 72, bottom: 150, width: 936, height: 160, fontSize: 48, maxWords: 6});
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
    const scene = {id: 'S01', start_frame: 0, duration_frames: 90, narration: 'Noi dung', on_screen_text: 'Y chinh', visual: 'whiteboard' as const, visual_assets: []};
    const html = (layout: typeof LAYOUTS.vertical_clip) => renderToStaticMarkup(
      React.createElement(LayoutContext.Provider, {value: layout}, React.createElement(WhiteboardScene, {scene})),
    );
    const landscape = html(LAYOUTS.youtube_long);
    expect(landscape).toContain('viewBox="0 0 1200 148"');
    expect(landscape).toContain('width:1200px');
    expect(landscape).toContain('top:300px');
    expect(html(LAYOUTS.vertical_clip)).toContain('viewBox="0 0 936 160"');
  });
});


it('uses presenter windows at the cut line, clear of captions and vertical buttons', () => {
  for (const layout of Object.values(LAYOUTS)) {
    const vertical = layout.frame.height > layout.frame.width;
    const cut = vertical ? layout.frame.height - layout.captions.bottom - layout.captions.height : layout.frame.height;
    for (const box of [layout.assets.standard, layout.assets.explain, layout.assets.outroMascot]) {
      expect(box.height / layout.frame.height).toBeCloseTo(vertical ? 0.30 : 0.38);
      expect(box.top + box.height).toBe(cut);
      expect(inside(box, layout.frame)).toBe(true);
      if (vertical) expect(box.left + box.width).toBeLessThanOrEqual(layout.frame.width * 0.88);
      else expect(box.left + box.width).toBeLessThanOrEqual(layout.captions.left);
    }
  }
});
