import React from 'react';
import {Captions} from '../components/Captions';
import {LeadWordZoomAssemble} from '../motion/LeadWordZoomAssemble';
import {OutlineWordFill} from '../motion/OutlineWordFill';
import {MarkerUnderlineTitle} from '../motion/MarkerUnderlineTitle';
import {TitleDemoteToLabel} from '../motion/TitleDemoteToLabel';
import {SceneEnvelopeWrapper, type SceneTransitionProps} from '../motion/sceneEnvelope';
import type {Scene} from '../types';

export const KineticTermScene: React.FC<{scene: Scene; transition?: SceneTransitionProps}> = ({scene, transition}) => {
  const kt = scene.kinetic_term;
  if (!kt) {
    throw new Error('kinetic_term scene requires kinetic_term metadata');
  }
  const variant = kt.variant ?? 'lead-word-zoom-assemble';
  const content = (
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
      <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} />
    </>
  );
  return transition ? <SceneEnvelopeWrapper transition={transition}>{content}</SceneEnvelopeWrapper> : content;
};
