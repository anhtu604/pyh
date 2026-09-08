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
});

describe('SceneSchema', () => {
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
