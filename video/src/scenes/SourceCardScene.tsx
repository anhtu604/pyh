import React from 'react';
import {Captions} from '../components/Captions';
import {FONT_FAMILY} from '../fonts';
import {useLayout} from '../layout';
import type {Scene} from '../types';

type Card = NonNullable<Scene['source_card']>;
const GLYPH_EM = 0.6;
const LINE = 1.35;

// Estimated stack height at scale 1 (title/journal/ids/interpretation); long strings shrink the card text, never the box.
const cardHeight = (card: Card, inner: number, landscape: boolean, base: number, scale: number): number => {
  const rows = (text: string, size: number) => Math.ceil(Array.from(text).length * size * GLYPH_EM / inner) * size * LINE;
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
  const layout = useLayout();
  const card = scene.source_card;
  if (!card) throw new Error('source_card scene requires source metadata');
  const box = layout.sourceCard;
  const landscape = layout.frame.width > layout.frame.height;
  const duplicateNarration = card.interpretation.trim() === scene.narration.trim();
  const scale = sourceCardScale(card, {width: box.width - 2 * box.padding - 6, height: box.height - 2 * box.padding - 6}, landscape, box.fontSize);
  const s = (n: number) => Math.floor(n * scale);
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
      <div style={{borderTop: '2px solid #118577', marginTop: s(28), paddingTop: s(24)}}>
        <div style={{fontSize: s(28), color: '#118577', fontWeight: 700}}>Diễn giải</div>
        <p style={{fontSize: s(box.fontSize), margin: `${s(12)}px 0 0`, overflowWrap: 'anywhere'}}>{card.interpretation}</p>
      </div>
    </article>
    {!duplicateNarration ? <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} /> : null}
  </>;
};