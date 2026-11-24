import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {FONT_FAMILY} from '../../fonts';
import type {Box} from '../../layout';
import type {ResolvedR5Shot} from '../../types';
import {
  D1_MAX_TEXT_SECONDS,
  isPortraitLayout,
  R5_FPS,
  R5_PALETTE,
  r5EaseOut,
  r5PortraitContentBottom,
  resolveR5Layout,
  type R5LayoutInput,
  type R5RevisionAsset,
} from './ScaleChain';

export const CREDIT_MAX_PAGE_SECONDS = D1_MAX_TEXT_SECONDS;
export const CREDIT_MAX_PAGE_FRAMES = CREDIT_MAX_PAGE_SECONDS * R5_FPS;

export type CreditCardProps = {
  shot: ResolvedR5Shot;
  layout: R5LayoutInput;
  /** Strictly the list of assets actually used in this video/revision. */
  assets: readonly R5RevisionAsset[];
  title?: string;
  disclaimer?: string;
  itemsPerPage?: number;
  /** Frames per page; capped to CREDIT_MAX_PAGE_FRAMES (<= 6s per D1). */
  pageDurationFrames?: number;
  frame?: number;
};

export type CreditPagination = {
  pages: R5RevisionAsset[][];
  totalPages: number;
  currentPageIndex: number;
  currentPageItems: R5RevisionAsset[];
  pageDurationFrames: number;
  pageDurationSeconds: number;
  cardBox: Box;
};

export const paginateCreditAssets = (
  assets: readonly R5RevisionAsset[],
  itemsPerPage: number,
): R5RevisionAsset[][] => {
  const safePageSize = Math.max(1, Math.floor(itemsPerPage));
  const seen = new Set<string>();
  const unique: R5RevisionAsset[] = [];
  for (const asset of assets) {
    if (!seen.has(asset.path)) {
      seen.add(asset.path);
      unique.push(asset);
    }
  }
  if (unique.length === 0) {
    return [[]];
  }
  const pages: R5RevisionAsset[][] = [];
  for (let i = 0; i < unique.length; i += safePageSize) {
    pages.push(unique.slice(i, i + safePageSize));
  }
  return pages;
};

export const computeCreditPagination = (
  props: Pick<
    CreditCardProps,
    'shot' | 'layout' | 'assets' | 'itemsPerPage' | 'pageDurationFrames' | 'frame'
  >,
): CreditPagination => {
  const layout = resolveR5Layout(props.layout);
  const portrait = isPortraitLayout(layout);
  const defaultPerPage = portrait ? 3 : 4;
  const pages = paginateCreditAssets(props.assets, props.itemsPerPage ?? defaultPerPage);
  const totalPages = pages.length;

  const shotDuration = Math.max(1, props.shot.end_frame - props.shot.start_frame);
  const requestedPageFrames =
    props.pageDurationFrames ?? Math.ceil(shotDuration / totalPages);
  // Enforce D1 budget: each credit page holds for at most 6 seconds (180 frames at 30fps).
  const pageDurationFrames = Math.max(1, Math.min(CREDIT_MAX_PAGE_FRAMES, requestedPageFrames));
  const pageDurationSeconds = pageDurationFrames / R5_FPS;

  const rawFrame = props.frame ?? props.shot.start_frame;
  const localFrame = Math.max(0, rawFrame - props.shot.start_frame);
  const currentPageIndex = Math.min(
    totalPages - 1,
    Math.floor(localFrame / pageDurationFrames),
  );

  const cardBox: Box = portrait
    ? {
        left: 48,
        top: 104,
        width: layout.frame.width - 96,
        height: r5PortraitContentBottom(layout) - 120,
      }
    : {
        left: 88,
        top: 64,
        width: layout.frame.width - 176,
        height: layout.frame.height - 128,
      };

  return {
    pages,
    totalPages,
    currentPageIndex,
    currentPageItems: pages[currentPageIndex] ?? [],
    pageDurationFrames,
    pageDurationSeconds,
    cardBox,
  };
};

/**
 * End credit card generated strictly from the passed-in used assets list.
 * Paginates automatically and caps each page duration at <= 6s (D1 budget).
 */
