import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {R5_PALETTE, type R5RevisionAsset} from '../components/r5/ScaleChain';
import {
  boxesIntersect,
  captionBox,
  LAYOUTS,
  LayoutContext,
  shortsCaptionSafeBox,
  type Box,
  type FrameLayout,
} from '../layout';
import {ResolvedR5ShotSchema, type ResolvedR5Shot} from '../types';
import {
  computeR5LiverLeakGeometry,
  R5LiverLeakSignature,
  resolveLeakClock,
  type R5LeakLabel,
} from './R5LiverLeakSignature';

vi.mock('remotion', () => ({
  AbsoluteFill: 'div',
  Img: 'img',
  staticFile: (path: string) => `static://${path}`,
  useCurrentFrame: () => 20,
}));

const revisionAssets: R5RevisionAsset[] = [
  {
    id: 'niaid-hepatocyte-203',
    path: 'assets/medanim/niaid-hepatocyte-203.svg',
    name: 'Tế bào gan',
    author: 'NIAID Visual & Medical Arts',
    license: 'Public Domain',
  },
  {
    id: 'niaid-mitochondria-352',
    path: 'assets/medanim/niaid-mitochondria-352.svg',
    name: 'Ty thể',
    author: 'NIAID Visual & Medical Arts',
    license: 'Public Domain',
  },
  {
    id: 'niaid-blood-vessel-55',
    path: 'assets/medanim/niaid-blood-vessel-55.svg',
    name: 'Mạch máu nhỏ',
    author: 'NIAID Visual & Medical Arts',
    license: 'Public Domain',
  },
  {
    id: 'niaid-red-blood-cell-442',
    path: 'assets/medanim/niaid-red-blood-cell-442.svg',
    name: 'Hồng cầu',
    author: 'NIAID Visual & Medical Arts',
    license: 'Public Domain',
  },
  {
    id: 'niaid-blood-vial-52',
    path: 'assets/medanim/niaid-blood-vial-52.svg',
    name: 'Ống máu xét nghiệm',
    author: 'NIAID Visual & Medical Arts',
    license: 'Public Domain',
  },
];

const makeShot = (overrides: Partial<ResolvedR5Shot> = {}): ResolvedR5Shot =>
  ResolvedR5ShotSchema.parse({
    id: 'SH-LEAK-01',
    kind: 'mechanism',
    tier: 'cell',
    component: 'R5LiverLeakSignature',
    asset_paths: revisionAssets.map((a) => a.path),
    question_ids: ['Q1'],
    start_frame: 0,
    end_frame: 360,
    actions: [
      {
        actor: 'enzyme',
        compartment: 'bào tương tế bào gan',
        change: 'men nằm trong tế bào khi màng lành',
        outcome: 'nồng độ máu nền thấp',
        start_frame: 0,
        end_frame: 120,
      },
      {
        actor: 'plasma_membrane',
        compartment: 'màng tế bào gan',
        change: 'tăng tính thấm màng tế bào',
        outcome: 'hàng rào màng bị thay đổi',
        start_frame: 120,
        end_frame: 210,
      },
      {
        actor: 'enzyme',
        compartment: 'xoang máu và ống nghiệm',
        change: 'men thoát qua màng vào dòng máu',
        outcome: 'lượng men trong mẫu máu tăng lên',
        start_frame: 210,
        end_frame: 340,
      },
    ],
    text_windows: [],
    ...overrides,
  });

