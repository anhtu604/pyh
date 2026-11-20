import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext, SAFE_GAP, captionBox} from '../layout';
import type {Scene} from '../types';
import {
  SourceCardScene,
  activeSentenceIndex,
  isProgressiveSourceCard,
  sourceCardScale,
  sourceCardSentenceTimings,
  splitInterpretationSentences,
} from './SourceCardScene';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', async (original) => ({
  ...await original<typeof import('remotion')>(),
  useCurrentFrame: () => clock.frame,
  useVideoConfig: () => ({fps: 30}),
}));

const multiSentenceText =
  'Nghiên cứu theo dõi 1.200 người bệnh với ngưỡng acid uric 6.8 mg/dL trong 5 năm. '
  + 'Nhóm duy trì nồng độ dưới mục tiêu giảm rõ rệt số cơn gút cấp mỗi năm! '
  + 'Kết quả này nhất quán ở cả hai giới và nhóm tuổi trên 60.';

const makeScene = (overrides: Partial<Scene> = {}): Scene => ({
  id: 'S24',
  start_frame: 0,
  duration_frames: 600, // 20s
  narration: multiSentenceText,
  visual: 'source_card',
  claim_id: 'C05',
  source_marker: '[E04]',
  source_card: {
    source_id: 'R04',
    title: 'Long-term urate-lowering outcomes in primary gout',
    journal: 'Annals of Rheumatic Diseases',
    year: 2024,
    pmid: '38123456',
    doi: '10.1136/ard-2024-000123',
    interpretation: multiSentenceText,
  },
  visual_assets: [],
  ...overrides,
});

const renderCard = (scene: Scene, format: keyof typeof LAYOUTS = 'youtube_long') =>
  renderToStaticMarkup(
    <LayoutContext.Provider value={LAYOUTS[format]}>
      <SourceCardScene scene={scene} />
    </LayoutContext.Provider>,
  );

describe('SourceCardScene sentence splitting and timing', () => {
  it('splits into sentences losslessly and ignores decimals and DOIs', () => {
    const sentences = splitInterpretationSentences(multiSentenceText);
    expect(sentences).toHaveLength(3);
    expect(sentences.join('')).toBe(multiSentenceText);
    expect(sentences[0]).toContain('6.8 mg/dL');
    expect(sentences[1]).toContain('gút cấp mỗi năm!');
    expect(sentences[2]).toContain('trên 60.');

    const single = 'Một câu duy nhất với p = 0.05 và DOI 10.1000/xyz.';
    expect(splitInterpretationSentences(single)).toEqual([single]);
  });

  it('activates progressive mode only when >= 2 sentences AND duration >= 8s', () => {
    const two = ['Câu một. ', 'Câu hai.'];
    const one = ['Một câu duy nhất.'];
    expect(isProgressiveSourceCard(two, 240, 30)).toBe(true);
    expect(isProgressiveSourceCard(two, 239, 30)).toBe(false);
    expect(isProgressiveSourceCard(one, 600, 30)).toBe(false);
  });

  it('allocates sentence timings proportionally by character length when words are absent', () => {
    const sentences = ['Ngắn. ', 'Câu này dài gấp nhiều lần câu đầu tiên để kiểm tra tỷ lệ chia thời gian.'];
    const timings = sourceCardSentenceTimings(sentences, 600);
    expect(timings).toHaveLength(2);
    expect(timings[0].startFrame).toBe(0);
    expect(timings[0].endFrame).toBe(timings[1].startFrame);
    expect(timings[1].endFrame).toBe(600);
    // Longer sentence gets strictly more duration
    expect(timings[1].endFrame - timings[1].startFrame).toBeGreaterThan(
      timings[0].endFrame - timings[0].startFrame,
    );
    expect(activeSentenceIndex(timings, 0)).toBe(0);
    expect(activeSentenceIndex(timings, timings[1].startFrame)).toBe(1);
    expect(activeSentenceIndex(timings, 599)).toBe(1);
  });

  it('uses scene.words timestamps when words match sentence starts', () => {
    const sentences = ['Câu một ngắn. ', 'Câu hai bắt đầu muộn hơn.'];
    const words: NonNullable<Scene['words']> = [
      {text: 'Câu', start_frame: 0, end_frame: 15},
      {text: 'một', start_frame: 16, end_frame: 30},
      {text: 'ngắn.', start_frame: 31, end_frame: 60},
      {text: 'Câu', start_frame: 210, end_frame: 230},
      {text: 'hai', start_frame: 231, end_frame: 250},
      {text: 'bắt', start_frame: 251, end_frame: 270},
      {text: 'đầu', start_frame: 271, end_frame: 290},
      {text: 'muộn', start_frame: 291, end_frame: 320},
      {text: 'hơn.', start_frame: 321, end_frame: 360},
    ];
    const timings = sourceCardSentenceTimings(sentences, 420, words);
    expect(timings[0]).toEqual({text: sentences[0], startFrame: 0, endFrame: 210});
    expect(timings[1]).toEqual({text: sentences[1], startFrame: 210, endFrame: 420});
  });
});

