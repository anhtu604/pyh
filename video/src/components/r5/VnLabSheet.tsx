import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {FONT_FAMILY} from '../../fonts';
import type {Box} from '../../layout';
import type {ResolvedR5Shot} from '../../types';
import {
  isPortraitLayout,
  R5_PALETTE,
  r5Clamp01,
  r5EaseOut,
  r5PortraitContentBottom,
  resolveR5Layout,
  type R5LayoutInput,
  type R5RevisionAsset,
} from './ScaleChain';

export const VN_LAB_EMPTY_CELL = '—';

export const VN_LAB_COLUMNS = [
  'Chỉ số',
  'Kết quả',
  'Đơn vị',
  'Khoảng tham chiếu',
] as const;

export type VnLabRow = {
  id: string;
  analyte: string;
  result?: string | null;
  unit?: string | null;
  referenceRange?: string | null;
  flag?: 'H' | 'L' | null;
  highlight?: boolean;
  claimIds: readonly string[];
};

export type VnLabSheetProps = {
  shot: ResolvedR5Shot;
  layout: R5LayoutInput;
  assets?: readonly R5RevisionAsset[];
  title: string;
  revisedTitle?: string | null;
  renameProgress?: number;
  subtitleBadge?: string;
  rows: readonly VnLabRow[];
  footerNote?: string | null;
  frame?: number;
};

export const formatLabCell = (value?: string | null): string => {
  if (value === null || value === undefined) {
    return VN_LAB_EMPTY_CELL;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : VN_LAB_EMPTY_CELL;
};

export const computeVnLabSheetGeometry = (layoutInput: R5LayoutInput): {sheetBox: Box} => {
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);
  if (portrait) {
    const maxBottom = r5PortraitContentBottom(layout);
    const width = layout.frame.width - 72;
    const height = Math.min(820, maxBottom - 200);
    return {
      sheetBox: {
        left: 36,
        top: 180,
        width,
        height,
      },
    };
  }
  const width = 1220;
  const height = 740;
  return {
    sheetBox: {
      left: Math.round((layout.frame.width - width) / 2),
      top: Math.round((layout.frame.height - height) / 2),
      width,
      height,
    },
  };
};

/**
 * Vietnamese hospital lab result sheet with four explicit columns:
 * Chỉ số | Kết quả | Đơn vị | Khoảng tham chiếu, plus H/L flag support.
 * Empty cells always render "—"; zero hardcoded analytes or fabricated patient data.
 */
