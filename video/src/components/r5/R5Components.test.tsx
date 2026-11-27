import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {
  boxesIntersect,
  captionBox,
  LAYOUTS,
  LayoutContext,
  shortsCaptionSafeBox,
  type Box,
  type FrameLayout,
} from '../../layout';
import {ResolvedR5ShotSchema, type ResolvedR5Shot} from '../../types';
import {
  computeCreditPagination,
  CREDIT_MAX_PAGE_FRAMES,
  CREDIT_MAX_PAGE_SECONDS,
  CreditCard,
} from './CreditCard';
import {
  computeDistributionGeometry,
  ReferenceDistribution,
} from './ReferenceDistribution';
import {
  computeScaleChainGeometry,
  R5_PALETTE,
  ScaleChain,
  type R5RevisionAsset,
  type ScaleTier,
} from './ScaleChain';
import {computeStoryShotGeometry, StoryShot} from './StoryShot';
import {
  computeTakeawayGeometry,
  R5_MAX_MASCOT_AREA_RATIO,
  R5_MAX_TAKEAWAY_WORDS,
  TakeawayCard,
} from './TakeawayCard';
import {
  computeVnLabSheetGeometry,
  VN_LAB_COLUMNS,
  VN_LAB_EMPTY_CELL,
  VnLabSheet,
} from './VnLabSheet';
import {computeZoomChainGeometry, ZoomChain} from './ZoomChain';

vi.mock('remotion', () => ({
  AbsoluteFill: 'div',
  Img: 'img',
  staticFile: (path: string) => `static://${path}`,
  useCurrentFrame: () => 15,
}));

const makeShot = (overrides: Partial<ResolvedR5Shot> = {}): ResolvedR5Shot =>
  ResolvedR5ShotSchema.parse({
    id: 'SH01',
    kind: 'mechanism',
    tier: 'organ',
    component: 'ZoomChain',
    asset_paths: ['assets/medanim/sample-organ.svg'],
    question_ids: ['Q1'],
    start_frame: 0,
    end_frame: 240,
    actions: [
      {
        actor: 'marker',
        compartment: 'tissue',
        change: 'highlight',
        outcome: 'localized',
        start_frame: 10,
        end_frame: 120,
      },
    ],
    text_windows: [],
    ...overrides,
  });

const revisionAssets: R5RevisionAsset[] = [
  {
    id: 'sample-organ',
    path: 'assets/medanim/sample-organ.svg',
    name: 'Mô hình cơ quan mẫu',
    author: 'Tác giả A',
    repository: 'Kho A',
    license: 'Public Domain',
  },
  {
    id: 'mascot-explain',
    path: 'assets/brand/mascot/explain.png',
    name: 'Mascot giải thích',
    author: 'PYH Brand',
    license: 'Internal',
  },
];

const renderWithLayout = (element: React.ReactElement, layout: FrameLayout): string =>
  renderToStaticMarkup(
    <LayoutContext.Provider value={layout}>{element}</LayoutContext.Provider>,
  );

const assertClearsPortraitCaptions = (box: Box, layout: FrameLayout): void => {
  expect(boxesIntersect(box, captionBox(layout))).toBe(false);
  expect(boxesIntersect(box, shortsCaptionSafeBox(layout, false))).toBe(false);
  expect(boxesIntersect(box, shortsCaptionSafeBox(layout, true))).toBe(false);
};

