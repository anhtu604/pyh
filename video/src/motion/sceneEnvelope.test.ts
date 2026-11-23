import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {brand} from '../anatomy/palette';
import {PresenterMascot} from '../components/PresenterMascot';
import {HealthVideo} from '../HealthVideo';
import {LAYOUTS, LayoutContext} from '../layout';
import {AnatomyScene} from '../scenes/AnatomyScene';
import {parseRenderInput, type Scene} from '../types';
import {
  computeSceneEnvelope,
  sceneTransitionPlan,
  smoothstepCubic,
} from './sceneEnvelope';
import {WipeTransitions} from './WipeTransitions';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', async (original) => ({
  ...(await original<typeof import('remotion')>()),
  AbsoluteFill: 'div',
  Audio: 'audio',
  Img: 'img',
  Sequence: ({children}: {children: React.ReactNode}) => children,
  staticFile: (p: string) => p,
  useCurrentFrame: () => clock.frame,
  useVideoConfig: () => ({fps: 30, width: 1920, height: 1080}),
}));

const makeScene = (overrides: Partial<Scene> = {}): Scene => ({
  schema_version: '1.0',
  id: 'S01',
  start_frame: 0,
  duration_frames: 120,
  narration: 'Nội dung mẫu.',
  chapter_id: 'CH01',
  visual: 'whiteboard',
  visual_assets: [],
  ...overrides,
});

