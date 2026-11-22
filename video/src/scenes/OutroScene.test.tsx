import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {VisualAsset, visualAssetBox} from '../components/VisualAsset';
import {LAYOUTS, LayoutContext, SAFE_GAP, boxesIntersect, captionBox} from '../layout';
import type {Box} from '../layout';
import type {Scene} from '../types';
import {OutroScene, estimateOutroTextHeight, outroFontSize} from './OutroScene';

vi.mock('remotion', async (original) => ({
  ...await original<typeof import('remotion')>(),
  AbsoluteFill: 'div',
  Img: 'img',
  interpolate: () => 1,
  staticFile: (path: string) => path,
  useCurrentFrame: () => 15,
  useVideoConfig: () => ({fps: 30}),
}));

const inside = (box: Box, frame: {width: number; height: number}): boolean =>
  box.left >= 0 && box.top >= 0 && box.left + box.width <= frame.width && box.top + box.height <= frame.height;

const TYPICAL_OUTRO =
  'Cảm ơn bạn đã theo dõi Protect Your Health. Nếu thấy hữu ích, hãy đăng ký kênh và chia sẻ cho người thân cùng biết để bảo vệ sức khỏe mỗi ngày.';
const LONG_OUTRO = `${TYPICAL_OUTRO} `.repeat(4).trim();

const outroScene = (narration: string): Scene => ({
  id: 'S36',
  start_frame: 0,
  duration_frames: 300,
  narration,
  visual: 'brand_outro',
  visual_assets: [
    {path: 'assets/pyh.svg', role: 'brand'},
    {path: 'assets/welcome.svg', role: 'mascot', pose: 'welcome'},
  ],
});

describe.each(['vertical_clip', 'youtube_long'] as const)('brand_outro geometry (%s)', (format) => {
  const layout = LAYOUTS[format];
  const brandBox = visualAssetBox({path: 'assets/pyh.svg', role: 'brand'}, true, layout);
  const mascotBox = visualAssetBox({path: 'assets/welcome.svg', role: 'mascot', pose: 'welcome'}, true, layout);
  const textBox: Box = {
    left: layout.outroText.left,
    top: layout.outroText.top,
    width: layout.outroText.width,
    height: layout.outroText.height,
  };
  const captions = captionBox(layout);

  it('keeps logo, mascot, active outro elements, and caption zone pairwise disjoint and inside the frame', () => {
    const named: [string, Box][] = format === 'vertical_clip'
      ? [
        ['outroBrand', brandBox],
        ['outroMascot', mascotBox],
        ['outroText', textBox],
        ['captionBox', captions],
      ]
      : [
        ['outroBrand', brandBox],
        ['outroMascot', mascotBox],
        ['captionBox', captions],
      ];
    for (const [, box] of named) {
      expect(inside(box, layout.frame)).toBe(true);
    }
    for (let i = 0; i < named.length; i += 1) {
      for (let j = i + 1; j < named.length; j += 1) {
        expect(boxesIntersect(named[i][1], named[j][1])).toBe(false);
      }
    }
    if (format === 'youtube_long') {
      expect(brandBox.left + brandBox.width / 2).toBe(layout.frame.width / 2);
    }
  });

  it('maintains safe separation around outro layout elements and preserves >= 54px base font size', () => {
    expect(layout.outroText.fontSize).toBeGreaterThanOrEqual(54);
    if (format === 'vertical_clip') {
      expect(textBox.top - (brandBox.top + brandBox.height)).toBeGreaterThanOrEqual(SAFE_GAP);
      expect(captions.top - (textBox.top + textBox.height)).toBeGreaterThanOrEqual(SAFE_GAP);
      expect(mascotBox.top - (textBox.top + textBox.height)).toBeGreaterThanOrEqual(SAFE_GAP);
    } else {
      expect(brandBox.left - (mascotBox.left + mascotBox.width)).toBeGreaterThanOrEqual(SAFE_GAP);
      expect(captions.top - (brandBox.top + brandBox.height)).toBeGreaterThanOrEqual(SAFE_GAP);
    }
  });

  it('fits typical outro narration at full 54px and shrinks long narration without overflowing the box', () => {
    const typicalSize = outroFontSize(TYPICAL_OUTRO, textBox.width, textBox.height, layout.outroText.fontSize);
    expect(typicalSize).toBe(layout.outroText.fontSize);
    expect(estimateOutroTextHeight(TYPICAL_OUTRO, textBox.width, typicalSize)).toBeLessThanOrEqual(textBox.height);

    const longSize = outroFontSize(LONG_OUTRO, textBox.width, textBox.height, layout.outroText.fontSize);
    expect(longSize).toBeLessThan(layout.outroText.fontSize);
    expect(estimateOutroTextHeight(LONG_OUTRO, textBox.width, longSize)).toBeLessThanOrEqual(textBox.height);
  });

  it('renders OutroScene with high-contrast brand badge on #FFFDF7, keeping text in 9:16 and omitting it in 16:9', () => {
    const scene = outroScene(TYPICAL_OUTRO);
    const html = renderToStaticMarkup(
      <LayoutContext.Provider value={layout}>
        <OutroScene scene={scene} />
        {(scene.visual_assets ?? []).map((asset) => (
          <VisualAsset key={asset.path} asset={asset} outro />
        ))}
      </LayoutContext.Provider>,
    );
    expect(html).toContain('background-color:#FFFDF7');
    expect(html).toContain('data-brand-badge="true"');
    expect(html).toContain('data-mascot-presenter="true"');
    if (format === 'vertical_clip') {
      expect(html).toContain('data-outro-text="true"');
      expect(html).toContain(`height:${textBox.height}px`);
      expect(html).toContain('overflow:hidden');
      expect(html).toContain(TYPICAL_OUTRO);
    } else {
      expect(html).toContain('data-outro-landscape="true"');
      expect(html).toContain('data-outro-accent="true"');
      expect(html).not.toContain('data-outro-text');
      expect(html).not.toContain(TYPICAL_OUTRO);
    }
  });
});