describe('ScaleChain', () => {
  const customTiers: ScaleTier[] = [
    {id: 'body', label: 'Cơ thể'},
    {id: 'vessel', label: 'Mạch máu'},
    {id: 'wall', label: 'Thành mạch'},
    {id: 'endothelium', label: 'Nội mô'},
    {id: 'molecule', label: 'Phân tử'},
  ];

  it.each([
    ['16:9', LAYOUTS.youtube_long],
    ['9:16', LAYOUTS.vertical_clip],
  ] as const)('renders prop-driven tiers and highlights active tier in %s', (label, layout) => {
    const shot = makeShot({component: 'ScaleChain', tier: 'wall'});
    const geom = computeScaleChainGeometry(layout, customTiers, shot.tier);
    const html = renderWithLayout(
      <ScaleChain shot={shot} layout={layout} tiers={customTiers} frame={20} />,
      layout,
    );

    expect(html).toContain('data-r5-component="ScaleChain"');
    expect(html).toContain(`data-layout="${label}"`);
    expect(html).toContain('data-active-tier="wall"');
    expect(html).toContain('Thành mạch');
    // Must not hardcode liver-specific tiers.
    expect(html).not.toContain('Tiểu thùy');
    expect(html).not.toContain('Xoang mạch');
    expect(html).toContain(R5_PALETTE.teal);

    if (label === '9:16') {
      expect(geom.compacted).toBe(true);
      assertClearsPortraitCaptions(geom.box, layout);
    } else {
      expect(geom.compacted).toBe(false);
      expect(html).not.toContain('aria-label="Phụ đề đang đọc"');
    }
  });
});

describe('ZoomChain', () => {
  const tiers: ScaleTier[] = [
    {id: 'body', label: 'Cơ thể'},
    {id: 'organ', label: 'Cơ quan'},
    {id: 'tissue', label: 'Mô'},
  ];

  const baseProps = {
    shot: makeShot({component: 'ZoomChain', tier: 'body'}),
    assets: revisionAssets,
    fromAnchor: {tierId: 'body', x: 0.42, y: 0.45},
    toAnchor: {tierId: 'organ', x: 0.62, y: 0.54, radius: 52},
    landmarks: [
      {id: 'lm-1', label: 'Vùng định vị A', x: 0.25, y: 0.35, claimIds: ['C01']},
      {id: 'lm-2', label: 'Vùng định vị B', x: 0.72, y: 0.92, claimIds: ['C02']},
    ],
    tiers,
    frame: 230,
  };

  it.each([
    ['16:9', LAYOUTS.youtube_long],
    ['9:16', LAYOUTS.vertical_clip],
  ] as const)('connects from/to anchors with landmarks and preserves orientation in %s', (label, layout) => {
    const geom = computeZoomChainGeometry({...baseProps, layout});
    const html = renderWithLayout(<ZoomChain {...baseProps} layout={layout} />, layout);

    expect(html).toContain('data-r5-component="ZoomChain"');
    expect(html).toContain('data-from-tier="body"');
    expect(html).toContain('data-to-tier="organ"');
    expect(html).toContain('data-anchor-connector="true"');
    expect(html).toContain('PHẢI (cơ thể)');
    expect(html).toContain('TRÁI (cơ thể)');
    expect(html).toContain('Vùng định vị A');
    expect(html).toContain('Vùng định vị B');
    expect(html).toContain('static://assets/medanim/sample-organ.svg');
    expect(geom.landmarkBoxes.length).toBeGreaterThanOrEqual(1);
    expect(geom.camera.scale).toBeGreaterThan(1);
    expect(geom.fromPoint.tierId).toBe('body');
    expect(geom.toPoint.tierId).toBe('organ');

    if (label === '9:16') {
      assertClearsPortraitCaptions(geom.stageBox, layout);
      for (const landmark of geom.landmarkBoxes) {
        assertClearsPortraitCaptions(landmark.box, layout);
      }
    } else {
      expect(html).not.toContain('aria-label="Phụ đề đang đọc"');
    }
  });

  it('rejects missing landmarks so every zoom has >= 1 positioning region', () => {
    expect(() =>
      renderWithLayout(
        <ZoomChain {...baseProps} layout={LAYOUTS.youtube_long} landmarks={[]} />,
        LAYOUTS.youtube_long,
      ),
    ).toThrow(/landmark/i);
  });
});

