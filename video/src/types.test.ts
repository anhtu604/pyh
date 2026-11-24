import {describe, expect, it, vi} from 'vitest';
import {EvidenceHighlightSchema, RenderInputSchema, SceneSchema,
  R5ContractSchema, R5ShotSchema, ResolvedR5ShotSchema, QualityReportSchema} from './types';

const validHighlight = {
  image: 'assets/evidence-card.svg',
  quote: 'Đọc kết quả trong đúng bối cảnh.',
  x: 0.1,
  y: 0.2,
  width: 0.6,
  height: 0.3,
};

describe('EvidenceHighlightSchema', () => {
  it('rejects highlights that extend past the right edge', () => {
    expect(EvidenceHighlightSchema.safeParse({...validHighlight, x: 0.5, width: 0.6}).success).toBe(
      false,
    );
  });

  it('rejects highlights that extend past the bottom edge', () => {
    expect(EvidenceHighlightSchema.safeParse({...validHighlight, y: 0.8, height: 0.3}).success).toBe(
      false,
    );
  });

  it('requires pixel dimensions with crop provenance', () => {
    expect(EvidenceHighlightSchema.safeParse({
      ...validHighlight,
      source_id: 'R01',
      page: 2,
      crop_x: 0.05,
      crop_y: 0.15,
      crop_width: 0.7,
      crop_height: 0.4,
    }).success).toBe(false);
  });
});

