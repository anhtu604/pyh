import React from 'react';
import {MarkerUnderlineTitle} from './MarkerUnderlineTitle';
import {LeadWordZoomAssemble} from './LeadWordZoomAssemble';
import {OutlineWordFill} from './OutlineWordFill';
import {TitleDemoteToLabel} from './TitleDemoteToLabel';
import {ScanBracketSweep} from './ScanBracketSweep';
import {ScanlineAnnotateFocus} from './ScanlineAnnotateFocus';
import {SpotlightSweepMoves} from './SpotlightSweepMoves';
import {CircleMatchIris} from './CircleMatchIris';
import {WipeTransitions} from './WipeTransitions';
import {CrashZoomPunch} from './CrashZoomPunch';
import type {SceneMotion} from '../types';

export type SceneMotionOverlayProps = {
  motion: SceneMotion;
  narration?: string;
};

export const SceneMotionOverlay: React.FC<SceneMotionOverlayProps> = ({motion}) => {
  const emphasisText = motion.emphasis_text ?? undefined;
  return (
    <div data-scene-motion-overlay="true" style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
      {motion.transition_in === 'circle-match-iris' ? (
        <CircleMatchIris overlay />
      ) : motion.transition_in === 'wipe-transitions' ? (
        <WipeTransitions overlay />
      ) : motion.transition_in === 'crash-zoom-punch' ? (
        <CrashZoomPunch overlay />
      ) : null}

      {motion.emphasis === 'marker-underline-title' ? (
        <MarkerUnderlineTitle overlay emphasisText={emphasisText} />
      ) : motion.emphasis === 'lead-word-zoom-assemble' ? (
        <LeadWordZoomAssemble overlay term={emphasisText} />
      ) : motion.emphasis === 'outline-word-fill' ? (
        <OutlineWordFill overlay term={emphasisText} />
      ) : motion.emphasis === 'title-demote-to-label' ? (
        <TitleDemoteToLabel overlay title={emphasisText} />
      ) : motion.emphasis === 'scan-bracket-sweep' ? (
        <ScanBracketSweep overlay emphasisText={emphasisText} />
      ) : motion.emphasis === 'scanline-annotate-focus' ? (
        <ScanlineAnnotateFocus overlay emphasisText={emphasisText} />
      ) : motion.emphasis === 'spotlight-sweep-moves' ? (
        <SpotlightSweepMoves overlay emphasisText={emphasisText} />
      ) : null}
    </div>
  );
};
