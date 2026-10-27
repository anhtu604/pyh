// Ported from video-shotcraft effects/scan-bracket-sweep (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const SCAN_BRACKET_SWEEP_DURATION = 150;

const DH = 580;
const PASSES = 5;
const TAIL = 82;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const inOutSine = (x: number): number => 0.5 - Math.cos(Math.PI * clamp01(x)) / 2;
const outCubic = (x: number): number => 1 - Math.pow(1 - clamp01(x), 3);

// 5 passes across t in [0.17, 0.95], inOutSine per pass with 12% pause at turnaround.
export const scanPositionAt = (t: number): {y: number; dir: 1 | -1} => {
  const sp = clamp01((t - 0.17) / (0.95 - 0.17));
  const raw = sp * PASSES;
  const pi = Math.min(PASSES - 1, Math.floor(raw));
  const local = clamp01((raw - pi) / 0.88);
  const dir: 1 | -1 = pi % 2 === 0 ? 1 : -1;
  const prog = inOutSine(local);
  return {y: dir > 0 ? prog * DH : DH - prog * DH, dir};
};

export type ScanBracketSweepProps = {
  title?: string;
  emphasisText?: string;
  rows?: readonly [string, string, string][];
  overlay?: boolean;
};

export const ScanBracketSweep: React.FC<ScanBracketSweepProps> = ({
  title,
  emphasisText,
  rows,
  overlay = false,
}) => {
  const frame = useCurrentFrame();
  const {width, isVertical, u} = useMotionScale();
  const t = clamp01(frame / (SCAN_BRACKET_SWEEP_DURATION - 1));
  const dt = 1 / (SCAN_BRACKET_SWEEP_DURATION - 1);

  const dp = outCubic(t / 0.11);
  const docScale = 0.86 + 0.14 * dp;
  const docOpacity = clamp01(dp * 3);

  const docW = isVertical ? Math.round(width * 0.86) : Math.round(width * 0.82);
  const docH = isVertical ? u(1140) : u(680);
  const scaleY = docH / DH;

  const {y: rawY, dir} = scanPositionAt(t);
  const y = rawY * scaleY;
  const speed = Math.abs(scanPositionAt(t + dt / 2).y - scanPositionAt(t - dt / 2).y) * scaleY;
  const peakSpeed =
    (docH * Math.PI) / 2 / (((0.78 * SCAN_BRACKET_SWEEP_DURATION) / PASSES) * 0.88);
  const tailLen = TAIL * scaleY * Math.pow(clamp01(speed / peakSpeed), 0.75);
  const beamOpacity =
    clamp01((t - 0.16) / (0.2 - 0.16)) * (1 - clamp01((t - 0.93) / (0.99 - 0.93)));

  const corners = [
    {left: -u(14), top: -u(14), d: 'M2 34V2h32', dx: 1, dy: 1},
    {left: docW + u(14) - u(36), top: -u(14), d: 'M2 2h32v32', dx: -1, dy: 1},
    {left: docW + u(14) - u(36), top: docH + u(14) - u(36), d: 'M34 2v32H2', dx: -1, dy: -1},
    {left: -u(14), top: docH + u(14) - u(36), d: 'M34 34H2V2', dx: 1, dy: -1},
  ];

  const safeRows = rows ?? [];
  // In vertical mode, stack each data row vertically so there are no cramped side-by-side columns.
  const displayRows = isVertical && safeRows.length > 1 ? safeRows.slice(1) : safeRows;

  return (
    <AbsoluteFill
      data-motion="scan-bracket-sweep"
      data-scan-dir={dir}
      data-scan-y={rawY.toFixed(1)}
      style={{
        backgroundColor: overlay ? 'transparent' : brand.off_white,
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: FONT_FAMILY,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'relative',
          width: docW,
          height: docH,
          opacity: docOpacity,
          transform: `scale(${docScale.toFixed(4)})`,
        }}
      >
        {!overlay ? (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: u(24),
              backgroundColor: '#FFFFFF',
              border: `${u(3)}px solid ${brand.navy}`,
              padding: isVertical ? `${u(44)}px ${u(44)}px` : `${u(38)}px ${u(48)}px`,
              boxSizing: 'border-box',
              color: brand.navy,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {title ? (
              <div style={{fontSize: u(48), fontWeight: 800, lineHeight: 1.15}}>{title}</div>
            ) : null}
            {emphasisText ? (
              <div
                style={{
                  fontSize: u(36),
                  fontWeight: 700,
                  color: brand.teal,
                  marginTop: title ? u(12) : 0,
                  lineHeight: 1.25,
                }}
              >
                {emphasisText}
              </div>
            ) : null}
            {displayRows.length > 0 ? (
              <div
                style={{
                  marginTop: u(32),
                  display: 'flex',
                  flexDirection: 'column',
                  gap: isVertical ? u(24) : u(18),
                  flex: 1,
                  justifyContent: 'center',
                }}
              >
                {displayRows.map((r, idx) => {
                  const rowCenterY =
                    isVertical
                      ? u(240) + idx * u(280)
                      : u(190) + idx * u(105);
                  const rowLit = beamOpacity * Math.exp(-Math.pow((y - rowCenterY) / u(54), 2));
                  if (isVertical) {
                    return (
                      <div
                        key={idx}
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          gap: u(10),
                          padding: `${u(26)}px ${u(30)}px`,
                          borderRadius: u(18),
                          backgroundColor:
                            rowLit > 0.05
                              ? `rgba(24, 166, 166, ${(0.2 * rowLit).toFixed(3)})`
                              : 'rgba(18, 48, 74, 0.05)',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            gap: u(16),
                          }}
                        >
                          <span style={{fontSize: u(34), fontWeight: 800, color: brand.navy}}>
                            {r[0]}
                          </span>
                          <span style={{fontSize: u(34), fontWeight: 800, color: brand.teal}}>
                            {r[1]}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: u(40),
                            fontWeight: 600,
                            color: brand.charcoal,
                            lineHeight: 1.3,
                          }}
                        >
                          {r[2]}
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: `${u(18)}px ${u(24)}px`,
                        borderRadius: u(14),
                        backgroundColor:
                          rowLit > 0.05
                            ? `rgba(24, 166, 166, ${(0.18 * rowLit).toFixed(3)})`
                            : 'rgba(18, 48, 74, 0.04)',
                        fontSize: idx === 0 ? u(32) : u(40),
                        fontWeight: idx === 0 ? 800 : 600,
                      }}
                    >
                      <span style={{flex: 1}}>{r[0]}</span>
                      <span style={{flex: 1, color: brand.teal}}>{r[1]}</span>
                      <span style={{flex: 1.4, textAlign: 'right'}}>{r[2]}</span>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </div>
        ) : emphasisText ? (
          <div
            style={{
              position: 'absolute',
              left: u(32),
              top: u(24),
              padding: `${u(12)}px ${u(24)}px`,
              borderRadius: u(14),
              backgroundColor: brand.navy,
              color: brand.yellow,
              fontSize: u(34),
              fontWeight: 800,
            }}
          >
            {emphasisText}
          </div>
        ) : null}

        {/* Clipped scan beam inside rounded document bounds */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: u(24),
            overflow: 'hidden',
            opacity: beamOpacity,
          }}
        >
          <div
            data-scan-beam="true"
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: y,
              height: u(4),
              backgroundColor: brand.teal,
              boxShadow: `0 0 ${u(14)}px ${brand.teal}`,
            }}
          />
          <div
            data-scan-tail="true"
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: dir > 0 ? y - tailLen : y,
              height: tailLen,
              background:
                dir > 0
                  ? 'linear-gradient(180deg, rgba(24,166,166,0) 0%, rgba(24,166,166,0.26) 100%)'
                  : 'linear-gradient(180deg, rgba(24,166,166,0.26) 0%, rgba(24,166,166,0) 100%)',
            }}
          />
        </div>

        {/* 4 L-shaped viewfinder brackets with staggered overshoot */}
        {corners.map((c, i) => {
          const cp = outCubic((t - (0.04 + i * 0.022)) / 0.055);
          const offset = (1 - cp) * u(14);
          return (
            <svg
              key={i}
              data-scan-bracket={i}
              width={u(36)}
              height={u(36)}
              viewBox="0 0 36 36"
              style={{
                position: 'absolute',
                left: c.left - c.dx * offset,
                top: c.top - c.dy * offset,
                opacity: clamp01(cp * 2),
              }}
            >
              <path
                d={c.d}
                fill="none"
                stroke={brand.teal}
                strokeWidth={4}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
