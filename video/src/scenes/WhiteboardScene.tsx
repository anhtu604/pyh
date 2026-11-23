import {FONT_FAMILY} from '../fonts';
import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {Captions} from '../components/Captions';
import {textEntrances} from '../components/entrances';
import {slowDriftTransform} from '../components/slowDrift';
import {useLayout} from '../layout';
import {SceneEnvelopeWrapper, type SceneTransitionProps} from '../motion/sceneEnvelope';
import type {Scene} from '../types';
import {AuthoredWorksheet, panelRows} from '../components/AuthoredPanels';

type WhiteboardSceneProps = {
  scene: Scene;
  transition?: SceneTransitionProps;
};

export const WHITEBOARD_REVEAL_MIN_FRAMES = 9; // 0.3s @ 30fps
export const WHITEBOARD_REVEAL_MAX_FRAMES = 24; // 0.8s @ 30fps
export const WHITEBOARD_REVEAL_FRAMES = 15; // 0.5s @ 30fps

export const whiteboardInkReveal = (
  frame: number,
  startFrame: number,
  revealFrames = WHITEBOARD_REVEAL_FRAMES,
) => {
  const duration = Math.max(
    WHITEBOARD_REVEAL_MIN_FRAMES,
    Math.min(WHITEBOARD_REVEAL_MAX_FRAMES, revealFrames),
  );
  const progress = Math.max(0, Math.min(1, (frame - startFrame) / duration));
  return {
    progress,
    opacity: progress,
    dashOffset: 1 - progress,
    started: frame >= startFrame,
  };
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

export const WhiteboardScene: React.FC<WhiteboardSceneProps> = ({scene, transition}) => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const dashOffset = interpolate(frame, [0, 30], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const accentOffset = interpolate(frame, [12, 36], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const visualAssets = scene.visual_assets ?? [];
  const hasIllustration = visualAssets.some(asset => asset.role === 'whiteboard');
  const hasMascot = visualAssets.some(asset => asset.role === 'mascot');
  const textBox = hasIllustration ? layout.illustrationText : layout.whiteboardText;
  const pieces = textEntrances(scene);
  const drift = slowDriftTransform(frame, scene.duration_frames);
  const captionVariant = scene.words?.length ? 'shorts' : undefined;

  if (panelRows(scene, 3).length) {
    const content = <>
      <AuthoredWorksheet scene={scene} frame={frame}/>
      <Captions variant={captionVariant} hasMascot={hasMascot} text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames}/>
    </>;
    return transition ? <SceneEnvelopeWrapper transition={transition}>{content}</SceneEnvelopeWrapper> : content;
  }

  const isPortrait = layout.frame.height > layout.frame.width;
  const ruleY = textBox.top - 28;
  const ruleLeft = textBox.left + (isPortrait ? 48 : 80);
  const ruleRight = textBox.left + textBox.width - (isPortrait ? 48 : 80);

  const content = (
    <>
      {!hasIllustration ? <svg
        aria-label="Nét vẽ whiteboard"
        data-slow-drift={drift.active ? 'true' : undefined}
        data-whiteboard-palette="brand-3plus1"
        style={{height: '100%', left: 0, position: 'absolute', top: 0, width: '100%', overflow: 'hidden'}}
        viewBox={`0 0 ${layout.frame.width} ${layout.frame.height}`}
      >
        <g style={{transform: drift.transform, transformOrigin: 'center', transformBox: 'fill-box'}}>
          <path
            d={layout.whiteboardPath}
            fill="none"
            pathLength="1"
            stroke={brand.navy}
            strokeLinecap="round"
            strokeWidth="16"
            style={{
              strokeDasharray: 1,
              strokeDashoffset: dashOffset,
            }}
          />
          <path
            d={`M${ruleLeft} ${ruleY} Q${(ruleLeft + ruleRight) / 2} ${ruleY + 18} ${ruleRight} ${ruleY}`}
            fill="none"
            pathLength="1"
            stroke={brand.teal}
            strokeLinecap="round"
            strokeWidth="8"
            style={{
              strokeDasharray: 1,
              strokeDashoffset: accentOffset,
            }}
          />
          {pieces.map((piece, index) => {
            const reveal = whiteboardInkReveal(frame, piece.start_frame);
            const t = pieces.length <= 1 ? 0.5 : index / (pieces.length - 1);
            const cx = ruleLeft + (ruleRight - ruleLeft) * t;
            const cy = ruleY + Math.sin(t * Math.PI) * 9;
            return (
              <circle
                key={`node-${index}`}
                cx={cx}
                cy={cy}
                r={10 * reveal.progress}
                fill={reveal.progress > 0 && reveal.progress < 1 ? brand.yellow : brand.teal}
                stroke={brand.navy}
                strokeWidth="3"
                opacity={reveal.opacity}
              />
            );
          })}
        </g>
      </svg> : null}
      {scene.on_screen_text ? <div
        aria-label="Ý chính"
        style={{
          color: brand.navy,
          fontFamily: FONT_FAMILY,
          fontSize: whiteboardFontSize(scene.on_screen_text, textBox.width,
            textBox.height, layout.narration.fontSize),
          fontWeight: 800,
          ...textBox,
          lineHeight: 1.26,
          position: 'absolute',
          textAlign: 'center',
          overflowWrap: 'anywhere',
        }}
      >
        {pieces.map((piece, index) => {
          const reveal = whiteboardInkReveal(frame, piece.start_frame);
          const isWriting = reveal.progress > 0 && reveal.progress < 1;
          return (
            <span
              key={index}
              data-entrance-frame={piece.start_frame}
              data-ink-progress={reveal.progress.toFixed(2)}
              style={{
                position: 'relative',
                display: 'inline',
                opacity: reveal.opacity,
                borderBottom: reveal.progress > 0
                  ? `5px solid ${isWriting ? brand.yellow : brand.teal}`
                  : undefined,
                paddingBottom: 3,
              }}
            >
              {piece.text}
            </span>
          );
        })}
      </div> : null}
      <Captions variant={captionVariant} hasMascot={hasMascot} text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} />
    </>
  );

  return transition ? <SceneEnvelopeWrapper transition={transition}>{content}</SceneEnvelopeWrapper> : content;
};
