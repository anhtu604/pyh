import React from 'react';
import {Img, staticFile, useCurrentFrame} from 'remotion';
import {FONT_FAMILY} from '../../fonts';
import {boxesIntersect, SAFE_GAP, type Box} from '../../layout';
import type {MascotPose} from '../../style/pyhStyle';
import type {ResolvedR5Shot} from '../../types';
import {
  isPortraitLayout,
  R5_MAX_TAKEAWAY_WORDS,
  R5_PALETTE,
  r5EaseOut,
  r5PortraitContentBottom,
  resolveR5Layout,
  type R5LayoutInput,
  type R5RevisionAsset,
} from './ScaleChain';

export {R5_MAX_TAKEAWAY_WORDS};

export const R5_MAX_MASCOT_AREA_RATIO = 0.25;

export type TakeawayMascotConfig = {
  assetPath: string;
  pose: MascotPose;
  side?: 'left' | 'right';
};

export type TakeawayCardProps = {
  shot: ResolvedR5Shot;
  layout: R5LayoutInput;
  assets: readonly R5RevisionAsset[];
  text: string;
  claimIds: readonly string[];
  tag?: string;
  accent?: string;
  mascot?: TakeawayMascotConfig | null;
  /** Optional close-up anatomy region that neither the takeaway card nor the mascot may overlap. */
  anatomyExclusionBox?: Box | null;
  frame?: number;
};

export type TakeawayGeometry = {
  cardBox: Box;
  placement: 'bottom' | 'top';
  mascotBox: Box | null;
  mascotAreaRatio: number;
  wordCount: number;
};

export const countTakeawayWords = (text: string): number =>
  text
    .trim()
    .split(/\s+/)
    .filter(Boolean).length;

export const computeTakeawayGeometry = (
  layoutInput: R5LayoutInput,
  text: string,
  hasMascot: boolean,
  anatomyExclusionBox?: Box | null,
  mascotSide: 'left' | 'right' = 'right',
): TakeawayGeometry => {
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);
  const frameArea = layout.frame.width * layout.frame.height;
  const wordCount = countTakeawayWords(text);

  const cardWidth = portrait ? layout.frame.width - 96 : 1120;
  const cardHeight = portrait ? 104 : 96;
  const cardLeft = Math.round((layout.frame.width - cardWidth) / 2);

  const portraitBottom = r5PortraitContentBottom(layout);
  const bottomTop = portrait ? portraitBottom - cardHeight - 16 : layout.frame.height - cardHeight - 44;
  const topTop = portrait ? 168 : 36;

  let cardBox: Box = {left: cardLeft, top: bottomTop, width: cardWidth, height: cardHeight};
  let placement: 'bottom' | 'top' = 'bottom';

  if (anatomyExclusionBox && boxesIntersect(cardBox, anatomyExclusionBox)) {
    const topCandidate: Box = {left: cardLeft, top: topTop, width: cardWidth, height: cardHeight};
    if (!boxesIntersect(topCandidate, anatomyExclusionBox)) {
      cardBox = topCandidate;
      placement = 'top';
    }
  }

  let mascotBox: Box | null = null;
  if (hasMascot) {
    const mascotHeight = portrait ? 220 : 280;
    const mascotWidth = Math.round(mascotHeight * 0.72);
    const mascotTop = portrait
      ? Math.max(topTop, cardBox.top - mascotHeight - SAFE_GAP)
      : layout.frame.height - mascotHeight - 24;

    const makeSideBox = (side: 'left' | 'right'): Box => ({
      left: side === 'right' ? layout.frame.width - mascotWidth - 36 : 36,
      top: mascotTop,
      width: mascotWidth,
      height: mascotHeight,
    });

    const primary = makeSideBox(mascotSide);
    const alternate = makeSideBox(mascotSide === 'right' ? 'left' : 'right');

    const isSafe = (box: Box): boolean => {
      const areaOk = (box.width * box.height) / frameArea <= R5_MAX_MASCOT_AREA_RATIO;
      const anatomyOk = !anatomyExclusionBox || !boxesIntersect(box, anatomyExclusionBox);
      const captionOk = !portrait || box.top + box.height <= portraitBottom;
      return areaOk && anatomyOk && captionOk;
    };

    if (isSafe(primary)) {
      mascotBox = primary;
    } else if (isSafe(alternate)) {
      mascotBox = alternate;
    }
  }

  const mascotAreaRatio = mascotBox ? (mascotBox.width * mascotBox.height) / frameArea : 0;

  return {
    cardBox,
    placement,
    mascotBox,
    mascotAreaRatio,
    wordCount,
  };
};

