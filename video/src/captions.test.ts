import {describe, expect, it} from 'vitest';
import {captionRows, captionTextLength} from './components/Captions';

describe('captionRows', () => {
  const words = ['một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín', 'mười'];

  it('uses at most two rows and includes the active word across a page boundary', () => {
    expect(captionRows(words, 5, 6)).toEqual({
      startIndex: 0,
      rows: [
        [{index: 0, text: 'một'}, {index: 1, text: 'hai'}, {index: 2, text: 'ba'}],
        [{index: 3, text: 'bốn'}, {index: 4, text: 'năm'}, {index: 5, text: 'sáu'}],
      ],
    });
    expect(captionRows(words, 6, 6)).toEqual({
      startIndex: 6,
      rows: [
        [{index: 6, text: 'bảy'}, {index: 7, text: 'tám'}],
        [{index: 8, text: 'chín'}, {index: 9, text: 'mười'}],
      ],
    });
  });

  it('keeps the active word in the final partial page', () => {
    const layout = captionRows(words, 9, 6);
    expect(layout).toEqual({
      startIndex: 6,
      rows: [
        [{index: 6, text: 'bảy'}, {index: 7, text: 'tám'}],
        [{index: 8, text: 'chín'}, {index: 9, text: 'mười'}],
      ],
    });
    expect(layout.rows.flat().some((word) => word.index === 9)).toBe(true);
  });

  it('keeps a very long active word in one of two non-wrapping rows', () => {
    const longWords = [
      'điệntâmđồgắngsứcthậtdàivàcầnđượcđọcđúngngữcảnh',
      'không',
      'thể',
      'bị',
      'cắt',
      'mất',
    ];
    const layout = captionRows(longWords, 0, 6);

    expect(layout.rows).toHaveLength(2);
    expect(layout.rows.flat().some((word) => word.index === 0)).toBe(true);
  });
});

describe('captionTextLength', () => {
  it('leaves a short Vietnamese row at its natural width', () => {
    expect(captionTextLength('Đọc đúng bối cảnh', 48, 900)).toBeUndefined();
  });

  it('fits a long row to the available width', () => {
    expect(
      captionTextLength('điệntâmđồgắngsứcthậtdàivàcầnđượcđọcđúngngữcảnh', 48, 900),
    ).toBe(900);
  });

  it('counts Unicode code points rather than UTF-16 code units', () => {
    expect(captionTextLength('A😀 B', 100, 400)).toBeUndefined();
  });
});
