// Ported from video-shotcraft data/before-after-slider-scrub (Apache-2.0)
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useMotionScale} from './scale';

export const BEFORE_AFTER_SLIDER_SCRUB_DURATION = 150;

const PRE = 10;
const T0 = 14;
const FLING = 26;
const BOUNCE = 38;
const HOLD = 56;
const SCRUB = 104;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const outCubic = (t: number): number => 1 - Math.pow(1 - clamp01(t), 3);
const smooth = (t: number): number => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

// Fast fling 12f (6.5% -> 76%) vs slow scrub 48f (70% -> 40%) = 4:1..5:1 speed ratio,
// then >=46f still hold from f104..150.
export const sliderPercentAt = (f: number): number => {
  if (f < T0) return mix(8, 6.5, smooth((f - PRE) / (T0 - PRE)));
  if (f < FLING) return mix(6.5, 76, outCubic((f - T0) / (FLING - T0)));
  if (f < BOUNCE) return mix(76, 70, smooth((f - FLING) / (BOUNCE - FLING)));
  if (f < HOLD) return 70;
  return mix(70, 40, smooth((f - HOLD) / (SCRUB - HOLD)));
};

export type BeforeAfterSliderScrubProps = {
  beforeLabel?: string;
  afterLabel?: string;
  beforeTitle?: string;
  afterTitle?: string;
  beforeValue?: string;
  afterValue?: string;
};

