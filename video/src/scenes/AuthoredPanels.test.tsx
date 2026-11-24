import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext} from '../layout';
import type {Scene} from '../types';
import {WhiteboardScene} from './WhiteboardScene';
import {AnatomyScene} from './AnatomyScene';
import {SourceCardScene} from './SourceCardScene';
import {ProcessScene} from './ProcessScene';
import {MechanismScene} from './MechanismScene';
import {R5ShotScene} from './R5ShotScene';
import {AuthoredWorksheet, panelRows} from '../components/AuthoredPanels';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', async original => ({
  ...await original<typeof import('remotion')>(),
  useCurrentFrame: () => clock.frame, useVideoConfig: () => ({fps: 30}),
}));
const base: Scene = {id: 'example', start_frame: 0, duration_frames: 600,
  narration: 'Lời đọc đã được duyệt.', visual: 'whiteboard', on_screen_text: 'Phiếu giả định'};
const render = (Component: React.FC<{scene: Scene}>, scene: Scene, format: keyof typeof LAYOUTS) =>
  renderToStaticMarkup(<LayoutContext.Provider value={LAYOUTS[format]}><Component scene={scene}/></LayoutContext.Provider>);

it('keeps unstructured entrances on the existing renderer and does not mutate authored timing', () => {
  expect(panelRows({...base, entrances: [{text: 'Plain entrance', start_frame: 0}]}, 2)).toEqual([]);
  const scene: Scene = {...base, entrances: [{text: 'Ý chính\tChi tiết', start_frame: 30}],
    beats: [{at: 0, start_frame: 50, focus: 'overview', labels: []}]};
  expect(panelRows(scene, 2)[0].start_frame).toBe(50);
  expect(scene.entrances![0].start_frame).toBe(30);
});

describe.each(['youtube_long', 'vertical_clip'] as const)('authored panels in %s', format => {
  it('shows a real two-row lab worksheet, focuses AST later and retains ALT units', () => {
    const scene: Scene = {...base, entrances: [
      {text: 'ALT\t240 U/L\tGiới hạn trên 40 U/L', start_frame: 0},
      {text: 'Phép tính\t240 U/L ÷ 40 U/L\t= 6 lần', start_frame: 75},
      {text: 'AST\tChỉ số trên phiếu\tGiới hạn trên và đơn vị riêng', start_frame: 150},
    ]};
    clock.frame = 0;
    const early = render(WhiteboardScene, scene, format);
    expect(early).toContain('data-worksheet="true"');
    expect(early).toContain('240 U/L');
    expect(early).not.toContain('Chỉ số trên phiếu');
    clock.frame = 170;
    const late = render(WhiteboardScene, scene, format);
    for (const text of ['240 U/L', '40 U/L', '= 6 lần', 'AST', 'Giới hạn trên và đơn vị riêng']) expect(late).toContain(text);
    expect(late).toContain('data-active-row="2"');
    expect(late).toContain('data-leader="2"');
    if (format === 'vertical_clip') {
      expect(late).toContain('aria-label="Phụ đề đang đọc"');
    } else {
      expect(late).not.toContain('aria-label="Phụ đề đang đọc"');
    }
  });

  it('changes the mechanism meaning with each authored idea without modifying narration', () => {
    const scene: Scene = {...base, visual: 'anatomy_animation',
      anatomy: {subject: 'liver_organ', state: 'normal', severity: 0, motion: 'Sơ đồ định vị.'},
      entrances: [{text: 'Tìm nguyên nhân\tVirus B, C', start_frame: 0},
        {text: 'Cách xử lý\tTùy nguyên nhân', start_frame: 150}]};
    clock.frame = 10;
    expect(render(AnatomyScene, scene, format)).toContain('Virus B, C');
    clock.frame = 175;
    const html = render(AnatomyScene, scene, format);
    expect(html).toContain('Tùy nguyên nhân');
    expect(html).not.toContain('Virus B, C');
    expect(html).toContain('data-authored-step="1"');
  });

  it('shows a medication timeline and lab sheet instead of a cell, driven by resolved word beats', () => {
    const scene: Scene = {...base, visual: 'process_animation', on_screen_text: 'Dòng thời gian dùng thuốc',
      anatomy: {subject: 'hepatocyte_sinusoid_unit', state: 'normal', severity: 0, motion: 'Đối chiếu hồ sơ.'},
      entrances: [
        {text: 'Ngày …/…\tBắt đầu uống\tTên thuốc / viên tự mua', start_frame: 0},
        {text: 'Ngày …/…\tNgừng / đổi liều\tGhi nếu nhớ', start_frame: 100},
        {text: 'Ngày …/…\tLần thử máu\tPhiếu xét nghiệm: ALT / AST', start_frame: 200},
        {text: 'Đối chiếu\tTrước hay sau?\tThứ tự thời gian chưa chứng minh nhân quả', start_frame: 300}],
      beats: [0, 110, 220, 330].map((start_frame, i) => ({at: i, start_frame, focus: 'overview', labels: []}))};
    for (const [frame, row] of [[109, 0], [110, 1], [220, 2], [330, 3]]) {
      clock.frame = frame;
      const html = render(ProcessScene, scene, format);
      expect(html).toContain(`data-active-row="${row}"`);
      expect(html).not.toContain('data-layer="hepatocyte-membrane"');
      if (row === 3) {
        expect(html).toContain('Thứ tự thời gian chưa chứng minh nhân quả');
        expect(html).toContain('Phiếu xét nghiệm: ALT / AST');
      }
    }
  });

  it('paces source-card ideas from entrances while retaining immutable source metadata', () => {
    const scene: Scene = {...base, visual: 'source_card', claim_id: 'E04', source_marker: '[8]',
      source_card: {source_id: 'fixture', title: 'Source fixture', journal: 'Fixture', year: 2017,
        pmid: null, doi: 'fixture-id', interpretation: 'Diễn giải giữ nguyên trong dữ liệu.'},
      entrances: [{text: 'Men giảm nhẹ\tChưa rõ lợi ích', start_frame: 0},
        {text: 'Không thay khám\tTìm nguyên nhân', start_frame: 180}]};
    clock.frame = 210;
    const html = render(SourceCardScene, scene, format);
    expect(html).toContain('data-authored-step="1"');
    expect(html).toContain('Tìm nguyên nhân');
    expect(html).toContain('Source fixture');
    expect(html).toContain('fixture-id');
    expect(scene.source_card?.interpretation).toBe('Diễn giải giữ nguyên trong dữ liệu.');
  });
});

