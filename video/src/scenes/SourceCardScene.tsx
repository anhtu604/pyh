import React from 'react';
import {Captions} from '../components/Captions';
import {FONT_FAMILY} from '../fonts';
import {useLayout} from '../layout';
import type {Scene} from '../types';
import {SourceMarker} from './WhiteboardScene';

export const SourceCardScene: React.FC<{scene: Scene}> = ({scene}) => {
  const layout = useLayout();
  const card = scene.source_card;
  if (!card) throw new Error('source_card scene requires source metadata');
  const landscape = layout.frame.width > layout.frame.height;
  const duplicateNarration = card.interpretation.trim() === scene.narration.trim();
  return <>
    <article aria-label="Thẻ nguồn" style={{
      position: 'absolute', left: landscape ? 500 : 72, top: landscape ? 150 : 250,
      width: landscape ? 1200 : 936, boxSizing: 'border-box', padding: landscape ? 44 : 48,
      backgroundColor: '#FFFDF7', color: '#202124', border: '3px solid #118577',
      borderRadius: 28, fontFamily: FONT_FAMILY, lineHeight: 1.35,
    }}>
      <div style={{fontSize: 26, color: '#118577', fontWeight: 700}}>{card.source_id}</div>
      <h2 style={{fontSize: landscape ? 42 : 46, margin: '12px 0 22px', overflowWrap: 'anywhere'}}>{card.title}</h2>
      <div style={{fontSize: 28}}>{card.journal}{card.year === null ? '' : ` · ${card.year}`}</div>
      <div style={{fontSize: 24, marginTop: 12, overflowWrap: 'anywhere'}}>
        {card.pmid ? <div>PMID: {card.pmid}</div> : null}
        {card.doi ? <div>DOI: {card.doi}</div> : null}
      </div>
      <div style={{borderTop: '2px solid #118577', marginTop: 28, paddingTop: 24}}>
        <div style={{fontSize: 28, color: '#118577', fontWeight: 700}}>Diễn giải</div>
        <p style={{fontSize: landscape ? 36 : 40, margin: '12px 0 0'}}>{card.interpretation}</p>
      </div>
    </article>
    {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
    {!duplicateNarration ? <Captions text={scene.narration} durationInFrames={scene.duration_frames} /> : null}
  </>;
};
