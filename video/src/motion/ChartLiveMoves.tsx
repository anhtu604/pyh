// Ported from video-shotcraft data/chart-live-moves (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const CHART_LIVE_MOVES_DURATION = 165;

const PW = 1520;
const PH = 440;
const HEAD = Math.round(PW * 0.86);
const SPEED = 8;
const FREEZE0 = 104;
const FREEZE1 = 118;
const OFFSET = 1400;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const outCubic = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);
const smooth = (t: number): number => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};

export const worldAtFrame = (f: number): number => {
  if (f <= FREEZE0) return OFFSET + f * SPEED;
  const brake = (SPEED * (FREEZE1 - FREEZE0)) / 3;
  return OFFSET + FREEZE0 * SPEED + brake * outCubic((f - FREEZE0) / (FREEZE1 - FREEZE0));
};

const S0 = OFFSET + 46 * SPEED;
const SW = 176;
const SC = S0 + SW * 0.5;
const gauss = (x: number, c: number, w: number): number => Math.exp(-Math.pow((x - c) / w, 2));
const bump = (x: number): number =>
  2.2 * gauss(x, SC, 26) + 0.45 * gauss(x, SC - 62, 18) + 0.6 * gauss(x, SC + 48, 20);
const wave = (x: number): number =>
  0.34 * Math.sin(x * 0.019) +
  0.27 * Math.sin(x * 0.047 + 1.7) +
  0.18 * Math.sin(x * 0.011 + 4.2);
const signal = (x: number): number => wave(x) * (1 + 0.6 * gauss(x, SC, SW * 0.45)) + bump(x);

export type ChartLiveMovesProps = {
  value?: number | string;
  unit?: string;
  label?: string;
  sourceMarker?: string | null;
  variant?: 'oscilloscope-stream' | 'axis-rescale-shock';
};

export const ChartLiveMoves: React.FC<ChartLiveMovesProps> = ({
  value,
  unit,
  label,
  sourceMarker,
  variant = 'oscilloscope-stream',
}) => {
  const frame = useCurrentFrame();
  const {width, isVertical, u} = useMotionScale();

  // f0..104 stream at 8px/f, f46..68 spike (2.2x amplitude), f104..118 out-cubic brake,
  // f118..165 >=47f still hold with 3% slow push toward the spike.
  const worldX = worldAtFrame(frame);
  const worldOf = (px: number): number => worldX - (HEAD - px);
  const yOf = (wx: number): number => PH - clamp01((0.35 + signal(wx) * 0.22)) * PH;

  const pts: Array<[number, number, number]> = [];
  for (let px = 0; px <= HEAD; px += 8) {
    const wx = worldOf(px);
    pts.push([px, yOf(wx), wx]);
  }
  if (pts[pts.length - 1]?.[0] !== HEAD) {
    pts.push([HEAD, yOf(worldX), worldX]);
  }
  const toD = (arr: Array<[number, number, number]>): string =>
    arr.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

  const lineD = toD(pts);
  const spikePts = pts.filter(([, , w]) => w >= S0 + 10 && w <= Math.min(worldX, S0 + SW - 10));
  const spikeD = spikePts.length > 1 ? toD(spikePts) : '';
  const inBurst = frame >= 46 && frame <= 72;
  const postHoldPush = 1 + 0.03 * smooth((frame - FREEZE1) / 47);

  const hasValue = value !== undefined && value !== '';

  const contentW = isVertical ? Math.round(width * 0.86) : width - u(192);
  const chartH = isVertical ? u(540) : u(440);

  return (
    <AbsoluteFill
      data-motion="chart-live-moves"
      data-variant={variant}
      data-paused={frame >= FREEZE1}
      style={{
        backgroundColor: brand.night,
        color: brand.off_white,
        fontFamily: FONT_FAMILY,
        alignItems: 'center',
        justifyContent: 'center',
        padding: isVertical ? `${u(80)}px ${u(64)}px` : `${u(72)}px ${u(96)}px`,
        boxSizing: 'border-box',
        overflow: 'hidden',
        transform: `scale(${postHoldPush.toFixed(4)})`,
      }}
    >
      <div style={{width: contentW, display: 'flex', flexDirection: 'column', gap: u(36)}}>
        <div
          style={{
            display: 'flex',
            flexDirection: isVertical ? 'column' : 'row',
            justifyContent: 'space-between',
            alignItems: isVertical ? 'flex-start' : 'flex-end',
            gap: isVertical ? u(24) : u(32),
          }}
        >
          <div>
            {sourceMarker ? (
              <div style={{fontSize: u(34), fontWeight: 700, color: brand.teal}}>
                {sourceMarker}
              </div>
            ) : null}
            {label ? (
              <div
                style={{
                  fontSize: u(48),
                  fontWeight: 800,
                  marginTop: sourceMarker ? u(10) : 0,
                  lineHeight: 1.2,
                }}
              >
                {label}
              </div>
            ) : null}
          </div>
          {hasValue || unit ? (
            <div style={{textAlign: isVertical ? 'left' : 'right'}}>
              <div
                data-readout="value"
                style={{
                  fontSize: u(128),
                  fontWeight: 800,
                  lineHeight: 1,
                  color: inBurst || frame >= 68 ? brand.yellow : brand.off_white,
                }}
              >
                {hasValue ? String(value) : null}
                {hasValue && unit ? ' ' : null}
                {unit ? (
                  <span style={{fontSize: u(52), fontWeight: 700, color: brand.teal}}>{unit}</span>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>

        <div
          style={{
            position: 'relative',
            width: contentW,
            height: chartH,
            border: `${u(3)}px solid ${brand.navy}`,
            borderRadius: u(24),
            backgroundColor: 'rgba(18, 48, 74, 0.55)',
            overflow: 'hidden',
          }}
        >
          <svg
            width="100%"
            height="100%"
            viewBox={`0 0 ${PW} ${PH}`}
            preserveAspectRatio="none"
          >
            {[0.25, 0.5, 0.75].map((ratio) => (
              <line
                key={ratio}
                x1={0}
                y1={PH * ratio}
                x2={PW}
                y2={PH * ratio}
                stroke={brand.navy}
                strokeDasharray="8 8"
                strokeWidth={2}
              />
            ))}
            <path d={lineD} fill="none" stroke={brand.teal} strokeWidth={5} />
            {spikeD ? (
              <path
                data-spike-trace="true"
                d={spikeD}
                fill="none"
                stroke={brand.yellow}
                strokeWidth={7}
              />
            ) : null}
            <line
              x1={HEAD}
              y1={0}
              x2={HEAD}
              y2={PH}
              stroke={brand.off_white}
              strokeOpacity={frame >= FREEZE1 ? 0.25 : 0.75}
              strokeWidth={2.5}
            />
            <circle
              cx={HEAD}
              cy={yOf(worldX)}
              r={10}
              fill={inBurst ? brand.yellow : brand.teal}
            />
          </svg>
          {frame >= 68 && hasValue ? (
            <div
              data-spike-badge="true"
              style={{
                position: 'absolute',
                right: u(28),
                top: u(24),
                backgroundColor: brand.yellow,
                color: brand.night,
                padding: `${u(10)}px ${u(22)}px`,
                borderRadius: u(14),
                fontSize: u(32),
                fontWeight: 800,
              }}
            >
              {String(value)}
              {unit ? ` ${unit}` : ''}
            </div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
