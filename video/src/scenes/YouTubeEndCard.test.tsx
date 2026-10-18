import React from 'react';
import {expect, it, vi} from 'vitest';
import {YouTubeEndCard} from './YouTubeEndCard';

vi.mock('remotion', () => ({
  AbsoluteFill: 'div', Img: 'img', interpolate: () => 1,
  staticFile: (path: string) => path, useCurrentFrame: () => 12,
}));

it('shows configured text and welcome SVG inside vertical safe bounds', () => {
  const card = YouTubeEndCard({text: 'Custom YouTube invitation', mascotPath: 'clips/cta/welcome.svg'}) as React.ReactElement<{children: React.ReactElement<{
    children?: React.ReactNode; src?: string; style: React.CSSProperties & {
      left: number; top: number; width: number; height?: number;
    };
  }> []}>;
  const [text, mascot] = card.props.children;
  expect(text.props.children).toBe('Custom YouTube invitation');
  expect(mascot.props.src).toBe('clips/cta/welcome.svg');
  for (const element of [text, mascot]) {
    const box = element.props.style;
    expect(box.left).toBeGreaterThanOrEqual(72);
    expect(box.left + box.width).toBeLessThan(936);
    expect(box.top + (box.height ?? 300)).toBeLessThan(1570);
  }
});
