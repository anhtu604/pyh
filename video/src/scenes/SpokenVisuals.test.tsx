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
import {R5ShotScene} from './R5ShotScene';
import {R5_COMPONENT_IDS} from '../types';

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
    it(`${visual} keeps narration captions in 9:16 and omits them in 16:9`, () => {
      // Render wrappers as well, so the mechanism scenes cannot lose their captions unnoticed.
      const portrait = markup(component, {...base, visual: visual as Scene['visual']}, LAYOUTS.vertical_clip);
      expect(portrait).toContain('aria-label="Phụ đề đang đọc"');
      expect(portrait).toContain('Lời');

      const landscape = markup(component, {...base, visual: visual as Scene['visual']}, LAYOUTS.youtube_long);
      expect(landscape).not.toContain('aria-label="Phụ đề đang đọc"');
      expect(landscape).not.toContain('data-mechanism-caption-band');
    });
  }
});

it('source card displays real metadata and a labelled interpretation without yellow highlight', () => {
  const output = markup(SourceCardScene);
  for (const text of ['A documented study', 'Journal', '2024', 'PMID: 12345', 'DOI: 10.1000/example', 'Diễn giải']) expect(output).toContain(text);
  expect(output).not.toContain('[1]');
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

describe('R5 caption policy across all components and kinds', () => {
  const r5Words = [
    {text: 'Lời', start_frame: 0, end_frame: 30},
    {text: 'đọc', start_frame: 30, end_frame: 60},
    {text: 'R5', start_frame: 60, end_frame: 90},
  ];
  const r5Assets = [
    {
      id: 'sample-organ',
      path: 'assets/medanim/sample.svg',
      title: 'Sample Organ Diagram',
      author: 'Fixture author',
      repository: 'servier',
      license: 'CC BY 4.0' as const,
      license_url: 'https://creativecommons.org/licenses/by/4.0/',
      source_page: 'https://smart.servier.com/smart_image/sample-organ/',
      sha256: 'a'.repeat(64),
    },
    {
      id: 'mascot-explain',
      path: 'assets/brand/mascot/explain.png',
      title: 'Mascot Explain Pose',
      author: 'Fixture author',
      repository: 'servier',
      license: 'CC BY 4.0' as const,
      license_url: 'https://creativecommons.org/licenses/by/4.0/',
      source_page: 'https://smart.servier.com/smart_image/mascot-explain/',
      sha256: 'b'.repeat(64),
    },
  ];

  const shotFor = (component: (typeof R5_COMPONENT_IDS)[number], kind: 'story' | 'mechanism' | 'recap' | 'credit') => ({
    id: `SH-${component}-${kind}`,
    kind,
    tier: 'organ',
    component,
    asset_paths: ['assets/medanim/sample.svg', 'assets/brand/mascot/explain.png'],
    question_ids: ['Q1'],
    long_shot_reason: null,
    start_frame: 0,
    end_frame: 90,
    actions: [
      {actor: 'a', compartment: 'Vùng A', change: 'c1', outcome: 'o1', start_frame: 0, end_frame: 30},
      {actor: 'a', compartment: 'Vùng B', change: 'c2', outcome: 'o2', start_frame: 30, end_frame: 60},
      {actor: 'a', compartment: 'Vùng C', change: 'c3', outcome: 'o3', start_frame: 60, end_frame: 90},
    ],
    text_windows: [
      {kind: 'scale_bar' as const, text: 'Cơ thể → Cơ quan', claim_ids: ['C01'], exception_reason: null, start_frame: 0, end_frame: 90},
      {kind: 'label' as const, text: 'Vùng A', claim_ids: ['C01'], exception_reason: null, start_frame: 0, end_frame: 90},
      {kind: 'takeaway' as const, text: 'Chốt ý chính ngắn gọn', claim_ids: ['C01'], exception_reason: null, start_frame: 0, end_frame: 90},
      {kind: 'lab_sheet' as const, text: 'ALT | 240 | U/L | < 40 | H', claim_ids: ['C01'], exception_reason: null, start_frame: 0, end_frame: 90},
      {kind: 'credit' as const, text: 'Kho A · CC BY 4.0', claim_ids: [], exception_reason: null, start_frame: 0, end_frame: 90},
    ],
  });

  for (const component of R5_COMPONENT_IDS) {
    it(`R5 ${component} omits burned-in captions in 16:9 and renders them in 9:16 with mascot and word timings intact`, () => {
      const scene: Scene = {
        ...base,
        narration: 'Lời đọc R5',
        words: r5Words,
        visual_assets: [{path: 'assets/brand/mascot/explain.png', role: 'mascot', pose: 'explain'}],
        resolved_shots: [shotFor(component, 'mechanism')],
      };

      const landscape = renderToStaticMarkup(
        <LayoutContext.Provider value={LAYOUTS.youtube_long}>
          <R5ShotScene scene={scene} frame={15} assets={r5Assets} />
        </LayoutContext.Provider>,
      );
      expect(landscape).not.toContain('aria-label="Phụ đề đang đọc"');
      expect(landscape).not.toContain('data-mechanism-caption-band');

      const portrait = renderToStaticMarkup(
        <LayoutContext.Provider value={LAYOUTS.vertical_clip}>
          <R5ShotScene scene={scene} frame={15} assets={r5Assets} />
        </LayoutContext.Provider>,
      );
      expect(portrait).toContain('aria-label="Phụ đề đang đọc"');
      expect(scene.words).toEqual(r5Words);
    });
  }
});
