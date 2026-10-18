import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {YouTubeEndCard, endCardGeometry} from './YouTubeEndCard';
import {MascotGuide} from '../components/MascotGuide';
import {brand} from '../anatomy/palette';
import {LAYOUTS, LayoutContext} from '../layout';

const clock = vi.hoisted(() => ({frame: 12}));
vi.mock('remotion', async (original) => ({
  ...await original<typeof import('remotion')>(),
  AbsoluteFill: 'div', Img: 'img',
  staticFile: (path: string) => `/static/${path}`,
  useCurrentFrame: () => clock.frame, useVideoConfig: () => ({fps: 30}),
}));

it('shows configured text, brand colours and the welcome asset through MascotGuide', () => {
  const output = renderToStaticMarkup(<YouTubeEndCard text="Custom YouTube invitation" mascotPath="clips/cta/welcome.svg" />);
  expect(output.replace(/<[^>]+>/g, '')).toContain('Custom YouTube invitation');
  expect(output).toContain('/static/clips/cta/welcome.svg');
  expect(output).toContain(brand.off_white);
  expect(output).toContain(brand.night);
  expect(output).toContain('data-mascot-plate="true"');
  expect(output).toContain('PYH mascot welcome');
  const box = LAYOUTS.vertical_clip.mechanism.mascot;
  expect(box.left + box.width).toBeLessThan(1080 * 0.85);
  expect(box.top + box.height + 5).toBeLessThan(1920 * 0.88);
});

it('enters then bobs deterministically, uses only a registered mascot, and supports both layouts', () => {
  const scene = {visual_assets: [{path: 'registered/caution.svg', role: 'mascot' as const, pose: 'caution' as const}]};
  for (const layout of Object.values(LAYOUTS)) {
    const render = () => renderToStaticMarkup(<LayoutContext.Provider value={layout}><MascotGuide scene={scene} /></LayoutContext.Provider>);
    clock.frame = 0;
    expect(render()).toContain('opacity:0');
    clock.frame = 45;
    const settled = render();
    expect(settled).toContain('/static/registered/caution.svg');
    expect(settled).toContain(`left:${layout.mechanism.mascot.left}px`);
    expect(render()).toBe(settled);
    clock.frame = 55;
    expect(render()).not.toBe(settled);
  }
  expect(renderToStaticMarkup(<MascotGuide scene={{visual_assets: []}} />)).toBe('');
});


it('centres text and mascot as one group with a shared spring and literal YouTube highlight', () => {
  for (const layout of Object.values(LAYOUTS)) {
    const {group, mascot} = endCardGeometry(layout.frame.width, layout.frame.height);
    expect(group.left + group.width / 2).toBe(layout.frame.width / 2);
    expect(group.top + group.height / 2).toBe(layout.frame.height / 2);
    expect(group.left + mascot.left + mascot.width / 2).toBeCloseTo(layout.frame.width / 2, 6);
    if (layout.frame.height > layout.frame.width) {
      expect(group.top).toBeGreaterThanOrEqual(layout.frame.height / 3);
      expect(group.top + group.height).toBeLessThanOrEqual(layout.frame.height * 2 / 3);
      expect(group.left + group.width).toBeLessThanOrEqual(layout.frame.width * 0.85);
    }
    const render = (text: string) => renderToStaticMarkup(<LayoutContext.Provider value={layout}><YouTubeEndCard text={text} mascotPath="cta.svg" /></LayoutContext.Provider>);
    clock.frame = 45;
    const settled = render('Visit YouTube then YouTube again');
    expect(settled.match(/color:#F4B942/g)).toHaveLength(2);
    expect(settled).toContain('font-size:72px;font-weight:700');
    expect(settled).toContain('color:#F7F4EC');
    expect(settled).toContain(`left:${group.left}px;top:${group.top}px`);
    expect(settled).toContain(`left:${mascot.left}px;top:${mascot.top}px`);
    expect(render('Custom invitation')).not.toContain('YouTube');
    expect(render('Custom invitation')).not.toContain('color:#F4B942');
    clock.frame = 0;
    expect(render('Visit YouTube')).toContain('opacity:0;transform:translateY(40px)');
    expect(render('Visit YouTube')).not.toBe(settled);
  }
});
