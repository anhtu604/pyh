import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {ANATOMY_SUBJECTS} from '../anatomy/registry';
import {HealthVideo} from '../HealthVideo';
import {boxesIntersect, LAYOUTS, LayoutContext, type Box} from '../layout';
import {MechanismScene} from '../scenes/MechanismScene';
import {parseRenderInput, type Scene} from '../types';
import {
  computeLayerTransition,
  computeScaleZoomState,
  LAYER_HANDOFF_T,
  logZoomInterpolate,
  resolveScaleLevel,
  resolveScaleSurface,
  SCALE_TRANSITION_FRAMES,
  SUBJECT_SCALE_LEVEL,
} from './levels';
import {
  leaderSegmentForLabel,
  MAX_SCALEZOOM_LABELS,
  resolveNonOverlappingLabels,
  segmentIntersectsBox,
  segmentsIntersect,
  type LabelCandidate,
} from './SingleLabel';
import {ScaleZoomStage} from './ScaleZoomStage';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', async (original) => ({
  ...(await original<typeof import('remotion')>()),
  AbsoluteFill: 'div',
  Audio: 'audio',
  Img: 'img',
  staticFile: (p: string) => p,
  Sequence: ({children}: {children: React.ReactNode}) => children,
  useCurrentFrame: () => clock.frame,
  useVideoConfig: () => ({fps: 30, width: 1920, height: 1080}),
}));

const hepatocyteScene: Scene = {
  id: 'S-SZ-01',
  start_frame: 0,
  duration_frames: 360,
  narration: 'Tế bào gan bị quá tải khiến men ALT và AST rò rỉ vào dòng máu.',
  visual: 'process_animation',
  visualTakeaway: 'Men ALT/AST tăng là dấu hiệu màng tế bào gan đang tổn thương',
  anatomy: {
    subject: 'hepatocyte_sinusoid_unit',
    state: 'diseased',
    severity: 0.85,
    motion: 'zoom from cell to enzyme leak',
    cues: [
      {word: 'Tế bào gan', action: 'toxic', start_frame: 30},
      {word: 'rò rỉ', action: 'leak', start_frame: 150},
    ],
  },
  beats: [
    {at: 0, focus: 'overview', labels: ['cell'], start_frame: 0},
    {at: 4, focus: 'cell', labels: ['cell', 'enzyme'], action: 'toxic', start_frame: 120},
    {at: 8, focus: 'blood', labels: ['enzyme', 'blood'], action: 'leak', start_frame: 240},
  ],
};