describe('SourceCardScene progressive rendering & larger typography', () => {
  it('advances sentences across a long scene while keeping header metadata visible and enlarging text', () => {
    const longParagraph = [
      'Nghiên cứu đoàn hệ lớn đánh giá 4.500 bệnh nhân tăng men gan kéo dài trong suốt 10 năm theo dõi lâm sàng.',
      'Nhóm tự ý dùng thuốc bổ gan không rõ nguồn gốc không giảm nguy cơ tiến triển xơ hóa gan so với nhóm đối chứng.',
      'Ngược lại, phát hiện sớm nguyên nhân nền và theo dõi định kỳ với bác sĩ giúp kiểm soát men gan an toàn hơn.',
      'Người bệnh cần mang kết quả xét nghiệm và toàn bộ thuốc đang dùng khi đi khám chuyên khoa tiêu hóa gan mật.',
    ].join(' ');
    const scene = makeScene({
      duration_frames: 600,
      narration: longParagraph,
      source_card: {
        source_id: 'R10',
        title: 'Long-term outcomes of unexplained elevated transaminases in outpatient clinics',
        journal: 'Hepatology International',
        year: 2025,
        pmid: '39001122',
        doi: '10.1007/s12072-025-0001-x',
        interpretation: longParagraph,
      },
    });

    // Compare scale of a single sentence vs full paragraph on landscape card
    const box = LAYOUTS.youtube_long.sourceCard;
    const inner = {width: box.width - 2 * box.padding - 6, height: box.height - 2 * box.padding - 6};
    const fullScale = sourceCardScale(scene.source_card!, inner, true, box.fontSize);
    const firstSentence = splitInterpretationSentences(longParagraph)[0].trim();
    const singleScale = sourceCardScale({...scene.source_card!, interpretation: firstSentence}, inner, true, box.fontSize);
    expect(singleScale).toBeGreaterThan(fullScale);

    clock.frame = 10;
    const earlyHtml = renderCard(scene, 'youtube_long');
    expect(earlyHtml).toContain('data-source-card-progressive="true"');
    expect(earlyHtml).toContain('data-sentence-index="0"');
    expect(earlyHtml).toContain('1/4');
    expect(earlyHtml).toContain('Hepatology International');
    expect(earlyHtml).toContain('PMID: 39001122');
    expect(earlyHtml).toContain('4.500 bệnh nhân');
    expect(earlyHtml).not.toContain('data-previous-sentence');

    clock.frame = 220;
    const midHtml = renderCard(scene, 'youtube_long');
    expect(midHtml).toContain('data-sentence-index="1"');
    expect(midHtml).toContain('2/4');
    expect(midHtml).toContain('thuốc bổ gan không rõ nguồn gốc');
    expect(midHtml).toContain('Hepatology International');
    // Previous sentence is either dimmed at 0.45 or hidden to prevent overflow
    if (midHtml.includes('data-previous-sentence="true"')) {
      expect(midHtml).toContain('opacity:0.45');
    }
  });

  it('keeps legacy single-block rendering for short scenes (< 8s) or single-sentence interpretations', () => {
    clock.frame = 30;
    const shortScene = makeScene({duration_frames: 180});
    const shortHtml = renderCard(shortScene, 'youtube_long');
    expect(shortHtml).not.toContain('data-source-card-progressive');
    expect(shortHtml).toContain(multiSentenceText);

    const oneSentenceScene = makeScene({
      duration_frames: 600,
      source_card: {...makeScene().source_card!, interpretation: 'Chỉ một câu ngắn gọn.'},
    });
    const oneHtml = renderCard(oneSentenceScene, 'youtube_long');
    expect(oneHtml).not.toContain('data-source-card-progressive');
    expect(oneHtml).toContain('Chỉ một câu ngắn gọn.');
  });

  it('enlarges sourceCard.fontSize by ~20% in both layouts without loosening safe zones', () => {
    expect(LAYOUTS.vertical_clip.sourceCard.fontSize).toBe(48);
    expect(LAYOUTS.youtube_long.sourceCard.fontSize).toBe(44);
    for (const layout of Object.values(LAYOUTS)) {
      const box = layout.sourceCard;
      expect(captionBox(layout).top - (box.top + box.height)).toBeGreaterThanOrEqual(SAFE_GAP);
    }
  });
});