describe('TakeawayCard', () => {
  const shot = makeShot({
    component: 'TakeawayCard',
    asset_paths: ['assets/brand/mascot/explain.png'],
  });
  const mascot = {
    assetPath: 'assets/brand/mascot/explain.png',
    pose: 'explain' as const,
    side: 'right' as const,
  };

  it.each([
    ['16:9', LAYOUTS.youtube_long],
    ['9:16', LAYOUTS.vertical_clip],
  ] as const)('keeps card and mascot clear of close-up anatomy and <= 25% area in %s', (label, layout) => {
    const closeUpAnatomy: Box =
      label === '9:16'
        ? {left: 80, top: 760, width: 920, height: 600}
        : {left: 200, top: 680, width: 1520, height: 380};

    const geom = computeTakeawayGeometry(
      layout,
      'Chỉ số tăng cần đối chiếu lâm sàng',
      true,
      closeUpAnatomy,
      'right',
    );
    const html = renderWithLayout(
      <TakeawayCard
        shot={shot}
        layout={layout}
        assets={revisionAssets}
        text="Chỉ số tăng cần đối chiếu lâm sàng"
        claimIds={['C03']}
        tag="Chốt"
        mascot={mascot}
        anatomyExclusionBox={closeUpAnatomy}
        frame={30}
      />,
      layout,
    );

    expect(html).toContain('data-r5-component="TakeawayCard"');
    expect(geom.wordCount).toBeLessThanOrEqual(R5_MAX_TAKEAWAY_WORDS);
    expect(geom.mascotAreaRatio).toBeLessThanOrEqual(R5_MAX_MASCOT_AREA_RATIO);
    expect(boxesIntersect(geom.cardBox, closeUpAnatomy)).toBe(false);
    if (geom.mascotBox) {
      expect(boxesIntersect(geom.mascotBox, closeUpAnatomy)).toBe(false);
    }
    if (label === '9:16') {
      assertClearsPortraitCaptions(geom.cardBox, layout);
      if (geom.mascotBox) {
        assertClearsPortraitCaptions(geom.mascotBox, layout);
      }
    } else {
      expect(html).not.toContain('aria-label="Phụ đề đang đọc"');
    }
  });

  it('rejects takeaway copy exceeding R5_MAX_TAKEAWAY_WORDS (8 words)', () => {
    expect(() =>
      renderWithLayout(
        <TakeawayCard
          shot={shot}
          layout={LAYOUTS.youtube_long}
          assets={revisionAssets}
          text="Một hai ba bốn năm sáu bảy tám chín"
          claimIds={['C03']}
          frame={10}
        />,
        LAYOUTS.youtube_long,
      ),
    ).toThrow(/1\.\.8 words/);
  });
});

describe('VnLabSheet', () => {
  const shot = makeShot({component: 'VnLabSheet'});

  it.each([
    ['16:9', LAYOUTS.youtube_long],
    ['9:16', LAYOUTS.vertical_clip],
  ] as const)('renders 4 columns, H flag, and em-dash for empty cells in %s', (label, layout) => {
    const geom = computeVnLabSheetGeometry(layout);
    const html = renderWithLayout(
      <VnLabSheet
        shot={shot}
        layout={layout}
        title="Bảng xét nghiệm mẫu"
        rows={[
          {id: 'r1', analyte: 'Chỉ số X', result: null, unit: 'U/L', referenceRange: '', flag: 'H', claimIds: ['C04']},
          {id: 'r2', analyte: 'Chỉ số Y', result: undefined, unit: null, referenceRange: null, claimIds: ['C05']},
        ]}
        frame={20}
      />,
      layout,
    );

    for (const col of VN_LAB_COLUMNS) {
      expect(html).toContain(col);
    }
    expect(html).toContain('data-lab-flag="H"');
    expect(html).toContain(VN_LAB_EMPTY_CELL);
    // Must never hardcode ALT/AST/Glucose/Creatinine.
    expect(html).not.toContain('ALT');
    expect(html).not.toContain('AST');
    expect(html).not.toContain('Glucose');
    expect(html).not.toContain('Creatinine');

    if (label === '9:16') {
      assertClearsPortraitCaptions(geom.sheetBox, layout);
    } else {
      expect(html).not.toContain('aria-label="Phụ đề đang đọc"');
    }
  });
});

