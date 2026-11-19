import React from 'react';
import {Img, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Box} from '../layout';
import {mascotAssetPath, type MascotPose} from '../style/pyhStyle';
import {bobOffset, entranceOffset, entranceProgress, normalizePoseTrack, poseAt, type MascotBeat} from './mascotMotion';

export type MascotHostProps = {
  box: Box;
  track: readonly MascotBeat[];
  /** Mirror the artwork so it looks toward the diagram. */
  flip?: boolean;
  enterFrame?: number;
  /** Bob only while the host is speaking. */
  speakingUntil?: number;
};

/** Narrating mascot: slide+bounce entrance, 2 px bob, 6-frame pose cross-fade. Upper 65% shown, like PresenterMascot. */
export const MascotHost: React.FC<MascotHostProps> = ({box, track, flip = false, enterFrame = 0, speakingUntil = Infinity}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const poses = normalizePoseTrack(track, fps);
  const state = poseAt(poses, frame);
  const fullHeight = box.height / 0.65;
  const offsetY = entranceOffset(frame, box.height * 0.5, enterFrame) + bobOffset(frame, fps, frame < speakingUntil);
  const opacity = Math.min(1, entranceProgress(frame, enterFrame));
  const layer = (pose: MascotPose, alpha: number) => <Img key={pose} data-mascot-pose={pose}
    aria-label={`PYH mascot ${pose}`} src={staticFile(mascotAssetPath(pose))}
    style={{position: 'absolute', left: 0, top: 0, width: '100%', height: fullHeight, objectFit: 'contain',
      objectPosition: 'center top', opacity: alpha}} />;
  return <div data-mascot-host="true" data-pose={state.pose} data-from-pose={state.from ?? ''}
    style={{...box, position: 'absolute', overflow: 'hidden', opacity}}>
    <div style={{position: 'absolute', inset: 0, transform: `translateY(${offsetY}px)${flip ? ' scaleX(-1)' : ''}`}}>
      {state.from ? layer(state.from, 1) : null}
      {layer(state.pose, state.from ? state.mix : 1)}
    </div>
  </div>;
};
