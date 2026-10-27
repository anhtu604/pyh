// Ported from video-shotcraft transition/circle-match-iris (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const CIRCLE_MATCH_IRIS_DURATION = 165;

// Shared concentric reference center in 1080p coordinates.
export const IRIS_CENTER = {cx: 540, cy: 540} as const;
const AV_R = 36;
const RING_R = 280;
const RING_W = 42;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const outCubic = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);
const irisEase = (t: number): number => {
  const x = clamp01(t);
  return x * x * (2.6 - 1.6 * x);
};
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;
const ramp = (f: number, s: number, d: number, ease = outCubic): number => ease((f - s) / d);

export type CircleMatchIrisProps = {
  anchorLabel?: string;
  targetTitle?: string;
  targetPercent?: number;
  overlay?: boolean;
};

export const CircleMatchIris: React.FC<CircleMatchIrisProps> = ({
  anchorLabel,
  targetTitle,
  targetPercent,
  overlay = false,
}) => {
  const f = useCurrentFrame();
  const {width, height, isVertical, u} = useMotionScale();
  const cx = isVertical ? Math.round(width * 0.5) : u(IRIS_CENTER.cx);
  const cy = isVertical ? Math.round(height * 0.42) : u(IRIS_CENTER.cy);

  // In overlay (transition_in) mode, run a brisk 30f concentric iris reveal from (cx, cy) then unmount/transparent.
  if (overlay) {
    const t = clamp01(f / 28);
    const r = mix(u(36), u(2200), irisEase(t));
    if (f >= 30) {
      return (
        <AbsoluteFill
          data-motion="circle-match-iris"
          data-iris-complete="true"
          style={{pointerEvents: 'none'}}
        />
      );
    }
    return (
      <AbsoluteFill data-motion="circle-match-iris" style={{pointerEvents: 'none'}}>
        <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`}>
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={brand.teal}
            strokeWidth={Math.max(u(4), (1 - t) * u(44))}
            opacity={1 - t}
          />
        </svg>
      </AbsoluteFill>
    );
  }

  const pulse = (s: number): number => ramp(f, s, 5) - ramp(f, s + 5, 11);
  const anticip = ramp(f, 40, 7);
  const avScale = 1 + 0.16 * (pulse(18) + pulse(30)) - 0.1 * anticip;
  const grow = ramp(f, 47, 28);
  // Solid disc hollows into ring: strokeWidth starts equal to diameter, shrinks to RING_W.
  const ringR = mix(u(AV_R) * 0.9, u(RING_R), grow);
  const ringW = mix(u(AV_R) * 0.9 * 2, u(RING_W), ramp(f, 47, 22));
  const irisR = ringR + ringW / 2 + u(10) + u(2400) * ramp(f, 54, 30, irisEase);
  const hasPercent = typeof targetPercent === 'number' && Number.isFinite(targetPercent);
  const sweep = hasPercent ? (targetPercent / 100) * ramp(f, 60, 58) : 0;
  const circ = 2 * Math.PI * ringR;

  const marginX = Math.round(width * 0.08);
  const safeW = width - marginX * 2;

  return (
    <AbsoluteFill
      data-motion="circle-match-iris"
      data-iris-radius={irisR.toFixed(1)}
      style={{
        backgroundColor: brand.off_white,
        fontFamily: FONT_FAMILY,
        color: brand.navy,
        overflow: 'hidden',
      }}
    >
      {/* Scene A: Foreground list with circular anchor at (cx, cy) */}
      <AbsoluteFill>
        {anchorLabel ? (
          <div
            style={{
              position: 'absolute',
              left: marginX,
              width: safeW,
              top: isVertical ? cy - u(260) : u(120),
              textAlign: isVertical ? 'center' : 'left',
              fontSize: u(52),
              fontWeight: 800,
              lineHeight: 1.25,
            }}
          >
            {anchorLabel}
          </div>
        ) : null}
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          style={{position: 'absolute', inset: 0}}
        >
          <circle cx={cx} cy={cy} r={u(AV_R) * avScale} fill={brand.teal} />
        </svg>
      </AbsoluteFill>

      {/* Scene B: Concentric ring chart expanding inside iris clip-path from exact same (cx, cy) */}
      {f >= 47 ? (
        <AbsoluteFill
          data-iris-scene-b="true"
          style={{
            backgroundColor: brand.night,
            color: brand.off_white,
            clipPath: `circle(${irisR.toFixed(1)}px at ${cx}px ${cy}px)`,
          }}
        >
          <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            style={{position: 'absolute', inset: 0}}
          >
            <circle
              cx={cx}
              cy={cy}
              r={ringR}
              fill="none"
              stroke={brand.navy}
              strokeWidth={ringW}
            />
            {hasPercent ? (
              <circle
                cx={cx}
                cy={cy}
                r={ringR}
                fill="none"
                stroke={brand.yellow}
                strokeWidth={ringW}
                strokeDasharray={`${(sweep * circ).toFixed(1)} ${circ.toFixed(1)}`}
                strokeLinecap="round"
                transform={`rotate(-90 ${cx} ${cy})`}
              />
            ) : null}
          </svg>
          {hasPercent ? (
            <div
              style={{
                position: 'absolute',
                left: cx - u(200),
                top: cy - u(72),
                width: u(400),
                textAlign: 'center',
                fontSize: u(128),
                fontWeight: 800,
                lineHeight: 1.1,
                color: brand.yellow,
              }}
            >
              {targetPercent}%
            </div>
          ) : null}
          {targetTitle ? (
            isVertical ? (
              <div
                data-iris-label-position="below"
                style={{
                  position: 'absolute',
                  left: marginX,
                  width: safeW,
                  top: cy + u(RING_R) + u(80),
                  textAlign: 'center',
                  fontSize: u(52),
                  fontWeight: 800,
                  lineHeight: 1.3,
                }}
              >
                {targetTitle}
              </div>
            ) : (
              <div
                data-iris-label-position="right"
                style={{
                  position: 'absolute',
                  left: u(920),
                  top: u(430),
                  maxWidth: u(820),
                  fontSize: u(52),
                  fontWeight: 800,
                  lineHeight: 1.25,
                }}
              >
                {targetTitle}
              </div>
            )
          ) : null}
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
