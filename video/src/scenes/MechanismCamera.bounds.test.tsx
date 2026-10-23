import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {ANATOMY_COMPONENTS, ANATOMY_CONTENT_BOXES} from '../anatomy/registry';
import {LAYOUTS} from '../layout';
import {mechanismCamera, mechanismContentBounds} from './MechanismScene';

vi.mock('remotion', async (original) => ({...await original<typeof import('remotion')>(),
  useCurrentFrame: () => 0, useVideoConfig: () => ({fps: 30})}));

it('keeps actual SVG content inside each viewport for every framing, subject, format and camera progress', () => {
  for (const layout of Object.values(LAYOUTS)) {
    for (const [subject, Organ] of Object.entries(ANATOMY_COMPONENTS)) {
      const key = subject as keyof typeof ANATOMY_COMPONENTS;
      const markup = renderToStaticMarkup(<Organ state="diseased" severity={1} emphasizeFlow />);
      const [vx, vy, vw, vh] = markup.match(/viewBox="([^"]+)"/)![1].split(' ').map(Number);
      for (const boxes of [[layout.mechanism.subject], layout.mechanism.comparison]) {
        const left = Math.min(...boxes.map(b => b.left));
        const top = Math.min(...boxes.map(b => b.top));
        const viewport = {left, top, width: Math.max(...boxes.map(b => b.left + b.width)) - left,
          height: Math.max(...boxes.map(b => b.top + b.height)) - top};
        const bounds = mechanismContentBounds(key, boxes, viewport);
        for (let framing = 0; framing < 4; framing++) for (let step = 0; step <= 100; step++) {
          const camera = mechanismCamera('S-BOUNDS', step / 100, framing, {viewport, content: bounds});
          const [ox, oy] = camera.origin.split(' ').map(v => parseFloat(v) / 100);
          for (const box of boxes) {
            const scale = Math.min(box.width / vw, box.height / vh);
            const c = ANATOMY_CONTENT_BOXES[key];
            const x = box.left - left + (box.width - vw * scale) / 2 + (c.left - vx) * scale;
            const y = box.top - top + (box.height - vh * scale) / 2 + (c.top - vy) * scale;
            const tx = (p: number) => ox * viewport.width + (p - ox * viewport.width) * camera.zoom + camera.x / 100 * viewport.width;
            const ty = (p: number) => oy * viewport.height + (p - oy * viewport.height) * camera.zoom + camera.y / 100 * viewport.height;
            expect(tx(x), `${subject}/${framing}`).toBeGreaterThanOrEqual(-1e-6);
            expect(ty(y)).toBeGreaterThanOrEqual(-1e-6);
            expect(tx(x + c.width * scale)).toBeLessThanOrEqual(viewport.width + 1e-6);
            expect(ty(y + c.height * scale)).toBeLessThanOrEqual(viewport.height + 1e-6);
          }
        }
      }
    }
  }
});
