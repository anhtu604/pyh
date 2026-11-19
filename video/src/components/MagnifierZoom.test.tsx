import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {pyhColors} from '../style/pyhStyle';
import {MagnifierZoom, magnifierOverviewOpacity, type MagnifierBox} from './MagnifierZoom';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', () => ({useCurrentFrame: () => clock.frame}));

const sourceRegion: MagnifierBox = {left: 200, top: 300, width: 140, height: 100};
const detailBox: MagnifierBox = {left: 720, top: 80, width: 960, height: 740};
const locatorStart = 24;
const open = {start: 48, end: 78};
const close = {start: 200, end: 230};

const renderMagnifier = (
  frame: number,
  extra?: Partial<React.ComponentProps<typeof MagnifierZoom>>,
): string => {
  clock.frame = frame;
  return renderToStaticMarkup(
    <MagnifierZoom
      sourceRegion={sourceRegion}
      detailBox={detailBox}
      locatorStart={locatorStart}
      open={open}
      {...extra}
    >
      <div data-test-detail="true" style={{position: 'absolute', left: 900, top: 250}}>
        Detail
      </div>
    </MagnifierZoom>,
  );
};

const extractStyle = (html: string, attr: string): string => {
  const escaped = attr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const tagMatch = html.match(new RegExp(`<[^>]*${escaped}[^>]*>`));
  if (!tagMatch) throw new Error(`Missing element matching ${attr} in: ${html}`);
  const styleMatch = tagMatch[0].match(/style="([^"]*)"/);
  if (!styleMatch) throw new Error(`Missing style attribute on ${attr}: ${tagMatch[0]}`);
  return styleMatch[1];
};

const cssNumber = (style: string, prop: string): number => {
  const match = style.match(new RegExp(`(?:^|;)${prop}:(-?\\d+(?:\\.\\d+)?)px`));
  if (!match) throw new Error(`Missing px property "${prop}" in style: ${style}`);
  return Number.parseFloat(match[1]);
};

const extractLineCoords = (html: string): {x1: number; y1: number; x2: number; y2: number; stroke: string; strokeWidth: string} => {
  const tagMatch = html.match(/<line[^>]*data-magnifier-leader="true"[^>]*>/);
  if (!tagMatch) throw new Error(`Missing [data-magnifier-leader="true"] in: ${html}`);
  const tag = tagMatch[0];
  const attr = (name: string) => {
    const m = tag.match(new RegExp(`${name}="([^"]*)"`));
    if (!m) throw new Error(`Missing ${name} on ${tag}`);
    return m[1];
  };
  return {
    x1: Number.parseFloat(attr('x1')),
    y1: Number.parseFloat(attr('y1')),
    x2: Number.parseFloat(attr('x2')),
    y2: Number.parseFloat(attr('y2')),
    stroke: attr('stroke'),
    strokeWidth: attr('stroke-width'),
  };
};