export const BeforeAfterSliderScrub: React.FC<BeforeAfterSliderScrubProps> = ({
  beforeLabel,
  afterLabel,
  beforeTitle,
  afterTitle,
  beforeValue,
  afterValue,
}) => {
  const frame = useCurrentFrame();
  const {width, height, isVertical, u} = useMotionScale();
  const pct = sliderPercentAt(frame);
  const span = isVertical ? height : width;
  const pos = (pct / 100) * span;
  const vel = ((sliderPercentAt(frame + 0.5) - sliderPercentAt(frame - 0.5)) / 100) * span;
  const squish = 1 + Math.min(Math.abs(vel) / 110, 1) * 0.18;

  if (isVertical) {
    // Vertical format: top/bottom split with a horizontal scrub bar.
    const marginX = Math.round(width * 0.08);
    const contentWidth = width - marginX * 2;
    return (
      <AbsoluteFill
        data-motion="before-after-slider-scrub"
        data-slider-orientation="horizontal"
        data-slider-percent={pct.toFixed(2)}
        style={{
          backgroundColor: brand.off_white,
          fontFamily: FONT_FAMILY,
          overflow: 'hidden',
        }}
      >
        {/* BEFORE layer on bottom below horizontal slider */}
        <AbsoluteFill
          data-layer="before"
          style={{
            backgroundColor: '#E5E2D9',
            color: brand.charcoal,
            clipPath: `inset(${pos.toFixed(1)}px 0 0 0)`,
          }}
        >
          <div
            style={{
              position: 'absolute',
              left: marginX,
              width: contentWidth,
              bottom: u(160),
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
            }}
          >
            {beforeLabel ? (
              <div
                style={{
                  padding: `${u(10)}px ${u(24)}px`,
                  borderRadius: u(20),
                  backgroundColor: '#FFFFFF',
                  fontSize: u(32),
                  fontWeight: 800,
                  color: brand.charcoal,
                }}
              >
                {beforeLabel}
              </div>
            ) : null}
            {beforeValue ? (
              <div
                style={{
                  fontSize: u(124),
                  fontWeight: 800,
                  color: brand.navy,
                  lineHeight: 1.05,
                  marginTop: beforeLabel ? u(24) : 0,
                }}
              >
                {beforeValue}
              </div>
            ) : null}
            {beforeTitle ? (
              <div style={{fontSize: u(46), fontWeight: 700, marginTop: u(16), lineHeight: 1.25}}>
                {beforeTitle}
              </div>
            ) : null}
          </div>
        </AbsoluteFill>

        {/* AFTER layer on top above horizontal slider */}
        <AbsoluteFill
          data-layer="after"
          style={{
            backgroundColor: brand.navy,
            color: brand.off_white,
            clipPath: `inset(0 0 ${(height - pos).toFixed(1)}px 0)`,
          }}
        >
          <div
            style={{
              position: 'absolute',
              left: marginX,
              width: contentWidth,
              top: u(160),
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
            }}
          >
            {afterLabel ? (
              <div
                style={{
                  padding: `${u(10)}px ${u(24)}px`,
                  borderRadius: u(20),
                  backgroundColor: brand.teal,
                  fontSize: u(32),
                  fontWeight: 800,
                  color: brand.off_white,
                }}
              >
                {afterLabel}
              </div>
            ) : null}
            {afterValue ? (
              <div
                style={{
                  fontSize: u(124),
                  fontWeight: 800,
                  color: brand.yellow,
                  lineHeight: 1.05,
                  marginTop: afterLabel ? u(24) : 0,
                }}
              >
                {afterValue}
              </div>
            ) : null}
            {afterTitle ? (
              <div style={{fontSize: u(46), fontWeight: 700, marginTop: u(16), lineHeight: 1.25}}>
                {afterTitle}
              </div>
            ) : null}
          </div>
        </AbsoluteFill>

        {/* Horizontal divider line and handle */}
        <div
          data-slider-handle="true"
          style={{
            position: 'absolute',
            top: pos,
            left: 0,
            right: 0,
            height: u(6),
            backgroundColor: brand.yellow,
            transform: 'translateY(-50%)',
          }}
        >
          <div
            style={{
              position: 'absolute',
              left: '50%',
              top: '50%',
              width: u(76),
              height: u(76),
              borderRadius: u(38),
              backgroundColor: brand.yellow,
              border: `${u(4)}px solid ${brand.navy}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 800,
              fontSize: u(34),
              color: brand.navy,
              transform: `translate(-50%, -50%) scaleY(${squish.toFixed(3)})`,
            }}
          >
            ↕
          </div>
        </div>
      </AbsoluteFill>
    );
  }

  // Horizontal format (1920x1080): left/right split with complementary clipPaths so text never collides.
  return (
    <AbsoluteFill
      data-motion="before-after-slider-scrub"
      data-slider-orientation="vertical"
      data-slider-percent={pct.toFixed(2)}
      style={{
        backgroundColor: brand.off_white,
        fontFamily: FONT_FAMILY,
        overflow: 'hidden',
      }}
    >
      {/* BEFORE layer clipped to right of slider */}
      <AbsoluteFill
        data-layer="before"
        style={{
          backgroundColor: '#E5E2D9',
          color: brand.charcoal,
          clipPath: `inset(0 0 0 ${pos.toFixed(1)}px)`,
        }}
      >
        {beforeLabel ? (
          <div
            style={{
              position: 'absolute',
              right: u(96),
              top: u(64),
              padding: `${u(10)}px ${u(24)}px`,
              borderRadius: u(20),
              backgroundColor: '#FFFFFF',
              fontSize: u(32),
              fontWeight: 800,
              color: brand.charcoal,
            }}
          >
            {beforeLabel}
          </div>
        ) : null}
        <div
          style={{
            position: 'absolute',
            right: u(96),
            top: u(280),
            maxWidth: u(560),
            textAlign: 'right',
          }}
        >
          {beforeValue ? (
            <div style={{fontSize: u(120), fontWeight: 800, color: brand.navy, lineHeight: 1.05}}>
              {beforeValue}
            </div>
          ) : null}
          {beforeTitle ? (
            <div style={{fontSize: u(46), fontWeight: 700, marginTop: u(24), lineHeight: 1.25}}>
              {beforeTitle}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>

      {/* AFTER layer revealed on left of slider */}
      <AbsoluteFill
        data-layer="after"
        style={{
          backgroundColor: brand.navy,
          color: brand.off_white,
          clipPath: `inset(0 ${(width - pos).toFixed(1)}px 0 0)`,
        }}
      >
        {afterLabel ? (
          <div
            style={{
              position: 'absolute',
              left: u(96),
              top: u(64),
              padding: `${u(10)}px ${u(24)}px`,
              borderRadius: u(20),
              backgroundColor: brand.teal,
              fontSize: u(32),
              fontWeight: 800,
              color: brand.off_white,
            }}
          >
            {afterLabel}
          </div>
        ) : null}
        <div
          style={{
            position: 'absolute',
            left: u(96),
            top: u(280),
            maxWidth: u(960),
          }}
        >
          {afterValue ? (
            <div style={{fontSize: u(124), fontWeight: 800, color: brand.yellow, lineHeight: 1.05}}>
              {afterValue}
            </div>
          ) : null}
          {afterTitle ? (
            <div style={{fontSize: u(48), fontWeight: 700, marginTop: u(24), lineHeight: 1.25}}>
              {afterTitle}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>

      {/* Vertical divider line and velocity-squished handle */}
      <div
        data-slider-handle="true"
        style={{
          position: 'absolute',
          left: pos,
          top: 0,
          bottom: 0,
          width: u(4),
          backgroundColor: brand.yellow,
          transform: 'translateX(-50%)',
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            width: u(72),
            height: u(72),
            borderRadius: u(36),
            backgroundColor: brand.yellow,
            border: `${u(4)}px solid ${brand.navy}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 800,
            fontSize: u(34),
            color: brand.navy,
            transform: `translate(-50%, -50%) scaleX(${squish.toFixed(3)})`,
          }}
        >
          ↔
        </div>
      </div>
    </AbsoluteFill>
  );
};
