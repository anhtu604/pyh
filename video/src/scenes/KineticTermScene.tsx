import React from 'react';
import {Captions} from '../components/Captions';
import {LeadWordZoomAssemble} from '../motion/LeadWordZoomAssemble';
import {OutlineWordFill} from '../motion/OutlineWordFill';
import {MarkerUnderlineTitle} from '../motion/MarkerUnderlineTitle';
import {TitleDemoteToLabel} from '../motion/TitleDemoteToLabel';
import type {Scene} from '../types';
import {SourceMarker} from './WhiteboardScene';

export const KineticTermScene: React.FC<{scene: Scene}> = ({scene}) => {
  const kt = scene.kinetic_term;
  if (!kt) {
    throw new Error('kinetic_term scene requires kinetic_term metadata');
  }
  const variant = kt.variant ?? 'lead-word-zoom-assemble';
  return (
    <>
      {variant === 'outline-word-fill' ? (
        <OutlineWordFill term={kt.term} definition={kt.definition} />
      ) : variant === 'marker-underline-title' ? (
        <MarkerUnderlineTitle emphasisText={kt.term} subline={kt.definition} />
      ) : variant === 'title-demote-to-label' ? (
        <TitleDemoteToLabel title={kt.term} summary={kt.definition} />
      ) : (
        <LeadWordZoomAssemble term={kt.term} definition={kt.definition} />
      )}
      {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
      <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} />
    </>
  );
};