describe('SceneSchema', () => {
  it('parses the declared brand outro and rejects role pose misuse', () => {
    const outro = {id: 'OUTRO', script_line_id: 'OUTRO', start_frame: 600,
      duration_frames: 90, narration: 'Cảm ơn', visual: 'brand_outro',
      visual_assets: [{path: 'assets/pyh.svg', role: 'brand'}]};
    expect(SceneSchema.safeParse(outro).success).toBe(true);
    expect(SceneSchema.safeParse({...outro, visual_assets: [
      {path: 'assets/pyh.svg', role: 'brand', pose: 'welcome'},
    ]}).success).toBe(false);
  });
  it('accepts declared mascot refs and defaults legacy scenes', () => {
    const legacy = SceneSchema.parse({
      id: 'S01', start_frame: 0, duration_frames: 90,
      narration: 'Legacy', visual: 'whiteboard',
    });
    expect(legacy.visual_assets).toEqual([]);
    const current = SceneSchema.parse({...legacy, visual_assets: [
      {path: 'assets/guide.svg', role: 'mascot', pose: 'welcome'},
    ]});
    expect(current.visual_assets).toHaveLength(1);
    expect(SceneSchema.safeParse({...legacy, visual_assets: [
      {path: '../guide.svg', role: 'mascot', pose: 'welcome'},
    ]}).success).toBe(false);
    expect(SceneSchema.safeParse({...legacy, visual_assets: [
      {path: '.', role: 'mascot', pose: 'welcome'},
    ]}).success).toBe(false);
    expect(SceneSchema.safeParse({...legacy, visual_assets: [
      {path: 'assets/same.svg', role: 'mascot', pose: 'welcome'},
      {path: 'assets/same.svg', role: 'mascot', pose: 'welcome'},
    ]}).success).toBe(false);
  });
  it('requires a source marker for evidence scenes', () => {
    expect(
      SceneSchema.safeParse({
        id: 'S02',
        start_frame: 0,
        duration_frames: 90,
        narration: 'Bằng chứng cần ngữ cảnh.',
        visual: 'evidence_highlight',
        evidence_highlight: validHighlight,
      }).success,
    ).toBe(false);
  });

  it('requires evidence highlight details for evidence scenes', () => {
    expect(
      SceneSchema.safeParse({
        id: 'S02',
        start_frame: 0,
        duration_frames: 90,
        narration: 'Bằng chứng cần ngữ cảnh.',
        source_marker: '[1]',
        visual: 'evidence_highlight',
      }).success,
    ).toBe(false);
  });

  it('accepts a chart role without pose', () => {
    expect(SceneSchema.safeParse({
      id: 'S03', start_frame: 0, duration_frames: 90,
      narration: 'Chart declared', visual: 'chart',
      visual_assets: [{path: 'assets/chart.svg', role: 'chart'}],
    }).success).toBe(true);
    expect(SceneSchema.safeParse({
      id: 'S03', start_frame: 0, duration_frames: 90,
      narration: 'Chart declared', visual: 'chart',
      visual_assets: [{path: 'assets/chart.svg', role: 'chart', pose: 'explain'}],
    }).success).toBe(false);
  });

  it('validates motion overlay emphasis_text against scene narration', () => {
    const base = {
      id: 'S04',
      start_frame: 0,
      duration_frames: 90,
      narration: 'Tăng acid uric máu kéo dài gây lắng đọng tinh thể urat.',
      visual: 'whiteboard',
    };
    expect(SceneSchema.safeParse({
      ...base,
      motion: {
        emphasis: 'marker-underline-title',
        emphasis_text: 'tăng acid uric máu',
        transition_in: 'circle-match-iris',
      },
    }).success).toBe(true);
    expect(SceneSchema.safeParse({
      ...base,
      motion: {
        emphasis: 'marker-underline-title',
        emphasis_text: 'suy thận mạn',
      },
    }).success).toBe(false);
    expect(SceneSchema.safeParse({
      ...base,
      motion: {
        emphasis_text: 'tăng acid uric',
      },
    }).success).toBe(false);
  });

  it('validates stat_gauge requires claim_id and payload, and kinetic_term requires payload', () => {
    expect(SceneSchema.safeParse({
      id: 'S05',
      start_frame: 0,
      duration_frames: 90,
      narration: 'Ngưỡng bão hòa urat huyết thanh khoảng 6,8 mg/dL.',
      claim_id: 'C01',
      visual: 'stat_gauge',
      stat_gauge: {value: 6.8, unit: 'mg/dL', label: 'Ngưỡng bão hòa urat'},
    }).success).toBe(true);
    expect(SceneSchema.safeParse({
      id: 'S05',
      start_frame: 0,
      duration_frames: 90,
      narration: 'Ngưỡng bão hòa urat huyết thanh khoảng 6,8 mg/dL.',
      claim_id: 'C01',
      visual: 'stat_gauge',
      stat_gauge: {
        value: 6.8,
        unit: 'mg/dL',
        label: 'Ngưỡng bão hòa urat',
        variant: 'before-after-slider-scrub',
      },
    }).success).toBe(false);
    expect(SceneSchema.safeParse({
      id: 'S05',
      start_frame: 0,
      duration_frames: 90,
      narration: 'Ngưỡng bão hòa urat huyết thanh khoảng 6,8 mg/dL.',
      visual: 'stat_gauge',
      stat_gauge: {value: 6.8, unit: 'mg/dL', label: 'Ngưỡng bão hòa urat'},
    }).success).toBe(false);
    expect(SceneSchema.safeParse({
      id: 'S06',
      start_frame: 0,
      duration_frames: 90,
      narration: 'Gút cấp là phản ứng viêm khớp do tinh thể urat.',
      visual: 'kinetic_term',
      kinetic_term: {term: 'GÚT CẤP', definition: 'Viêm khớp cấp tính do tinh thể muối urat.'},
    }).success).toBe(true);
    expect(SceneSchema.safeParse({
      id: 'S06',
      start_frame: 0,
      duration_frames: 90,
      narration: 'Gút cấp là phản ứng viêm khớp do tinh thể urat.',
      visual: 'kinetic_term',
    }).success).toBe(false);
  });
});