describe('MagnifierZoom', () => {
  it('returns null before locatorStart', () => {
    expect(renderMagnifier(0)).toBe('');
    expect(renderMagnifier(locatorStart - 1)).toBe('');
  });

  it('shows only the teal locator around sourceRegion before open.start with smooth 12f fade', () => {
    const atStart = renderMagnifier(locatorStart);
    expect(atStart).toContain('data-magnifier-zoom="true"');
    expect(atStart).toContain('data-zoom-locator="true"');
    expect(atStart).not.toContain('data-magnifier-lens="true"');
    expect(atStart).not.toContain('data-magnifier-leader="true"');

    const startStyle = extractStyle(atStart, 'data-zoom-locator="true"');
    expect(cssNumber(startStyle, 'left')).toBe(sourceRegion.left);
    expect(cssNumber(startStyle, 'top')).toBe(sourceRegion.top);
    expect(cssNumber(startStyle, 'width')).toBe(sourceRegion.width);
    expect(cssNumber(startStyle, 'height')).toBe(sourceRegion.height);
    expect(startStyle).toContain(`border:4px solid ${pyhColors.accent}`);
    expect(startStyle).toContain('opacity:0');

    const midFadeStyle = extractStyle(renderMagnifier(locatorStart + 6), 'data-zoom-locator="true"');
    expect(midFadeStyle).toContain('opacity:0.5');

    const settledStyle = extractStyle(renderMagnifier(locatorStart + 12), 'data-zoom-locator="true"');
    expect(settledStyle).toContain('opacity:1');
    expect(cssNumber(settledStyle, 'border-radius')).toBeGreaterThan(0);
  });

  it('draws SVG leader line from sourceRegion edge to expanding lens edge without NaNs', () => {
    const atOpenStart = renderMagnifier(open.start);
    expect(atOpenStart).toContain('data-zoom-locator="true"');
    expect(atOpenStart).toContain('data-magnifier-leader="true"');
    const startLine = extractLineCoords(atOpenStart);
    expect(startLine.stroke).toBe(pyhColors.accent);
    expect(startLine.strokeWidth).toBe('4');

    const midHtml = renderMagnifier((open.start + open.end) / 2);
    const midLine = extractLineCoords(midHtml);
    expect(midLine.x1).toBeCloseTo(sourceRegion.left + sourceRegion.width, 1);
    expect(midLine.y1).toBeGreaterThanOrEqual(sourceRegion.top);
    expect(midLine.y1).toBeLessThanOrEqual(sourceRegion.top + sourceRegion.height);

    const settledHtml = renderMagnifier(open.end);
    const settledLine = extractLineCoords(settledHtml);
    expect(settledLine.stroke).toBe(pyhColors.ink);
    expect(settledLine.strokeWidth).toBe('4');
    expect(settledLine.x1).toBeCloseTo(sourceRegion.left + sourceRegion.width, 1);
    expect(settledLine.x2).toBeCloseTo(detailBox.left, 1);
    expect(settledLine.y2).toBeGreaterThanOrEqual(detailBox.top);
    expect(settledLine.y2).toBeLessThanOrEqual(detailBox.top + detailBox.height);
    expect(settledLine.x2).toBeGreaterThan(midLine.x2);
  });

  it('morphs lens with solid #F7F4EC background, opacity 1 (never cross-fades), and no bitmap scale', () => {
    const startLens = extractStyle(renderMagnifier(open.start), 'data-magnifier-lens="true"');
    expect(cssNumber(startLens, 'width')).toBe(140);
    expect(cssNumber(startLens, 'height')).toBe(140);
    expect(startLens).toContain('border-radius:50%');
    expect(startLens).toContain(`background-color:${pyhColors.background}`);
    expect(startLens).toContain('opacity:1');
    expect(startLens).toContain(`border:6px solid ${pyhColors.accent}`);

    const midHtml = renderMagnifier((open.start + open.end) / 2);
    const midLens = extractStyle(midHtml, 'data-magnifier-lens="true"');
    expect(cssNumber(midLens, 'width')).toBeCloseTo((140 + detailBox.width) / 2, 5);
    expect(cssNumber(midLens, 'height')).toBeCloseTo((140 + detailBox.height) / 2, 5);
    expect(midLens).toContain(`background-color:${pyhColors.background}`);
    expect(midLens).toContain('opacity:1');
    expect(midLens).toContain('border:6px solid #156B78');

    const settledHtml = renderMagnifier(open.end);
    const settledLens = extractStyle(settledHtml, 'data-magnifier-lens="true"');
    expect(cssNumber(settledLens, 'left')).toBe(detailBox.left);
    expect(cssNumber(settledLens, 'top')).toBe(detailBox.top);
    expect(cssNumber(settledLens, 'width')).toBe(detailBox.width);
    expect(cssNumber(settledLens, 'height')).toBe(detailBox.height);
    expect(cssNumber(settledLens, 'border-radius')).toBe(14);
    expect(settledLens).toContain('overflow:hidden');
    expect(settledLens).toContain(`background-color:${pyhColors.background}`);
    expect(settledLens).toContain('opacity:1');
    expect(settledLens).toContain(`border:6px solid ${pyhColors.ink}`);
    expect(settledHtml).not.toMatch(/scale\(/);

    const customRadiusLens = extractStyle(renderMagnifier(open.end, {detailRadius: 24}), 'data-magnifier-lens="true"');
    expect(cssNumber(customRadiusLens, 'border-radius')).toBe(24);
  });

  it('aligns inner 1920x1080 children coordinates exactly with screen coordinates at t = 1', () => {
    const html = renderMagnifier(open.end);
    const lensStyle = extractStyle(html, 'data-magnifier-lens="true"');
    const contentStyle = extractStyle(html, 'data-magnifier-content="true"');

    expect(cssNumber(contentStyle, 'width')).toBe(1920);
    expect(cssNumber(contentStyle, 'height')).toBe(1080);

    // Border-box lens places its absolute-child containing block inside the 6px border.
    const borderWidth = 6;
    const screenOriginX = cssNumber(lensStyle, 'left') + borderWidth + cssNumber(contentStyle, 'left');
    const screenOriginY = cssNumber(lensStyle, 'top') + borderWidth + cssNumber(contentStyle, 'top');
    expect(screenOriginX).toBe(0);
    expect(screenOriginY).toBe(0);

    // At midpoint t = 0.5, detailBox center stays centered inside the moving lens.
    const midHtml = renderMagnifier((open.start + open.end) / 2);
    const midLens = extractStyle(midHtml, 'data-magnifier-lens="true"');
    const midContent = extractStyle(midHtml, 'data-magnifier-content="true"');
    const detailCenterX = detailBox.left + detailBox.width / 2;
    const detailCenterY = detailBox.top + detailBox.height / 2;
    const midLensCenterX = cssNumber(midLens, 'left') + cssNumber(midLens, 'width') / 2;
    const midLensCenterY = cssNumber(midLens, 'top') + cssNumber(midLens, 'height') / 2;
    expect(cssNumber(midLens, 'left') + borderWidth + cssNumber(midContent, 'left') + detailCenterX).toBeCloseTo(midLensCenterX, 5);
    expect(cssNumber(midLens, 'top') + borderWidth + cssNumber(midContent, 'top') + detailCenterY).toBeCloseTo(midLensCenterY, 5);
  });

  it('retracts smoothly during close window and returns null at and after close.end', () => {
    const heldLens = extractStyle(renderMagnifier(close.start, {close}), 'data-magnifier-lens="true"');
    expect(cssNumber(heldLens, 'width')).toBe(detailBox.width);

    const midCloseHtml = renderMagnifier((close.start + close.end) / 2, {close});
    const midCloseLens = extractStyle(midCloseHtml, 'data-magnifier-lens="true"');
    expect(cssNumber(midCloseLens, 'width')).toBeCloseTo((140 + detailBox.width) / 2, 5);
    expect(midCloseLens).toContain('opacity:1');
    expect(midCloseLens).toContain(`background-color:${pyhColors.background}`);

    expect(renderMagnifier(close.end, {close})).toBe('');
    expect(renderMagnifier(close.end + 20, {close})).toBe('');
  });

  it('handles zero-span windows and concentric boxes without NaN', () => {
    const html = renderMagnifier(50, {
      sourceRegion: {left: 400, top: 300, width: 120, height: 120},
      detailBox: {left: 160, top: 90, width: 600, height: 540},
      locatorStart: 50,
      open: {start: 50, end: 50},
    });
    const line = extractLineCoords(html);
    expect(Number.isFinite(line.x1)).toBe(true);
    expect(Number.isFinite(line.y1)).toBe(true);
    expect(Number.isFinite(line.x2)).toBe(true);
    expect(Number.isFinite(line.y2)).toBe(true);
  });
});

describe('magnifierOverviewOpacity', () => {
  it('dims smoothly from 1 to 0.16 on open and restores to 1 on close', () => {
    expect(magnifierOverviewOpacity(0, open, close)).toBe(1);
    expect(magnifierOverviewOpacity(open.start, open, close)).toBe(1);
    expect(magnifierOverviewOpacity((open.start + open.end) / 2, open, close)).toBeCloseTo(0.58, 6);
    expect(magnifierOverviewOpacity(open.end, open, close)).toBeCloseTo(0.16, 6);
    expect(magnifierOverviewOpacity(close.start, open, close)).toBeCloseTo(0.16, 6);
    expect(magnifierOverviewOpacity((close.start + close.end) / 2, open, close)).toBeCloseTo(0.58, 6);
    expect(magnifierOverviewOpacity(close.end, open, close)).toBe(1);
    expect(magnifierOverviewOpacity(close.end + 50, open, close)).toBe(1);
  });

  it('supports custom dimmedOpacity and open-ended magnifiers without close', () => {
    expect(magnifierOverviewOpacity(open.end + 100, open)).toBeCloseTo(0.16, 6);
    expect(magnifierOverviewOpacity(open.end, open, undefined, 0.25)).toBeCloseTo(0.25, 6);
    expect(magnifierOverviewOpacity(open.end, open, undefined, 0)).toBe(0);
  });
});
