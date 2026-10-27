// Ported from video-shotcraft data/timeline-travel (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const TIMELINE_TRAVEL_DURATION = 160;

const TICK_GAP = 920;
const TRAVEL_START = 12;
const TRAVEL_END = 104;
const ZOOM_END = 114;

export type TimelineMilestone = {
  stage?: string;
  timeLabel?: string;
  title?: string;
  desc?: string;
};

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const inOutQuad = (t: number): number => {
  const x = clamp01(t);
  return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2;
};
const outCubic = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);

const travelProgressAt = (frame: number): number => {
  const t = clamp01((frame - TRAVEL_START) / (TRAVEL_END - TRAVEL_START));
  if (t <= 0.15) {
    return 0.055 * inOutQuad(t / 0.15);
  }
  if (t <= 0.88) {
    return 0.055 + (0.9 - 0.055) * inOutQuad((t - 0.15) / (0.88 - 0.15));
  }
  return 0.9 + 0.1 * inOutQuad((t - 0.88) / 0.12);
};

// 3-phase piecewise curve: [0, 0.15, 0.88, 1] -> [0, 0.055, 0.9, 1]
export const timelineCamXAt = (frame: number, tickCount = 4): number => {
  const total = Math.max(1, tickCount - 1) * TICK_GAP;
  return travelProgressAt(frame) * total;
};

const popFrameFor = (tickIndex: number, tickCount: number): number => {
  const targetX = tickIndex * TICK_GAP;
  for (let f = TRAVEL_START; f <= TRAVEL_END; f++) {
    if (timelineCamXAt(f, tickCount) >= targetX) return f;
  }
  return TRAVEL_END;
};

export type TimelineTravelProps = {
  milestones?: readonly TimelineMilestone[];
};

export const TimelineTravel: React.FC<TimelineTravelProps> = ({
  milestones = [],
}) => {
  const frame = useCurrentFrame();
  const {width, height, isVertical, u} = useMotionScale();
  const count = milestones.length;
  const rawCamX = timelineCamXAt(frame, count);
  const segProg = travelProgressAt(frame);

  const centerX = Math.round(width * 0.5);
  const axisY = isVertical ? Math.round(height * 0.62) : Math.round(height * 0.68);
  const cardWidth = isVertical ? Math.round(width * 0.82) : u(760);
  const tickGap = isVertical ? u(980) : u(920);

  // When a single milestone is supplied, glide smoothly into the centered milestone instead of panning past it.
  const camX =
    count <= 1 ? -(1 - segProg) * u(40) : segProg * (count - 1) * tickGap;
  const maxZoomBoost = isVertical ? 0.06 : 0.16;
  const zoom = 1 + maxZoomBoost * outCubic((frame - TRAVEL_END) / (ZOOM_END - TRAVEL_END));

  return (
    <AbsoluteFill
      data-motion="timeline-travel"
      data-cam-x={rawCamX.toFixed(1)}
      data-zoom={zoom.toFixed(3)}
      style={{
        backgroundColor: brand.off_white,
        fontFamily: FONT_FAMILY,
        color: brand.navy,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          transformOrigin: `${centerX}px ${axisY - u(120)}px`,
          transform: `scale(${zoom.toFixed(4)}) translateX(${(-camX).toFixed(1)}px)`,
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: centerX - u(600),
            top: axisY,
            width: Math.max(1, count - 1) * tickGap + u(1400),
            height: u(5),
            backgroundColor: brand.navy,
          }}
        />
        {milestones.map((m, idx) => {
          const x = centerX + idx * tickGap;
          // Pop 6f before camera reaches the tick with spring overshoot.
          const popStart = idx === 0 ? 0 : popFrameFor(idx, count) - 6;
          const elapsed = Math.max(0, (frame - popStart) / 18);
          const springScale =
            frame < popStart
              ? 0
              : 1 - Math.exp(-4.5 * elapsed) * Math.cos(Math.PI * 1.4 * elapsed);
          const isFinal = idx === count - 1;
          return (
            <div key={m.stage || m.title || m.timeLabel || idx} style={{position: 'absolute', left: x, top: axisY}}>
              <div
                style={{
                  position: 'absolute',
                  left: -u(14),
                  top: -u(14),
                  width: u(28),
                  height: u(28),
                  borderRadius: u(14),
                  backgroundColor: isFinal ? brand.yellow : brand.teal,
                  border: `${u(4)}px solid ${brand.navy}`,
                }}
              />
              <div
                data-milestone-card={idx}
                style={{
                  position: 'absolute',
                  left: -Math.round(cardWidth / 2),
                  bottom: u(44),
                  width: cardWidth,
                  padding: `${u(38)}px ${u(42)}px`,
                  boxSizing: 'border-box',
                  borderRadius: u(28),
                  backgroundColor: isFinal ? brand.navy : '#FFFFFF',
                  color: isFinal ? brand.off_white : brand.navy,
                  border: `${u(4)}px solid ${isFinal ? brand.yellow : brand.teal}`,
                  transformOrigin: '50% 100%',
                  transform: `scaleY(${Math.max(0, springScale).toFixed(3)})`,
                  opacity: clamp01((frame - popStart) / 4),
                }}
              >
                {m.stage || m.timeLabel ? (
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: u(34),
                      fontWeight: 800,
                      color: isFinal ? brand.yellow : brand.teal,
                    }}
                  >
                    {m.stage ? <span>{m.stage}</span> : null}
                    {m.timeLabel ? <span>{m.timeLabel}</span> : null}
                  </div>
                ) : null}
                {m.title ? (
                  <div
                    style={{
                      fontSize: u(48),
                      fontWeight: 800,
                      marginTop: m.stage || m.timeLabel ? u(16) : 0,
                      lineHeight: 1.2,
                    }}
                  >
                    {m.title}
                  </div>
                ) : null}
                {m.desc ? (
                  <div
                    style={{
                      fontSize: u(40),
                      fontWeight: 600,
                      marginTop: u(14),
                      lineHeight: 1.35,
                    }}
                  >
                    {m.desc}
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