const claimLabels: R5LeakLabel[] = [
  {
    id: 'lbl-cell',
    text: 'Trong tế bào',
    claimIds: ['C01'],
    startFrame: 10,
    endFrame: 115,
    anchor: 'cell',
    dotColor: R5_PALETTE.teal,
  },
  {
    id: 'lbl-membrane',
    text: 'Thay đổi màng',
    claimIds: ['C02'],
    startFrame: 125,
    endFrame: 205,
    anchor: 'membrane',
    dotColor: R5_PALETTE.alert,
  },
  {
    id: 'lbl-vial',
    text: 'Mẫu máu đo',
    claimIds: ['C03'],
    startFrame: 220,
    endFrame: 335,
    anchor: 'vial',
    dotColor: R5_PALETTE.navy,
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

describe('R5LiverLeakSignature', () => {
  it('defaults to the first 3 actions ordered by start_frame and never uses duration percentage', () => {
    const shortShot = makeShot({
      end_frame: 360,
      // Intentionally unsorted input order to verify start_frame ordering when stageActions is omitted.
      actions: [
        {
          actor: 'enzyme',
          compartment: 'xoang máu và ống nghiệm',
          change: 'men thoát qua màng vào dòng máu',
          outcome: 'lượng men trong mẫu máu tăng lên',
          start_frame: 210,
          end_frame: 340,
        },
        {
          actor: 'enzyme',
          compartment: 'bào tương tế bào gan',
          change: 'men nằm trong tế bào khi màng lành',
          outcome: 'nồng độ máu nền thấp',
          start_frame: 0,
          end_frame: 120,
        },
        {
          actor: 'plasma_membrane',
          compartment: 'màng tế bào gan',
          change: 'tăng tính thấm màng tế bào',
          outcome: 'hàng rào màng bị thay đổi',
          start_frame: 120,
          end_frame: 210,
        },
      ],
    });
    // Stretch total shot duration to 900 frames while keeping identical action frame windows.
    const longShot = makeShot({end_frame: 900});

    const beforeShort = resolveLeakClock(shortShot, 60);
    const beforeLong = resolveLeakClock(longShot, 60);
    expect(beforeShort.phase).toBe('intact');
    expect(beforeShort.membraneChangeProgress).toBe(0);
    expect(beforeShort.bloodLeakProgress).toBe(0);
    expect(beforeLong.phase).toBe(beforeShort.phase);
    expect(beforeLong.membraneChangeProgress).toBe(beforeShort.membraneChangeProgress);

    const duringShort = resolveLeakClock(shortShot, 165);
    const duringLong = resolveLeakClock(longShot, 165);
    expect(duringShort.phase).toBe('membrane_change');
    expect(duringShort.membraneChangeProgress).toBeCloseTo(0.5, 4);
    expect(duringShort.bloodLeakProgress).toBe(0);
    expect(duringShort.membraneChangeDescription).toBe('tăng tính thấm màng tế bào');
    expect(duringLong.membraneChangeProgress).toBeCloseTo(duringShort.membraneChangeProgress, 6);

    const afterShort = resolveLeakClock(shortShot, 300);
    const afterLong = resolveLeakClock(longShot, 300);
    expect(afterShort.phase).toBe('blood_leak');
    expect(afterShort.membraneChangeProgress).toBe(1);
    expect(afterShort.bloodLeakProgress).toBeGreaterThan(0.6);
    expect(afterLong.bloodLeakProgress).toBeCloseTo(afterShort.bloodLeakProgress, 6);

    const htmlDuring = renderWithLayout(
      <R5LiverLeakSignature
        shot={shortShot}
        layout={LAYOUTS.youtube_long}
        assets={revisionAssets}
        frame={165}
      />,
      LAYOUTS.youtube_long,
    );
    expect(htmlDuring).toContain('data-leak-phase="membrane_change"');
    expect(htmlDuring).toContain('data-membrane-change="tăng tính thấm màng tế bào"');
    expect(htmlDuring).toContain('data-membrane-state="changed"');
  });

  it('supports explicit stageActions indices into shot.actions', () => {
    const fourActionShot = makeShot({
      id: 'SH-EXPLICIT-01',
      end_frame: 420,
      actions: [
        {
          actor: 'a0',
          compartment: 'c0',
          change: 'bước 0',
          outcome: 'o0',
          start_frame: 0,
          end_frame: 60,
        },
        {
          actor: 'a1',
          compartment: 'c1',
          change: 'bước 1',
          outcome: 'o1',
          start_frame: 60,
          end_frame: 140,
        },
        {
          actor: 'a2',
          compartment: 'c2',
          change: 'biến đổi màng tường minh',
          outcome: 'o2',
          start_frame: 140,
          end_frame: 260,
        },
        {
          actor: 'a3',
          compartment: 'c3',
          change: 'bước 3',
          outcome: 'o3',
          start_frame: 260,
          end_frame: 400,
        },
      ],
    });

    const stageActions = {intact: 1, membraneChange: 2, bloodLeak: 3};
    expect(resolveLeakClock(fourActionShot, 100, stageActions).phase).toBe('intact');
    const mid = resolveLeakClock(fourActionShot, 200, stageActions);
    expect(mid.phase).toBe('membrane_change');
    expect(mid.membraneChangeProgress).toBeCloseTo(0.5, 4);
    expect(mid.membraneChangeDescription).toBe('biến đổi màng tường minh');
    expect(resolveLeakClock(fourActionShot, 330, stageActions).phase).toBe('blood_leak');

    const html = renderWithLayout(
      <R5LiverLeakSignature
        shot={fourActionShot}
        layout={LAYOUTS.youtube_long}
        assets={revisionAssets}
        stageActions={stageActions}
        frame={200}
      />,
      LAYOUTS.youtube_long,
    );
    expect(html).toContain('data-leak-phase="membrane_change"');
    expect(html).toContain('data-membrane-change="biến đổi màng tường minh"');
  });

  it('does not change state when free-text wording in compartment/change/outcome changes', () => {
    const baseShot = makeShot();
    const rewordedShot = makeShot({
      actions: [
        {
          actor: 'x',
          compartment: 'vùng một hoàn toàn khác máu màng',
          change: 'rò rỉ giả trong mô tả bước đầu',
          outcome: 'kết quả chữ bất kỳ A',
          start_frame: 0,
          end_frame: 120,
        },
        {
          actor: 'y',
          compartment: 'vùng hai không nhắc từ khóa cũ',
          change: 'trạng thái trung gian viết kiểu khác',
          outcome: 'kết quả chữ bất kỳ B',
          start_frame: 120,
          end_frame: 210,
        },
        {
          actor: 'z',
          compartment: 'vùng ba hoàn toàn trung tính',
          change: 'bước cuối viết theo cách khác',
          outcome: 'kết quả chữ bất kỳ C',
          start_frame: 210,
          end_frame: 340,
        },
      ],
    });

    for (const frame of [30, 120, 165, 210, 290, 340]) {
      const a = resolveLeakClock(baseShot, frame);
      const b = resolveLeakClock(rewordedShot, frame);
      expect(b.phase).toBe(a.phase);
      expect(b.intactProgress).toBeCloseTo(a.intactProgress, 6);
      expect(b.membraneChangeProgress).toBeCloseTo(a.membraneChangeProgress, 6);
      expect(b.bloodLeakProgress).toBeCloseTo(a.bloodLeakProgress, 6);
    }
  });

  it('throws an Error naming shot.id for missing actions, out-of-range/duplicate stageActions, or non-increasing frames', () => {
    const twoActionsShot = makeShot({
      id: 'SH-ERR-FEW',
      actions: makeShot().actions.slice(0, 2),
    });
    expect(() => resolveLeakClock(twoActionsShot, 10)).toThrow(/SH-ERR-FEW/);

    const validShot = makeShot({id: 'SH-ERR-IDX'});
    expect(() =>
      resolveLeakClock(validShot, 10, {intact: -1, membraneChange: 1, bloodLeak: 2}),
    ).toThrow(/SH-ERR-IDX/);
    expect(() =>
      resolveLeakClock(validShot, 10, {intact: 0, membraneChange: 1, bloodLeak: 3}),
    ).toThrow(/SH-ERR-IDX/);
    expect(() =>
      resolveLeakClock(validShot, 10, {intact: 0, membraneChange: 1, bloodLeak: 1}),
    ).toThrow(/SH-ERR-IDX/);
    // Explicit stageActions pointing to non-increasing start_frame order.
    expect(() =>
      resolveLeakClock(validShot, 10, {intact: 1, membraneChange: 0, bloodLeak: 2}),
    ).toThrow(/SH-ERR-IDX/);

    // Default ordering with equal start_frame (not strictly increasing).
    const tiedStartShot = makeShot({
      id: 'SH-ERR-TIED',
      actions: [
        {...validShot.actions[0], start_frame: 0, end_frame: 100},
        {...validShot.actions[1], start_frame: 100, end_frame: 200},
        {...validShot.actions[2], start_frame: 100, end_frame: 300},
      ],
    });
    expect(() => resolveLeakClock(tiedStartShot, 50)).toThrow(/SH-ERR-TIED/);
  });

  it('preserves the exact same enzyme particle entities across before, during, and after milestones', () => {
    const shot = makeShot();
    const layout = LAYOUTS.youtube_long;

    const before = computeR5LiverLeakGeometry({shot, layout, assets: revisionAssets, frame: 50});
    const during = computeR5LiverLeakGeometry({shot, layout, assets: revisionAssets, frame: 180});
    const after = computeR5LiverLeakGeometry({shot, layout, assets: revisionAssets, frame: 335});

    const beforeIds = before.particles.map((p) => p.id);
    const duringIds = during.particles.map((p) => p.id);
    const afterIds = after.particles.map((p) => p.id);

    // Identical entity IDs preserved across all three phases.
    expect(beforeIds.length).toBeGreaterThanOrEqual(8);
    expect(duringIds).toEqual(beforeIds);
    expect(afterIds).toEqual(beforeIds);

    // Before: every enzyme entity starts inside the hepatocyte (internal ambient drift never leaks).
    expect(before.particles.every((p) => p.compartment === 'intracellular')).toBe(true);

    // During: migrating entities move to the membrane boundary while resident entities stay inside.
    const migratingDuring = during.particles.filter((p) => p.migrates);
    expect(migratingDuring.every((p) => p.compartment === 'membrane')).toBe(true);

    // After: those exact same migrating entities are in the bloodstream or sample vial.
    const migratingAfter = after.particles.filter((p) => p.migrates);
    expect(migratingAfter.some((p) => p.compartment === 'bloodstream')).toBe(true);
    expect(migratingAfter.some((p) => p.compartment === 'vial')).toBe(true);

    const trackedId = migratingAfter.find((p) => p.compartment === 'vial')!.id;
    expect(before.particles.find((p) => p.id === trackedId)?.compartment).toBe('intracellular');
    expect(during.particles.find((p) => p.id === trackedId)?.compartment).toBe('membrane');
    expect(after.particles.find((p) => p.id === trackedId)?.compartment).toBe('vial');
  });

  it('renders full cell -> membrane -> vessel -> vial pathway in 9:16 portrait and keeps labels clear of captions', () => {
    const shot = makeShot();
    const portrait = LAYOUTS.vertical_clip;

    for (const frame of [60, 165, 310]) {
      const geom = computeR5LiverLeakGeometry({
        shot,
        layout: portrait,
        assets: revisionAssets,
        labels: claimLabels,
        frame,
      });

      // Full vertical pathway fits inside 1080x1920 and clears all portrait subtitle boxes.
      expect(geom.portrait).toBe(true);
      expect(geom.cellBox.top + geom.cellBox.height).toBeLessThan(geom.vesselBox.top);
      expect(geom.vesselBox.top + geom.vesselBox.height).toBeLessThan(geom.vialBox.top + geom.vialBox.height);
      assertClearsPortraitCaptions(geom.stageBox, portrait);
      assertClearsPortraitCaptions(geom.cellBox, portrait);
      assertClearsPortraitCaptions(geom.vesselBox, portrait);
      assertClearsPortraitCaptions(geom.vialBox, portrait);

      for (const lbl of geom.activeLabels) {
        assertClearsPortraitCaptions(lbl.box, portrait);
      }
    }

    const html = renderWithLayout(
      <R5LiverLeakSignature
        shot={shot}
        layout={portrait}
        assets={revisionAssets}
        labels={claimLabels}
        frame={310}
      />,
      portrait,
    );
    expect(html).toContain('data-layout="9:16"');
    expect(html).toContain('Mẫu máu đo');
    expect(html).toContain('data-claim-ids="C03"');
  });

  it('renders no labels and no hardcoded clinical text when labels are not provided', () => {
    const shot = makeShot({text_windows: []});
    const html = renderWithLayout(
      <R5LiverLeakSignature
        shot={shot}
        layout={LAYOUTS.youtube_long}
        assets={revisionAssets}
        frame={260}
      />,
      LAYOUTS.youtube_long,
    );

    expect(html).not.toContain('data-leak-label=');
    expect(html).not.toContain('ALT');
    expect(html).not.toContain('AST');
    expect(html).not.toContain('Màng lành');
    expect(html).not.toContain('Màng tổn thương');
    expect(html).not.toContain('Xét nghiệm');
    expect(html).not.toContain('47 giờ');
  });

  it('uses only assets passed in via props and never references unpassed or hardcoded paths', () => {
    const customOnlyAssets: R5RevisionAsset[] = [
      {
        id: 'custom-cell',
        path: 'assets/rev02/custom-hepatocyte.svg',
        author: 'Verified Author',
        license: 'CC BY 4.0',
      },
      {
        id: 'custom-vial',
        path: 'assets/rev02/custom-blood-vial.svg',
        author: 'Verified Author',
        license: 'Public Domain',
      },
    ];
    const shot = makeShot({asset_paths: customOnlyAssets.map((a) => a.path)});

    const html = renderWithLayout(
      <R5LiverLeakSignature
        shot={shot}
        layout={LAYOUTS.youtube_long}
        assets={customOnlyAssets}
        frame={260}
      />,
      LAYOUTS.youtube_long,
    );

    expect(html).toContain('static://assets/rev02/custom-hepatocyte.svg');
    expect(html).toContain('static://assets/rev02/custom-blood-vial.svg');
    // Must never leak hardcoded library/cache/proto paths or unpassed assets.
    expect(html).not.toContain('niaid-');
    expect(html).not.toContain('medanim/liver-enzyme-leak');
    expect(html).not.toContain('cache/');
    expect(html).not.toContain('data-asset-slot="rbc"');
    expect(html).not.toContain('data-asset-slot="mitochondria"');
  });

  it('is strictly deterministic: identical props yield identical markup and geometry', () => {
    const shot = makeShot();
    const renderOnce = () =>
      renderWithLayout(
        <R5LiverLeakSignature
          shot={shot}
          layout={LAYOUTS.youtube_long}
          assets={revisionAssets}
          labels={claimLabels}
          frame={245}
        />,
        LAYOUTS.youtube_long,
      );

    expect(renderOnce()).toEqual(renderOnce());
    expect(
      computeR5LiverLeakGeometry({
        shot,
        layout: LAYOUTS.vertical_clip,
        assets: revisionAssets,
        labels: claimLabels,
        frame: 245,
      }),
    ).toEqual(
      computeR5LiverLeakGeometry({
        shot,
        layout: LAYOUTS.vertical_clip,
        assets: revisionAssets,
        labels: claimLabels,
        frame: 245,
      }),
    );
  });
});
