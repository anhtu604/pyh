import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {ArterySection, arteryGeometry} from './anatomy/ArterySection';
import {Heart, heartGeometry} from './anatomy/Heart';
import {AnatomyScene} from './scenes/AnatomyScene';
import {ProcessScene} from './scenes/ProcessScene';
import {ComparisonScene} from './scenes/ComparisonScene';
import {TimelapseScene} from './scenes/TimelapseScene';
import {brand} from './anatomy/palette';
import {HealthVideo} from './HealthVideo';
import {LAYOUTS, LayoutContext} from './layout';
import {parseRenderInput, type Scene} from './types';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', async (original) => ({
  ...await original<typeof import('remotion')>(),
  AbsoluteFill: 'div', Sequence: 'section', Audio: 'audio', Img: 'img',
  staticFile: (path: string) => `/static/${path}`,
  useCurrentFrame: () => clock.frame,
  useVideoConfig: () => ({fps: 30}),
}));

const scene: Scene = {
  id: 'S-TEST-01', start_frame: 0, duration_frames: 90,
  narration: 'Illustration only — never displayed', visual: 'anatomy_animation',
  anatomy: {subject: 'artery_cross_section', state: 'diseased', severity: 0.8, motion: 'Illustration only'},
  visual_assets: [{path: 'assets/explain.svg', role: 'mascot', pose: 'explain'}],
};
const html = (Component: React.FC<{scene: Scene}>, s = scene, format: keyof typeof LAYOUTS = 'youtube_long') =>
  renderToStaticMarkup(<LayoutContext.Provider value={LAYOUTS[format]}><Component scene={s} /></LayoutContext.Provider>);

describe('anatomy geometry', () => {
  it('thickens the wall and narrows the lumen monotonically, preserving normal geometry', () => {
    const normal = arteryGeometry('normal', 0, 0, 30);
    const mild = arteryGeometry('diseased', 0.4, 0, 30);
    const severe = arteryGeometry('diseased', 0.9, 0, 30);
    expect(normal.wallThickness).toBeLessThan(mild.wallThickness);
    expect(mild.wallThickness).toBeLessThan(severe.wallThickness);
    expect(normal.lumenRadius).toBeGreaterThan(mild.lumenRadius);
    expect(mild.lumenRadius).toBeGreaterThan(severe.lumenRadius);
    expect(arteryGeometry('normal', 1, 0, 30)).toEqual(normal);
    expect(severe.flowSpeed).toBeLessThan(normal.flowSpeed);
    expect(severe.cellCount).toBeGreaterThan(normal.cellCount);
  });
  it('pulses less in a stiff artery and thickens the left ventricle', () => {
    expect(arteryGeometry('normal', 0, 5, 30).outerRadius).not.toBe(arteryGeometry('normal', 0, 0, 30).outerRadius);
    expect(heartGeometry('diseased', 1, 0, 30).wallThickness).toBeGreaterThan(heartGeometry('normal', 0, 0, 30).wallThickness);
    for (const Component of [ArterySection, Heart]) {
      clock.frame = 0;
      const first = renderToStaticMarkup(<Component state="diseased" severity={0.8} />);
      clock.frame = 5;
      expect(renderToStaticMarkup(<Component state="diseased" severity={0.8} />)).not.toBe(first);
    }
  });
});

describe('mechanism scenes', () => {
  for (const Component of [AnatomyScene, ProcessScene, ComparisonScene, TimelapseScene]) {
    for (const format of ['youtube_long', 'vertical_clip'] as const) {
      for (const subject of ['artery_cross_section', 'heart'] as const) {
        it(`${Component.name} renders ${subject} in ${format} at first/mid/last frames`, () => {
          for (const frame of [0, 45, 89]) {
            clock.frame = frame;
            const output = html(Component, {...scene, anatomy: {...scene.anatomy!, subject}}, format);
            expect(output).toContain('<svg');
            expect(output).toContain('background-color:#0A1C2E');
            expect(output).toContain('data-mascot-plate="true"');
            expect(output).toContain('/static/assets/explain.svg');
            expect(output).not.toContain(scene.narration);
            expect(output).not.toMatch(/NaN|Infinity|linearGradient|radialGradient|filter=|animation:/);
            expect(html(Component, {...scene, anatomy: {...scene.anatomy!, subject}}, format)).toBe(output);
          }
        });
      }
    }
    it(`${Component.name} rejects unknown subjects and missing anatomy`, () => {
      expect(() => html(Component, {...scene, anatomy: {...scene.anatomy!, subject: 'unknown' as never}})).toThrow(/Unsupported anatomy subject: unknown/);
      expect(() => html(Component, {...scene, anatomy: undefined})).toThrow(/requires anatomy/);
    });
  }
  it('switches comparison axis and forces normal/diseased states', () => {
    expect(html(ComparisonScene)).toContain('flex-direction:row');
    expect(html(ComparisonScene, scene, 'vertical_clip')).toContain('flex-direction:column');
    expect(html(ComparisonScene)).toContain('data-state="normal"');
    expect(html(ComparisonScene)).toContain('data-state="diseased"');
  });
  it('animates timelapse severity from zero to the target', () => {
    clock.frame = 0;
    expect(html(TimelapseScene)).toContain('data-severity="0"');
    clock.frame = 89;
    expect(html(TimelapseScene)).toContain('data-severity="0.8"');
  });
  it('keeps subject and mascot in safe bounds at maximum camera scale', () => {
    const l = LAYOUTS.vertical_clip.mechanism;
    for (const box of [l.subject, ...l.comparison]) {
      expect(box.left - box.width * 0.075).toBeGreaterThanOrEqual(0);
      expect(box.left + box.width * 1.075).toBeLessThanOrEqual(1080 * 0.85);
      expect(box.top + box.height * 1.075).toBeLessThanOrEqual(1920 * 0.8);
    }
    expect(l.mascot.top + l.mascot.height + 5).toBeLessThan(1920 * 0.88);
    expect(l.mascot.left + l.mascot.width).toBeLessThan(1080 * 0.85);
  });
  it.each(['anatomy_animation', 'process_animation', 'comparison', 'timelapse'] as const)('dispatches %s without duplicate mascots', (visual) => {
    const props = parseRenderInput({title: 'Illustration only', audio_file: 'audio/silence.wav', visual_budget_profile: 'explain_first_v1', scenes: [{...scene, visual}]});
    const output = renderToStaticMarkup(<HealthVideo {...props} />);
    expect(output).toContain('<svg');
    expect(output.match(/src="\/static\/assets\/explain.svg"/g)).toHaveLength(1);
  });
});