describe('ReferenceDistribution', () => {
  const shot = makeShot({component: 'ReferenceDistribution'});
  // Intentionally right-skewed points to verify non-Gaussian data rendering.
  const skewedPoints = [
    {x: 0.0, y: 0.05},
    {x: 0.2, y: 0.85},
    {x: 0.4, y: 0.95},
    {x: 0.65, y: 0.45},
    {x: 0.85, y: 0.15},
    {x: 1.0, y: 0.04},
  ];

  it.each([
    ['16:9', LAYOUTS.youtube_long],
    ['9:16', LAYOUTS.vertical_clip],
  ] as const)('renders prop curve with illustrative badge and clears captions in %s', (label, layout) => {
    const geom = computeDistributionGeometry(layout, true);
    const html = renderWithLayout(
      <ReferenceDistribution
        shot={shot}
        layout={layout}
        title="Khoảng tham chiếu quần thể"
        points={skewedPoints}
        bands={[
          {id: 'b-main', label: 'Vùng tham chiếu', startX: 0.1, endX: 0.85, tone: 'teal', claimIds: ['C06']},
          {id: 'b-tail', label: 'Đuôi ngoài', startX: 0.85, endX: 1.0, tone: 'yellow', claimIds: ['C06']},
        ]}
        markers={[{id: 'm1', label: 'Mốc A', x: 0.85, tone: 'alert', claimIds: ['C06']}]}
        cohort={{total: 10, outsideCount: 1, caption: 'Nhóm minh họa', claimIds: ['C06']}}
        frame={40}
      />,
      layout,
    );

    expect(html).toContain('data-r5-component="ReferenceDistribution"');
    expect(html).toContain('data-illustration-label="true"');
    expect(html.toLowerCase()).toContain('minh họa');
    expect(html).toContain('không mặc định mọi chỉ số đều phân phối chuẩn');
    expect(html).toContain('Mốc A');
    expect(html).not.toContain('29–33');
    expect(html).not.toContain('19–25');

    if (label === '9:16') {
      assertClearsPortraitCaptions(geom.badgeBox, layout);
      assertClearsPortraitCaptions(geom.plotBox, layout);
      assertClearsPortraitCaptions(geom.noteBox, layout);
      if (geom.cohortBox) {
        assertClearsPortraitCaptions(geom.cohortBox, layout);
      }
    } else {
      expect(html).not.toContain('aria-label="Phụ đề đang đọc"');
    }
  });
});

describe('CreditCard', () => {
  const usedAssets: R5RevisionAsset[] = [
    {path: 'assets/a1.svg', name: 'Hình 1', author: 'Tác giả 1', repository: 'Kho 1', license: 'CC BY 4.0'},
    {path: 'assets/a2.svg', name: 'Hình 2', author: 'Tác giả 2', repository: 'Kho 2', license: 'Public Domain'},
    {path: 'assets/a3.svg', name: 'Hình 3', author: 'Tác giả 3', license: 'CC0'},
    {path: 'assets/a4.svg', name: 'Hình 4', author: 'Tác giả 4', license: 'CC BY 4.0'},
    {path: 'assets/a5.svg', name: 'Hình 5', author: 'Tác giả 5', license: 'Public Domain'},
  ];

  it.each([
    ['16:9', LAYOUTS.youtube_long],
    ['9:16', LAYOUTS.vertical_clip],
  ] as const)('lists only passed-in assets, paginates within <= 6s D1 budget in %s', (label, layout) => {
    const shot = makeShot({
      component: 'CreditCard',
      kind: 'credit',
      start_frame: 0,
      end_frame: 600,
    });
    const page0 = computeCreditPagination({
      shot,
      layout,
      assets: usedAssets,
      pageDurationFrames: 300, // intentionally > 180 to verify cap
      frame: 10,
    });
    const page1 = computeCreditPagination({
      shot,
      layout,
      assets: usedAssets,
      pageDurationFrames: 300,
      frame: CREDIT_MAX_PAGE_FRAMES + 5,
    });

    expect(page0.pageDurationFrames).toBeLessThanOrEqual(CREDIT_MAX_PAGE_FRAMES);
    expect(page0.pageDurationSeconds).toBeLessThanOrEqual(CREDIT_MAX_PAGE_SECONDS);
    expect(page0.totalPages).toBe(2);
    expect(page0.currentPageIndex).toBe(0);
    expect(page1.currentPageIndex).toBe(1);

    const html0 = renderWithLayout(
      <CreditCard shot={shot} layout={layout} assets={usedAssets} frame={10} />,
      layout,
    );
    const html1 = renderWithLayout(
      <CreditCard shot={shot} layout={layout} assets={usedAssets} frame={CREDIT_MAX_PAGE_FRAMES + 5} />,
      layout,
    );

    expect(html0).toContain('Hình 1');
    expect(html0).toContain('Tác giả 1 (Kho 1) · CC BY 4.0');
    expect(html0).not.toContain('Hình 5');
    expect(html1).toContain('Hình 5');
    // Must not contain hardcoded proto credits.
    expect(html0).not.toContain('NIAID');
    expect(html0).not.toContain('Servier');
    expect(html0).not.toContain('Reactome');

    if (label === '9:16') {
      assertClearsPortraitCaptions(page0.cardBox, layout);
    } else {
      expect(html0).not.toContain('aria-label="Phụ đề đang đọc"');
    }
  });
});

