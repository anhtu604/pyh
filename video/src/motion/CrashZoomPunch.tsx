// Ported from video-shotcraft camera/crash-zoom-punch (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const CRASH_ZOOM_PUNCH_DURATION = 132;

const PUSH_START = 40;
const HIT_FRAME = 46;
const PEAK_ZOOM = 2.48;
const REST_ZOOM = 2.34;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const easeInCubic = (t: number): number => {
  const x = clamp01(t);
  return x * x * x;
};
const smooth = (t: number): number => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

// Wide hold + 6f pullback (f34..40) -> 6f log-space ease-in crash zoom (f40..46) -> damped bounce.
export const crashZoomStateAt = (
  frame: number,
  variant: 'bounce' | 'impact' = 'bounce',
): {zoom: number; shakeX: number; shakeY: number} => {
  const settle = smooth(frame / 34);
  const wind = smooth((frame - 34) / 6);
  const z0 = mix(0.7, 0.72, settle) * mix(1, 0.96, wind);

  if (frame < PUSH_START) {
    return {zoom: z0, shakeX: 0, shakeY: 0};
  }
  if (frame < HIT_FRAME) {
    const p = easeInCubic((frame - PUSH_START) / (HIT_FRAME - PUSH_START));
    return {
      zoom: Math.exp(mix(Math.log(z0), Math.log(PEAK_ZOOM), p)),
      shakeX: 0,
      shakeY: 0,
    };
  }
  const t = frame - HIT_FRAME;
  if (variant === 'impact') {
    const env = t <= 8 ? 14 * Math.exp(-t / 1.8) : 0;
    return {
      zoom: REST_ZOOM,
      shakeX: env * Math.sin(t * 2.7),
      shakeY: env * Math.cos(t * 3.4),
    };
  }
  const bounceZoom =
    REST_ZOOM + (PEAK_ZOOM - REST_ZOOM) * Math.exp(-t / 2.2) * Math.cos((Math.PI * t) / 5.2);
  return {zoom: bounceZoom, shakeX: 0, shakeY: 0};
};

export type CrashZoomPunchProps = {
  targetLabel?: string;
  targetValue?: string;
  targetDetail?: string;
  variant?: 'bounce' | 'impact';
  overlay?: boolean;
};

export const CrashZoomPunch: React.FC<CrashZoomPunchProps> = ({
  targetLabel,
  targetValue,
  targetDetail,
  variant = 'bounce',
  overlay = false,
}) => {
  const frame = useCurrentFrame();
  const {width, isVertical, u} = useMotionScale();

  if (overlay) {
    // 6f punch-in entrance flash + target bracket lock for scene transition_in.
    if (frame >= 18) {
      return (
        <AbsoluteFill
          data-motion="crash-zoom-punch"
          data-punch-complete="true"
          style={{pointerEvents: 'none'}}
        />
      );
    }
    const flash = Math.exp(-frame / 3.5);
    const pad = Math.max(0, (1 - clamp01(frame / 6)) * u(72));
    return (
      <AbsoluteFill data-motion="crash-zoom-punch" style={{pointerEvents: 'none'}}>
        <div
          style={{
            position: 'absolute',
            left: u(84) - pad,
            right: u(84) - pad,
            top: u(96) - pad * 0.5,
            bottom: u(160) - pad * 0.5,
            border: `${u(4)}px solid ${brand.yellow}`,
            borderRadius: u(28),
            opacity: flash,
          }}
        />
      </AbsoluteFill>
    );
  }

  const {zoom, shakeX, shakeY} = crashZoomStateAt(frame, variant);
  const flash = frame >= HIT_FRAME ? Math.exp(-(frame - HIT_FRAME) / 2.8) : 0;
  const cardWidth = isVertical ? Math.round(width * 0.86) : Math.round(width * 0.64);
  const safeValue = targetValue ?? '';
  const isNumericHero = Array.from(safeValue).length <= 16;
  const valueFontSize = isNumericHero ? u(124) : u(68);

  return (
    <AbsoluteFill
      data-motion="crash-zoom-punch"
      data-zoom={zoom.toFixed(3)}
      style={{
        backgroundColor: brand.night,
        fontFamily: FONT_FAMILY,
        color: brand.off_white,
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: cardWidth,
          padding: isVertical ? `${u(56)}px ${u(52)}px` : `${u(48)}px ${u(60)}px`,
          boxSizing: 'border-box',
          borderRadius: u(32),
          backgroundColor: brand.navy,
          border: `${u(4)}px solid ${frame >= HIT_FRAME ? brand.yellow : brand.teal}`,
          boxShadow:
            flash > 0.02 ? `0 0 ${(u(48) * flash).toFixed(1)}px ${brand.yellow}` : undefined,
          transform: `translate(${shakeX.toFixed(1)}px, ${shakeY.toFixed(1)}px) scale(${(zoom / REST_ZOOM).toFixed(4)})`,
        }}
      >
        {targetLabel ? (
          <div style={{fontSize: u(34), fontWeight: 800, color: brand.yellow}}>{targetLabel}</div>
        ) : null}
        {targetValue ? (
          <div
            style={{
              fontSize: valueFontSize,
              fontWeight: 800,
              marginTop: targetLabel ? u(18) : 0,
              lineHeight: 1.1,
              color: brand.off_white,
            }}
          >
            {targetValue}
          </div>
        ) : null}
        {targetDetail ? (
          <div
            style={{
              fontSize: u(42),
              fontWeight: 600,
              color: brand.off_white,
              marginTop: u(22),
              lineHeight: 1.35,
            }}
          >
            {targetDetail}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
