// Ported from video-shotcraft data/gauge-readout-moves (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const GAUGE_READOUT_MOVES_DURATION = 140;

const R = 210;
const CX = 320;
const CY = 280;
const START_FRAME = 12;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const outCubic = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

const polar = (deg: number, r: number): [number, number] => [
  CX + r * Math.cos((deg * Math.PI) / 180),
  CY + r * Math.sin((deg * Math.PI) / 180),
];

const arcPath = (d0: number, d1: number, r: number): string => {
  const [x0, y0] = polar(135 + d0, r);
  const [x1, y1] = polar(135 + Math.max(d0 + 0.01, d1), r);
  const large = d1 - d0 > 180 ? 1 : 0;
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
};

// Needle sweep selftest: f12..24 (12f) full 270° sweep ease-out, f24..58 damped spring return
// with ~8° overshoot, f >= 58 locked constant for >=82f still hold.
export const needleAngleAt = (frame: number, targetDeg: number, start = START_FRAME): number => {
  if (frame <= start) return 0;
  if (frame <= start + 12) {
    return 270 * outCubic((frame - start) / 12);
  }
  if (frame >= start + 46) return targetDeg;
  const t = (frame - (start + 12)) / 34;
  const springK = 1 - Math.exp(-4.2 * t) * Math.cos(Math.PI * 1.35 * t);
  return mix(270, targetDeg, springK);
};

export type GaugeReadoutMovesProps = {
  value?: number | string;
  maxValue?: number;
  unit?: string;
  label?: string;
  sourceMarker?: string | null;
  variant?: 'needle-sweep-selftest' | 'tape-scroll-fixed-pointer';
};

export const GaugeReadoutMoves: React.FC<GaugeReadoutMovesProps> = ({
  value,
  maxValue = 10,
  unit,
  label,
  sourceMarker,
  variant = 'needle-sweep-selftest',
}) => {
  const frame = useCurrentFrame();
  const {width, isVertical, u} = useMotionScale();
  const parsed =
    typeof value === 'number'
      ? value
      : value !== undefined
        ? Number.parseFloat(String(value).replace(',', '.'))
        : Number.NaN;
  const numericValue = Number.isFinite(parsed) ? parsed : 0;
  const safeMax = maxValue > 0 ? maxValue : Math.max(10, numericValue * 1.25 || 10);
  const ratio = clamp01(numericValue / safeMax);
  const targetDeg = Math.round(ratio * 270);
  const angle = needleAngleAt(frame, targetDeg);
  const settleFrame = START_FRAME + 32;
  const settled = frame >= settleFrame;
  const pop = outCubic((frame - settleFrame) / 10);
  const hasValue = value !== undefined && value !== '';

  const cardWidth = isVertical ? Math.round(width * 0.86) : Math.round(width * 0.82);

  return (
    <AbsoluteFill
      data-motion="gauge-readout-moves"
      data-variant={variant}
      data-needle-angle={angle.toFixed(1)}
      style={{
        backgroundColor: brand.night,
        color: brand.off_white,
        fontFamily: FONT_FAMILY,
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: cardWidth,
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: isVertical ? 'column' : 'row',
          alignItems: 'center',
          justifyContent: 'center',
          gap: isVertical ? u(32) : u(56),
          padding: isVertical ? `${u(56)}px ${u(48)}px` : `${u(48)}px ${u(64)}px`,
          borderRadius: u(32),
          backgroundColor: brand.navy,
          border: `${u(3)}px solid ${brand.teal}`,
        }}
      >
        <svg
          width={isVertical ? u(580) : u(600)}
          height={isVertical ? u(435) : u(450)}
          viewBox="0 0 640 480"
          aria-label="Đồng hồ đo chỉ số"
          style={{flexShrink: 0}}
        >
          <path
            d={arcPath(0, 270, R)}
            fill="none"
            stroke="rgba(247, 244, 236, 0.2)"
            strokeWidth={18}
            strokeLinecap="round"
          />
          {angle > 0.5 ? (
            <path
              d={arcPath(0, Math.min(270, Math.max(1, angle)), R)}
              fill="none"
              stroke={angle >= 210 ? brand.yellow : brand.teal}
              strokeWidth={18}
              strokeLinecap="round"
            />
          ) : null}
          {Array.from({length: 31}, (_, k) => {
            const dd = k * 9;
            const major = k % 3 === 0;
            const [x0, y0] = polar(135 + dd, R - 16);
            const [x1, y1] = polar(135 + dd, major ? R - 38 : R - 26);
            return (
              <line
                key={k}
                x1={x0}
                y1={y0}
                x2={x1}
                y2={y1}
                stroke={dd >= 216 ? brand.yellow : brand.off_white}
                strokeWidth={major ? 3 : 1.5}
                opacity={angle >= dd ? 0.95 : 0.3}
              />
            );
          })}
          <g transform={`translate(${CX} ${CY}) rotate(${(135 + angle).toFixed(2)})`}>
            <polygon points="-18,-6 168,0 -18,6" fill={brand.yellow} />
            <circle cx={0} cy={0} r={14} fill={brand.off_white} />
          </g>
        </svg>

        <div
          style={{
            flex: 1,
            width: isVertical ? '100%' : undefined,
            textAlign: isVertical ? 'center' : 'left',
          }}
        >
          {sourceMarker ? (
            <div style={{fontSize: u(34), fontWeight: 700, color: brand.teal}}>
              {sourceMarker}
            </div>
          ) : null}
          {hasValue || unit ? (
            <div
              data-gauge-value={hasValue ? String(value) : undefined}
              style={{
                fontSize: u(128),
                fontWeight: 800,
                lineHeight: 1.05,
                marginTop: sourceMarker ? u(16) : 0,
                color: brand.yellow,
                opacity: settled ? Math.max(0.35, pop) : 0.65,
                transform: `scale(${settled ? (0.9 + 0.1 * pop).toFixed(3) : '0.92'})`,
                transformOrigin: isVertical ? '50% 50%' : '0 50%',
              }}
            >
              {hasValue ? String(value) : null}
              {hasValue && unit ? ' ' : null}
              {unit ? (
                <span style={{fontSize: u(52), fontWeight: 700, color: brand.off_white}}>
                  {unit}
                </span>
              ) : null}
            </div>
          ) : null}
          {label ? (
            <div style={{fontSize: u(44), fontWeight: 700, marginTop: u(18), lineHeight: 1.25}}>
              {label}
            </div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
