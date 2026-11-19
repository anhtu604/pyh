import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {boxesIntersect, captionBox, LAYOUTS} from '../layout';
import {MEDANIM_DURATION_FRAMES, MEDANIM_FPS, MEDANIM_MASCOT_BOX, labelCardSize, stepCaptionTiming, type Box, type LabelSpec, type MedAnimStep} from './medAnimShared';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', async () => {
  const R = await import('react');
  const Offset = R.createContext(0);
  const useCurrentFrame = () => clock.frame - R.useContext(Offset);
  const Sequence = ({from = 0, durationInFrames = Infinity, children}: {from?: number; durationInFrames?: number; children: React.ReactNode}) => {
    const parent = R.useContext(Offset);
    const local = clock.frame - parent;
    if (local < from || local >= from + durationInFrames) return null;
    return R.createElement(Offset.Provider, {value: parent + from}, children);
  };
  return {
    useCurrentFrame,
    Sequence,
    useVideoConfig: () => ({fps: MEDANIM_FPS, width: 1920, height: 1080, durationInFrames: MEDANIM_DURATION_FRAMES}),
    AbsoluteFill: ({children, style, ...rest}: {children?: React.ReactNode; style?: React.CSSProperties}) =>
      R.createElement('div', {...rest, style: {position: 'absolute', inset: 0, ...style}}, children),
    Img: (props: Record<string, unknown>) => R.createElement('img', props),
    staticFile: (p: string) => `/static/${p}`,
  };
});

import {evenWordTiming, paginateCaptions} from '../components/captionPaging';
import * as gas from './alveolarGasExchange';
import * as phago from './macrophagePhagocytosis';
import * as plaque from './atheroscleroticPlaqueRupture';

const {MedAnimAlveolarGasExchange} = await import('./MedAnimAlveolarGasExchange');
const {MedAnimMacrophagePhagocytosis} = await import('./MedAnimMacrophagePhagocytosis');
const {MedAnimAtheroscleroticPlaqueRupture} = await import('./MedAnimAtheroscleroticPlaqueRupture');

const MINI_MAP_SAFE: Box = {left: 1120, top: 16, width: 762, height: 68};
const band = captionBox(LAYOUTS.youtube_long);

type EntrySpec = {
  id: string;
  Component: React.FC;
  assetDir: string;
  steps: readonly MedAnimStep[];
  glossary: readonly string[];
  labels: readonly LabelSpec[];
  images: Record<string, {file: string; isSvg: boolean}>;
  zoomWindows: readonly {locatorStart: number; open: {start: number; end: number}; source: Box; detail: Box; firstLabelId: string}[];
  subjectBoxes: readonly Box[];
  creditNeedles: readonly string[];
  sampleFrames: readonly number[];
};

