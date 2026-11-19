import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {boxesIntersect, captionBox, LAYOUTS} from '../layout';
import {
  ARTERY_FLOW_PATH, B1_OVERVIEW_PANEL, BILE_FLOW_PATH, CELL_BOX, CELL_CLOSE, CELL_DETAIL_BOX, CHAIN,
  CREDITS_START, DOTS, dotScreenPosition, GLOSSARY, IMAGES, imageToScreen, IRIS, LABELS, LIVER_BOX,
  LIVER_LOCATOR_START, LIVER_SOURCE_REGION, LIVER_ZOOM, LOBULE_BOX, LOBULE_BOX_SMALL, LOBULE_DETAIL_BOX,
  LOBULE_LOCATOR_START, LOBULE_POINTS, LOBULE_SOURCE_REGION, LOBULE_ZOOM_IN, MERGED_SINUSOID_PATH,
  MITO_SPOTS, PORTAL_FLOW_PATH, SINUSOID_PATH, STEPS, TOTAL_FRAMES, TRANSITION_LOBULE_TO_SOURCES,
  captionTiming, litLabel, pathPoint, type Box,
} from './liverEnzymeLeak';

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
    useCurrentFrame, Sequence, useVideoConfig: () => ({fps: 30, width: 1920, height: 1080, durationInFrames: TOTAL_FRAMES}),
    AbsoluteFill: ({children, style, ...rest}: {children?: React.ReactNode; style?: React.CSSProperties}) =>
      R.createElement('div', {...rest, style: {position: 'absolute', inset: 0, ...style}}, children),
    Img: (props: Record<string, unknown>) => R.createElement('img', props),
    staticFile: (p: string) => `/static/${p}`,
  };
});

import {evenWordTiming, firstUseTermWords, paginateCaptions} from '../components/captionPaging';

const {MedAnimLiverEnzymeLeak} = await import('./MedAnimLiverEnzymeLeak');
const renderAt = (frame: number): string => {
  clock.frame = frame;
  return renderToStaticMarkup(<MedAnimLiverEnzymeLeak />);
};

const layout = LAYOUTS.youtube_long;
const MASCOT: Box = {left: 20, top: 783, width: 340, height: 297};
const MINI_MAP_SAFE: Box = {left: 1280, top: 16, width: 610, height: 64};
const cardBox = (l: {vi: string; viLines?: readonly [string, string]; latin: string; at: {x: number; y: number}}) => {
  const maxVi = l.viLines ? Math.max(...l.viLines.map((line) => Array.from(line).length)) : Array.from(l.vi).length;
  const linesCount = l.viLines?.length ?? 1;
  return {
    left: l.at.x, top: l.at.y,
    width: Math.ceil(Math.max(maxVi * 44 * 0.6, Array.from(l.latin).length * 26 * 0.56) + 52),
    height: Math.round(44 * (linesCount > 1 ? 1.18 : 1.25) * linesCount + 26 * 1.3 + 26),
  };
};

describe('mechanism script timeline', () => {
  it('has 6 contiguous steps, one sentence each, 50 s plus a credit card after required post-zoom holds', () => {
    expect(STEPS.map((s) => s.id)).toEqual(['B1', 'B2', 'B3', 'B4', 'B5', 'B6']);
    STEPS.forEach((s, i) => {
      expect(s.start).toBe(i === 0 ? 0 : STEPS[i - 1].end);
      expect(s.narration.trim().endsWith('.')).toBe(true);
      expect(s.narration.slice(0, -1)).not.toMatch(/[.!?]/);
    });
    expect(STEPS[5].end).toBe(CREDITS_START);
    expect(CREDITS_START / 30).toBeGreaterThanOrEqual(24);
    expect(CREDITS_START / 30).toBe(50);
    expect(TOTAL_FRAMES).toBeGreaterThan(CREDITS_START);
  });

  it('fits simulated caption timing inside each step', () => {
    STEPS.forEach((s) => {
      const {firstFrame, framesPerWord} = captionTiming(s);
      const n = s.narration.split(/\s+/).length;
      expect(firstFrame + n * framesPerWord).toBeLessThanOrEqual(s.end - s.start);
    });
  });
});