export const VnLabSheet: React.FC<VnLabSheetProps> = ({
  shot,
  layout: layoutInput,
  title,
  revisedTitle = null,
  renameProgress = 0,
  subtitleBadge = 'Mẫu minh họa',
  rows,
  footerNote = null,
  frame,
}) => {
  const currentFrame = useCurrentFrame();
  const effectiveFrame = frame ?? currentFrame;
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);
  const {sheetBox} = computeVnLabSheetGeometry(layout);

  const localFrame = Math.max(0, effectiveFrame - shot.start_frame);
  const opacity = r5EaseOut(localFrame / 14);
  const clampedRename = r5Clamp01(renameProgress);

  const displayRows: readonly VnLabRow[] =
    rows.length > 0
      ? rows
      : [{id: 'empty', analyte: VN_LAB_EMPTY_CELL, claimIds: []}];

  return (
    <AbsoluteFill
      data-r5-component="VnLabSheet"
      data-shot-id={shot.id}
      data-layout={portrait ? '9:16' : '16:9'}
      style={{
        backgroundColor: R5_PALETTE.bg,
        fontFamily: FONT_FAMILY,
        overflow: 'hidden',
      }}
    >
      <div
        data-lab-sheet-card="true"
        style={{
          position: 'absolute',
          left: sheetBox.left,
          top: sheetBox.top,
          width: sheetBox.width,
          maxHeight: sheetBox.height,
          backgroundColor: R5_PALETTE.surface,
          border: `4px solid ${R5_PALETTE.navy}`,
          borderRadius: 18,
          boxShadow: '0 18px 40px rgba(18, 48, 74, 0.16)',
          overflow: 'hidden',
          color: R5_PALETTE.navy,
          opacity: Math.max(0.01, opacity),
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            backgroundColor: R5_PALETTE.navy,
            color: R5_PALETTE.bg,
            padding: portrait ? '18px 22px' : '22px 34px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <div>
            <div style={{fontSize: portrait ? 18 : 20, fontWeight: 600, opacity: 0.8, letterSpacing: 1.1}}>
              PHIẾU KẾT QUẢ XÉT NGHIỆM
            </div>
            <div style={{position: 'relative', marginTop: 6, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap'}}>
              <span
                style={{
                  fontSize: portrait ? 28 : 34,
                  fontWeight: 800,
                  position: 'relative',
                  opacity: revisedTitle && clampedRename > 0.05 ? 0.52 : 1,
                }}
              >
                {title}
                {revisedTitle && clampedRename > 0.01 ? (
                  <span
                    style={{
                      position: 'absolute',
                      left: -4,
                      right: -4,
                      top: '52%',
                      height: 5,
                      backgroundColor: R5_PALETTE.alert,
                      borderRadius: 3,
                      transformOrigin: 'left center',
                      transform: `scaleX(${r5Clamp01(clampedRename * 1.4).toFixed(3)})`,
                    }}
                  />
                ) : null}
              </span>
              {revisedTitle && clampedRename > 0.35 ? (
                <span
                  style={{
                    fontSize: portrait ? 28 : 34,
                    fontWeight: 800,
                    color: R5_PALETTE.navy,
                    backgroundColor: R5_PALETTE.yellow,
                    padding: '4px 16px',
                    borderRadius: 10,
                    opacity: r5Clamp01((clampedRename - 0.35) / 0.45),
                  }}
                >
                  {revisedTitle}
                </span>
              ) : null}
            </div>
          </div>

          <div
            style={{
              border: '2px solid rgba(247, 244, 236, 0.35)',
              borderRadius: 10,
              padding: '6px 14px',
              fontSize: portrait ? 16 : 18,
              fontWeight: 600,
              opacity: 0.9,
              flexShrink: 0,
            }}
          >
            {subtitleBadge}
          </div>
        </div>

        <div style={{padding: portrait ? '16px 18px 20px' : '20px 30px 26px'}}>
          <div
            role="row"
            data-lab-header="true"
            style={{
              display: 'grid',
              gridTemplateColumns: '2fr 1.2fr 0.9fr 1.4fr',
              padding: portrait ? '10px 12px' : '12px 16px',
              backgroundColor: R5_PALETTE.surfaceSoft,
              borderRadius: 10,
              fontSize: portrait ? 20 : 22,
              fontWeight: 800,
              color: R5_PALETTE.navy,
              borderBottom: `3px solid ${R5_PALETTE.navy}`,
            }}
          >
            {VN_LAB_COLUMNS.map((column, index) => (
              <div
                key={column}
                role="columnheader"
                style={{textAlign: index === 0 ? 'left' : 'center'}}
              >
                {column}
              </div>
            ))}
          </div>

          {displayRows.map((row) => {
            const isHighlighted = Boolean(row.highlight || row.flag === 'H');
            const resultText = formatLabCell(row.result);
            const unitText = formatLabCell(row.unit);
            const refText = formatLabCell(row.referenceRange);

            return (
              <div
                key={row.id}
                role="row"
                data-lab-row={row.id}
                data-claim-ids={row.claimIds.join(',')}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '2fr 1.2fr 0.9fr 1.4fr',
                  alignItems: 'center',
                  padding: portrait ? '14px 12px' : '16px 16px',
                  marginTop: 8,
                  borderRadius: 12,
                  backgroundColor: isHighlighted ? 'rgba(244, 185, 66, 0.24)' : 'transparent',
                  border: isHighlighted
                    ? `3px solid ${R5_PALETTE.alert}`
                    : `1.5px solid ${R5_PALETTE.border}`,
                  fontSize: portrait ? 22 : 26,
                  fontWeight: isHighlighted ? 800 : 600,
                }}
              >
                <div role="cell">{formatLabCell(row.analyte)}</div>
                <div
                  role="cell"
                  style={{
                    textAlign: 'center',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  <span style={{color: resultText === VN_LAB_EMPTY_CELL ? R5_PALETTE.muted : R5_PALETTE.navy}}>
                    {resultText}
                  </span>
                  {row.flag ? (
                    <span
                      data-lab-flag={row.flag}
                      style={{
                        display: 'inline-block',
                        padding: '2px 12px',
                        borderRadius: 999,
                        backgroundColor: row.flag === 'H' ? R5_PALETTE.alert : R5_PALETTE.teal,
                        color: '#FFFFFF',
                        fontWeight: 800,
                        fontSize: portrait ? 20 : 22,
                      }}
                    >
                      {row.flag}
                    </span>
                  ) : null}
                </div>
                <div role="cell" style={{textAlign: 'center', color: R5_PALETTE.muted}}>
                  {unitText}
                </div>
                <div role="cell" style={{textAlign: 'center', color: R5_PALETTE.muted}}>
                  {refText}
                </div>
              </div>
            );
          })}

          {footerNote ? (
            <div
              data-lab-footer="true"
              style={{
                marginTop: 16,
                padding: '12px 18px',
                borderRadius: 10,
                backgroundColor: 'rgba(24, 166, 166, 0.12)',
                border: `2px solid ${R5_PALETTE.teal}`,
                fontSize: portrait ? 20 : 22,
                fontWeight: 700,
                color: R5_PALETTE.navy,
              }}
            >
              {footerNote}
            </div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