describe('determinism across all R5 components', () => {
  it('produces identical markup and geometry for identical props', () => {
    const shot = makeShot();
    const layout = LAYOUTS.youtube_long;
    const tiers: ScaleTier[] = [
      {id: 'body', label: 'Cơ thể'},
      {id: 'organ', label: 'Cơ quan'},
    ];
    const renderAll = () => [
      renderWithLayout(<ScaleChain shot={shot} layout={layout} tiers={tiers} frame={42} />, layout),
      renderWithLayout(
        <ZoomChain
          shot={shot}
          layout={layout}
          assets={revisionAssets}
          fromAnchor={{tierId: 'body', x: 0.3, y: 0.4}}
          toAnchor={{tierId: 'organ', x: 0.6, y: 0.5}}
          landmarks={[{id: 'l1', label: 'Mốc 1', x: 0.4, y: 0.4, claimIds: ['C01']}]}
          frame={42}
        />,
        layout,
      ),
      renderWithLayout(
        <TakeawayCard
          shot={shot}
          layout={layout}
          assets={revisionAssets}
          text="Câu chốt ngắn gọn rõ ràng"
          claimIds={['C01']}
          frame={42}
        />,
        layout,
      ),
      renderWithLayout(
        <VnLabSheet
          shot={shot}
          layout={layout}
          title="Phiếu mẫu"
          rows={[{id: 'r1', analyte: 'Mục A', result: null, unit: 'U/L', referenceRange: null, flag: 'H', claimIds: ['C01']}]}
          frame={42}
        />,
        layout,
      ),
      renderWithLayout(
        <ReferenceDistribution
          shot={shot}
          layout={layout}
          title="Phân bố mẫu"
          points={[{x: 0, y: 0.1}, {x: 0.5, y: 0.9}, {x: 1, y: 0.1}]}
          bands={[{id: 'b1', label: 'Chính', startX: 0.2, endX: 0.8, tone: 'teal', claimIds: ['C01']}]}
          frame={42}
        />,
        layout,
      ),
      renderWithLayout(
        <CreditCard shot={shot} layout={layout} assets={revisionAssets.slice(0, 1)} frame={42} />,
        layout,
      ),
      renderWithLayout(
        <StoryShot
          shot={makeShot({component: 'StoryShot', kind: 'story', tier: null, actions: [], text_windows: []})}
          layout={layout}
          assets={revisionAssets}
          frame={42}
        />,
        layout,
      ),
    ];

    expect(renderAll()).toEqual(renderAll());
  });
});