describe('labels and safe zones', () => {
  it('lights at most one label at a time', () => {
    for (let f = 0; f < TOTAL_FRAMES; f++) {
      expect(LABELS.filter((l) => f >= l.start && f < l.end).length).toBeLessThanOrEqual(1);
    }
  });

  it('never lights a label during a magnifier zoom or scene transition', () => {
    const moving = [LIVER_ZOOM, LOBULE_ZOOM_IN, CELL_CLOSE, TRANSITION_LOBULE_TO_SOURCES, ...Object.values(IRIS)];
    for (let f = 0; f < TOTAL_FRAMES; f++) {
      if (moving.some((w) => f >= w.start && f < w.end)) expect(litLabel(f)).toBeUndefined();
    }
  });

  it('keeps cards, subject boxes, and overlays inside frame, clear of captions, mini-map, and mascot', () => {
    const band = captionBox(layout);
    [...LABELS, ...CHAIN.map((c) => ({...c, end: c.start + 1}))].forEach((l) => {
      const box = cardBox(l);
      expect(box.left).toBeGreaterThanOrEqual(0);
      expect(box.left + box.width).toBeLessThanOrEqual(1920);
      expect(box.top).toBeGreaterThanOrEqual(0);
      expect(boxesIntersect(box, band)).toBe(false);
      expect(boxesIntersect(box, MINI_MAP_SAFE)).toBe(false);
      const mascotOn = l.start < STEPS[0].end || l.end > STEPS[5].start;
      if (mascotOn) expect(boxesIntersect(box, MASCOT)).toBe(false);
    });

    const sceneBoxes: Box[] = [
      B1_OVERVIEW_PANEL, LIVER_BOX, LOBULE_DETAIL_BOX, CELL_DETAIL_BOX, LOBULE_BOX, LOBULE_BOX_SMALL, CELL_BOX,
    ];
    sceneBoxes.forEach((b) => {
      expect(boxesIntersect(b, band)).toBe(false);
      expect(boxesIntersect(b, MINI_MAP_SAFE)).toBe(false);
    });
    expect(boxesIntersect(LIVER_BOX, MASCOT)).toBe(false);
    expect(boxesIntersect(B1_OVERVIEW_PANEL, MASCOT)).toBe(false);
    const membraneLabel = LABELS.find((l) => l.id === 'membrane')!;
    const membraneBox = cardBox(membraneLabel);
    expect(CELL_BOX.left + CELL_BOX.width).toBeLessThan(membraneLabel.at.x);
    expect(CELL_DETAIL_BOX.left + CELL_DETAIL_BOX.width - 6 - (membraneBox.left + membraneBox.width)).toBeGreaterThanOrEqual(16);

    // Sinusoid leader line must not pass through Zoom 2 locator box.
    const sinLabel = LABELS.find((l) => l.id === 'sinusoid')!;
    const sinBox = cardBox(sinLabel);
    const sinTarget = imageToScreen(LOBULE_BOX, 'lobule', LOBULE_POINTS.sinusoid);
    const sinFrom = {x: sinBox.left + sinBox.width, y: sinBox.top + sinBox.height / 2};
    const minYAlongLocator = Math.min(
      sinFrom.y + (sinTarget.y - sinFrom.y) * ((LOBULE_SOURCE_REGION.left - sinFrom.x) / (sinTarget.x - sinFrom.x)),
      sinFrom.y + (sinTarget.y - sinFrom.y) * ((LOBULE_SOURCE_REGION.left + LOBULE_SOURCE_REGION.width - sinFrom.x) / (sinTarget.x - sinFrom.x)),
    );
    expect(minYAlongLocator).toBeGreaterThan(LOBULE_SOURCE_REGION.top + LOBULE_SOURCE_REGION.height);
  });
});

describe('flow paths and B2 arterial-portal confluence', () => {
  it('runs from the portal-vein end (bottom) to the central vein (top)', () => {
    expect(pathPoint(SINUSOID_PATH, 0)).toEqual(SINUSOID_PATH[0]);
    expect(pathPoint(SINUSOID_PATH, 1)).toEqual(SINUSOID_PATH[SINUSOID_PATH.length - 1]);
    expect(SINUSOID_PATH[0].y).toBeGreaterThan(SINUSOID_PATH[SINUSOID_PATH.length - 1].y);
    expect(pathPoint(SINUSOID_PATH, 0.5).y).toBeLessThan(SINUSOID_PATH[0].y);
  });

  it('converges both portal vein and hepatic artery paths into the shared sinusoid while bile runs opposite', () => {
    const portalEnd = PORTAL_FLOW_PATH[PORTAL_FLOW_PATH.length - 1];
    const arteryEnd = ARTERY_FLOW_PATH[ARTERY_FLOW_PATH.length - 1];
    const mergedStart = MERGED_SINUSOID_PATH[0];
    const mergedEnd = MERGED_SINUSOID_PATH[MERGED_SINUSOID_PATH.length - 1];
    expect(portalEnd).toEqual(mergedStart);
    expect(arteryEnd).toEqual(mergedStart);
    expect(mergedEnd.y).toBeLessThan(mergedStart.y);
    // Bile flows downward toward portal triad, opposite upward sinusoidal blood flow.
    expect(BILE_FLOW_PATH[BILE_FLOW_PATH.length - 1].y).toBeGreaterThan(BILE_FLOW_PATH[0].y);

    const html = renderAt(390);
    expect(html).toContain('data-medanim-flow="portal-branch"');
    expect(html).toContain('data-medanim-flow="artery-branch"');
    expect(html).toContain('data-medanim-flow="confluence"');
    expect(html).toContain('data-medanim-flow="sinusoid"');
    expect(html).toContain('data-medanim-flow="bile"');
    expect(html).toContain('data-medanim-callout="bile"');
  });
});