describe('Scale Zoom style integration', () => {
  it('(a) preserves legacy rendering when visualStyle is omitted', () => {
    clock.frame = 60;
    const legacy = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <MechanismScene scene={hepatocyteScene} kind="process" />
      </LayoutContext.Provider>,
    );
    expect(legacy).not.toContain('data-scalezoom-stage="true"');
    expect(legacy).not.toContain('data-scalezoom-bar="true"');
    expect(legacy).toContain('data-mechanism-camera="true"');

    const parsed = parseRenderInput({
      title: 'Legacy default',
      audio_file: 'audio/silence.wav',
      format_profile: 'youtube_long',
      width: 1920,
      height: 1080,
      scenes: [hepatocyteScene],
    });
    expect(parsed.visualStyle).toBeUndefined();
    const videoMarkup = renderToStaticMarkup(<HealthVideo {...parsed} />);
    expect(videoMarkup).not.toContain('data-scalezoom-stage="true"');
  });

  it('(b) renders ScaleZoomStage, ScaleBar, single primary label, focus ring, underline, and zero rotation when visualStyle is scale_zoom', () => {
    clock.frame = 150;
    const parsed = parseRenderInput({
      title: 'Scale Zoom test',
      audio_file: 'audio/silence.wav',
      visualStyle: 'scale_zoom',
      format_profile: 'youtube_long',
      width: 1920,
      height: 1080,
      scenes: [hepatocyteScene],
    });
    expect(parsed.visualStyle).toBe('scale_zoom');
    expect(parsed.scenes[0].visualTakeaway).toBe(hepatocyteScene.visualTakeaway);

    const markup = renderToStaticMarkup(<HealthVideo {...parsed} />);
    expect(markup).toContain('data-scalezoom-stage="true"');
    expect(markup).toContain('data-scalezoom-bar="true"');
    expect(markup).toContain('data-scalezoom-labels="true"');
    expect(markup).toContain('data-focus-ring="true"');
    expect(markup).toContain('data-emphasis-underline="true"');
    expect(markup).toContain('data-scalezoom-takeaway="true"');
    expect(markup).toContain('drop-shadow(0px 10px 0px');
    // Camera must never rotate
    const cameraStyle = markup.match(/data-scalezoom-camera="true"[^>]*style="([^"]+)"/)?.[1] ?? '';
    expect(cameraStyle).toContain('scale(');
    expect(cameraStyle).not.toContain('rotate(');
    // Exactly one primary label at a time
    const primaryMatches = [...markup.matchAll(/data-scalezoom-primary="true"/g)];
    expect(primaryMatches).toHaveLength(1);
  });

  it('(b2) supports scale_zoom in 9:16 vertical_clip while keeping standard 9:16 caption band', () => {
    clock.frame = 60;
    const verticalInput = parseRenderInput({
      title: 'Scale Zoom 9:16',
      audio_file: 'audio/silence.wav',
      visualStyle: 'scale_zoom',
      format_profile: 'vertical_clip',
      width: 1080,
      height: 1920,
      scenes: [hepatocyteScene],
    });
    const markup = renderToStaticMarkup(<HealthVideo {...verticalInput} />);
    expect(markup).toContain('data-scalezoom-stage="true"');
    expect(markup).toContain('data-scalezoom-bar="true"');
    expect(markup).toContain('data-mechanism-caption-band="true"');
  });

  it('(c) maps every registered subject to a scale level, applies focus/action overrides, chooses surface purely, and uses log-zoom', () => {
    for (const subject of ANATOMY_SUBJECTS) {
      const level = SUBJECT_SCALE_LEVEL[subject as keyof typeof SUBJECT_SCALE_LEVEL];
      expect(['organ', 'tissue', 'cell', 'molecule']).toContain(level);
    }
    expect(resolveScaleLevel('liver_organ', 'overview')).toBe('organ');
    expect(resolveScaleLevel('liver_lobule', 'central_vein')).toBe('tissue');
    expect(resolveScaleLevel('hepatocyte_sinusoid_unit', 'cell')).toBe('cell');
    expect(resolveScaleLevel('hepatocyte_sinusoid_unit', 'blood', 'leak')).toBe('molecule');

    expect(resolveScaleSurface('organ')).toBe('off_white');
    expect(resolveScaleSurface('tissue')).toBe('off_white');
    expect(resolveScaleSurface('cell')).toBe('night');
    expect(resolveScaleSurface('molecule')).toBe('night');

    // Transition duration stays strictly within 18-30 frames
    expect(SCALE_TRANSITION_FRAMES).toBeGreaterThanOrEqual(18);
    expect(SCALE_TRANSITION_FRAMES).toBeLessThanOrEqual(30);

    // Log-zoom midpoint at t=0.5 is geometric mean sqrt(a*b), not arithmetic mean
    const mid = logZoomInterpolate(1, 4, 0.5);
    expect(mid).toBeCloseTo(2.0, 5);
    expect(logZoomInterpolate(1, 4, 0)).toBeCloseTo(1, 5);
    expect(logZoomInterpolate(1, 4, 1)).toBeCloseTo(4, 5);
  });

  it('(d) caps rendered labels at 6 and guarantees zero overlaps among labels and obstacles', () => {
    const crowded: LabelCandidate[] = Array.from({length: 9}, (_, i) => ({
      id: `L${i}`,
      text: i === 0 ? 'Tế bào gan (Hepatocyte)' : `Nhãn cấu trúc số ${i}`,
      anchorX: 700 + i * 6,
      anchorY: 420 + i * 4,
      preferredX: 700,
      preferredY: 420,
      primary: i === 0,
    }));
    const bounds: Box = {left: 40, top: 120, width: 1840, height: 900};
    const obstacles: Box[] = [
      {left: 1440, top: 20, width: 460, height: 112}, // ScaleBar
      {left: 24, top: 750, width: 320, height: 280}, // Mascot
    ];
    const placed = resolveNonOverlappingLabels(crowded, bounds, obstacles);
    expect(placed.length).toBeLessThanOrEqual(MAX_SCALEZOOM_LABELS);
    expect(placed.length).toBe(6);
    expect(placed.some((item) => item.id === 'L0' && item.primary)).toBe(true);

    for (let i = 0; i < placed.length; i++) {
      for (let j = i + 1; j < placed.length; j++) {
        expect(boxesIntersect(placed[i].box, placed[j].box)).toBe(false);
      }
      for (const obs of obstacles) {
        expect(boxesIntersect(placed[i].box, obs)).toBe(false);
      }
    }
  });

  it('(e) guarantees meaningful visual change across every 5-second (150f) window, with or without authored beats', () => {
    const view: Box = {left: 0, top: 0, width: 560, height: 560};
    const regions = {
      overview: {left: 0, top: 0, width: 560, height: 560},
      right_lobe: {left: 30, top: 50, width: 290, height: 460},
      left_lobe: {left: 285, top: 90, width: 250, height: 270},
    };
    const viewport: Box = {left: 340, top: 96, width: 1500, height: 860};
    const subjectBox: Box = {left: 380, top: 136, width: 1420, height: 780};

    const unbeatedLongScene: Scene = {
      id: 'S-LONG-01',
      start_frame: 0,
      duration_frames: 450, // 15 seconds
      narration: 'Gan nhận máu từ tĩnh mạch cửa và xử lý dưỡng chất.',
      visual: 'anatomy_animation',
      anatomy: {subject: 'liver_organ', state: 'normal', severity: 0, motion: ''},
    };

    for (const testScene of [hepatocyteScene, unbeatedLongScene]) {
      const labelKeys = testScene.id === 'S-SZ-01' ? ['cell', 'enzyme', 'blood', 'bile'] : [];
      for (let start = 0; start + 150 <= testScene.duration_frames; start += 150) {
        const s0 = computeScaleZoomState(testScene, start, regions, view, subjectBox, viewport, labelKeys);
        const s1 = computeScaleZoomState(testScene, start + 149, regions, view, subjectBox, viewport, labelKeys);
        const zoomChanged = Math.abs(s1.camera.zoom - s0.camera.zoom) > 0.01;
        const panChanged = Math.abs(s1.camera.x - s0.camera.x) > 0.5 || Math.abs(s1.camera.y - s0.camera.y) > 0.5;
        const beatChanged = s1.activeBeatIndex !== s0.activeBeatIndex;
        const labelChanged = s1.activeBeat?.primaryLabelId !== s0.activeBeat?.primaryLabelId;
        expect(zoomChanged || panChanged || beatChanged || labelChanged).toBe(true);
      }
    }
  });

  it('(f) transitions hepatic cell subjects into the stylized ~10 nm molecular closeup at molecule level', () => {
    // At frame 30 (cell beat), molecular closeup is not shown.
    clock.frame = 30;
    const cellMarkup = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <ScaleZoomStage scene={hepatocyteScene} kind="process" />
      </LayoutContext.Provider>,
    );
    expect(cellMarkup).toContain('data-scalezoom-level="cell"');
    expect(cellMarkup).not.toContain('data-scalezoom-molecular-closeup="true"');

    // At frame 132 (mid 24-frame transition from cell to molecule), both layers crossfade with log-zoom.
    clock.frame = 132;
    const transitionMarkup = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <ScaleZoomStage scene={hepatocyteScene} kind="process" />
      </LayoutContext.Provider>,
    );
    expect(transitionMarkup).toContain('data-scalezoom-level="molecule"');
    expect(transitionMarkup).toContain('data-scalezoom-molecular-closeup="true"');
    expect(transitionMarkup).toContain('data-layer="hepatocyte-membrane"');

    // At frame 270 (settled molecule beat), lipid bilayer + breach + stylized caption are shown.
    clock.frame = 270;
    const moleculeMarkup = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <ScaleZoomStage scene={hepatocyteScene} kind="process" />
      </LayoutContext.Provider>,
    );
    expect(moleculeMarkup).toContain('data-scalezoom-molecular-closeup="true"');
    expect(moleculeMarkup).toContain('data-layer="lipid-bilayer"');
    expect(moleculeMarkup).toContain('data-layer="membrane-breach"');
    expect(moleculeMarkup).toContain('data-stylized-caption="true"');
    expect(moleculeMarkup).toContain('Minh họa cách điệu');
    expect(moleculeMarkup).toContain('thoát ra máu khi màng tổn thương');

    // Normal state in molecular view keeps intact-membrane caption instead of leak claim.
    const normalMolecularScene: Scene = {
      ...hepatocyteScene,
      id: 'S-SZ-NORM',
      anatomy: {
        subject: 'hepatic_synthesis_and_bile',
        state: 'normal',
        severity: 0,
        motion: 'normal export',
      },
      beats: [
        {at: 0, focus: 'overview', labels: ['cell'], start_frame: 0},
        {at: 4, focus: 'blood', labels: ['blood'], action: 'export', start_frame: 120},
      ],
    };
    const normalMoleculeMarkup = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <ScaleZoomStage scene={normalMolecularScene} kind="process" />
      </LayoutContext.Provider>,
    );
    expect(normalMoleculeMarkup).toContain('data-stylized-caption="true"');
    expect(normalMoleculeMarkup).toContain('màng tế bào gan nguyên vẹn giữ men ALT/AST bên trong tế bào');
    expect(normalMoleculeMarkup).not.toContain('thoát ra máu khi màng tổn thương');
  });

  it('(g) supports mascotSide left (default) and right while balancing the stage viewport', () => {
    clock.frame = 30;
    const withMascot: Scene = {
      ...hepatocyteScene,
      visual_assets: [{path: 'assets/brand/mascot/explain.png', role: 'mascot', pose: 'explain'}],
    };
    const leftMarkup = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <ScaleZoomStage scene={withMascot} kind="process" />
      </LayoutContext.Provider>,
    );
    const rightMarkup = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <ScaleZoomStage scene={withMascot} kind="process" mascotSide="right" />
      </LayoutContext.Provider>,
    );
    expect(leftMarkup).toContain('data-mascot-side="left"');
    expect(rightMarkup).toContain('data-mascot-side="right"');
    expect(leftMarkup).not.toBe(rightMarkup);
  });

  it('(h) prevents label boxes and leader lines from intersecting arrows, keep-outs, or other leaders', () => {
    const bounds: Box = {left: 40, top: 120, width: 1840, height: 900};
    const obstacles: Box[] = [
      {left: 1440, top: 20, width: 460, height: 112}, // ScaleBar
    ];
    // Horizontal blood-flow arrow directly between the anchor (y=740) and preferred label (y=830).
    const arrowObstacle: Box = {left: 400, top: 775, width: 700, height: 24};
    const leaderObstacles: Box[] = [...obstacles, arrowObstacle];

    const candidates: LabelCandidate[] = [
      {
        id: 'blood',
        text: 'Dòng máu',
        anchorX: 780,
        anchorY: 740,
        preferredX: 780,
        preferredY: 830, // Would cut straight across arrowObstacle at y=775..799!
        primary: true,
      },
      {
        id: 'enzyme',
        text: 'ALT / AST',
        anchorX: 620,
        anchorY: 600,
        preferredX: 620,
        preferredY: 500,
        primary: false,
      },
    ];

    const placed = resolveNonOverlappingLabels(candidates, bounds, obstacles, leaderObstacles);
    expect(placed).toHaveLength(2);

    for (let i = 0; i < placed.length; i++) {
      const segA = leaderSegmentForLabel(placed[i]);
      expect(segmentIntersectsBox(segA, arrowObstacle)).toBe(false);
      for (let j = i + 1; j < placed.length; j++) {
        expect(boxesIntersect(placed[i].box, placed[j].box)).toBe(false);
        const segB = leaderSegmentForLabel(placed[j]);
        expect(segmentsIntersect(segA, segB)).toBe(false);
        expect(segmentIntersectsBox(segA, placed[j].box)).toBe(false);
        expect(segmentIntersectsBox(segB, placed[i].box)).toBe(false);
      }
    }
  });

  it('(i) never has both outgoing and incoming layers simultaneously > 0.6 opacity at any t, and separates zoom exit from scale-in entry', () => {
    for (let i = 0; i <= 100; i++) {
      const t = i / 100;
      const m = computeLayerTransition(t);
      expect(m.outgoingOpacity > 0.6 && m.incomingOpacity > 0.6).toBe(false);
      // Strict sequential handoff: never simultaneously visible
      expect(Math.min(m.outgoingOpacity, m.incomingOpacity)).toBe(0);
    }

    // Verify milestones t=0.25, 0.5, 0.75 on rendered ScaleZoomStage (24-frame transition starting at frame 120)
    const milestones = [
      {frame: 120 + Math.round(SCALE_TRANSITION_FRAMES * 0.25), expectOutVisible: true, expectInVisible: false},
      {frame: 120 + Math.round(SCALE_TRANSITION_FRAMES * 0.5), expectOutVisible: false, expectInVisible: true},
      {frame: 120 + Math.round(SCALE_TRANSITION_FRAMES * 0.75), expectOutVisible: false, expectInVisible: true},
    ];
    for (const step of milestones) {
      clock.frame = step.frame;
      const html = renderToStaticMarkup(
        <LayoutContext.Provider value={LAYOUTS.youtube_long}>
          <ScaleZoomStage scene={hepatocyteScene} kind="process" />
        </LayoutContext.Provider>,
      );
      const outMatch = html.match(/data-scalezoom-outgoing-layer="true"[^>]*data-layer-opacity="([^"]+)"/);
      const inMatch = html.match(/data-scalezoom-incoming-layer="true"[^>]*data-layer-opacity="([^"]+)"/);
      const outOpacity = outMatch ? Number(outMatch[1]) : 0;
      const inOpacity = inMatch ? Number(inMatch[1]) : 0;
      expect(outOpacity > 0.6 && inOpacity > 0.6).toBe(false);
      if (step.expectOutVisible) {
        expect(outOpacity).toBeGreaterThan(0.5);
        expect(inOpacity).toBe(0);
      }
      if (step.expectInVisible) {
        expect(outOpacity).toBe(0);
        expect(inOpacity).toBeGreaterThan(0.5);
      }
    }

    // Incoming scale grows monotonically from < 1 at handoff to 1.0 at end
    const atHandoff = computeLayerTransition(LAYER_HANDOFF_T);
    const atMid = computeLayerTransition(0.5);
    const atThreeQuarter = computeLayerTransition(0.75);
    const atEnd = computeLayerTransition(1);
    expect(atHandoff.incomingScale).toBeLessThan(0.6);
    expect(atMid.incomingScale).toBeGreaterThan(atHandoff.incomingScale);
    expect(atThreeQuarter.incomingScale).toBeGreaterThan(atMid.incomingScale);
    expect(atEnd.incomingScale).toBeCloseTo(1, 5);
  });
});