const ENTRIES: readonly EntrySpec[] = [
  {
    id: 'alveolar-gas-exchange',
    Component: MedAnimAlveolarGasExchange,
    assetDir: gas.ASSET_DIR,
    steps: gas.STEPS,
    glossary: gas.GLOSSARY,
    labels: gas.LABELS,
    images: gas.IMAGES,
    zoomWindows: [
      {
        locatorStart: gas.LUNG_LOCATOR_START,
        open: gas.LUNG_ZOOM,
        source: gas.LUNG_SOURCE_REGION,
        detail: gas.ALVEOLI_DETAIL_BOX,
        firstLabelId: 'alveoli',
      },
      {
        locatorStart: gas.ALVEOLI_LOCATOR_START,
        open: gas.ALVEOLI_ZOOM,
        source: gas.ALVEOLI_SOURCE_REGION,
        detail: gas.MEMBRANE_DETAIL_BOX,
        firstLabelId: 'membrane',
      },
    ],
    subjectBoxes: [gas.B1_PANEL, gas.ALVEOLI_DETAIL_BOX, gas.B2_PANEL, gas.MEMBRANE_DETAIL_BOX, gas.B4_STAGE_BOX],
    creditNeedles: ['NIAID NIH BioArt', 'Servier Medical Art', 'Reactome', '30969729', '23484070', '41590881'],
    sampleFrames: [10, 35, 62, 105, 160, 272, 300, 345, 405, 520, 640, 760, 860, 990],
  },
  {
    id: 'macrophage-phagocytosis',
    Component: MedAnimMacrophagePhagocytosis,
    assetDir: phago.ASSET_DIR,
    steps: phago.STEPS,
    glossary: phago.GLOSSARY,
    labels: phago.LABELS,
    images: phago.IMAGES,
    zoomWindows: [
      {
        locatorStart: phago.PRR_LOCATOR_START,
        open: phago.PRR_ZOOM,
        source: phago.PRR_SOURCE_REGION,
        detail: phago.PRR_DETAIL_BOX,
        firstLabelId: 'prr-pamp',
      },
      {
        locatorStart: phago.FUSION_LOCATOR_START,
        open: phago.FUSION_ZOOM,
        source: phago.FUSION_SOURCE_REGION,
        detail: phago.FUSION_DETAIL_BOX,
        firstLabelId: 'phagolysosome',
      },
    ],
    subjectBoxes: [phago.B1_PANEL, phago.PRR_DETAIL_BOX, phago.B2_PANEL, phago.FUSION_DETAIL_BOX, phago.B4_STAGE_BOX],
    creditNeedles: ['NIAID NIH BioArt', 'Bioicons', 'Reactome', '32582172', '12061891'],
    sampleFrames: [10, 35, 62, 105, 160, 290, 410, 502, 530, 575, 640, 790, 880, 990],
  },
  {
    id: 'atherosclerotic-plaque-rupture',
    Component: MedAnimAtheroscleroticPlaqueRupture,
    assetDir: plaque.ASSET_DIR,
    steps: plaque.STEPS,
    glossary: plaque.GLOSSARY,
    labels: plaque.LABELS,
    images: plaque.IMAGES,
    zoomWindows: [
      {
        locatorStart: plaque.CORONARY_LOCATOR_START,
        open: plaque.CORONARY_ZOOM,
        source: plaque.CORONARY_SOURCE_REGION,
        detail: plaque.INTIMA_DETAIL_BOX,
        firstLabelId: 'ldl-oxldl',
      },
    ],
    subjectBoxes: [plaque.B1_PANEL, plaque.INTIMA_DETAIL_BOX, plaque.ARTERY_STAGE_BOX],
    creditNeedles: ['NIAID NIH BioArt', 'Servier Medical Art', 'Reactome', '35328769', '36361701', '32052833'],
    sampleFrames: [10, 35, 62, 105, 160, 290, 410, 530, 640, 760, 840, 990],
  },
];

const renderAt = (Component: React.FC, frame: number): string => {
  clock.frame = frame;
  return renderToStaticMarkup(<Component />);
};

const cardBox = (l: LabelSpec): Box => ({left: l.at.x, top: l.at.y, ...labelCardSize(l)});