describe('RenderInputSchema chart contract', () => {
  const chartInput = {
    title: 'PYH', audio_file: 'audio/narration.wav', visual_budget_profile: 'm6_5_v1',
    scenes: [{id: 'S01', start_frame: 0, duration_frames: 90,
      narration: 'Chart', visual: 'chart',
      visual_assets: [{path: 'assets/chart.svg', role: 'chart'}]}],
  };

  it('requires exactly one declared chart ref for enabled chart scenes', () => {
    expect(RenderInputSchema.safeParse(chartInput).success).toBe(true);
    expect(RenderInputSchema.safeParse({...chartInput, scenes: [{
      ...chartInput.scenes[0], visual_assets: [],
    }]}).success).toBe(false);
    expect(RenderInputSchema.safeParse({...chartInput, scenes: [{
      ...chartInput.scenes[0], visual_assets: [
        {path: 'assets/chart-a.svg', role: 'chart'},
        {path: 'assets/chart-b.svg', role: 'chart'},
      ],
    }]}).success).toBe(false);
  });

  it('defaults unmarked chart input to explain-first', () => {
    const explainFirst = {...chartInput, visual_budget_profile: undefined, scenes: [{
      ...chartInput.scenes[0], visual_assets: [],
    }]};
    expect(RenderInputSchema.safeParse(explainFirst).success).toBe(true);
  });
});


it('rejects removed AI clip scene and asset kinds', () => {
  const scene = {id: 'removed', start_frame: 0, duration_frames: 120,
    narration: 'Illustration', visual: 'ai_clip'};
  expect(SceneSchema.safeParse(scene).success).toBe(false);
  expect(SceneSchema.safeParse({...scene, visual: 'whiteboard', visual_assets: [
    {path: 'assets/removed.mp4', role: 'ai_clip'},
  ]}).success).toBe(false);
});

const contract = {
  questions: [
    {id: 'Q1', text: 'First?', hook_line_id: 'L1', answer_line_ids: ['L3']},
    {id: 'Q2', text: 'Second?', hook_line_id: 'L1', answer_line_ids: ['L3']},
  ],
  blocks: [{id: 'B1', line_ids: ['L2'], question_ids: ['Q1', 'Q2'],
    takeaway_line_id: 'L2', professional_update: true}],
};
const shot = {
  id: 'SH1', kind: 'mechanism', tier: 'cell', component: 'ZoomChain',
  asset_paths: ['assets/cell.svg'], question_ids: ['Q1'],
  start: {kind: 'scene_start', line_id: null, phrase: null},
  end: {kind: 'scene_end', line_id: null, phrase: null},
  actions: [], text_windows: [], long_shot_reason: null,
};

