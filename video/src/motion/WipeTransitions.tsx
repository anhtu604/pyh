// Ported from video-shotcraft transition/wipe-transitions (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const WIPE_TRANSITIONS_DURATION = 132;

const STRIPS = 12;
const WAVE0 = 16;
const SPAN = 28;
const WIPE_END = 76;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const smooth = (t: number): number => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};

// Stagger t^0.78 (accelerating wave from 3.4f to 2.1f spacing) + spring flip 0 -> 180 deg.
export const blindStartOf = (i: number, waveStart = WAVE0): number =>
  waveStart + SPAN * Math.pow(i / (STRIPS - 1), 0.78);

export const blindAngleAt = (frame: number, i: number, waveStart = WAVE0): number => {
  const s = blindStartOf(i, waveStart);
  if (frame < s) return 0;
  const elapsed = (frame - s) / 16;
  if (elapsed >= 2.2) return 180;
  const springK = 1 - Math.exp(-4.2 * elapsed) * Math.cos(Math.PI * 1.35 * elapsed);
  return 180 * springK;
};

// Monotonic wipe progress (0..100%) driving complementary clipPaths on old/new layers.
export const wipePercentAt = (frame: number): number => {
  if (frame <= WAVE0) return 0;
  if (frame >= WIPE_END) return 100;
  const t = clamp01((frame - WAVE0) / (WIPE_END - WAVE0));
  return smooth(Math.pow(t, 0.72)) * 100;
};

export type WipeTransitionsProps = {
  fromTitle?: string;
  toTitle?: string;
  fromSubtitle?: string;
  toSubtitle?: string;
  overlay?: boolean;
};

export const WipeTransitions: React.FC<WipeTransitionsProps> = ({
  fromTitle,
  toTitle,
  fromSubtitle,
  toSubtitle,
  overlay = false,
}) => {
  const frame = useCurrentFrame();
  const {width, isVertical, u} = useMotionScale();

  if (overlay) {
    if (frame >= 44) {
      return (
        <AbsoluteFill
          data-motion="wipe-transitions"
          data-wipe-complete="true"
          style={{pointerEvents: 'none'}}
        />
      );
    }
    return (
      <AbsoluteFill
        data-motion="wipe-transitions"
        style={{pointerEvents: 'none', overflow: 'hidden'}}
      >
        {Array.from({length: STRIPS}, (_, i) => {
          const deg = blindAngleAt(frame, i, 0);
          const progress = clamp01(deg / 180);
          return (
            <div
              key={i}
              data-blind-strip={i}
              style={{
                position: 'absolute',
                left: `${(i * 100) / STRIPS}%`,
                top: 0,
                bottom: 0,
                width: `${100 / STRIPS}%`,
                backgroundColor: brand.navy,
                borderRight: `${u(2)}px solid ${brand.teal}`,
                transformOrigin: '50% 50%',
                transform: `scaleX(${(1 - progress).toFixed(3)})`,
                opacity: 1 - progress,
              }}
            />
          );
        })}
      </AbsoluteFill>
    );
  }

  const pct = wipePercentAt(frame);
  const fromClipLeft = pct.toFixed(2);
  const toClipRight = (100 - pct).toFixed(2);
  const unmasked = frame >= WIPE_END;
  const marginX = isVertical ? Math.round(width * 0.08) : u(140);
  const contentWidth = width - marginX * 2;
  const titleSize = isVertical ? u(76) : u(96);

  return (
    <AbsoluteFill
      data-motion="wipe-transitions"
      data-unmasked={unmasked}
      data-wipe-percent={fromClipLeft}
      style={{
        backgroundColor: '#120D0A',
        fontFamily: FONT_FAMILY,
        overflow: 'hidden',
      }}
    >
      {/* Old layer (FROM): clipped from the left by pct% so it never overlaps the new layer */}
      <AbsoluteFill
        data-wipe-layer="from"
        style={{
          backgroundColor: brand.off_white,
          color: brand.navy,
          alignItems: 'center',
          justifyContent: 'center',
          padding: `${u(120)}px ${marginX}px`,
          boxSizing: 'border-box',
          clipPath: `inset(0 0 0 ${fromClipLeft}%)`,
        }}
      >
        <div style={{width: contentWidth}}>
          {fromTitle ? (
            <div
              style={{
                fontSize: titleSize,
                fontWeight: 800,
                lineHeight: 1.15,
              }}
            >
              {fromTitle}
            </div>
          ) : null}
          {fromSubtitle ? (
            <div
              style={{
                fontSize: u(44),
                fontWeight: 600,
                color: brand.charcoal,
                marginTop: fromTitle ? u(24) : 0,
                lineHeight: 1.3,
              }}
            >
              {fromSubtitle}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>

      {/* New layer (TO): clipped from the right by (100 - pct)% so it complements FROM */}
      <AbsoluteFill
        data-wipe-layer="to"
        style={{
          backgroundColor: brand.navy,
          color: brand.off_white,
          alignItems: 'center',
          justifyContent: 'center',
          padding: `${u(120)}px ${marginX}px`,
          boxSizing: 'border-box',
          clipPath: `inset(0 ${toClipRight}% 0 0)`,
        }}
      >
        <div style={{width: contentWidth}}>
          {toTitle ? (
            <div
              style={{
                fontSize: titleSize,
                fontWeight: 800,
                lineHeight: 1.15,
              }}
            >
              {toTitle}
            </div>
          ) : null}
          {toSubtitle ? (
            <div
              style={{
                fontSize: u(44),
                fontWeight: 600,
                color: brand.teal,
                marginTop: toTitle ? u(24) : 0,
                lineHeight: 1.3,
              }}
            >
              {toSubtitle}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>

      {/* Decorative wipe seam and blind slats along the active transition boundary */}
      {pct > 0 && pct < 100 ? (
        <div
          data-wipe-seam="true"
          style={{
            position: 'absolute',
            left: `${fromClipLeft}%`,
            top: 0,
            bottom: 0,
            width: u(6),
            backgroundColor: brand.yellow,
            boxShadow: `0 0 ${u(20)}px ${brand.yellow}`,
            transform: 'translateX(-50%)',
            pointerEvents: 'none',
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};