describe.each(ENTRIES)('PYH medanim "$id"', (entry) => {
  it('follows the 4-step 35s timeline cleanly and passes static StyleCaptions constraints', () => {
    expect(entry.steps.map((s) => s.id)).toEqual(['B1', 'B2', 'B3', 'B4']);
    let prior: string[] = [];
    entry.steps.forEach((s, i) => {
      expect(s.start).toBe(i === 0 ? 0 : entry.steps[i - 1].end);
      expect(s.narration.trim().endsWith('.')).toBe(true);
      const {firstFrame, framesPerWord} = stepCaptionTiming(s);
      const words = evenWordTiming(s.narration, firstFrame, framesPerWord);
      const plain = words.map((w) => w.text);
      expect(firstFrame + plain.length * framesPerWord).toBeLessThanOrEqual(s.end - s.start);

      const pages = paginateCaptions(plain, 42);
      expect(pages.length).toBeGreaterThanOrEqual(1);
      expect(pages.flatMap((p) => p.lines.flat().map((w) => w.text))).toEqual(plain);
      pages.forEach((page) => {
        const idxs = page.lines.flat().map((w) => w.index);
        expect(idxs.length).toBeGreaterThanOrEqual(4);
        expect(page.lines.length).toBeLessThanOrEqual(2);
        page.lines.forEach((line) => expect(line.map((w) => w.text).join(' ').length).toBeLessThanOrEqual(42));
        const pageStart = words[idxs[0]].start_frame;
        const html = renderAt(entry.Component, s.start + pageStart + 1);
        expect((html.match(/data-term-group="true"/g) ?? []).length).toBeLessThanOrEqual(1);
      });
      prior = [...prior, ...plain];
    });
    expect(entry.steps[3].end).toBe(960);
  });

  it('uses MagnifierZoom (>=24f locator -> >=60f post-zoom hold, non-overlapping source/detail) and renders clean scenes', () => {
    entry.zoomWindows.forEach((z) => {
      expect(z.open.start - z.locatorStart).toBeGreaterThanOrEqual(24);
      const lbl = entry.labels.find((l) => l.id === z.firstLabelId)!;
      expect(lbl.start - z.open.end).toBeGreaterThanOrEqual(60);
      expect(boxesIntersect(z.source, z.detail)).toBe(false);

      const locHtml = renderAt(entry.Component, z.locatorStart + 8);
      expect(locHtml).toContain('data-zoom-locator="true"');
      expect(locHtml).not.toContain('data-magnifier-lens="true"');

      const zoomHtml = renderAt(entry.Component, z.open.start + 12);
      expect(zoomHtml).toContain('data-magnifier-lens="true"');
      expect(zoomHtml).toMatch(/background-color:\s*(#F7F4EC|rgb\(247,\s*244,\s*236\))/i);
      expect(zoomHtml).not.toMatch(/data-magnifier-lens="true"[^>]*scale\(/);

      // Zero labels anywhere inside the 60f post-zoom hold.
      for (let f = z.open.end; f < z.open.end + 60; f++) {
        expect(entry.labels.filter((l) => f >= l.start && f < l.end)).toHaveLength(0);
      }
    });
  });

  it('keeps subjects >= 60% width, at most 1 label card, safe zones clear, licensed SVGs only, and zero draft slop', () => {
    entry.subjectBoxes.forEach((b) => {
      expect(b.width).toBeGreaterThanOrEqual(1920 * 0.6);
      expect(boxesIntersect(b, band)).toBe(false);
      expect(boxesIntersect(b, MINI_MAP_SAFE)).toBe(false);
    });

    for (let f = 0; f < MEDANIM_DURATION_FRAMES; f++) {
      expect(entry.labels.filter((l) => f >= l.start && f < l.end).length).toBeLessThanOrEqual(1);
    }

    entry.labels.forEach((l) => {
      const box = cardBox(l);
      expect(box.left).toBeGreaterThanOrEqual(0);
      expect(box.left + box.width).toBeLessThanOrEqual(1920);
      expect(box.top).toBeGreaterThanOrEqual(0);
      expect(boxesIntersect(box, band)).toBe(false);
      expect(boxesIntersect(box, MINI_MAP_SAFE)).toBe(false);
      const mascotOn = l.start < entry.steps[0].end || l.end > entry.steps[3].start;
      if (mascotOn) expect(boxesIntersect(box, MEDANIM_MASCOT_BOX)).toBe(false);
    });

    const allowed = new Set(Object.values(entry.images).map((img) => `${entry.assetDir}/${img.file}`));
    Object.values(entry.images).forEach((img) => expect(img.isSvg).toBe(true));

    entry.sampleFrames.forEach((f) => {
      const html = renderAt(entry.Component, f);
      expect((html.match(/data-medanim-label=/g) ?? []).length).toBeLessThanOrEqual(1);
      expect(html).not.toContain('text-decoration');
      expect(html).not.toContain('data-active=');
      const srcs = [...html.matchAll(/src="\/static\/([^"]+)"/g)].map((m) => m[1]);
      srcs.filter((s) => !s.startsWith('assets/brand/mascot/')).forEach((s) => expect(allowed.has(s)).toBe(true));
      const text = html.replace(/<[^>]*>/g, ' ');
      expect(text).not.toContain('*');
      expect(text).not.toContain('TODO');
      expect(text).not.toContain('Chưa có hình');
      expect(text).not.toContain('khái quát');
    });

    // Mascot visible only in B1, B4, Credits
    expect(renderAt(entry.Component, 12)).toContain('data-mascot-host');
    expect(renderAt(entry.Component, 390)).not.toContain('data-mascot-host');
    expect(renderAt(entry.Component, 590)).not.toContain('data-mascot-host');
    expect(renderAt(entry.Component, 760)).toContain('data-mascot-host');

    const creditsHtml = renderAt(entry.Component, 990);
    entry.creditNeedles.forEach((needle) => expect(creditsHtml).toContain(needle));
  });
});

describe('soft SVG masks in pathology and immunology mechanisms', () => {
  it('uses soft SVG <mask> (never polygon clipPath) for bacterial lysis and plaque fibrous-cap rupture', () => {
    const phagoHtml = renderAt(MedAnimMacrophagePhagocytosis, 860);
    expect(phagoHtml).toContain('data-digestion-mask="svg-mask"');
    expect(phagoHtml).toContain('id="lysis-mask"');
    expect(phagoHtml).not.toMatch(/clip-path:\s*polygon/i);

    const plaqueHtml = renderAt(MedAnimAtheroscleroticPlaqueRupture, 860);
    expect(plaqueHtml).toContain('data-rupture-mask="svg-mask"');
    expect(plaqueHtml).toContain('id="cap-rupture-mask"');
    expect(plaqueHtml).toContain('data-medanim-thrombus="active"');
    expect(plaqueHtml).not.toMatch(/clip-path:\s*polygon/i);
  });
});
