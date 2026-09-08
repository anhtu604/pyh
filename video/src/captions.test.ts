import {describe, expect, it} from 'vitest';
import {captionWindow} from './components/Captions';

describe('captionWindow', () => {
  const words = ['một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín', 'mười'];

  it('keeps the active word visible when advancing to the next page', () => {
    expect(captionWindow(words, 5, 6)).toEqual({
      startIndex: 0,
      words: ['một', 'hai', 'ba', 'bốn', 'năm', 'sáu'],
    });
    expect(captionWindow(words, 6, 6)).toEqual({
      startIndex: 6,
      words: ['bảy', 'tám', 'chín', 'mười'],
    });
  });

  it('returns the final partial page containing the active word', () => {
    expect(captionWindow(words, 9, 6)).toEqual({
      startIndex: 6,
      words: ['bảy', 'tám', 'chín', 'mười'],
    });
  });
});
