import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext, type Box} from '../layout';
import {visualAssetBox} from '../components/VisualAsset';
import {WhiteboardScene, whiteboardFontSize} from './WhiteboardScene';

vi.mock('remotion', () => ({interpolate: () => 1, useCurrentFrame: () => 60}));

const overlaps = (a: Box, b: Box) => a.left < b.left + b.width && b.left < a.left + a.width &&
  a.top < b.top + b.height && b.top < a.top + a.height;

it.each(Object.keys(LAYOUTS) as (keyof typeof LAYOUTS)[])(
  'test_whiteboard_text_never_overlaps_illustration: %s', format => {
    const layout = LAYOUTS[format];
    const asset = {path: 'illustration.png', role: 'whiteboard' as const};
    const image = visualAssetBox(asset, false, layout);
    const text = layout.illustrationText;
    const caption = {...layout.captions, top: layout.frame.height - layout.captions.bottom - layout.captions.height};
    expect(overlaps(image, text)).toBe(false);
    for (const box of [image, text]) {
      expect(box.left).toBeGreaterThanOrEqual(0);
      expect(box.top + box.height).toBeLessThanOrEqual(layout.frame.height);
      expect(box.left + box.width).toBeLessThanOrEqual(layout.frame.width);
      for (const reserved of [caption, layout.assets.standard, layout.assets.explain]) {
        expect(overlaps(box, reserved)).toBe(false);
      }
    }
    const on_screen_text = 'Khớp ngón chân sưng đỏ: điều gì xảy ra bên trong?';
    const scene = {id: 'hook', start_frame: 0, duration_frames: 180, narration: on_screen_text,
      on_screen_text, visual: 'whiteboard' as const, visual_assets: [asset]};
    const html = renderToStaticMarkup(<LayoutContext.Provider value={layout}>
      <WhiteboardScene scene={scene}/></LayoutContext.Provider>);
    expect(html).toContain(`top:${text.top}px`);
    expect(html).toContain(`height:${text.height}px`);
    expect(html).not.toContain('Nét vẽ whiteboard');
    expect(whiteboardFontSize('ấ'.repeat(90), text.width, text.height, layout.narration.fontSize)).toBeGreaterThanOrEqual(32);
  },
);
