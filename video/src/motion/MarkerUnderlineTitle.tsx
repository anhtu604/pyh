// Ported from video-shotcraft typography/marker-underline-title (Apache-2.0)
import React, {useId} from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const MARKER_UNDERLINE_TITLE_DURATION = 75;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const snappy = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);
const smooth = (t: number): number => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};

const mulberry32 = (seed: number) => () => {
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

const buildStroke = (len: number, seed: number): string => {
  const rand = mulberry32(seed);
  const steps = 40;
  const top: string[] = [];
  const bot: string[] = [];
  const wob = Array.from({length: steps + 1}, () => rand() - 0.5);
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const x = t * len;
    // Slight upward tilt from left-low to right-high following italic slant.
    const mid = 19 - t * 9 + Math.sin(t * Math.PI * 1.6 + 0.4) * 2.6 + wob[i] * 1.6;
    const wBase =
      14 + Math.sin(t * Math.PI) * 6 - Math.max(0, t - 0.86) * 46 - Math.max(0, 0.06 - t) * 70;
    const w = Math.max(2.2, wBase + wob[i] * 3);
    top.push(`${x.toFixed(1)},${(mid - w / 2).toFixed(1)}`);
    bot.push(`${x.toFixed(1)},${(mid + w / 2).toFixed(1)}`);
  }
  return `M${top.join('L')}L${bot.reverse().join('L')}Z`;
};

const STROKE_LEN = 252;
const STROKE_PATH = buildStroke(STROKE_LEN, 77);

export type MarkerUnderlineTitleProps = {
  prefix?: string;
  emphasisText?: string;
  subline?: string;
  overlay?: boolean;
};

export const MarkerUnderlineTitle: React.FC<MarkerUnderlineTitleProps> = ({
  prefix,
  emphasisText,
  subline,
  overlay = false,
}) => {
  const frame = useCurrentFrame();
  const {width, isVertical, u} = useMotionScale();
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const revealId = `marker-reveal-${uid}`;

  // 22f settle -> wait +10f -> f32..42 (10f) marker stroke draw -> >=33f still hold.
  const line1 = snappy((frame - 0) / 22);
  const line2 = snappy((frame - 4) / 22);
  const drawRaw = clamp01((frame - 32) / 10);
  const drawEase = 1 - Math.pow(1 - drawRaw, 2.2);
  const push = 1 + 0.015 * smooth(frame / 74);

  const safeWidth = Math.round(width * 0.86);

  return (
    <AbsoluteFill
      data-motion="marker-underline-title"
      style={{
        backgroundColor: overlay ? 'transparent' : brand.off_white,
        alignItems: 'center',
        justifyContent: overlay ? 'flex-start' : 'center',
        paddingTop: overlay ? u(96) : 0,
        pointerEvents: 'none',
        overflow: 'hidden',
        transform: `scale(${push.toFixed(4)})`,
      }}
    >
      <div
        style={{
          width: overlay ? undefined : safeWidth,
          maxWidth: safeWidth,
          fontFamily: FONT_FAMILY,
          color: brand.navy,
          textAlign: 'center',
          lineHeight: 1.2,
          backgroundColor: overlay ? 'rgba(247, 244, 236, 0.94)' : 'transparent',
          padding: overlay ? `${u(18)}px ${u(36)}px ${u(26)}px` : 0,
          borderRadius: overlay ? u(22) : 0,
          border: overlay ? `${u(3)}px solid ${brand.teal}` : 'none',
        }}
      >
        {prefix || emphasisText ? (
          <div
            style={{
              fontSize: overlay ? u(52) : isVertical ? u(76) : u(84),
              fontWeight: 800,
              opacity: Math.min(1, line1 * 1.4),
              transform: `translateY(${((1 - line1) * u(36)).toFixed(1)}px)`,
            }}
          >
            {prefix ? (emphasisText ? `${prefix} ` : prefix) : null}
            {emphasisText ? (
              <span
                data-marker-keyword={emphasisText}
                style={{
                  fontStyle: 'italic',
                  position: 'relative',
                  display: 'inline-block',
                  color: brand.teal,
                }}
              >
                {emphasisText}
                <svg
                  aria-label="Nét gạch bút dạ"
                  width={STROKE_LEN}
                  height={44}
                  viewBox={`0 0 ${STROKE_LEN} 44`}
                  preserveAspectRatio="none"
                  style={{
                    position: 'absolute',
                    left: -u(8),
                    bottom: -u(16),
                    width: `calc(100% + ${u(16)}px)`,
                    height: u(36),
                    overflow: 'visible',
                  }}
                >
                  <defs>
                    <clipPath id={revealId}>
                      <rect x={0} y={-20} width={drawEase * (STROKE_LEN + 6)} height={60} />
                    </clipPath>
                  </defs>
                  {drawRaw > 0 ? (
                    <g clipPath={`url(#${revealId})`} data-marker-stroke={drawEase.toFixed(2)}>
                      <path d={STROKE_PATH} fill={brand.yellow} fillOpacity={0.95} />
                    </g>
                  ) : null}
                </svg>
              </span>
            ) : null}
          </div>
        ) : null}
        {subline && !overlay ? (
          <div
            style={{
              marginTop: u(32),
              fontSize: u(42),
              fontWeight: 600,
              color: brand.charcoal,
              opacity: Math.min(1, line2 * 1.4),
              transform: `translateY(${((1 - line2) * u(36)).toFixed(1)}px)`,
            }}
          >
            {subline}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
