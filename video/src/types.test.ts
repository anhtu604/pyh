import {describe, expect, it} from 'vitest';
import {EvidenceHighlightSchema, RenderInputSchema, SceneSchema} from './types';

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
      visual_assets: [{path: 'assets/phy.svg', role: 'brand'}]};
    expect(SceneSchema.safeParse(outro).success).toBe(true);
    expect(SceneSchema.safeParse({...outro, visual_assets: [
      {path: 'assets/phy.svg', role: 'brand', pose: 'welcome'},
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

  it('keeps an unmarked legacy chart input compatible', () => {
    const legacy = {...chartInput, visual_budget_profile: undefined, scenes: [{
      ...chartInput.scenes[0], visual_assets: [],
    }]};
    expect(RenderInputSchema.safeParse(legacy).success).toBe(true);
  });
});