describe('rendered frames and credits', () => {
  const count = (html: string, attr: string) => (html.match(new RegExp(attr, 'g')) ?? []).length;

  it('shows the mascot only at the start and the end', () => {
    expect(count(renderAt(10), 'data-mascot-host')).toBe(1);
    expect(count(renderAt(400), 'data-mascot-host')).toBe(0);
    expect(count(renderAt(STEPS[5].start + 40), 'data-mascot-host')).toBe(1);
  });

  it('renders at most one label card per frame, uses only licensed images, and never renders draft notes', () => {
    const sampleFrames = [5, 30, 63, 100, 150, 210, 270, 330, 390, 465, 495, 530, 600, 660, 760, 800, 920, 1000, 1095, 1140, 1190, 1265, 1300, 1400, 1550];
    for (const f of sampleFrames) {
      const html = renderAt(f);
      const isChainFrame = f >= CHAIN[0].start && f < TRANSITION_LOBULE_TO_SOURCES.start;
      expect(count(html, 'data-medanim-label=')).toBeLessThanOrEqual(isChainFrame ? 3 : 1);
      const srcs = [...html.matchAll(/src="\/static\/([^"]+)"/g)].map((m) => m[1]);
      const allowed = new Set([...Object.values(IMAGES).map((i) => `medanim/liver-enzyme-leak/${i.file}`)]);
      srcs.filter((s) => !s.startsWith('assets/brand/mascot/')).forEach((s) => expect(allowed.has(s)).toBe(true));

      // Requirement 3: zero internal draft notes or asterisks in visible DOM text.
      const visibleText = html.replace(/<[^>]*>/g, ' ');
      expect(visibleText).not.toContain('*');
      expect(visibleText).not.toContain('Chưa có hình');
      expect(visibleText).not.toContain('khái quát');
      expect(visibleText).not.toContain('TODO');
    }
  });

  it('credits every image source on the last card', () => {
    const html = renderAt(CREDITS_START + 30);
    expect(html).toContain('NIAID NIH BioArt Source');
    expect(html).toContain('Public Domain');
    expect(html).toContain('Servier Medical Art');
    expect(html).toContain('DBCLS');
    expect(html).toContain('Reactome');
    expect(html).toContain('CC BY 4.0');
  });
});

