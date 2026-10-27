// Ported from video-shotcraft effects/scanline-annotate-focus (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const SCANLINE_ANNOTATE_FOCUS_DURATION = 150;

const SCAN0 = 6;
const SCAN1 = 80;
const Y0 = -20;
const Y1 = 860;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));

// Strictly linear scanline (zero easing): machine gaze moving top to bottom.
export const scanlineYAt = (frame: number): number =>
  Y0 + (Y1 - Y0) * clamp01((frame - SCAN0) / (SCAN1 - SCAN0));

const frameAtY = (y: number): number => SCAN0 + ((y - Y0) / (Y1 - Y0)) * (SCAN1 - SCAN0);

export type AnnotateTarget = {
  key: string;
  x: number;
  y: number;
  w: number;
  h: number;
  head: string;
  detail: string;
};

export type ScanlineAnnotateFocusProps = {
  emphasisText?: string;
  targets?: readonly AnnotateTarget[];
  overlay?: boolean;
};

export const ScanlineAnnotateFocus: React.FC<ScanlineAnnotateFocusProps> = ({
  emphasisText,
  targets,
  overlay = false,
}) => {
  const frame = useCurrentFrame();
  const {width, isVertical, u} = useMotionScale();
  const rawY = scanlineYAt(frame);

  const panelW = isVertical ? Math.round(width * 0.86) : width - u(240);
  const panelH = isVertical ? u(1160) : u(820);
  const scanY = (clamp01((rawY - Y0) / (Y1 - Y0)) * (panelH + u(40))) - u(20);

  const activeTargets = overlay ? [] : (targets ?? []);
  // In vertical mode, stack all annotation boxes in a single vertical column so none get clipped on the right.
  const layoutTargets = activeTargets.map((t, idx) => {
    if (!isVertical) {
      return {
        ...t,
        x: u(t.x),
        y: u(t.y),
        w: u(t.w),
        h: u(t.h),
        triggerY: t.y + t.h,
      };
    }
    const boxX = u(44);
    const boxW = panelW - u(88);
    const boxH = u(188);
    const boxY = u(76) + idx * u(268);
    // Keep trigger timing within Y0..Y1 so all 4 boxes lock before frame 64.
    const triggerY = 180 + idx * 170;
    return {
      ...t,
      x: boxX,
      y: boxY,
      w: boxW,
      h: boxH,
      triggerY,
    };
  });

  // Compute trigger frames when scanline crosses each target's triggerY, clamped >=4f apart.
  const scheduled = (() => {
    const items = layoutTargets.map((t) => ({...t, ft: frameAtY(t.triggerY)}));
    let prev = -99;
    for (const item of [...items].sort((a, b) => a.triggerY - b.triggerY)) {
      item.ft = Math.max(item.ft, prev + 4);
      prev = item.ft;
    }
    return items;
  })();

  const firedCount = scheduled.filter((t) => frame >= t.ft).length;
  const scanActive = frame >= SCAN0 && frame <= SCAN1 + 8;

  return (
    <AbsoluteFill
      data-motion="scanline-annotate-focus"
      data-fired-count={firedCount}
      style={{
        backgroundColor: overlay ? 'transparent' : brand.off_white,
        fontFamily: FONT_FAMILY,
        color: brand.navy,
        alignItems: 'center',
        justifyContent: 'center',
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: panelW,
          display: 'flex',
          flexDirection: 'column',
          gap: u(24),
        }}
      >
        {emphasisText ? (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: `${u(16)}px ${u(28)}px`,
              borderRadius: u(16),
              backgroundColor: brand.navy,
              color: brand.off_white,
              fontSize: u(32),
              fontWeight: 800,
            }}
          >
            <span>{emphasisText}</span>
          </div>
        ) : null}

        <div
          style={{
            position: 'relative',
            width: panelW,
            height: panelH,
            borderRadius: u(24),
            overflow: 'hidden',
            border: overlay ? `${u(2)}px solid ${brand.teal}` : `${u(3)}px solid ${brand.navy}`,
            backgroundColor: overlay ? 'rgba(247, 244, 236, 0.12)' : '#FFFFFF',
          }}
        >
          {scheduled.map((t) => {
            const fired = frame >= t.ft;
            const elapsed = Math.max(0, (frame - t.ft) / 14);
            const springK = fired
              ? 1 - Math.exp(-4.2 * elapsed) * Math.cos(Math.PI * 1.3 * elapsed)
              : 0;
            const pad = (1 - springK) * u(56);
            const tagText = `${t.head} · ${t.detail}`;
            const typedChars = fired
              ? Math.min(tagText.length, Math.max(1, Math.floor((frame - (t.ft + 5)) * 2.2)))
              : 0;

            return (
              <div key={t.key}>
                {!overlay ? (
                  <div
                    style={{
                      position: 'absolute',
                      left: t.x,
                      top: t.y,
                      width: t.w,
                      height: t.h,
                      borderRadius: u(18),
                      backgroundColor: 'rgba(18, 48, 74, 0.06)',
                      padding: `${u(24)}px ${u(28)}px`,
                      boxSizing: 'border-box',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'center',
                    }}
                  >
                    <div style={{fontSize: u(34), fontWeight: 800, color: brand.navy}}>
                      {t.head}
                    </div>
                    <div
                      style={{
                        fontSize: u(40),
                        fontWeight: 600,
                        color: brand.charcoal,
                        marginTop: u(10),
                        lineHeight: 1.25,
                      }}
                    >
                      {t.detail}
                    </div>
                  </div>
                ) : null}

                {fired ? (
                  <div
                    data-annotated-target={t.key}
                    style={{
                      position: 'absolute',
                      left: t.x - pad,
                      top: t.y - pad,
                      width: t.w + pad * 2,
                      height: t.h + pad * 2,
                      border: `${u(3)}px solid ${brand.teal}`,
                      borderRadius: u(18),
                      boxSizing: 'border-box',
                    }}
                  >
                    {frame >= t.ft + 5 ? (
                      <div
                        style={{
                          position: 'absolute',
                          left: 0,
                          top: -u(52),
                          maxWidth: t.w,
                          padding: `${u(6)}px ${u(16)}px`,
                          borderRadius: u(10),
                          backgroundColor: brand.teal,
                          color: brand.off_white,
                          fontSize: u(30),
                          fontWeight: 800,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {tagText.slice(0, typedChars)}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}

          {/* Linear scanline */}
          {scanActive ? (
            <div
              data-scanline-bar="true"
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: scanY,
                height: u(4),
                backgroundColor: brand.teal,
                boxShadow: `0 -${u(24)}px ${u(48)}px rgba(24, 166, 166, 0.25)`,
              }}
            />
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
