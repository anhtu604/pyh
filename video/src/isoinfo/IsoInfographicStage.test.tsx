import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {findForbiddenColorLiterals} from '../anatomy/colorPaletteGuard.test';
import {HealthVideo} from '../HealthVideo';
import {LAYOUTS, LayoutContext} from '../layout';
import {AnatomyScene} from '../scenes/AnatomyScene';
import {ProcessScene} from '../scenes/ProcessScene';
import {parseRenderInput, type Scene} from '../types';
import {
  computeIsoPathMotion,
  ISO_ANGLE_DEG,
  ISO_TRACK_DRAW_FRAMES,
  IsoInfographicStage,
  isoProject,
  orthogonalLeaderPoints,
} from './IsoInfographicStage';
// @ts-expect-error @types/node is not installed in video workspace
import fs from 'node:fs';
// @ts-expect-error @types/node is not installed in video workspace
import path from 'node:path';
// @ts-expect-error @types/node is not installed in video workspace
import {fileURLToPath} from 'node:url';

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

const isoScene: Scene = {
  id: 'S-ISO-01',
  start_frame: 0,
  duration_frames: 180,
  narration: 'Tế bào gan trao đổi chất qua xoang mạch và đường mật.',
  visual: 'anatomy_animation',
  visualTakeaway: 'Mặt cắt đẳng cự 30° cho thấy đường mật tách biệt dòng máu',
  anatomy: {
    subject: 'hepatocyte_sinusoid_unit',
    state: 'diseased',
    severity: 0.65,
    motion: 'isometric cutaway',
  },
  beats: [
    {at: 0, focus: 'cell', labels: ['cell', 'enzyme', 'bile'], start_frame: 0},
  ],
};

describe('IsoInfographicStage (S6)', () => {
  it('uses exact 30-degree isometric projection and zero off-palette colors', () => {
    expect(ISO_ANGLE_DEG).toBe(30);
    const pt = isoProject(100, 0, 0, {x: 0, y: 0});
    expect(pt.x).toBeCloseTo(100 * Math.cos(Math.PI / 6), 5);
    expect(pt.y).toBeCloseTo(100 * Math.sin(Math.PI / 6), 5);

    const here = path.dirname(fileURLToPath(import.meta.url));
    const source = fs.readFileSync(path.join(here, 'IsoInfographicStage.tsx'), 'utf8');
    expect(findForbiddenColorLiterals(source)).toEqual([]);
  });

  it('pre-draws isometric track completely before moving the traveling marker', () => {
    const early = computeIsoPathMotion(9, 180);
    expect(early.trackDrawProgress).toBeCloseTo(0.5, 4);
    expect(early.travelerProgress).toBe(0);

    const boundary = computeIsoPathMotion(ISO_TRACK_DRAW_FRAMES, 180);
    expect(boundary.trackDrawProgress).toBe(1);
    expect(boundary.travelerProgress).toBe(0);

    const moving = computeIsoPathMotion(99, 180);
    expect(moving.trackDrawProgress).toBe(1);
    expect(moving.travelerProgress).toBeGreaterThan(0);

    clock.frame = 9;
    const earlyHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <IsoInfographicStage scene={isoScene} kind="anatomy" />
      </LayoutContext.Provider>,
    );
    expect(earlyHtml).toContain('data-iso-track="true"');
    expect(earlyHtml).not.toContain('data-iso-traveler="true"');

    clock.frame = 90;
    const midHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <IsoInfographicStage scene={isoScene} kind="anatomy" />
      </LayoutContext.Provider>,
    );
    expect(midHtml).toContain('data-iso-traveler="true"');
  });

  it('builds strictly vertical-then-horizontal orthogonal pin leaders', () => {
    const [p0, p1, p2] = orthogonalLeaderPoints(420, 310, {left: 700, top: 200, width: 180, height: 46});
    expect(p0.x).toBe(p1.x); // Vertical segment
    expect(p1.y).toBe(p2.y); // Horizontal segment
  });

  it('dispatches from AnatomyScene, ProcessScene, and HealthVideo when visualStyle is iso_infographic', () => {
    clock.frame = 45;
    const anatomyHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <AnatomyScene scene={isoScene} visualStyle="iso_infographic" />
      </LayoutContext.Provider>,
    );
    expect(anatomyHtml).toContain('data-isoinfo-stage="true"');
    expect(anatomyHtml).toContain('data-iso-plinth="true"');
    expect(anatomyHtml).toContain('data-iso-peel="true"');
    expect(anatomyHtml).toContain('data-iso-orthogonal-leader="true"');
    expect(anatomyHtml).toContain('background-color:#F7F4EC');
    expect(anatomyHtml).not.toContain('aria-label="Phụ đề đang đọc"');

    const processHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <ProcessScene scene={{...isoScene, visual: 'process_animation'}} visualStyle="iso_infographic" />
      </LayoutContext.Provider>,
    );
    expect(processHtml).toContain('data-isoinfo-stage="true"');

    const parsed = parseRenderInput({
      title: 'Iso Infographic',
      audio_file: 'audio/silence.wav',
      visualStyle: 'iso_infographic',
      format_profile: 'vertical_clip',
      width: 1080,
      height: 1920,
      scenes: [{
        ...isoScene,
        words: [
          {text: 'Tế', start_frame: 0, end_frame: 20},
          {text: 'bào', start_frame: 20, end_frame: 50},
          {text: 'gan', start_frame: 50, end_frame: 80},
        ],
      }],
    });
    const videoHtml = renderToStaticMarkup(<HealthVideo {...parsed} />);
    expect(videoHtml).toContain('data-isoinfo-stage="true"');
    expect(videoHtml).toContain('data-shorts-captions="true"');
    expect(videoHtml).toContain('data-active="true"');
  });
});