describe('StoryShot', () => {
  it.each([
    ['16:9', LAYOUTS.youtube_long],
    ['9:16', LAYOUTS.vertical_clip],
  ] as const)('renders licensed asset with frame-driven push-in/pan and no text in %s', (label, layout) => {
    const shot = makeShot({
      id: 'SH-STORY-ASSET',
      kind: 'story',
      tier: null,
      component: 'StoryShot',
      asset_paths: ['assets/medanim/sample-organ.svg'],
      actions: [],
      text_windows: [],
    });
    const earlyGeom = computeStoryShotGeometry({shot, layout, assets: revisionAssets, frame: 10});
    const lateGeom = computeStoryShotGeometry({shot, layout, assets: revisionAssets, frame: 200});
    const html = renderWithLayout(
      <StoryShot shot={shot} layout={layout} assets={revisionAssets} frame={60} />,
      layout,
    );

    expect(earlyGeom.mode).toBe('asset');
    expect(lateGeom.motion.scale).toBeGreaterThan(earlyGeom.motion.scale);
    expect(lateGeom.motion.tx).not.toBe(earlyGeom.motion.tx);
    expect(html).toContain('data-r5-component="StoryShot"');
    expect(html).toContain(`data-layout="${label}"`);
    expect(html).toContain('data-story-mode="asset"');
    expect(html).toContain('static://assets/medanim/sample-organ.svg');
    expect(html).not.toContain('data-story-label=');
    expect(html).not.toContain('data-story-mascot=');

    if (label === '9:16') {
      assertClearsPortraitCaptions(earlyGeom.stageBox, layout);
    }
  });

  it.each([
    ['16:9', LAYOUTS.youtube_long],
    ['9:16', LAYOUTS.vertical_clip],
  ] as const)('falls back to scene mascot with gentle breathing/tilt when no asset is present in %s', (label, layout) => {
    const shot = makeShot({
      id: 'SH-STORY-MASCOT',
      kind: 'story',
      tier: null,
      component: 'StoryShot',
      asset_paths: [],
      actions: [],
      text_windows: [],
    });
    const mascot = {assetPath: 'assets/brand/mascot/explain.png', pose: 'explain' as const};
    const geomA = computeStoryShotGeometry({shot, layout, assets: [], mascot, frame: 5});
    const geomB = computeStoryShotGeometry({shot, layout, assets: [], mascot, frame: 25});
    const html = renderWithLayout(
      <StoryShot shot={shot} layout={layout} assets={[]} mascot={mascot} frame={25} />,
      layout,
    );

    expect(geomA.mode).toBe('mascot');
    expect(geomA.mascotBox).not.toBeNull();
    expect(geomB.motion.ty).not.toBe(geomA.motion.ty);
    expect(geomB.motion.rotateDeg).not.toBe(geomA.motion.rotateDeg);
    expect(html).toContain('data-story-mode="mascot"');
    expect(html).toContain('data-story-mascot="true"');
    expect(html).toContain('static://assets/brand/mascot/explain.png');

    if (label === '9:16' && geomA.mascotBox) {
      assertClearsPortraitCaptions(geomA.mascotBox, layout);
    }
  });

  it('renders optional label text_windows only and throws when neither asset nor mascot exists', () => {
    const withLabel = makeShot({
      id: 'SH-STORY-LABEL',
      kind: 'story',
      tier: null,
      component: 'StoryShot',
      asset_paths: ['assets/medanim/sample-organ.svg'],
      actions: [],
      text_windows: [
        {kind: 'label', text: 'Bữa ăn tối', claim_ids: [], exception_reason: null, start_frame: 0, end_frame: 120},
        {kind: 'takeaway', text: 'Không vẽ chữ này', claim_ids: [], exception_reason: null, start_frame: 0, end_frame: 120},
      ],
    });
    const html = renderWithLayout(
      <StoryShot shot={withLabel} layout={LAYOUTS.youtube_long} assets={revisionAssets} frame={30} />,
      LAYOUTS.youtube_long,
    );
    expect(html).toContain('Bữa ăn tối');
    expect(html).not.toContain('Không vẽ chữ này');

    const emptyShot = makeShot({
      id: 'SH-STORY-EMPTY',
      kind: 'story',
      tier: null,
      component: 'StoryShot',
      asset_paths: [],
      actions: [],
      text_windows: [],
    });
    expect(() =>
      renderWithLayout(
        <StoryShot shot={emptyShot} layout={LAYOUTS.youtube_long} assets={[]} mascot={null} frame={15} />,
        LAYOUTS.youtube_long,
      ),
    ).toThrow(/SH-STORY-EMPTY.*licensed asset or a scene mascot/i);
  });
});