describe('R5 policy: reject implicit tab layout and require explicit VnLabSheet', () => {
  const tabbedScene: Scene = {
    ...base,
    id: 'R5-TAB',
    visual: 'process_animation',
    anatomy: {subject: 'hepatocyte_sinusoid_unit', state: 'normal', severity: 0, motion: 'Đối chiếu.'},
    entrances: [
      {text: 'ALT\t240 U/L\tGiới hạn trên 40 U/L', start_frame: 0},
      {text: 'AST\t180 U/L\tGiới hạn trên 40 U/L', start_frame: 120},
    ],
  };

  it('rejects tab-delimited entrances in panelRows, AuthoredWorksheet, WhiteboardScene, and MechanismScene under r5_v1', () => {
    expect(() => panelRows(tabbedScene, 3, 'r5_v1')).toThrow(/R5-TAB.*tab layout/i);
    expect(() =>
      renderToStaticMarkup(
        <LayoutContext.Provider value={LAYOUTS.youtube_long}>
          <AuthoredWorksheet scene={tabbedScene} frame={0} qualityProfile="r5_v1" />
        </LayoutContext.Provider>,
      ),
    ).toThrow(/R5-TAB.*AuthoredWorksheet/i);
    expect(() =>
      renderToStaticMarkup(
        <LayoutContext.Provider value={LAYOUTS.youtube_long}>
          <WhiteboardScene scene={{...tabbedScene, visual: 'whiteboard'}} qualityProfile="r5_v1" />
        </LayoutContext.Provider>,
      ),
    ).toThrow(/R5-TAB.*tab layout/i);
    expect(() =>
      renderToStaticMarkup(
        <LayoutContext.Provider value={LAYOUTS.youtube_long}>
          <MechanismScene scene={tabbedScene} kind="process" qualityProfile="r5_v1" />
        </LayoutContext.Provider>,
      ),
    ).toThrow(/R5-TAB.*tab layout/i);
  });

  it('renders a lab sheet in R5 only when the shot explicitly declares VnLabSheet', () => {
    const labScene: Scene = {
      ...base,
      id: 'R5-LAB',
      on_screen_text: 'Phiếu xét nghiệm minh họa',
      resolved_shots: [
        {
          id: 'SH-LAB',
          kind: 'story',
          tier: null,
          component: 'VnLabSheet',
          asset_paths: [],
          question_ids: ['Q1'],
          long_shot_reason: null,
          start_frame: 0,
          end_frame: 180,
          actions: [],
          text_windows: [
            {
              kind: 'lab_sheet',
              text: 'ALT | 240 | U/L | < 40 | H',
              claim_ids: ['C01'],
              exception_reason: null,
              start_frame: 0,
              end_frame: 180,
            },
          ],
        },
      ],
    };
    const html = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <R5ShotScene scene={labScene} frame={20} />
      </LayoutContext.Provider>,
    );
    expect(html).toContain('data-r5-component="VnLabSheet"');
    expect(html).toContain('240');
    expect(html).toContain('U/L');
    expect(html).toContain('data-lab-flag="H"');
    expect(html).not.toContain('data-worksheet="true"');
  });
});
