import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext, SAFE_GAP, boxesIntersect, captionBox, evidenceFrame} from './layout';
import type {Scene} from './types';
import {ChartScene} from './scenes/ChartScene';
import {EvidenceHighlightScene} from './scenes/EvidenceHighlightScene';
import {SourceCardScene, sourceCardScale} from './scenes/SourceCardScene';
import {AnatomyScene} from './scenes/AnatomyScene';
import {KineticTermScene} from './scenes/KineticTermScene';
import {StatGaugeScene} from './scenes/StatGaugeScene';
import {highlightImageLayout} from './scenes/highlightGeometry';
import {WhiteboardScene} from './scenes/WhiteboardScene';

vi.mock('remotion', () => ({
  AbsoluteFill: 'div', Img: 'img', staticFile: (path: string) => path,
  interpolate: () => 1, useCurrentFrame: () => 0, useVideoConfig: () => ({fps: 30}),
}));

const INTERNAL_CODE = /\[E\d+\]|\bR\d{2}_\w+|\bM\d{2}\b/;
const long = 'Rất dài '.repeat(60);
const card = {source_id: 'R06_internal_ledger', title: long, journal: 'Journal of Very Long Names '.repeat(4), year: 2024,
  pmid: '12345678', doi: '10.1000/' + 'x'.repeat(80), interpretation: long};
const base: Scene = {id: 'S01', start_frame: 0, duration_frames: 90, narration: 'Lời đọc của cảnh.',
  visual: 'whiteboard', claim_id: 'C01', source_marker: '[E03]', source_card: card,
  stat_gauge: {value: 6.8, unit: 'mg/dL', label: 'Ngưỡng'},
  kinetic_term: {term: 'GÚT', definition: 'Viêm khớp.'},
  evidence_highlight: {image: 'source.png', quote: 'Trích dẫn.', x: 0, y: 0, width: 0.5, height: 0.2},
  anatomy: {subject: 'heart', state: 'normal', severity: 0, motion: ''},
  visual_assets: [{path: 'chart.svg', role: 'chart'}]};
const scenes: Record<string, React.FC<{scene: Scene}>> = {
  whiteboard: WhiteboardScene, chart: ChartScene, evidence_highlight: EvidenceHighlightScene,
  source_card: SourceCardScene, anatomy_animation: AnatomyScene, stat_gauge: StatGaugeScene, kinetic_term: KineticTermScene,
};
const render = (component: React.FC<{scene: Scene}>, scene: Scene, format: keyof typeof LAYOUTS) =>
  renderToStaticMarkup(<LayoutContext.Provider value={LAYOUTS[format]}>{React.createElement(component, {scene})}</LayoutContext.Provider>);

describe.each(['vertical_clip', 'youtube_long'] as const)('source safe zones (%s)', (format) => {
  for (const [visual, component] of Object.entries(scenes)) {
    it(`${visual} never draws internal source codes`, () => {
      const text = render(component, {...base, visual: visual as Scene['visual'], source_marker: '[E03]',
        source_card: {...card, title: 'Tên bài', interpretation: 'Diễn giải.'}}, format).replace(/<[^>]*>/g, ' ');
      expect(text).not.toMatch(INTERNAL_CODE);
      expect(text).not.toContain('R06_internal_ledger');
    });
  }

  it('source card box stays clear of the caption box', () => {
    const layout = LAYOUTS[format];
    const box = layout.sourceCard;
    expect(boxesIntersect(box, captionBox(layout))).toBe(false);
    expect(captionBox(layout).top - (box.top + box.height)).toBeGreaterThanOrEqual(SAFE_GAP);
    expect(box.top + box.height).toBeLessThanOrEqual(layout.frame.height);
    expect(box.left + box.width).toBeLessThanOrEqual(layout.frame.width);
  });

  it('evidence image area stays above the caption band', () => {
    const layout = LAYOUTS[format];
    const hardened = {...base.evidence_highlight!, crop_pixel_width: 3000, crop_pixel_height: 4000};
    for (const h of [base.evidence_highlight!, hardened]) {
      const img = highlightImageLayout(h, evidenceFrame(layout));
      expect(boxesIntersect(img, captionBox(layout))).toBe(false);
      expect(img.top + img.height).toBeLessThanOrEqual(captionBox(layout).top - SAFE_GAP + 0.001);
    }
  });

  it('long source strings keep the rendered card inside its safe box and shrink the text', () => {
    const layout = LAYOUTS[format];
    const box = layout.sourceCard;
    const landscape = layout.frame.width > layout.frame.height;
    const scale = sourceCardScale(card, {width: box.width - 2 * box.padding, height: box.height - 2 * box.padding}, landscape, box.fontSize);
    expect(scale).toBeLessThan(1);
    const html = render(SourceCardScene, {...base, visual: 'source_card'}, format);
    expect(html).toContain('overflow:hidden');
    expect(html).toContain(`height:${box.height}px`);
    expect(html).not.toContain('R06_internal_ledger');
  });
});