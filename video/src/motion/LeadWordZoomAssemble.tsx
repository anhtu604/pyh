// Ported from video-shotcraft typography/lead-word-zoom-assemble (Apache-2.0)
import React, {Fragment} from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const LEAD_WORD_ZOOM_ASSEMBLE_DURATION = 84;

const INITIAL_SCALE = 2.3;
const INTRO_DURATION = 6;
const HOLD_DURATION = 12;
const PUSH_SCALE = 1.06;
const RECEDE_DURATION = 12;
const ASSEMBLE_DURATION = 24;
const WORD_DELAY = 6;
const WORD_STAGGER = 4;
const WORD_DURATION = 12;
const WORD_PUSH_EM = 0.5;
const WORD_FADE = 2;
const LIFT_START = 32;
const LIFT_END = 46;
const LIFT_DISTANCE = -56;
const CRASH_FRAMES = 12;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));

// Cubic-bezier approximation matching PUSH_EASE (.25,1,.5,1), ZOOM_EASE (.5,0,.05,1), WORD_EASE (.22,.8,.36,1).
const pushEase = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);
const zoomEase = (t: number): number => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};
const wordEase = (t: number): number => 1 - Math.pow(1 - clamp01(t), 2.6);

export const leadWordScaleAt = (frame: number): number =>
  INITIAL_SCALE +
  (INITIAL_SCALE * PUSH_SCALE - INITIAL_SCALE) * pushEase(frame / HOLD_DURATION) +
  (1 - INITIAL_SCALE * PUSH_SCALE) * zoomEase((frame - HOLD_DURATION) / RECEDE_DURATION);

export type LeadWordZoomAssembleProps = {
  term?: string;
  definition?: string;
  highlightWord?: string;
  crashTail?: boolean;
  overlay?: boolean;
};

export const LeadWordZoomAssemble: React.FC<LeadWordZoomAssembleProps> = ({
  term,
  definition,
  highlightWord,
  crashTail = false,
  overlay = false,
}) => {
  const frame = useCurrentFrame();
  const {width, isVertical, u} = useMotionScale();
  const safeTerm = term ?? '';
  const words = safeTerm.trim().split(/\s+/).filter(Boolean);
  const firstWord = words[0] ?? safeTerm;
  const totalChars = Math.max(1, Array.from(safeTerm).length);
  const leadChars = Array.from(firstWord).length;
  // Deterministic lead-word center ratio and baseline so SSR and frame sampling never flicker.
  const leadRatio = Math.min(0.45, Math.max(0.1, (leadChars * 0.5) / totalChars));

  const safeWidth = Math.round(width * 0.86);
  const rawHeroSize = Math.floor(safeWidth / Math.max(6, totalChars * 0.58));
  const heroFontSize = overlay
    ? u(54)
    : Math.min(isVertical ? u(88) : u(96), Math.max(u(52), rawHeroSize));
  const lineWidth = Math.min(safeWidth, totalChars * heroFontSize * 0.56);
  const baselinePx = Math.round(heroFontSize * 0.9);

  const scale = leadWordScaleAt(frame);
  const slideDistance = lineWidth * (0.5 - leadRatio);
  const slideProgress = zoomEase((frame - HOLD_DURATION) / ASSEMBLE_DURATION);
  const translateX = slideDistance * (1 - slideProgress);
  const leadOpacity = clamp01(frame / INTRO_DURATION);

  const liftProgress = pushEase((frame - LIFT_START) / (LIFT_END - LIFT_START));
  const liftY = u(LIFT_DISTANCE) * liftProgress;

  const crashStart = LEAD_WORD_ZOOM_ASSEMBLE_DURATION - CRASH_FRAMES;
  const crashProgress = crashTail ? clamp01((frame - crashStart) / CRASH_FRAMES) : 0;
  const sceneScale = 1 + 0.2 * crashProgress * crashProgress;
  const sceneOpacity = 1 - 0.55 * crashProgress * crashProgress;

  const targetHighlight = highlightWord ?? words[words.length - 1];

  return (
    <AbsoluteFill
      data-motion="lead-word-zoom-assemble"
      data-lead-scale={scale.toFixed(3)}
      style={{
        backgroundColor: overlay ? 'transparent' : brand.off_white,
        alignItems: 'center',
        justifyContent: overlay ? 'flex-start' : 'center',
        paddingTop: overlay ? u(84) : 0,
        pointerEvents: 'none',
        overflow: 'hidden',
        transform: `scale(${sceneScale.toFixed(4)})`,
        opacity: sceneOpacity,
      }}
    >
      <div
        style={{
          position: 'relative',
          width: overlay ? undefined : safeWidth,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          fontFamily: FONT_FAMILY,
          backgroundColor: overlay ? 'rgba(247, 244, 236, 0.94)' : 'transparent',
          padding: overlay ? `${u(20)}px ${u(38)}px` : 0,
          borderRadius: overlay ? u(24) : 0,
        }}
      >
        {words.length > 0 ? (
          <div style={{transform: `translateY(${overlay ? 0 : liftY.toFixed(1)}px)`}}>
            <span
              data-pivot-origin={`${(leadRatio * 100).toFixed(1)}% ${baselinePx}px`}
              style={{
                display: 'inline-block',
                fontSize: heroFontSize,
                fontWeight: 800,
                letterSpacing: '-0.025em',
                lineHeight: 1.15,
                color: brand.navy,
                whiteSpace: 'nowrap',
                transformOrigin: `${(leadRatio * 100).toFixed(2)}% ${baselinePx}px`,
                transform: `translateX(${translateX.toFixed(1)}px) scale(${scale.toFixed(4)})`,
              }}
            >
              {words.map((word, index) => {
                const isLead = index === 0;
                const pushStart = HOLD_DURATION + WORD_DELAY + (index - 1) * WORD_STAGGER;
                const wordProgress = isLead ? 1 : wordEase((frame - pushStart) / WORD_DURATION);
                const wordX = isLead ? 0 : (1 - wordProgress) * WORD_PUSH_EM;
                const wordOpacity = isLead ? leadOpacity : clamp01((frame - pushStart) / WORD_FADE);
                const isHighlighted = word === targetHighlight && words.length > 1;
                return (
                  <Fragment key={`${word}-${index}`}>
                    <span
                      data-word-index={index}
                      style={{
                        display: 'inline-block',
                        color: isHighlighted ? brand.teal : brand.navy,
                        opacity: wordOpacity,
                        transform: `translateX(${wordX.toFixed(3)}em)`,
                      }}
                    >
                      {word}
                    </span>
                    {index < words.length - 1 ? ' ' : null}
                  </Fragment>
                );
              })}
            </span>
          </div>
        ) : null}
        {definition && !overlay ? (
          <div
            data-subline="definition"
            style={{
              marginTop: u(20),
              maxWidth: safeWidth,
              fontSize: u(42),
              fontWeight: 600,
              color: brand.charcoal,
              textAlign: 'center',
              lineHeight: 1.35,
              opacity: liftProgress,
              transform: `translateY(${((1 - liftProgress) * u(16)).toFixed(1)}px)`,
            }}
          >
            {definition}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
