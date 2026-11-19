// Word-lit captions for style A: line breaking by character budget and first-use glossary highlight.
import type {StyleFormat} from '../style/pyhStyle';
import {pyhCaptions} from '../style/pyhStyle';

export type TimedWord = {text: string; start_frame: number; end_frame: number};
export type CaptionLine = {index: number; text: string}[];
export type CaptionPage = {startIndex: number; lines: CaptionLine[]};

const SENTENCE_END = /[.!?;…]$/;
const CLAUSE_END = /[,:]$/;

/** Partition by meaning, with no short orphan pages; balance two-line pages.
 * Reject impossible inputs rather than emitting an orphan page or inventing words. */
export const paginateCaptions = (words: readonly string[], maxCharsPerLine: number, maxLines = 2): CaptionPage[] => {
  if (!words.length) return [];
  if (words.length < 4) throw new Error('Style captions require at least four words; merge this fragment with adjacent speech.');
  const length = (a: number, b: number) => words.slice(a, b).join(' ').length;
  const split = (a: number, b: number): number[] | undefined => {
    if (length(a, b) <= maxCharsPerLine || b - a === 1) return [b];
    if (maxLines < 2) return undefined;
    let best: number | undefined;
    let cost = Infinity;
    for (let k = a + 1; k < b; k++) {
      if (length(a, k) > maxCharsPerLine || length(k, b) > maxCharsPerLine) continue;
      const c = Math.abs(length(a, k) - length(k, b)) - (CLAUSE_END.test(words[k - 1]) ? 4 : 0);
      if (c < cost) {best = k; cost = c;}
    }
    return best === undefined ? undefined : [best, b];
  };
  const costs = Array(words.length + 1).fill(Infinity) as number[];
  const choices = new Map<number, {end: number; breaks: number[]}>();
  costs[words.length] = 0;
  for (let a = words.length - 1; a >= 0; a--) {
    for (let b = a + 1; b <= words.length; b++) {
      const breaks = split(a, b);
      if (!breaks) continue;
      // A short whole input is unavoidable; otherwise require >=4 words per page.
      if (b - a < 4 && words.length >= 4) continue;
      const sentence = SENTENCE_END.test(words[b - 1]);
      const internalStops = words.slice(a, b - 1).filter((w) => SENTENCE_END.test(w)).length;
      const cost = costs[b] + 100 + (sentence || b === words.length ? 0 : 24)
        + internalStops * 160 + (CLAUSE_END.test(words[b - 1]) ? -8 : 0);
      if (cost < costs[a]) {costs[a] = cost; choices.set(a, {end: b, breaks});}
    }
  }
  if (!choices.has(0)) throw new Error('Caption text cannot fit the line budget with at least four words per page.');
  const pages: CaptionPage[] = [];
  for (let a = 0; a < words.length;) {
    const {end, breaks} = choices.get(a)!;
    let cursor = a;
    const lines = breaks.map((b) => {
      const line = words.slice(cursor, b).map((text, i) => ({text, index: cursor + i}));
      cursor = b; return line;
    });
    pages.push({startIndex: a, lines}); a = end;
  }
  return pages;
};
export const pageAtFrame = (pages: readonly CaptionPage[], words: readonly TimedWord[], frame: number): CaptionPage | undefined =>
  [...pages].reverse().find((p) => frame >= words[p.startIndex].start_frame) ?? pages[0];

const norm = (value: string): string => value.toLowerCase().replace(/[.,:;!?…"“”()]/g, '');

/** Word indices that belong to the first appearance of each glossary term (multi-word terms allowed). */
export const firstUseTermWords = (words: readonly string[], terms: readonly string[]): Set<number> => {
  const result = new Set<number>();
  const normalized = words.map(norm);
  terms.forEach((term) => {
    const parts = term.split(/\s+/).map(norm).filter(Boolean);
    if (!parts.length) return;
    for (let start = 0; start + parts.length <= words.length; start++) {
      if (parts.every((part, offset) => normalized[start + offset] === part)) {
        parts.forEach((_, offset) => result.add(start + offset));
        return;
      }
    }
  });
  return result;
};

/** Even word timing for samples without TTS timing. */
export const evenWordTiming = (text: string, firstFrame: number, framesPerWord: number, hold = framesPerWord - 2): TimedWord[] =>
  text.trim().split(/\s+/).filter(Boolean).map((word, i) => ({
    text: word, start_frame: firstFrame + i * framesPerWord, end_frame: firstFrame + i * framesPerWord + hold}));

export const captionLimits = (format: StyleFormat) => pyhCaptions[format];

