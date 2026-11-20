import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {Captions} from '../components/Captions';
import {LONG_SCENE_SECONDS} from '../components/slowDrift';
import {FONT_FAMILY} from '../fonts';
import {useLayout} from '../layout';
import type {Scene} from '../types';

type Card = NonNullable<Scene['source_card']>;
const GLYPH_EM = 0.6;
const LINE = 1.35;
const DEFAULT_FPS = 30;
const PREVIOUS_SENTENCE_OPACITY = 0.45;
const PREVIOUS_SENTENCE_RATIO = 0.72;
const COLON_CLAUSE_MIN_CHARS = 24;

export type SentenceTiming = {
  text: string;
  startFrame: number;
  endFrame: number;
};

const normalizeToken = (text: string): string =>
  text.normalize('NFC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

/**
 * Splits an interpretation into sentences or long clauses (`;` and long `:`) while
 * preserving the exact original string (`splitInterpretationSentences(t).join('') === t`).
 */
export const splitInterpretationSentences = (text: string): string[] => {
  if (!text) return [];
  const parts: string[] = [];
  const boundary = /([.!?…;]+["”’')»]*|:)(\s+)/g;
  let start = 0;
  let match: RegExpExecArray | null;
  while ((match = boundary.exec(text)) !== null) {
    const end = match.index + match[1].length + match[2].length;
    if (
      match[1] === ':'
      && (
        text.slice(start, match.index).trim().length < COLON_CLAUSE_MIN_CHARS
        || text.slice(end).trim().length < COLON_CLAUSE_MIN_CHARS
      )
    ) {
      continue;
    }
    parts.push(text.slice(start, end));
    start = end;
  }
  if (start < text.length) {
    parts.push(text.slice(start));
  }
  return parts.filter((part) => part.trim().length > 0);
};

export const isProgressiveSourceCard = (
  sentences: string[],
  durationFrames: number,
  fps = DEFAULT_FPS,
): boolean => sentences.length >= 2 && durationFrames >= LONG_SCENE_SECONDS * fps;

const matchWordStartFrames = (
  sentences: string[],
  durationFrames: number,
  words: NonNullable<Scene['words']>,
): number[] | null => {
  if (words.length === 0) return null;
  const wordTokens = words.map((w) => normalizeToken(w.text));
  const starts: number[] = [0];
  let cursor = 0;

  for (let i = 1; i < sentences.length; i++) {
    const tokens = sentences[i].trim().split(/\s+/).map(normalizeToken).filter(Boolean);
    if (tokens.length === 0) return null;
    const probe = tokens.slice(0, Math.min(2, tokens.length));
    let found = -1;
    for (let j = cursor + 1; j <= wordTokens.length - probe.length; j++) {
      if (probe.every((tok, k) => wordTokens[j + k] === tok)) {
        found = j;
        break;
      }
    }
    if (found < 0) return null;
    const frame = words[found].start_frame;
    if (frame <= starts[i - 1] || frame >= durationFrames) return null;
    starts.push(frame);
    cursor = found;
  }
  return starts;
};

export const sourceCardSentenceTimings = (
  sentences: string[],
  durationFrames: number,
  words?: Scene['words'],
): SentenceTiming[] => {
  if (sentences.length === 0) return [];
  const safeDuration = Math.max(1, durationFrames);
  if (sentences.length === 1) {
    return [{text: sentences[0], startFrame: 0, endFrame: safeDuration}];
  }

  const wordStarts = words && words.length > 0
    ? matchWordStartFrames(sentences, safeDuration, words)
    : null;

  if (wordStarts) {
    return sentences.map((text, index) => ({
      text,
      startFrame: wordStarts[index],
      endFrame: index === sentences.length - 1 ? safeDuration : wordStarts[index + 1],
    }));
  }

  const weights = sentences.map((s) => Math.max(1, Array.from(s.trim()).length));
  const totalWeight = weights.reduce((sum, w) => sum + w, 0);
  const timings: SentenceTiming[] = [];
  let accWeight = 0;
  let prevEnd = 0;

  for (let i = 0; i < sentences.length; i++) {
    const startFrame = prevEnd;
    accWeight += weights[i];
    const remaining = sentences.length - 1 - i;
    const rawEnd = i === sentences.length - 1
      ? safeDuration
      : Math.round((accWeight / totalWeight) * safeDuration);
    const endFrame = i === sentences.length - 1
      ? safeDuration
      : Math.min(safeDuration - remaining, Math.max(startFrame + 1, rawEnd));
    timings.push({text: sentences[i], startFrame, endFrame});
    prevEnd = endFrame;
  }
  return timings;
};

export const activeSentenceIndex = (timings: SentenceTiming[], frame: number): number => {
  if (timings.length === 0) return 0;
  if (frame <= timings[0].startFrame) return 0;
  for (let i = 0; i < timings.length; i++) {
    if (frame >= timings[i].startFrame && frame < timings[i].endFrame) return i;
  }
  return timings.length - 1;
};

const estimatedRowsHeight = (text: string, size: number, inner: number): number =>
  Math.ceil(Math.max(1, Array.from(text).length) * size * GLYPH_EM / inner) * size * LINE;

// Estimated stack height at scale 1 (title/journal/ids/interpretation); long strings shrink the card text, never the box.
const cardHeight = (card: Card, inner: number, landscape: boolean, base: number, scale: number): number => {
  const rows = (text: string, size: number) => estimatedRowsHeight(text, size, inner);
  const s = (n: number) => n * scale;
  const ids = [card.pmid ? `PMID: ${card.pmid}` : '', card.doi ? `DOI: ${card.doi}` : ''].filter(Boolean);
  return rows(card.title, s(landscape ? 42 : 46)) + s(12 + 22)
    + rows(`${card.journal}${card.year === null ? '' : ` · ${card.year}`}`, s(28))
    + ids.reduce((sum, id) => sum + rows(id, s(24)), 0) + (ids.length ? s(12) : 0)
    + s(28 + 24 + 28 * LINE + 12) + rows(card.interpretation, s(base));
};

export const sourceCardScale = (card: Card, inner: {width: number; height: number}, landscape: boolean, base: number): number => {
  for (let scale = 1; scale > 0.3; scale -= 0.05) {
    if (cardHeight(card, inner.width, landscape, base, scale) <= inner.height) return scale;
  }
  return 0.3;
};

export const SourceCardScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const card = scene.source_card;
  if (!card) throw new Error('source_card scene requires source metadata');
  const box = layout.sourceCard;
  const landscape = layout.frame.width > layout.frame.height;
  const duplicateNarration = card.interpretation.trim() === scene.narration.trim();
  const inner = {width: box.width - 2 * box.padding - 6, height: box.height - 2 * box.padding - 6};

  const sentences = splitInterpretationSentences(card.interpretation);
  const progressive = isProgressiveSourceCard(sentences, scene.duration_frames, DEFAULT_FPS);
  const timings = progressive
    ? sourceCardSentenceTimings(sentences, scene.duration_frames, scene.words)
    : [];
  const activeIdx = progressive ? activeSentenceIndex(timings, frame) : 0;
  const activeText = progressive ? timings[activeIdx].text.trim() : card.interpretation;
  const activeCard = progressive ? {...card, interpretation: activeText} : card;

  const scale = sourceCardScale(activeCard, inner, landscape, box.fontSize);
  const s = (n: number) => Math.floor(n * scale);

  const previousText = progressive && activeIdx > 0 ? timings[activeIdx - 1].text.trim() : '';
  const previousHeight = previousText
    ? estimatedRowsHeight(previousText, box.fontSize * PREVIOUS_SENTENCE_RATIO * scale, inner.width) + 12 * scale
    : 0;
  const showPrevious = Boolean(previousText)
    && cardHeight(activeCard, inner.width, landscape, box.fontSize, scale) + previousHeight <= inner.height;

  const activeOpacity = progressive
    ? interpolate(frame - timings[activeIdx].startFrame, [0, 6], [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    })
    : 1;

  return <>
    <article aria-label="Thẻ nguồn" style={{
      position: 'absolute', left: box.left, top: box.top, width: box.width, height: box.height,
      boxSizing: 'border-box', padding: box.padding, overflow: 'hidden',
      backgroundColor: '#FFFDF7', color: '#202124', border: '3px solid #118577',
      borderRadius: 28, fontFamily: FONT_FAMILY, lineHeight: LINE,
    }}>
      <h2 style={{fontSize: s(landscape ? 42 : 46), margin: `0 0 ${s(22)}px`, overflowWrap: 'anywhere'}}>{card.title}</h2>
      <div style={{fontSize: s(28), overflowWrap: 'anywhere'}}>{card.journal}{card.year === null ? '' : ` · ${card.year}`}</div>
      <div style={{fontSize: s(24), marginTop: s(12), overflowWrap: 'anywhere'}}>
        {card.pmid ? <div>PMID: {card.pmid}</div> : null}
        {card.doi ? <div>DOI: {card.doi}</div> : null}
      </div>
      <div
        data-source-card-progressive={progressive ? 'true' : undefined}
        data-sentence-index={progressive ? activeIdx : undefined}
        data-sentence-count={progressive ? sentences.length : undefined}
        style={{borderTop: '2px solid #118577', marginTop: s(28), paddingTop: s(24)}}
      >
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', fontSize: s(28), color: '#118577', fontWeight: 700}}>
          <span>Diễn giải</span>
          {progressive ? <span style={{fontSize: s(22), opacity: 0.75}}>{activeIdx + 1}/{sentences.length}</span> : null}
        </div>
        {showPrevious ? (
          <p
            data-previous-sentence="true"
            style={{
              fontSize: s(box.fontSize * PREVIOUS_SENTENCE_RATIO),
              margin: `${s(10)}px 0 0`,
              opacity: PREVIOUS_SENTENCE_OPACITY,
              overflowWrap: 'anywhere',
            }}
          >
            {previousText}
          </p>
        ) : null}
        <p
          data-active-sentence={progressive ? 'true' : undefined}
          style={{
            fontSize: s(box.fontSize),
            margin: `${s(12)}px 0 0`,
            opacity: activeOpacity,
            overflowWrap: 'anywhere',
          }}
        >
          {activeText}
        </p>
      </div>
    </article>
    {!duplicateNarration ? <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} /> : null}
  </>;
};