describe('sceneEnvelope (Workstream A)', () => {
  it('uses monotonic smoothstep cubic easing with zero overshoot', () => {
    expect(smoothstepCubic(0)).toBe(0);
    expect(smoothstepCubic(0.5)).toBe(0.5);
    expect(smoothstepCubic(1)).toBe(1);
    let prev = 0;
    for (let i = 0; i <= 20; i++) {
      const val = smoothstepCubic(i / 20);
      expect(val).toBeGreaterThanOrEqual(prev);
      expect(val).toBeLessThanOrEqual(1);
      prev = val;
    }
  });

  it('returns identity envelope when transition is undefined or durationFrames < 45', () => {
    expect(computeSceneEnvelope(0, undefined)).toEqual({opacity: 1, transform: undefined, bridge: null});
    expect(
      computeSceneEnvelope(0, {enterMode: 'scene_cut', exitMode: 'scene_exit', durationFrames: 30}),
    ).toEqual({opacity: 1, transform: undefined, bridge: null});
  });

  it('plans hook_open, shared_continuation, scene_cut, chapter_enter, and outro deterministically', () => {
    const scenes: Scene[] = [
      makeScene({
        id: 'S01',
        chapter_id: 'CH01',
        script_line_id: 'N01',
        visual_assets: [{path: 'assets/m1.png', role: 'mascot', pose: 'welcome'}],
      }),
      makeScene({
        id: 'S02',
        start_frame: 120,
        chapter_id: 'CH01',
        script_line_id: 'N01',
        visual_assets: [{path: 'assets/m2.png', role: 'mascot', pose: 'explain'}],
      }),
      makeScene({id: 'S03', start_frame: 240, chapter_id: 'CH01', script_line_id: 'N02'}),
      makeScene({id: 'S04', start_frame: 360, chapter_id: 'CH02', script_line_id: 'N03'}),
      makeScene({
        id: 'S05',
        start_frame: 480,
        chapter_id: 'CH02',
        visual: 'brand_outro',
        visual_assets: [{path: 'assets/brand/pyh-logo.svg', role: 'brand'}],
      }),
    ];

    const p0 = sceneTransitionPlan(scenes, 0);
    expect(p0.enterMode).toBe('hook_open');
    expect(p0.exitMode).toBe('none'); // followed by shared_continuation
    expect(p0.mascotContinuation).toBe(false);

    const p1 = sceneTransitionPlan(scenes, 1);
    expect(p1.enterMode).toBe('shared_continuation');
    expect(p1.exitMode).toBe('scene_exit');
    expect(p1.mascotContinuation).toBe(true);

    const p2 = sceneTransitionPlan(scenes, 2);
    expect(p2.enterMode).toBe('scene_cut');
    expect(p2.exitMode).toBe('chapter_exit');

    const p3 = sceneTransitionPlan(scenes, 3);
    expect(p3.enterMode).toBe('chapter_enter');
    expect(p3.exitMode).toBe('chapter_exit'); // followed by brand_outro

    const p4 = sceneTransitionPlan(scenes, 4);
    expect(p4.enterMode).toBe('chapter_enter');
    expect(p4.isOutro).toBe(true);
    expect(p4.exitMode).toBe('none');
  });

  it('computes exact enter/exit curves and chapter bridge timing without overshoot', () => {
    // hook_open: 0.92 -> 1 in 6f, no slide
    expect(computeSceneEnvelope(0, {enterMode: 'hook_open', exitMode: 'none', durationFrames: 120})).toEqual({
      opacity: 0.92,
      transform: undefined,
      bridge: null,
    });
    expect(computeSceneEnvelope(6, {enterMode: 'hook_open', exitMode: 'none', durationFrames: 120}).opacity).toBe(1);

    // shared_continuation: 0.88 -> 1 in 6f, no slide
    expect(
      computeSceneEnvelope(0, {enterMode: 'shared_continuation', exitMode: 'none', durationFrames: 120}),
    ).toEqual({opacity: 0.88, transform: undefined, bridge: null});

    // scene_cut: 10f enter (18px -> 0), 6f exit (0 -> -12px)
    const cutStart = computeSceneEnvelope(0, {enterMode: 'scene_cut', exitMode: 'scene_exit', durationFrames: 120});
    expect(cutStart.opacity).toBe(0);
    expect(cutStart.transform).toBe('translateX(18.00px)');
    const cutMid = computeSceneEnvelope(10, {enterMode: 'scene_cut', exitMode: 'scene_exit', durationFrames: 120});
    expect(cutMid.opacity).toBe(1);
    expect(cutMid.transform).toBeUndefined();
    const cutExit = computeSceneEnvelope(119, {enterMode: 'scene_cut', exitMode: 'scene_exit', durationFrames: 120});
    expect(cutExit.opacity).toBeLessThan(0.2);
    expect(cutExit.transform).toContain('translateX(-');

    // chapter_enter: 12f enter (28px -> 0) + bridge during 0..32
    const chapStart = computeSceneEnvelope(0, {enterMode: 'chapter_enter', exitMode: 'chapter_exit', durationFrames: 120});
    expect(chapStart.opacity).toBe(0);
    expect(chapStart.transform).toBe('translateX(28.00px)');
    expect(chapStart.bridge).toEqual({widthPercent: 0, opacity: 1});
    const chapBridge = computeSceneEnvelope(18, {enterMode: 'chapter_enter', exitMode: 'chapter_exit', durationFrames: 120});
    expect(chapBridge.bridge?.widthPercent).toBe(100);
    expect(chapBridge.bridge?.opacity).toBe(1);
    expect(
      computeSceneEnvelope(33, {enterMode: 'chapter_enter', exitMode: 'chapter_exit', durationFrames: 120}).bridge,
    ).toBeNull();

    // brand_outro: 15f fade only, no slide, no bridge
    const outroStart = computeSceneEnvelope(0, {
      enterMode: 'chapter_enter',
      exitMode: 'none',
      durationFrames: 120,
      isOutro: true,
    });
    expect(outroStart.transform).toBeUndefined();
    expect(outroStart.bridge).toBeNull();
  });

  it('keeps PresenterMascot anchored without bottom-up drop on continuation and caps new entrance to 36px', () => {
    const box = {left: 0, top: 669, width: 470, height: 410};
    const asset = {path: 'assets/welcome.png', role: 'mascot' as const, pose: 'welcome' as const};

    clock.frame = 0;
    const contHtml = renderToStaticMarkup(
      React.createElement(
        LayoutContext.Provider,
        {value: LAYOUTS.youtube_long},
        React.createElement(PresenterMascot, {
          asset,
          box,
          continuation: true,
          transition: {enterMode: 'shared_continuation', exitMode: 'none', durationFrames: 120, mascotContinuation: true},
        }),
      ),
    );
    expect(contHtml).toContain('data-mascot-continuation="true"');
    expect(contHtml).toContain('translateY(0px)');
    expect(contHtml).toContain('opacity:0.82');

    const freshHtml = renderToStaticMarkup(
      React.createElement(
        LayoutContext.Provider,
        {value: LAYOUTS.youtube_long},
        React.createElement(PresenterMascot, {
          asset,
          box,
          continuation: false,
          transition: {enterMode: 'scene_cut', exitMode: 'none', durationFrames: 120},
        }),
      ),
    );
    expect(freshHtml).toContain('translateY(36px)');
  });

  it('renders WipeTransitions overlay=true as a smooth 14f off_white curtain without blind strips', () => {
    clock.frame = 7;
    const midHtml = renderToStaticMarkup(React.createElement(WipeTransitions, {overlay: true}));
    expect(midHtml).toContain('data-motion="wipe-transitions"');
    expect(midHtml).toContain('data-wipe-curtain="true"');
    expect(midHtml).toContain(brand.off_white);
    expect(midHtml).toContain(brand.teal);
    expect(midHtml).not.toContain('data-blind-strip');

    clock.frame = 14;
    const doneHtml = renderToStaticMarkup(React.createElement(WipeTransitions, {overlay: true}));
    expect(doneHtml).toContain('data-wipe-complete="true"');
  });

  it('forces off_white canvas on 16:9 HealthVideo mechanism scenes while keeping standalone AnatomyScene dark without mascot', () => {
    const mechScene: Scene = makeScene({
      id: 'S06',
      visual: 'anatomy_animation',
      anatomy: {subject: 'liver_organ', state: 'normal', severity: 0, motion: 'overview'},
      visual_assets: [],
    });

    // Standalone unit render keeps dark night surface when no mascot
    const standaloneHtml = renderToStaticMarkup(
      React.createElement(
        LayoutContext.Provider,
        {value: LAYOUTS.youtube_long},
        React.createElement(AnatomyScene, {scene: mechScene}),
      ),
    );
    expect(standaloneHtml).toContain(`background-color:${brand.night}`);

    // Full 16:9 HealthVideo forces light off_white canvas across scenes (no dark flash)
    clock.frame = 15;
    const parsed = parseRenderInput({
      title: 'Style A Smooth',
      audio_file: 'audio/silence.wav',
      format_profile: 'youtube_long',
      width: 1920,
      height: 1080,
      scenes: [
        makeScene({id: 'S01', chapter_id: 'CH01', duration_frames: 90}),
        {...mechScene, id: 'S06', start_frame: 90, chapter_id: 'CH02'},
      ],
    });
    const fullHtml = renderToStaticMarkup(React.createElement(HealthVideo, parsed));
    expect(fullHtml).toContain(`background-color:${brand.off_white}`);
    expect(fullHtml).not.toContain(`background-color:${brand.night}`);
    expect(fullHtml).toContain('data-chapter-bridge="true"');
  });
});
