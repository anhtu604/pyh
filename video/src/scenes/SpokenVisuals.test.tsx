import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext} from '../layout';
import {SceneSchema, type Scene} from '../types';
import {WhiteboardScene, whiteboardFontSize} from './WhiteboardScene';
import {EvidenceHighlightScene} from './EvidenceHighlightScene';
import {SourceCardScene} from './SourceCardScene';
import {ChartScene} from './ChartScene';
import {AnatomyScene} from './AnatomyScene';
import {ProcessScene} from './ProcessScene';
import {ComparisonScene} from './ComparisonScene';
import {TimelapseScene} from './TimelapseScene';
import {StatGaugeScene} from './StatGaugeScene';
import {KineticTermScene} from './KineticTermScene';

vi.mock('remotion', () => ({
  AbsoluteFill: 'div', Img: 'img', staticFile: (path: string) => path,
  interpolate: () => 1, useCurrentFrame: () => 0, useVideoConfig: () => ({fps: 30}),
}));

const source = {source_id: 'R01', title: 'A documented study', journal: 'Journal', year: 2024,
  pmid: '12345', doi: '10.1000/example', interpretation: 'Diễn giải đã được duyệt.'};
const base: Scene = {id: 'S01', start_frame: 0, duration_frames: 90, narration: 'Lời đọc của cảnh.',
  visual: 'whiteboard', claim_id: 'C01', source_marker: '[1]',
  source_card: source,
  stat_gauge: {value: 6.8, unit: 'mg/dL', label: 'Ngưỡng bão hòa urat'},
  kinetic_term: {term: 'GÚT CẤP', definition: 'Viêm khớp cấp do tinh thể urat.'},
  evidence_highlight: {image: 'source.png', quote: 'Lời đọc của cảnh.', x: 0, y: 0, width: 0.5, height: 0.2},
  anatomy: {subject: 'heart', state: 'normal', severity: 0, motion: ''},
  visual_assets: [{path: 'chart.svg', role: 'chart'}]};
const markup = (component: React.FC<{scene: Scene}>, scene = base, layout = LAYOUTS.vertical_clip) =>
  renderToStaticMarkup(<LayoutContext.Provider value={layout}>{React.createElement(component, {scene})}</LayoutContext.Provider>);

describe('spoken visual captions', () => {
  const components = {
    whiteboard: WhiteboardScene, chart: ChartScene, evidence_highlight: EvidenceHighlightScene,
    source_card: SourceCardScene, anatomy_animation: AnatomyScene,
    process_animation: ProcessScene, comparison: ComparisonScene, timelapse: TimelapseScene,
    stat_gauge: StatGaugeScene, kinetic_term: KineticTermScene,
  } satisfies Record<Exclude<Scene['visual'], 'brand_outro'>, React.FC<{scene: Scene}>>;
  for (const [visual, component] of Object.entries(components)) {
    it(`${visual} keeps narration captions`, () => {
      // Render wrappers as well, so the mechanism scenes cannot lose their captions unnoticed.
      const output = markup(component, {...base, visual: visual as Scene['visual']});
      expect(output).toContain('aria-label="Phụ đề đang đọc"');
      expect(output).toContain('Lời');
    });
  }
});

it('source card displays real metadata and a labelled interpretation without yellow highlight', () => {
  const output = markup(SourceCardScene);
  for (const text of ['A documented study', 'Journal', '2024', 'PMID: 12345', 'DOI: 10.1000/example', 'Diễn giải', '[1]']) expect(output).toContain(text);
  expect(output).not.toContain('mix-blend-mode');
  expect(output).not.toContain('rgba(250, 204, 21');
});

it('shows identical source interpretation once and suppresses duplicate captions', () => {
  const scene = {...base, narration: source.interpretation};
  const output = markup(SourceCardScene, scene);
  expect(output).not.toContain('aria-label="Phụ đề đang đọc"');
  expect(output.split(source.interpretation)).toHaveLength(2);
});

it('keeps image evidence legible with a translucent multiply highlight and no extra quote box', () => {
  const output = markup(EvidenceHighlightScene);
  expect(output).toContain('rgba(250, 204, 21, 0.3)');
  expect(output).toContain('mix-blend-mode:multiply');
  expect(output).not.toContain('Lời đọc của cảnh.'); // captions render words as separate spans
  expect(output).toContain('aria-label="Phụ đề đang đọc"');
});

it.each(Object.values(LAYOUTS))('whiteboard only enlarges an explicit short on-screen text', layout => {
  const noSummary = markup(WhiteboardScene, base, layout);
  expect(noSummary).not.toContain('aria-label="Ý chính"');
  const output = markup(WhiteboardScene, {...base, on_screen_text: 'Ý ngắn gọn'}, layout);
  expect(output).toContain('aria-label="Ý chính"');
  expect(output).toContain(`top:${layout.whiteboardText.top}px`);
  expect(output).toContain('Ý ngắn gọn');
});

it.each(Object.values(LAYOUTS))('fits the full 90-character whiteboard summary inside its reserved box', layout => {
  const {width, height} = layout.whiteboardText;
  const text = 'W'.repeat(90);
  const size = whiteboardFontSize(text, width, height, layout.narration.fontSize);
  expect(size).toBeGreaterThanOrEqual(32);
  expect(Math.ceil(90 / Math.floor(width / size)) * size * 1.15).toBeLessThanOrEqual(height);
  const output = markup(WhiteboardScene, {...base, on_screen_text: text}, layout);
  expect(output).toContain('overflow-wrap:anywhere');
  expect(output).toContain(text);
});

it('requires source-card claim, marker, and payload and bounds on-screen text by Unicode characters', () => {
  const valid = {...base, visual: 'source_card', stat_gauge: undefined, kinetic_term: undefined, evidence_highlight: undefined};
  expect(SceneSchema.safeParse(valid).success).toBe(true);
  for (const field of ['claim_id', 'source_marker', 'source_card']) expect(SceneSchema.safeParse({...valid, [field]: undefined}).success).toBe(false);
  expect(SceneSchema.safeParse({...valid, on_screen_text: '😀'.repeat(90)}).success).toBe(true);
  expect(SceneSchema.safeParse({...valid, on_screen_text: '😀'.repeat(91)}).success).toBe(false);
});