/**
 * Concise takeaway card (<= R5_MAX_TAKEAWAY_WORDS) with optional pinned mascot (<= 25% frame area).
 * Automatically avoids overlapping close-up anatomy and 9:16 portrait subtitle zones.
 */
export const TakeawayCard: React.FC<TakeawayCardProps> = ({
  shot,
  layout: layoutInput,
  assets,
  text,
  claimIds,
  tag,
  accent = R5_PALETTE.yellow,
  mascot = null,
  anatomyExclusionBox = null,
  frame,
}) => {
  const currentFrame = useCurrentFrame();
  const effectiveFrame = frame ?? currentFrame;
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);

  if (text.includes('\t')) {
    throw new Error(`TakeawayCard (${shot.id}) forbids tab layout`);
  }
  const wordCount = countTakeawayWords(text);
  if (wordCount === 0 || wordCount > R5_MAX_TAKEAWAY_WORDS) {
    throw new Error(
      `TakeawayCard (${shot.id}) requires 1..${R5_MAX_TAKEAWAY_WORDS} words, got ${wordCount}`,
    );
  }

  const allowedAssetPaths = new Set([...assets.map((a) => a.path), ...shot.asset_paths]);
  const hasValidMascot = Boolean(mascot && allowedAssetPaths.has(mascot.assetPath));
  const geom = computeTakeawayGeometry(
    layout,
    text,
    hasValidMascot,
    anatomyExclusionBox,
    mascot?.side ?? 'right',
  );

  const localFrame = Math.max(0, effectiveFrame - shot.start_frame);
  const opacity = r5EaseOut(localFrame / 12);
  const shiftY = (1 - opacity) * (geom.placement === 'bottom' ? 16 : -16);
  const bob = Math.sin(localFrame * 0.14) * 3;

  return (
    <div
      data-r5-component="TakeawayCard"
      data-shot-id={shot.id}
      data-layout={portrait ? '9:16' : '16:9'}
      data-word-count={String(geom.wordCount)}
      data-claim-ids={claimIds.join(',')}
      data-placement={geom.placement}
      data-mascot-area-ratio={geom.mascotAreaRatio.toFixed(4)}
      style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}
    >
      <div
        data-takeaway-box="true"
        style={{
          position: 'absolute',
          left: geom.cardBox.left,
          top: geom.cardBox.top,
          width: geom.cardBox.width,
          minHeight: geom.cardBox.height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 16,
          backgroundColor: R5_PALETTE.navy,
          color: R5_PALETTE.bg,
          border: `4px solid ${accent}`,
          borderRadius: 20,
          padding: portrait ? '14px 24px' : '16px 34px',
          boxShadow: '0 10px 26px rgba(18, 48, 74, 0.22)',
          fontFamily: FONT_FAMILY,
          fontSize: portrait ? 34 : 38,
          fontWeight: 800,
          lineHeight: 1.2,
          opacity: Math.max(0.01, opacity),
          transform: `translateY(${shiftY.toFixed(1)}px)`,
          boxSizing: 'border-box',
        }}
      >
        {tag ? (
          <span
            style={{
              backgroundColor: accent,
              color: R5_PALETTE.navy,
              borderRadius: 10,
              padding: '4px 14px',
              fontSize: portrait ? 24 : 26,
              fontWeight: 800,
              flexShrink: 0,
            }}
          >
            {tag}
          </span>
        ) : (
          <span
            style={{
              width: 16,
              height: 16,
              borderRadius: 8,
              backgroundColor: accent,
              flexShrink: 0,
            }}
          />
        )}
        <span>{text}</span>
      </div>

      {mascot && geom.mascotBox ? (
        <div
          data-takeaway-mascot="true"
          data-mascot-pose={mascot.pose}
          style={{
            position: 'absolute',
            left: geom.mascotBox.left,
            top: geom.mascotBox.top,
            width: geom.mascotBox.width,
            height: geom.mascotBox.height,
            opacity: Math.max(0.01, opacity),
            transform: `translateY(${((1 - opacity) * 24 + bob).toFixed(1)}px)`,
            filter: 'drop-shadow(0 8px 18px rgba(18, 48, 74, 0.2))',
          }}
        >
          <Img
            src={staticFile(mascot.assetPath)}
            style={{width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'bottom center'}}
          />
        </div>
      ) : null}
    </div>
  );
};