describe('visual regression fixes', () => {
  it('keeps a clear heart silhouette with rounded great vessels and no white chamber marks', () => {
    const output = renderToStaticMarkup(<Heart state="normal" severity={0} />);
    expect(output).not.toContain(brand.off_white);
    expect(output).not.toContain('M202 271 L231 286');
    expect(output).toContain('data-vessel="aortic-arch"');
    expect(output).toContain('data-vessel="pulmonary-trunk"');
    expect(output).toContain('viewBox="40 10 440 540"');
  });
  it('centres vertical subject, comparisons and mascot at frame x=540', () => {
    const l = LAYOUTS.vertical_clip.mechanism;
    for (const box of [l.subject, ...l.comparison, l.mascot]) {
      expect(Math.abs(box.left + box.width / 2 - 540)).toBeLessThanOrEqual(2);
    }
    for (const box of [l.subject, ...l.comparison]) {
      expect(box.top + box.height * 1.075).toBeLessThan(l.mascot.top);
    }
  });
  it.each([['youtube_long', 324], ['vertical_clip', 450]] as const)('caps the %s mascot height within the approved frame proportion', (format, height) => {
    const box = LAYOUTS[format].mechanism.mascot;
    expect(box.height).toBe(height);
    expect(box.height).toBeLessThanOrEqual(LAYOUTS[format].frame.height * (format === 'youtube_long' ? 0.30 : 0.24));
    expect(box.width).toBeGreaterThanOrEqual(Math.floor(height * 760 / 900));
    const output = html(AnatomyScene, scene, format);
    expect(output).toContain(`height:${height}px`);
    expect(output).toContain('background-color:#F7F4EC');
    expect(output).toContain('border-radius:50%');
  });
});


describe('anterior heart regression', () => {
  it('places the apex right of the base and the aortic arch above and to its left', () => {
    const g = heartGeometry('normal', 0, 0, 30);
    expect(g.apex.x).toBeGreaterThan(g.base.x);
    expect(g.apex.y).toBeGreaterThan(g.base.y);
    expect(g.aortaArchApex.y).toBeLessThan(g.base.y);
    expect(g.aortaArchApex.x).toBeLessThan(g.base.x);
    const output = renderToStaticMarkup(<Heart state="normal" severity={0} />);
    expect(output).toContain(`${g.apex.x} ${g.apex.y}`);
    expect(output).toContain('data-vessel="superior-vena-cava"');
    expect(output).toContain('data-vessel="aortic-branches"');
    expect(output).toContain('data-septum="true"');
    expect(output).not.toMatch(/stroke=|gradient|filter=/i);
  });
  it('insets the LV cavity monotonically with severity and preserves normal geometry', () => {
    const stages = [0, 0.25, 0.5, 0.75, 1].map(s => heartGeometry('diseased', s, 0, 30));
    for (let i = 1; i < stages.length; i++) {
      expect(stages[i].wallThickness).toBeGreaterThan(stages[i - 1].wallThickness);
      const coords = (path: string) => path.match(/[-\d.]+/g)!.map(Number);
      const previous = coords(stages[i - 1].leftVentricleCavity);
      const current = coords(stages[i].leftVentricleCavity);
      expect(current[0]).toBeGreaterThan(previous[0]);
      expect(current[4]).toBeLessThan(previous[4]);
      expect(current[7]).toBeLessThan(previous[7]);
    }
    expect(heartGeometry('normal', 1, 0, 30)).toEqual(heartGeometry('normal', 0, 0, 30));
    const surface = renderToStaticMarkup(<Heart state="normal" severity={0} cutaway={false} />);
    expect(surface).toContain('data-heart-silhouette="true"');
    expect(surface).not.toContain('data-cutaway-chambers');
  });
  it('contracts atria before ventricles and anchors ventricular squeeze at the apex', () => {
    const early = heartGeometry('normal', 0, 0, 30);
    const ventricularBeat = heartGeometry('normal', 0, 6, 30);
    expect(early.atrialScale).toBeLessThan(ventricularBeat.atrialScale);
    expect(early.scaleY).toBeGreaterThan(ventricularBeat.scaleY);
    clock.frame = 6;
    expect(renderToStaticMarkup(<Heart state="normal" severity={0} />)).toContain('translate(365 510) scale(');
  });
});
