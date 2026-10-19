import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {VisualAsset, visualAssetBox} from './VisualAsset';

vi.mock('remotion', async (original) => ({
  ...await original<typeof import('remotion')>(),
  Img: 'img',
  interpolate: () => 1,
  staticFile: (path: string) => path,
  useCurrentFrame: () => 12,
  useVideoConfig: () => ({fps: 30}),
}));

describe('VisualAsset', () => {
  it('uses only the declared static path', () => {
    const output = renderToStaticMarkup(<VisualAsset asset={{path: 'assets/guide.svg', role: 'mascot', pose: 'welcome'}} />);
    expect(output).toContain('src="assets/guide.svg"');
    expect(output).toContain('data-mascot-presenter="true"');
    expect(output).toContain('overflow:hidden');
    expect(output).not.toContain('data-mascot-plate');
  });

  it('keeps mascot and whiteboard outside marker and caption zones', () => {
    for (const pose of ['welcome', 'explain', 'caution'] as const) {
      const box = visualAssetBox({path: `assets/${pose}.svg`, role: 'mascot', pose});
      expect(box.top).toBeGreaterThan(170);
      expect(box.top + box.height).toBe(1610);
      expect(box.left + box.width).toBeLessThan(1000);
    }
    expect(visualAssetBox({path: 'assets/board.svg', role: 'whiteboard'})).toEqual(
      {height: 980, left: 90, top: 190, width: 900},
    );
  });
});
