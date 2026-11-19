import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext} from '../layout';
import {Captions} from './Captions';
import {evenWordTiming, firstUseTermWords, paginateCaptions} from './captionPaging';
import {StyleCaptions} from './StyleCaptions';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', () => ({useCurrentFrame: () => clock.frame}));

const text = 'Men gan tăng chưa chắc gan bạn đang hỏng. Đây là điều xảy ra bên trong tế bào gan.';
const words = text.split(' ');
const lineText = (l: {text: string}[]) => l.map((w) => w.text).join(' ');

describe('caption line breaking', () => {
  it('16:9 keeps ≤ 2 lines of ≤ 42 characters, one idea per page', () => {
    const pages = paginateCaptions(words, 42, 2);
    expect(pages.map((p) => p.lines.map(lineText))).toEqual([
      ['Men gan tăng chưa chắc gan bạn đang hỏng.'], ['Đây là điều xảy ra bên trong tế bào gan.']]);
  });

  it('9:16 keeps ≤ 2 lines of ≤ 24 characters', () => {
    const pages = paginateCaptions(words, 24, 2);
    expect(pages.length).toBeGreaterThan(1);
    pages.forEach((page) => {
      expect(page.lines.length).toBeLessThanOrEqual(2);
      page.lines.forEach((line) => expect(lineText(line).length).toBeLessThanOrEqual(24));
    });
    expect(pages[0].lines.map(lineText)).toEqual(['Men gan tăng chưa chắc', 'gan bạn đang hỏng.']);
  });

  it('covers every word exactly once, in order, for long text', () => {
    const long = Array.from({length: 60}, (_, i) => `từ${i}`);
    for (const max of [24, 42]) {
      const pages = paginateCaptions(long, max, 2);
      expect(pages.flatMap((p) => p.lines.flat().map((w) => w.index))).toEqual(long.map((_, i) => i));
      pages.forEach((p) => p.lines.forEach((l) => expect(lineText(l).length).toBeLessThanOrEqual(max)));
    }
  });
});

describe('glossary highlight', () => {
  it('marks only the first appearance of a multi-word term', () => {
    const repeated = 'tế bào gan khỏe. Rồi tế bào gan hỏng.'.split(' ');
    expect([...firstUseTermWords(repeated, ['tế bào gan'])]).toEqual([0, 1, 2]);
  });
});

const render = (frame: number, format: keyof typeof LAYOUTS) => {
  clock.frame = frame;
  return renderToStaticMarkup(<LayoutContext.Provider value={LAYOUTS[format]}>
    <StyleCaptions text={text} durationInFrames={300} words={evenWordTiming(text, 4, 14, 12)} glossary={['tế bào gan']} />
  </LayoutContext.Provider>);
};

describe('StyleCaptions', () => {
  it('keeps the whole page static while words are being read', () => {
    const html = render(4 + 14 * 2 + 3, 'youtube_long');
    expect(html).not.toContain('data-active');
    expect(html).not.toContain('text-decoration');
    expect(html).toEqual(render(4 + 14 * 5, 'youtube_long'));
  });

  it('shows the second sentence on its own page and tints the term yellow', () => {
    const html = render(4 + 14 * 16 + 2, 'youtube_long');
    expect(html).toContain('Đây');
    expect(html).not.toContain('hỏng');
    expect(html.match(/data-term="true"/g)).toHaveLength(3);
    expect(html).toContain('#F4B942');
  });

  it('uses 24-character lines in portrait', () => {
    const html = render(10, 'vertical_clip');
    expect(html.match(/data-caption-line="true"/g)).toHaveLength(2);
    expect(html).toContain('data-format="portrait"');
  });

  it('keeps the legacy Captions renderer unless styleA is requested', () => {
    clock.frame = 10;
    const legacy = renderToStaticMarkup(<Captions text="Một hai ba bốn" durationInFrames={90} />);
    expect(legacy).toContain('<svg');
    const styled = renderToStaticMarkup(<Captions variant="styleA" text="Một hai ba bốn" durationInFrames={90} />);
    expect(styled).toContain('data-style-captions');
  });
});


describe('revision 1 caption constraints', () => {
  it('merges fragments and terminal orphans without losing words', () => {
    for (const text of ['Một. Hai ba bốn năm sáu bảy tám.',
      'Máu từ tĩnh mạch cửa và động mạch gan hòa vào nhau, chảy qua xoang gan về tĩnh mạch trung tâm.',
      'Một hai ba bốn năm sáu bảy tám chín mười mười một mười hai mười ba cuối.']) {
      const words = text.split(' ');
      const pages = paginateCaptions(words, 42);
      expect(pages.flatMap((p) => p.lines.flat().map((w) => w.text))).toEqual(words);
      pages.forEach((p) => {
        expect(p.lines.flat().length).toBeGreaterThanOrEqual(4);
        expect(p.lines.length).toBeLessThanOrEqual(2);
        p.lines.forEach((l) => expect(lineText(l).length).toBeLessThanOrEqual(42));
      });
    }
  });
  it('selects one term per page, suppresses repeat terms and requires a visible label', () => {
    clock.frame = 10;
    const render = (previousText: string, end = 100) => renderToStaticMarkup(
      <StyleCaptions text="Bào tương chứa ty thể trong tế bào gan." durationInFrames={100}
        glossary={['bào tương', 'ty thể']} previousText={previousText}
        labelWindows={[{term: 'bào tương', start: 0, end}, {term: 'ty thể', start: 0, end}]} />);
    expect(render('').match(/data-term-group="true"/g)).toHaveLength(1);
    expect(render('Bào tương và ty thể.')).not.toContain('data-term-group');
    expect(render('', 5)).not.toContain('data-term-group');
    expect(render('')).not.toContain('text-decoration');
  });
  it('cannot switch yellow phrases on one page when the label changes', () => {
    const render = (frame: number) => {
      clock.frame = frame;
      return renderToStaticMarkup(<StyleCaptions text="Bào tương chứa ty thể trong tế bào gan." durationInFrames={100}
        glossary={['bào tương', 'ty thể']} labelWindows={[
          {term: 'bào tương', start: 0, end: 20}, {term: 'ty thể', start: 20, end: 100}]} />);
    };
    expect(render(10)).not.toContain('data-term-group');
    expect(render(25)).not.toContain('data-term-group');
    expect(render(10)).toEqual(render(25));
  });
});


it('rejects impossible fragments instead of rendering one-word pages', () => {
  expect(paginateCaptions([], 42)).toEqual([]);
  expect(() => paginateCaptions(['gan'], 42)).toThrow(/four words/);
  expect(() => paginateCaptions(['a'.repeat(42), 'b'.repeat(42), 'c'.repeat(42), 'd'.repeat(42)], 42)).toThrow(/line budget/);
});
