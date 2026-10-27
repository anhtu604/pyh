// Ported from video-shotcraft typography/title-demote-to-label (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const TITLE_DEMOTE_TO_LABEL_DURATION = 112;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const easeOut = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);
// Asymmetric in-out matching bezier(0.6, 0, 0.18, 1): decisive launch, soft landing.
const demoteEase = (t: number): number => {
  const x = clamp01(t);
  return x < 0.45 ? 2.2 * x * x : 1 - Math.pow(1 - x, 3) * 1.65;
};
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;
const ramp = (f: number, start: number, dur: number, ease = easeOut): number =>
  ease((f - start) / dur);

export type TitleDemoteToLabelProps = {
  title?: string;
  chapterCode?: string;
  summary?: string;
  points?: readonly string[];
  overlay?: boolean;
};

export const TitleDemoteToLabel: React.FC<TitleDemoteToLabelProps> = ({
  title,
  chapterCode,
  summary,
  points,
  overlay = false,
}) => {
  const frame = useCurrentFrame();
  const {width, height, isVertical, u} = useMotionScale();

  // 0..16 title rise, 16..36 hold >=20f (with 1.5% slow push), 36..62 single continuous 26f demote tween,
  // 48+ (+12f after demote start) content staggered growth.
  const rise = ramp(frame, 0, 16, easeOut);
  const holdPush = 1 + 0.015 * ramp(frame, 16, 20, easeOut);
  const demote = ramp(frame, 36, 26, demoteEase);

  const marginX = isVertical ? Math.round(width * 0.07) : u(120);
  const contentWidth = width - marginX * 2;
  const slotX = marginX + u(88);
  const slotY = isVertical ? u(280) : u(140);

  const safeTitle = title ?? '';
  const charCount = Math.max(1, Array.from(safeTitle).length);
  const rawHeroSize = Math.floor((width * 0.84) / Math.max(6, charCount * 0.62));
  const heroFontSize = Math.min(isVertical ? u(96) : u(132), Math.max(u(56), rawHeroSize));
  const labelScale = u(40) / heroFontSize;

  const x = mix(Math.round(width * 0.5), slotX, demote);
  const y = mix(Math.round(height * 0.5), slotY, demote);
  const scale = mix(holdPush, labelScale, demote);
  const prefixIn = ramp(frame, 50, 12, easeOut);

  return (
    <AbsoluteFill
      data-motion="title-demote-to-label"
      data-demote-progress={demote.toFixed(3)}
      style={{
        backgroundColor: overlay ? 'transparent' : brand.off_white,
        fontFamily: FONT_FAMILY,
        color: brand.navy,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      {/* Section prefix wiping in at top-left slot when chapterCode is provided */}
      {!overlay && chapterCode ? (
        <div
          style={{
            position: 'absolute',
            left: marginX,
            top: slotY - u(22),
            fontSize: u(34),
            fontWeight: 800,
            color: brand.teal,
            opacity: prefixIn,
            transform: `translateX(${((1 - prefixIn) * -u(18)).toFixed(1)}px)`,
          }}
        >
          {chapterCode} /
        </div>
      ) : null}

      {/* Hero title demoting continuously into section label */}
      {safeTitle ? (
        <div
          data-demote-title={safeTitle}
          style={{
            position: 'absolute',
            left: x,
            top: y,
            fontSize: heroFontSize,
            fontWeight: 800,
            lineHeight: 1.08,
            letterSpacing: '-0.03em',
            whiteSpace: 'nowrap',
            transformOrigin: '0% 50%',
            transform: `translate(${(-(1 - demote) * 50).toFixed(2)}%, -50%) scale(${scale.toFixed(4)})`,
            opacity: rise,
          }}
        >
          {safeTitle}
          <span style={{color: brand.teal}}>.</span>
        </div>
      ) : null}

      {/* Content skeleton growing 12f into the demote (f >= 48) */}
      {!overlay && (summary || (points && points.length > 0)) ? (
        <div
          style={{
            position: 'absolute',
            left: marginX,
            top: slotY + u(76),
            width: contentWidth,
          }}
        >
          <div
            style={{
              height: u(3),
              backgroundColor: brand.navy,
              opacity: ramp(frame, 54, 18, easeOut),
              transform: `scaleX(${ramp(frame, 54, 18, easeOut).toFixed(3)})`,
              transformOrigin: '0 50%',
            }}
          />
          {summary ? (
            <div
              style={{
                marginTop: u(34),
                fontSize: u(50),
                fontWeight: 800,
                color: brand.navy,
                lineHeight: 1.25,
                opacity: ramp(frame, 48, 20, easeOut),
                transform: `translateY(${((1 - ramp(frame, 48, 20, easeOut)) * u(30)).toFixed(1)}px)`,
              }}
            >
              {summary}
            </div>
          ) : null}
          {points && points.length > 0 ? (
            <div
              data-cards-axis={isVertical ? 'column' : 'row'}
              style={{
                display: 'flex',
                flexDirection: isVertical ? 'column' : 'row',
                gap: isVertical ? u(28) : u(32),
                marginTop: u(42),
              }}
            >
              {points.map((pt, idx) => {
                const p = ramp(frame, 56 + idx * 7, 22, easeOut);
                return (
                  <div
                    key={idx}
                    data-content-card={idx}
                    style={{
                      flex: isVertical ? undefined : 1,
                      width: isVertical ? '100%' : undefined,
                      boxSizing: 'border-box',
                      padding: `${u(32)}px ${u(36)}px`,
                      borderRadius: u(22),
                      backgroundColor: '#FFFFFF',
                      border: `${u(3)}px solid ${brand.teal}`,
                      fontSize: u(40),
                      fontWeight: 600,
                      color: brand.charcoal,
                      lineHeight: 1.35,
                      opacity: p,
                      transform: `translateY(${((1 - p) * u(30)).toFixed(1)}px)`,
                    }}
                  >
                    {pt}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
