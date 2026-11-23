import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext} from '../layout';
import type {Scene} from '../types';
import {
  isScientificHepaticSubject,
  SCIENTIFIC_HEPATIC_SUBJECTS,
  ScientificHepaticArtwork,
} from './ScientificHepaticArtwork';
import {SplitClinicalWorksheetStage} from './SplitClinicalWorksheetStage';

const clock = vi.hoisted(() => ({frame: 60}));
vi.mock('remotion', async (original) => ({
  ...(await original<typeof import('remotion')>()),
  AbsoluteFill: 'div',
  Img: 'img',
  staticFile: (p: string) => `/static/${p}`,
  useCurrentFrame: () => clock.frame,
  useVideoConfig: () => ({fps: 30, width: 1920, height: 1080}),
}));

describe('ScientificHepaticArtwork', () => {
  it('renders all 7 hepatic subjects using NIAID/Servier/DBCLS/Reactome assets and proper Vietnamese labels', () => {
    expect(SCIENTIFIC_HEPATIC_SUBJECTS).toHaveLength(7);
    const expectedFiles: Record<(typeof SCIENTIFIC_HEPATIC_SUBJECTS)[number], string[]> = {
      liver_organ: ['niaid-liver-230.svg'],
      liver_lobule: ['servier-liver-lobule.png', 'dbcls-hepatic-lobule.svg'],
      hepatocyte_sinusoid_unit: ['niaid-hepatocyte-203.svg', 'niaid-blood-vessel-55.svg', 'niaid-red-blood-cell-442.svg', 'niaid-blood-vial-52.svg'],
      alt_ast_tissue_distribution: ['niaid-liver-230.svg', 'reactome-muscle-R-ICO-014108.svg', 'niaid-heart-228.svg'],
      hepatic_synthesis_and_bile: ['niaid-hepatocyte-203.svg', 'niaid-mitochondria-352.svg', 'niaid-blood-vessel-55.svg'],
      hepatic_fibrosis_section: ['niaid-hepatocyte-203.svg', 'niaid-blood-vessel-55.svg'],
      hepatic_toxic_injury: ['niaid-hepatocyte-203.svg', 'niaid-mitochondria-352.svg', 'niaid-blood-vessel-55.svg'],
    };

    for (const subject of SCIENTIFIC_HEPATIC_SUBJECTS) {
      expect(isScientificHepaticSubject(subject)).toBe(true);
      const html = renderToStaticMarkup(
        <ScientificHepaticArtwork
          subject={subject}
          state="diseased"
          severity={0.75}
          cueProgress={{leak: 1, toxic: 1, scar: 1}}
        />,
      );
      expect(html).toContain(`data-scientific-artwork="${subject}"`);
      for (const file of expectedFiles[subject]) {
        expect(html).toContain(`/static/medanim/liver-enzyme-leak/${file}`);
      }
      expect(html).not.toContain('LSEC có cửa sổ');
      expect(html).not.toContain('khoang Disse');
      if (
        subject === 'hepatocyte_sinusoid_unit' ||
        subject === 'hepatic_toxic_injury' ||
        subject === 'hepatic_synthesis_and_bile' ||
        subject === 'hepatic_fibrosis_section'
      ) {
        expect(html).toContain('data-layer="hepatocyte-membrane"');
        expect(html).toContain('Dòng máu xoang gan');
      }
    }
  });

  it('supports comparison (normal vs diseased) and timelapse modes', () => {
    const compHtml = renderToStaticMarkup(
      <ScientificHepaticArtwork subject="hepatocyte_sinusoid_unit" mode="comparison" state="diseased" severity={0.8} />,
    );
    expect(compHtml).toContain('data-comparison-panel="normal"');
    expect(compHtml).toContain('data-comparison-panel="diseased"');
    expect(compHtml).toContain('Bình thường');
    expect(compHtml).toContain('Tổn thương');

    clock.frame = 90;
    const tlHtml = renderToStaticMarkup(
      <ScientificHepaticArtwork
        subject="hepatic_fibrosis_section"
        mode="timelapse"
        state="diseased"
        severity={0.8}
        durationFrames={180}
      />,
    );
    expect(tlHtml).toContain('data-scientific-mode="timelapse"');
    expect(tlHtml).toContain('data-layer="fibrous-septa"');
  });
});

describe('SplitClinicalWorksheetStage', () => {
  const worksheetRows = [
    {text: 'Ngày 1\tUống thảo dược\tChế phẩm không rõ nhãn', start_frame: 0},
    {text: 'Ngày 14\tThử máu\tALT và AST tăng cao', start_frame: 40},
    {text: 'Xử lý\tNgưng & khám\tKhông tự uống thêm', start_frame: 80},
  ];

  it('shows FLUX illustration alongside progressive worksheet when whiteboard asset exists', () => {
    clock.frame = 50;
    const scene: Scene = {
      id: 'S02',
      start_frame: 0,
      duration_frames: 150,
      narration: 'Đối chiếu thuốc.',
      on_screen_text: 'Thuốc kê đơn: không tự ngưng',
      visualTakeaway: 'Hình minh họa kê đơn cùng phiếu theo dõi.',
      visual: 'process_animation',
      anatomy: {subject: 'liver_organ', state: 'normal', severity: 0, motion: 'overview'},
      entrances: worksheetRows,
      visual_assets: [{path: 'assets/illustrations/prescription-review.png', role: 'whiteboard'}],
    };
    const html = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <SplitClinicalWorksheetStage scene={scene} />
      </LayoutContext.Provider>,
    );
    expect(html).toContain('data-split-visual="flux"');
    expect(html).toContain('/static/assets/illustrations/prescription-review.png');
    expect(html).toContain('data-worksheet="true"');
    expect(html).toContain('data-active-row="1"');
  });

  it('shows ScientificHepaticArtwork alongside worksheet when no FLUX illustration is attached', () => {
    clock.frame = 90;
    const scene: Scene = {
      id: 'S23',
      start_frame: 0,
      duration_frames: 150,
      narration: 'Đối chiếu diễn tiến.',
      on_screen_text: 'Theo dõi xét nghiệm',
      visual: 'process_animation',
      anatomy: {subject: 'hepatic_toxic_injury', state: 'diseased', severity: 0.6, motion: 'injury'},
      entrances: worksheetRows,
      visual_assets: [],
    };
    const html = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <SplitClinicalWorksheetStage scene={scene} />
      </LayoutContext.Provider>,
    );
    expect(html).toContain('data-split-visual="anatomy"');
    expect(html).toContain('data-scientific-artwork="hepatic_toxic_injury"');
    expect(html).toContain('data-worksheet="true"');
    expect(html).toContain('data-active-row="2"');
  });
});
