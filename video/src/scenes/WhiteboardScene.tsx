import {FONT_FAMILY} from '../fonts';
import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {Captions} from '../components/Captions';
import {textEntrances} from '../components/entrances';
import {slowDriftTransform} from '../components/slowDrift';
import {useLayout} from '../layout';
import type {Scene} from '../types';
import {AuthoredWorksheet, panelRows} from '../components/AuthoredPanels';

type WhiteboardSceneProps = {
  scene: Scene;
};

// Conservative one-em character width keeps even unbroken 90-character text inside its box.
export const whiteboardFontSize = (text: string, width: number, height: number, preferred: number): number => {
  const length = Array.from(text).length;
  for (let size = preferred; size >= 1; size--) {
    const rows = Math.ceil(length / Math.max(1, Math.floor(width / size)));
    if (rows * size * 1.15 <= height) return size;
  }
  return 1;
};

export const WhiteboardScene: React.FC<WhiteboardSceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const dashOffset = interpolate(frame, [0, 45], [1, 0], {
    extrapolateRight: 'clamp',
  });
  const visualAssets = scene.visual_assets ?? [];
  const hasIllustration = visualAssets.some(asset => asset.role === 'whiteboard');
  const textBox = hasIllustration ? layout.illustrationText : layout.whiteboardText;
  const pieces = textEntrances(scene);
  const drift = slowDriftTransform(frame, scene.duration_frames);

  if (panelRows(scene, 3).length) return <>
    <AuthoredWorksheet scene={scene} frame={frame}/>
    <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames}/>
  </>;

  return (
    <>
      {!hasIllustration ? <svg
        aria-label="Nét vẽ whiteboard"
        data-slow-drift={drift.active ? 'true' : undefined}
        style={{height: '100%', left: 0, position: 'absolute', top: 0, width: '100%', overflow: 'hidden'}}
        viewBox={`0 0 ${layout.frame.width} ${layout.frame.height}`}
      >
        <path
          d={layout.whiteboardPath}
          fill="none"
          pathLength="1"
          stroke="#202124"
          strokeLinecap="round"
          strokeWidth="20"
          style={{
            strokeDasharray: 1,
            strokeDashoffset: dashOffset,
            transform: drift.transform,
            transformOrigin: 'center',
            transformBox: 'fill-box',
          }}
        />
      </svg> : null}
      {scene.on_screen_text ? <div
        aria-label="Ý chính"
        style={{
          color: '#202124',
          fontFamily: FONT_FAMILY,
          fontSize: whiteboardFontSize(scene.on_screen_text, textBox.width,
            textBox.height, layout.narration.fontSize),
          fontWeight: 800,
          ...textBox,
          lineHeight: 1.15,
          position: 'absolute',
          textAlign: 'center',
          overflowWrap: 'anywhere',
        }}
      >
        {pieces.map((piece, index) => <span key={index} data-entrance-frame={piece.start_frame}
          style={{opacity: frame >= piece.start_frame ? 1 : 0}}>{piece.text}</span>)}
      </div> : null}
      <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} />
    </>
  );
};
