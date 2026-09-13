import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {VisualAsset, visualAssetBox} from './VisualAsset';

vi.mock('remotion', () => ({
  Img: 'img',
  interpolate: () => 1,
  staticFile: (path: string) => path,
  useCurrentFrame: () => 12,
}));

describe('VisualAsset', () => {
  it('uses only the declared static path', () => {
    const element = VisualAsset({asset: {path: 'assets/guide.svg', role: 'mascot', pose: 'welcome'}}) as React.ReactElement<{src: string}>;
    expect(element.props.src).toBe('assets/guide.svg');
  });

  it('keeps mascot and whiteboard outside marker and caption zones', () => {
    for (const pose of ['welcome', 'explain', 'caution'] as const) {
      const box = visualAssetBox({path: `assets/${pose}.svg`, role: 'mascot', pose});
      expect(box.top).toBeGreaterThan(170);
      expect(box.top + box.height).toBeLessThan(1570);
      expect(box.left + box.width).toBeLessThan(1000);
    }
    expect(visualAssetBox({path: 'assets/board.svg', role: 'whiteboard'})).toEqual(
      {height: 980, left: 90, top: 190, width: 900},
    );
  });
});