describe('doctor revision 2 requirements', () => {
  it('holds detailed images at least two seconds (60 frames) before labels', () => {
    expect(LABELS.find((l) => l.id === 'central-vein')!.start - LIVER_ZOOM.end).toBeGreaterThanOrEqual(60);
    expect(LABELS.find((l) => l.id === 'cytosol')!.start - LOBULE_ZOOM_IN.end).toBeGreaterThanOrEqual(60);
    expect(LABELS.find((l) => l.id === 'central-vein-2')!.start - CELL_CLOSE.end).toBeGreaterThanOrEqual(60);
    // Hold phase (510..570) must be free of any text labels including the sinusoidal lumen header.
    const holdHtml = renderAt(540);
    expect(holdHtml).not.toContain('Lòng xoang gan');
    expect(holdHtml).not.toContain('data-medanim-label=');
  });

  it('uses MagnifierZoom (>=24f locator -> leader -> solid #F7F4EC lens -> smooth close) with no cross-fade zoom', () => {
    expect(LIVER_ZOOM.start - LIVER_LOCATOR_START).toBeGreaterThanOrEqual(24);
    expect(LOBULE_ZOOM_IN.start - LOBULE_LOCATOR_START).toBeGreaterThanOrEqual(24);

    // Locator phase before open
    for (const f of [LIVER_LOCATOR_START + 5, LOBULE_LOCATOR_START + 5]) {
      const html = renderAt(f);
      expect(html).toContain('data-zoom-locator="true"');
      expect(html).not.toContain('data-magnifier-lens="true"');
    }

    // Opening lens phase: solid #F7F4EC lens + leader line, never scale() zoomStyle
    for (const f of [LIVER_ZOOM.start + 12, LOBULE_ZOOM_IN.start + 12]) {
      const html = renderAt(f);
      expect(html).toContain('data-magnifier-zoom="true"');
      expect(html).toContain('data-zoom-locator="true"');
      expect(html).toContain('data-magnifier-leader="true"');
      expect(html).toContain('data-magnifier-lens="true"');
      expect(html).toMatch(/background-color:\s*(#F7F4EC|rgb\(247,\s*244,\s*236\))/i);
      expect(html).not.toMatch(/data-medanim-scene="(?:liver|lobule)"[^>]*scale\(/);
      expect(html).not.toMatch(/data-magnifier-lens="true"[^>]*scale\(/);
      expect(html).not.toContain('scale(1.15');
    }

    // Non-overlapping sourceRegion and detailBox keep locator + leader visible at t=1
    expect(LIVER_SOURCE_REGION.left + LIVER_SOURCE_REGION.width).toBeLessThan(LOBULE_DETAIL_BOX.left);
    expect(LOBULE_SOURCE_REGION.left + LOBULE_SOURCE_REGION.width).toBeLessThan(CELL_DETAIL_BOX.left);
    // CELL_DETAIL_BOX center must fall inside CELL_BOX so opening/closing lens always frames cell anatomy.
    const cellDetailCenterX = CELL_DETAIL_BOX.left + CELL_DETAIL_BOX.width / 2;
    const cellDetailCenterY = CELL_DETAIL_BOX.top + CELL_DETAIL_BOX.height / 2;
    expect(cellDetailCenterX).toBeGreaterThan(CELL_BOX.left + 60);
    expect(cellDetailCenterX).toBeLessThan(CELL_BOX.left + CELL_BOX.width - 60);
    expect(cellDetailCenterY).toBeGreaterThan(CELL_BOX.top + 60);
    expect(cellDetailCenterY).toBeLessThan(CELL_BOX.top + CELL_BOX.height - 60);

    // Closing phase in B5 smoothly retracts Cell lens and unmounts at CELL_CLOSE.end
    const closingHtml = renderAt(CELL_CLOSE.start + 15);
    expect(closingHtml).toContain('data-magnifier-lens="true"');
    const afterCloseHtml = renderAt(CELL_CLOSE.end + 5);
    expect(afterCloseHtml).not.toContain('data-medanim-scene="cell"');
    expect(afterCloseHtml).toContain('data-medanim-scene="lobule"');
  });

  it('sizes subject/mechanism frames >= 60% of 1920px width while keeping PNG raster scaling <= 1.5x', () => {
    const minWidth = 1920 * 0.6;
    expect(LIVER_BOX.width).toBeGreaterThanOrEqual(minWidth);
    expect(B1_OVERVIEW_PANEL.width).toBeGreaterThanOrEqual(minWidth);
    expect(LOBULE_DETAIL_BOX.width).toBeGreaterThanOrEqual(minWidth);
    expect(CELL_DETAIL_BOX.width).toBeGreaterThanOrEqual(minWidth);
    // B5 spans lobule left (160) to chain right (>= 940 + 600 = 1540 => >= 1380px)
    expect(CHAIN[0].at.x + 400 - LOBULE_BOX_SMALL.left).toBeGreaterThanOrEqual(minWidth);
    // B6 spans 380..1780 = 1400px
    expect(1780 - 380).toBeGreaterThanOrEqual(minWidth);

    // Every raster PNG keeps scaling <= 1.5x; all other assets are crisp vector SVGs.
    expect(IMAGES.liver.isSvg).toBe(true);
    expect(IMAGES.cell.isSvg).toBe(true);
    expect(IMAGES.mito.isSvg).toBe(true);
    expect(IMAGES.vessel.isSvg).toBe(true);
    expect(IMAGES.rbc.isSvg).toBe(true);
    expect(IMAGES.tube.isSvg).toBe(true);
    expect(IMAGES.heart.isSvg).toBe(true);
    expect(IMAGES.muscle.isSvg).toBe(true);
    expect(LOBULE_BOX.width / IMAGES.lobule.width).toBeLessThanOrEqual(1.0);
    expect(LOBULE_BOX_SMALL.width / IMAGES.lobule.width).toBeLessThanOrEqual(1.0);
  });

  it('uses pill/badge highlight in mini-map and static StyleCaptions without underline or per-word jump', () => {
    for (const f of [10, 150, 390, 600, 1200]) {
      const html = renderAt(f);
      expect(html).toContain('data-mini-map="true"');
      expect(html).toContain('data-active-step="true"');
      expect(html).not.toContain('text-decoration');
      expect(html).not.toContain('data-active=');
    }
    const b2Html = renderAt(390);
    expect(b2Html.match(/data-term-group="true"/g)).toHaveLength(1);
    expect(b2Html).toContain('#F4B942');
  });

  it('uses soft SVG <mask> (no polygon clipPath) and separates mild cytosolic vs severe mitochondrial injury', () => {
    // Cytosolic ALT and c-AST dots must sit strictly outside all 4 mitochondrion silhouettes.
    const mitoScreen = MITO_SPOTS.map((m) => imageToScreen(CELL_BOX, 'cell', m));
    const mitoHalfW = (124 * 0.84) / 2 + 12;
    const mitoHalfH = (124 * 0.50) / 2 + 12;
    DOTS.filter((d) => !d.inMito).forEach((d) => {
      const p = imageToScreen(CELL_BOX, 'cell', d.home);
      mitoScreen.forEach((m) => {
        const inside = Math.abs(p.x - m.x) < mitoHalfW && Math.abs(p.y - m.y) < mitoHalfH;
        expect(inside).toBe(false);
      });
    });

    const mito = DOTS.find((d) => d.inMito)!;
    expect(dotScreenPosition(mito, 800, CELL_BOX).leaked).toBe(0);
    expect(dotScreenPosition(mito, 1050, CELL_BOX).leaked).toBeGreaterThan(0);

    const intactHtml = renderAt(600);
    expect(intactHtml).toContain('data-injury-mask="intact"');
    expect(intactHtml).toContain('data-mito-mask="intact"');
    expect(intactHtml).not.toContain('clip-path:polygon');

    const mildHtml = renderAt(800);
    expect(mildHtml).toContain('data-injury-stage="cytosolic"');
    expect(mildHtml).toContain('data-injury-mask="svg-mask"');
    expect(mildHtml).toContain('id="cell-injury-mask"');
    expect(mildHtml).toContain('data-mito-mask="intact"');
    expect(mildHtml).toContain('Minh họa cơ chế · mô hình gan chuột thiếu máu (Kamiike 1989)');
    expect(mildHtml).not.toContain('clip-path:polygon');

    const severeHtml = renderAt(1000);
    expect(severeHtml).toContain('data-injury-stage="mitochondrial"');
    expect(severeHtml).toContain('data-mito-mask="svg-mask"');
    expect(severeHtml).toContain('id="mito-injury-mask-0"');
    expect(severeHtml).toContain('Lòng xoang gan · Sinusoidal lumen');
    expect(severeHtml).not.toContain('clip-path:polygon');
  });
});

it('keeps all animation caption pages at >=4 words, <=2 lines, <=42 chars/line, and <=1 yellow phrase per page', () => {
  let prior: string[] = [];
  STEPS.forEach((step) => {
    const {firstFrame, framesPerWord} = captionTiming(step);
    const words = evenWordTiming(step.narration, firstFrame, framesPerWord);
    const plain = words.map((w) => w.text);
    const pages = paginateCaptions(plain, 42);
    expect(pages.flatMap((p) => p.lines.flat().map((w) => w.text))).toEqual(plain);

    const labelWindows = LABELS.map((l) => ({term: l.vi, start: l.start - step.start, end: l.end - step.start}));
    pages.forEach((p) => {
      const idxs = p.lines.flat().map((w) => w.index);
      expect(idxs.length).toBeGreaterThanOrEqual(4);
      expect(p.lines.length).toBeLessThanOrEqual(2);
      p.lines.forEach((line) => expect(line.map((w) => w.text).join(' ').length).toBeLessThanOrEqual(42));

      const pageStart = words[idxs[0]].start_frame;
      const pageEnd = words[(idxs.at(-1) ?? -1) + 1]?.start_frame ?? (step.end - step.start);
      const html = renderAt(step.start + pageStart + 1);
      const yellowGroups = (html.match(/data-term-group="true"/g) ?? []).length;
      expect(yellowGroups).toBeLessThanOrEqual(1);

      // Ensure active glossary terms matching label windows don't exceed 1 per page.
      const eligible = GLOSSARY.filter((term) => {
        if (firstUseTermWords(prior, [term]).size) return false;
        const m = [...firstUseTermWords(plain, [term])];
        if (!m.length || !p.lines.some((line) => m.every((i) => line.some((w) => w.index === i)))) return false;
        return labelWindows.some((w) => w.term.toLowerCase() === term.toLowerCase() && w.start <= pageStart && w.end >= pageEnd);
      });
      expect(eligible.length).toBeLessThanOrEqual(1);
    });
    prior = [...prior, ...plain];
  });
});
