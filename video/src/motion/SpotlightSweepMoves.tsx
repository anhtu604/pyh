// Ported from video-shotcraft effects/spotlight-sweep-moves (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const SPOTLIGHT_SWEEP_MOVES_DURATION = 120;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

// Strictly linear radial spotlight expansion (zero easing): r 160 -> 1300 over 100f so r + feather
// reaches full 1080p diagonal right at the end without early saturation.
export const spotlightRadiusAt = (frame: number): number =>
  mix(160, 1300, clamp01(frame / 100));

export type SpotlightSweepMovesProps = {
  title?: string;
  emphasisText?: string;
  detail?: string;
  overlay?: boolean;
};

export const SpotlightSweepMoves: React.FC<SpotlightSweepMovesProps> = ({
  title,
  emphasisText,
  detail,
  overlay = false,
}) => {
  const frame = useCurrentFrame();
  const {width, height, isVertical, u} = useMotionScale();
  const linearT = clamp01(frame / 100);
  const rawR = spotlightRadiusAt(frame);
  const r = rawR * (Math.max(width, height) / 1920);
  const cx = mix(width * 0.28, width * 0.48, clamp01(frame / 96));
  const cy = mix(height * 0.34, height * 0.48, clamp01(frame / 96));
  const feather = r * 0.85;
  const innerStop = Math.max(0, ((r - feather * 0.25) / (r + feather)) * 100);
  const mask = `radial-gradient(circle ${(r + feather).toFixed(1)}px at ${cx.toFixed(1)}px ${cy.toFixed(1)}px, rgba(255,255,255,1) ${innerStop.toFixed(1)}%, rgba(255,255,255,0) 100%)`;

  const marginX = isVertical ? Math.round(width * 0.08) : u(140);
  const contentWidth = width - marginX * 2;

  return (
    <AbsoluteFill
      data-motion="spotlight-sweep-moves"
      data-spotlight-radius={rawR.toFixed(1)}
      style={{
        backgroundColor: overlay ? 'transparent' : brand.night,
        fontFamily: FONT_FAMILY,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      <AbsoluteFill
        style={{
          WebkitMaskImage: mask,
          maskImage: mask,
          backgroundColor: overlay ? 'rgba(18, 48, 74, 0.25)' : brand.off_white,
          color: overlay ? brand.off_white : brand.navy,
          alignItems: 'center',
          justifyContent: 'center',
          padding: `${u(110)}px ${marginX}px`,
          boxSizing: 'border-box',
        }}
      >
        {!overlay ? (
          <div style={{width: contentWidth, display: 'flex', flexDirection: 'column'}}>
            {/* Signature edge-hugging multi-layer glow line along top panel edge */}
            <div
              data-edge-glow="true"
              style={{
                width: `${(linearT * 88).toFixed(1)}%`,
                height: u(5),
                backgroundColor: brand.teal,
                boxShadow: `0 0 ${u(9)}px ${brand.teal}, 0 0 ${u(26)}px ${brand.yellow}`,
                marginBottom: u(36),
              }}
            />
            {title ? (
              <div style={{fontSize: isVertical ? u(72) : u(82), fontWeight: 800, lineHeight: 1.12}}>
                {title}
              </div>
            ) : null}
            {emphasisText ? (
              <div
                style={{
                  fontSize: u(46),
                  fontWeight: 800,
                  color: brand.teal,
                  marginTop: title ? u(22) : 0,
                  lineHeight: 1.25,
                }}
              >
                {emphasisText}
              </div>
            ) : null}
            {detail ? (
              <div
                style={{
                  fontSize: u(42),
                  fontWeight: 600,
                  color: brand.charcoal,
                  marginTop: u(24),
                  maxWidth: isVertical ? contentWidth : u(1280),
                  lineHeight: 1.35,
                }}
              >
                {detail}
              </div>
            ) : null}
          </div>
        ) : emphasisText ? (
          <div
            style={{
              position: 'absolute',
              left: marginX,
              top: u(104),
              padding: `${u(12)}px ${u(26)}px`,
              borderRadius: u(14),
              backgroundColor: brand.navy,
              color: brand.yellow,
              fontSize: u(36),
              fontWeight: 800,
            }}
          >
            {emphasisText}
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
