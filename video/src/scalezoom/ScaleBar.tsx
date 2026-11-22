import React from 'react';
import {
  ENTITY_COLORS,
  surfaceCardBackgroundHex,
  surfaceLabelTextHex,
  type ScaleSurface,
} from '../anatomy/entityColors';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {hexToRgba} from '../style/pyhStyle';
import {SCALE_LEVELS, SCALE_LEVEL_MAP, type ScaleLevel} from './levels';

export type ScaleBarProps = {
  level: ScaleLevel;
  previousLevel: ScaleLevel;
  transitionProgress: number;
  surface: ScaleSurface;
  isVertical: boolean;
};

/**
 * Scale ladder + physical scale readout showing current zoom tier and transition step.
 * Uses only brand / medical-entity color tokens with >= 4.5:1 text contrast on both surfaces.
 */
export const ScaleBar: React.FC<ScaleBarProps> = ({
  level,
  previousLevel,
  transitionProgress,
  surface,
  isVertical,
}) => {
  const currentMeta = SCALE_LEVEL_MAP[level];
  const prevMeta = SCALE_LEVEL_MAP[previousLevel];
  const ink = surfaceLabelTextHex(surface);
  const cardBg = surfaceCardBackgroundHex(surface);
  const borderColor = surface === 'night' ? hexToRgba(brand.off_white, 0.28) : hexToRgba(brand.navy, 0.22);
  const activeAccent = ENTITY_COLORS.blood_flow.hex; // teal
  const transitionAccent = ENTITY_COLORS.warning_threshold.hex; // yellow
  const isTransitioning = previousLevel !== level && transitionProgress < 1;

  const stepLabel = isTransitioning
    ? `${prevMeta.labelVi} → ${currentMeta.labelVi}`
    : currentMeta.labelVi;

  return (
    <div
      data-scalezoom-bar="true"
      data-scale-level={level}
      data-scale-step={stepLabel}
      style={{
        position: 'absolute',
        top: isVertical ? 36 : 32,
        right: isVertical ? 36 : 44,
        left: isVertical ? 36 : undefined,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        padding: isVertical ? '12px 18px' : '12px 20px',
        borderRadius: 14,
        backgroundColor: hexToRgba(cardBg, 0.94),
        border: `2px solid ${borderColor}`,
        boxShadow: surface === 'night'
          ? `0 6px 0 ${hexToRgba(brand.night, 0.7)}`
          : `0 6px 0 ${hexToRgba(brand.navy, 0.14)}`,
        fontFamily: FONT_FAMILY,
        color: ink,
        pointerEvents: 'none',
        zIndex: 6,
      }}
    >
      <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16}}>
        <span style={{fontSize: isVertical ? 20 : 18, fontWeight: 800, letterSpacing: 0.2}}>
          {stepLabel}
        </span>
        <span
          data-scale-readout={currentMeta.scaleText}
          style={{
            fontSize: isVertical ? 18 : 16,
            fontWeight: 800,
            color: surface === 'night' ? brand.yellow : brand.navy,
          }}
        >
          {currentMeta.scaleText}
        </span>
      </div>

      {/* 4-tier scale ruler */}
      <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
        {SCALE_LEVELS.map((tier) => {
          const isCurrent = tier.id === level;
          const isPassed = tier.order < currentMeta.order;
          const pillBg = isCurrent
            ? activeAccent
            : isPassed
              ? hexToRgba(activeAccent, 0.35)
              : hexToRgba(ink, 0.14);
          return (
            <div
              key={tier.id}
              data-scale-tier={tier.id}
              data-scale-active={isCurrent ? 'true' : 'false'}
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 4,
              }}
            >
              <div
                style={{
                  width: '100%',
                  height: isCurrent ? 8 : 5,
                  borderRadius: 4,
                  backgroundColor: isCurrent && isTransitioning ? transitionAccent : pillBg,
                }}
              />
              <span
                style={{
                  fontSize: isVertical ? 14 : 13,
                  fontWeight: isCurrent ? 800 : 600,
                  opacity: isCurrent ? 1 : 0.72,
                  whiteSpace: 'nowrap',
                }}
              >
                {tier.labelVi}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
