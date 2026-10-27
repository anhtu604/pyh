// Ported from video-shotcraft typography/outline-word-fill (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const OUTLINE_WORD_FILL_DURATION = 90;
export const OUTLINE_POP_FRAME = 54;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const easeOut = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);
const easeSnappy = (t: number): number => 1 - Math.pow(1 - clamp01(t), 4);
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;
const ramp = (f: number, start: number, dur: number, ease = easeOut): number =>
  ease((f - start) / dur);

export type OutlineWordFillProps = {
  term?: string;
  definition?: string;
  leftReadout?: string;
  rightReadout?: string;
  overlay?: boolean;
};

export const OutlineWordFill: React.FC<OutlineWordFillProps> = ({
  term,
  definition,
  leftReadout,
  rightReadout,
  overlay = false,
}) => {
  const frame = useCurrentFrame();
  const {width, height, isVertical, u} = useMotionScale();

  // 11f rapid outline contraction (2.4 -> 1), 44f slow dashed HUD circle contraction (2.4 -> 1),
  // hard-cut solid fill at exact frame POP = 54 (no gradual wipe).
  const born = ramp(frame, 2, 6, easeOut);
  const wordScale = mix(2.2, 1, ramp(frame, 2, 11, easeSnappy));
  const circleIn = ramp(frame, 8, 10, easeOut);
  const circleShrink = ramp(frame, 8, 44, easeOut);
  const lineExt = ramp(frame, 28, 18, easeOut);
  const warm = ramp(frame, 44, 9, easeOut);
  const lit = frame >= OUTLINE_POP_FRAME ? 1 : 0;
  const flash = lit * (1 - ramp(frame, OUTLINE_POP_FRAME, 8, easeOut));
  const shock = ramp(frame, OUTLINE_POP_FRAME, 14, easeOut);
  const rot =
    0.22 * Math.min(frame, OUTLINE_POP_FRAME) +
    (frame > OUTLINE_POP_FRAME ? 6 * ramp(frame, OUTLINE_POP_FRAME, 14, easeOut) : 0);
  const rotIn = -0.14 * frame;
  const subIn = ramp(frame, 56, 14, easeSnappy);
  const push = 1 + 0.015 * ramp(frame, 0, OUTLINE_WORD_FILL_DURATION, easeOut);

  const strokeColor = warm > 0.5 ? brand.yellow : '#8AAABF';
  const hudColor = lit ? brand.yellow : strokeColor;

  const cx = Math.round(width * 0.5);
  const cy = Math.round(height * 0.5);
  const r = isVertical ? u(380) : u(410);
  const lineEnd = Math.max(u(60), cx - r - u(28));

  // Enforce >= 8% horizontal margin on each side (>= 6% required) and scale/wrap long titles cleanly.
  const safeWidth = Math.round(width * 0.84);
  const safeTerm = term ?? '';
  const charCount = Math.max(1, Array.from(safeTerm).length);
  const fontSize = isVertical
    ? charCount > 12
      ? u(84)
      : u(104)
    : charCount > 14
      ? u(104)
      : u(132);

  return (
    <AbsoluteFill
      data-motion="outline-word-fill"
      data-lit={lit}
      style={{
        backgroundColor: overlay ? 'rgba(10, 28, 46, 0.88)' : brand.night,
        alignItems: 'center',
        justifyContent: 'center',
        pointerEvents: 'none',
        overflow: 'hidden',
        transform: `scale(${push.toFixed(4)})`,
      }}
    >
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        style={{position: 'absolute', inset: 0, width: '100%', height: '100%'}}
      >
        {lit > 0 && shock < 1 ? (
          <circle
            data-shock-ring="true"
            cx={cx}
            cy={cy}
            r={r + shock * u(160)}
            fill="none"
            stroke={brand.yellow}
            strokeOpacity={0.55 * (1 - shock)}
            strokeWidth={2 + 10 * (1 - shock)}
          />
        ) : null}
        <g
          transform={`translate(${cx} ${cy}) scale(${mix(2.4, 1, circleShrink).toFixed(4)})`}
          opacity={circleIn}
        >
          <g transform={`rotate(${rot.toFixed(2)})`}>
            <circle r={r} fill="none" stroke={hudColor} strokeWidth={2} strokeDasharray="22 18" />
            {[0, 90, 180, 270].map((a) => (
              <line
                key={a}
                x1={0}
                y1={-r - 22}
                x2={0}
                y2={-r + 10}
                stroke={hudColor}
                strokeWidth={2.5}
                strokeLinecap="round"
                transform={`rotate(${a})`}
              />
            ))}
          </g>
          <g transform={`rotate(${rotIn.toFixed(2)})`}>
            <circle r={r - 34} fill="none" stroke={hudColor} strokeWidth={1} opacity={0.35} />
            {Array.from({length: 72}, (_, i) => {
              const major = i % 6 === 0;
              return (
                <line
                  key={i}
                  x1={0}
                  y1={-(r - 34)}
                  x2={0}
                  y2={-(r - (major ? 58 : 44))}
                  stroke={hudColor}
                  strokeWidth={major ? 2 : 1.2}
                  opacity={major ? 0.7 : 0.32}
                  transform={`rotate(${i * 5})`}
                />
              );
            })}
          </g>
        </g>
        <line
          x1={0}
          y1={cy}
          x2={lineEnd * lineExt}
          y2={cy}
          stroke={hudColor}
          strokeWidth={2}
          strokeDasharray="14 12"
          opacity={lineExt}
        />
        <line
          x1={width}
          y1={cy}
          x2={width - lineEnd * lineExt}
          y2={cy}
          stroke={hudColor}
          strokeWidth={2}
          strokeDasharray="14 12"
          opacity={lineExt}
        />
      </svg>

      {/* Stacked flex column guarantees readouts, title, and definition never intersect */}
      <div
        style={{
          position: 'relative',
          width: safeWidth,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: isVertical ? u(40) : u(44),
          fontFamily: FONT_FAMILY,
        }}
      >
        {!overlay && (leftReadout || rightReadout) ? (
          <div
            data-readout-bar="true"
            style={{
              width: '100%',
              display: 'flex',
              flexDirection: isVertical ? 'column' : 'row',
              justifyContent: isVertical ? 'center' : 'space-between',
              alignItems: 'center',
              gap: isVertical ? u(16) : u(32),
              opacity: lineExt,
            }}
          >
            {leftReadout ? (
              <div
                style={{
                  padding: `${u(10)}px ${u(24)}px`,
                  borderRadius: u(16),
                  backgroundColor: 'rgba(18, 48, 74, 0.85)',
                  border: `${u(2)}px solid ${strokeColor}`,
                  fontSize: u(32),
                  fontWeight: 700,
                  color: brand.off_white,
                }}
              >
                {leftReadout}
              </div>
            ) : null}
            {rightReadout ? (
              <div
                style={{
                  padding: `${u(10)}px ${u(24)}px`,
                  borderRadius: u(16),
                  backgroundColor: 'rgba(18, 48, 74, 0.85)',
                  border: `${u(2)}px solid ${lit ? brand.yellow : strokeColor}`,
                  fontSize: u(32),
                  fontWeight: 800,
                  color: lit ? brand.yellow : brand.off_white,
                }}
              >
                {rightReadout}
              </div>
            ) : null}
          </div>
        ) : null}

        {safeTerm ? (
          <div
            data-title-box="true"
            style={{
              position: 'relative',
              width: safeWidth,
              fontSize,
              fontWeight: 800,
              lineHeight: 1.12,
              letterSpacing: '-0.02em',
              textAlign: 'center',
              overflowWrap: 'break-word',
              transform: `scale(${wordScale.toFixed(4)})`,
              opacity: born,
            }}
          >
            {/* Outline layer */}
            <span
              data-layer="outline"
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'center',
                color: 'transparent',
                WebkitTextStroke: `${u(2)}px ${strokeColor}`,
                opacity: 1 - lit,
              }}
            >
              {safeTerm}
            </span>
            {/* Solid hard-cut layer at frame 54 */}
            <span
              data-layer="solid"
              style={{
                position: 'absolute',
                inset: 0,
                display: 'block',
                width: '100%',
                textAlign: 'center',
                color: brand.off_white,
                opacity: lit,
                textShadow:
                  flash > 0.01
                    ? `0 0 ${(u(14) * flash).toFixed(1)}px ${brand.off_white}, 0 0 ${(u(60) * flash).toFixed(1)}px ${brand.yellow}`
                    : undefined,
              }}
            >
              {safeTerm}
            </span>
          </div>
        ) : null}

        {definition && !overlay ? (
          <div
            data-definition-box="true"
            style={{
              maxWidth: isVertical ? safeWidth : u(1080),
              fontSize: u(42),
              fontWeight: 600,
              color: brand.off_white,
              textAlign: 'center',
              lineHeight: 1.35,
              opacity: subIn,
              transform: `translateY(${((1 - subIn) * u(24)).toFixed(1)}px)`,
            }}
          >
            {definition}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