describe('R5 contracts', () => {
  it('round trips the Python wire payload including explicit nulls', () => {
    expect(R5ContractSchema.parse(contract)).toEqual(contract);
    expect(R5ShotSchema.parse(shot)).toEqual(shot);
    const {start: _start, end: _end, ...fields} = shot;
    const resolved = {...fields, start_frame: 0, end_frame: 300};
    expect(ResolvedR5ShotSchema.parse(resolved)).toEqual(resolved);
    const empty = {count: 0, median_seconds: null, p90_seconds: null};
    const report = {standard: 'pyh_r5_quality_v1', quality_profile: 'r5_v1', estimated: true,
      fps: 30, denominator_frames: 300, numerator_frames: 0, source_intervals: [],
      shot_intervals: [], text_union_intervals: [], story: empty, mechanism: empty, manual_review: 'pending', issues: []};
    expect(QualityReportSchema.parse(report)).toEqual(report);
  });

  it('round trips actual Python serialization through Zod and back to Python', async () => {
    // Node test helpers are imported through Vitest; the browser project has no @types/node.
    const {execFileSync} = await vi.importActual<{execFileSync: (file: string, args: string[],
      options: {cwd: string; env: Record<string, string | undefined>; encoding: 'utf8'; input?: string}) => string}>('node:child_process');
    const {fileURLToPath} = await vi.importActual<{fileURLToPath: (url: URL) => string}>('node:url');
    const process = await vi.importActual<{env: Record<string, string | undefined>; platform: string}>('node:process');
    const python = process.env.PYH_TEST_PYTHON ?? (process.platform === 'win32'
      ? 'E:/Protect Your Health/.venv/Scripts/python.exe' : 'python3');
    const cwd = fileURLToPath(new URL('../../', import.meta.url));
    const env = {...process.env, PYTHONPATH: fileURLToPath(new URL('../../src', import.meta.url))};
    const build = `
import json
from tests.domain.test_quality_standards import contract_payload, shot_payload
from healthvideo.domain.quality_standards import R5Contract, R5Shot, ResolvedR5Shot, QualityReport
s = shot_payload()
action = dict(actor='entity', compartment='cell', change='move', outcome='arrival')
s['actions'] = [dict(**action, start=s['start'], end=s['end'])]
s['text_windows'] = [dict(kind='label', text='Entity', start=s['start'], end=s['end'])]
resolved = {k:v for k,v in s.items() if k not in ('start','end','actions','text_windows')}
resolved['actions'] = [dict(**action, start_frame=0, end_frame=300)]
resolved['text_windows'] = [dict(kind='label', text='Entity', start_frame=0, end_frame=30)]
empty = dict(count=0, median_seconds=None, p90_seconds=None)
models = [R5Contract(**contract_payload()), R5Shot(**s),
          ResolvedR5Shot(**resolved, start_frame=0, end_frame=300),
          QualityReport(estimated=True, denominator_frames=300, numerator_frames=0,
              shot_intervals=[], source_intervals=[], text_union_intervals=[], story=empty, mechanism=empty)]
print(json.dumps([m.model_dump(mode='json') for m in models]))
`;
    const payload = JSON.parse(execFileSync(python, ['-c', build], {cwd, env, encoding: 'utf8'}));
    const schemas = [R5ContractSchema, R5ShotSchema, ResolvedR5ShotSchema, QualityReportSchema];
    const parsed = schemas.map((schema, i) => schema.parse(payload[i]));
    expect(parsed).toEqual(payload);
    const check = `
import json, sys
from healthvideo.domain.quality_standards import R5Contract, R5Shot, ResolvedR5Shot, QualityReport
models = [R5Contract, R5Shot, ResolvedR5Shot, QualityReport]
print(json.dumps([m.model_validate(p).model_dump(mode='json') for m,p in zip(models,json.load(sys.stdin))]))
`;
    expect(JSON.parse(execFileSync(python, ['-c', check], {
      cwd, env, encoding: 'utf8', input: JSON.stringify(parsed),
    }))).toEqual(payload);
  });

  it.each([
    {...contract, questions: contract.questions.slice(0, 1)},
    {...contract, questions: Array(5).fill(contract.questions[0])},
    {...contract, blocks: [{...contract.blocks[0], professional_update: false}]},
    {...contract, blocks: [{...contract.blocks[0], professional_update: 'true'}]},
    {...contract, blocks: [{...contract.blocks[0], question_ids: ['unknown']}]},
    {...contract, blocks: [{...contract.blocks[0], takeaway_line_id: 'missing'}]},
    {...contract, extra: true},
  ])('rejects incomplete and unknown contract fields', payload => {
    expect(R5ContractSchema.safeParse(payload).success).toBe(false);
  });

  it.each([
    {...shot, component: '../../evil.tsx'},
    {...shot, start: undefined},
    {...shot, extra: true},
    {...shot, asset_paths: ['../escape.svg']},
    {...shot, start: {kind: 'phrase', line_id: 'L1'}},
    {...shot, text_windows: [{kind: 'table', text: 'a\tb', start: shot.start, end: shot.end}]},
  ])('rejects unsafe or incomplete shots', payload => {
    expect(R5ShotSchema.safeParse(payload).success).toBe(false);
  });

  it('leaves absent legacy profile absent and keeps the old default', () => {
    const legacy = RenderInputSchema.parse({title: 'Legacy', audio_file: 'audio/narration.wav'});
    expect(legacy).not.toHaveProperty('quality_profile');
    expect(legacy).not.toHaveProperty('r5_contract');
    expect(legacy.visual_budget_profile).toBe('explain_first_v1');
    expect(RenderInputSchema.safeParse({title: 'Bad', audio_file: 'a.wav', r5_contract: contract}).success).toBe(false);
  });
});
