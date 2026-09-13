import {describe, expect, it} from 'vitest';
import {EvidenceHighlightSchema, SceneSchema} from './types';

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
});