export const CreditCard: React.FC<CreditCardProps> = ({
  shot,
  layout: layoutInput,
  assets,
  title = 'Nguồn hình ảnh khoa học',
  disclaimer = 'Nội dung mang tính giáo dục sức khỏe · Không thay thế tư vấn khám bệnh trực tiếp',
  itemsPerPage,
  pageDurationFrames,
  frame,
}) => {
  const currentFrame = useCurrentFrame();
  const effectiveFrame = frame ?? currentFrame;
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);

  const pagination = computeCreditPagination({
    shot,
    layout,
    assets,
    itemsPerPage,
    pageDurationFrames,
    frame: effectiveFrame,
  });

  const localFrame = Math.max(0, effectiveFrame - shot.start_frame);
  const pageLocalFrame = localFrame % pagination.pageDurationFrames;
  const opacity = r5EaseOut(pageLocalFrame / 10);

  return (
    <AbsoluteFill
      data-r5-component="CreditCard"
      data-shot-id={shot.id}
      data-layout={portrait ? '9:16' : '16:9'}
      data-page-index={String(pagination.currentPageIndex)}
      data-total-pages={String(pagination.totalPages)}
      data-page-seconds={pagination.pageDurationSeconds.toFixed(2)}
      style={{
        backgroundColor: R5_PALETTE.navy,
        color: R5_PALETTE.bg,
        fontFamily: FONT_FAMILY,
        overflow: 'hidden',
      }}
    >
      <div
        data-credit-card-box="true"
        style={{
          position: 'absolute',
          left: pagination.cardBox.left,
          top: pagination.cardBox.top,
          width: pagination.cardBox.width,
          height: pagination.cardBox.height,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          opacity: Math.max(0.01, opacity),
          boxSizing: 'border-box',
        }}
      >
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 16}}>
          <div style={{fontSize: portrait ? 34 : 38, fontWeight: 800, color: R5_PALETTE.yellow}}>
            {title}
          </div>
          {pagination.totalPages > 1 ? (
            <div
              data-credit-pager="true"
              style={{
                padding: '6px 16px',
                borderRadius: 999,
                backgroundColor: 'rgba(24, 166, 166, 0.24)',
                border: `2px solid ${R5_PALETTE.teal}`,
                fontSize: portrait ? 20 : 22,
                fontWeight: 800,
                color: R5_PALETTE.bg,
                flexShrink: 0,
              }}
            >
              Trang {pagination.currentPageIndex + 1}/{pagination.totalPages}
            </div>
          ) : null}
        </div>

        <ul
          data-credit-list="true"
          style={{
            listStyle: 'none',
            margin: '24px 0',
            padding: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: portrait ? 16 : 18,
            flex: 1,
          }}
        >
          {pagination.currentPageItems.map((asset) => {
            const displayName = asset.name?.trim() || asset.id || asset.path;
            const authorLine = asset.repository
              ? `${asset.author} (${asset.repository})`
              : asset.author;
            return (
              <li
                key={asset.path}
                data-credit-asset={asset.path}
                style={{
                  backgroundColor: 'rgba(255, 255, 255, 0.08)',
                  border: '2px solid rgba(247, 244, 236, 0.24)',
                  borderRadius: 16,
                  padding: portrait ? '16px 20px' : '18px 26px',
                }}
              >
                <div style={{fontSize: portrait ? 24 : 26, fontWeight: 800, color: R5_PALETTE.bg}}>
                  {displayName}
                </div>
                <div style={{fontSize: portrait ? 20 : 22, fontWeight: 600, color: R5_PALETTE.teal, marginTop: 6}}>
                  {authorLine} · {asset.license}
                </div>
                {asset.transformations ? (
                  <div style={{fontSize: portrait ? 18 : 19, opacity: 0.8, marginTop: 4}}>
                    Biến đổi: {asset.transformations}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>

        <div style={{fontSize: portrait ? 18 : 20, opacity: 0.78, textAlign: 'right'}}>
          {disclaimer}
        </div>
      </div>
    </AbsoluteFill>
  );
};
