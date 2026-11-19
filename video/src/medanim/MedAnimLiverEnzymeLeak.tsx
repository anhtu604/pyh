import React from 'react';
import {AbsoluteFill, Img, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {MascotHost} from '../components/MascotHost';
import {MagnifierZoom, magnifierOverviewOpacity} from '../components/MagnifierZoom';
import {StyleCaptions} from '../components/StyleCaptions';
import {evenWordTiming} from '../components/captionPaging';
import {LAYOUTS, LayoutContext, useLayout} from '../layout';
import {clamp01, formatOf, hexToRgba, pyhColors, pyhStroke, pyhTiming, pyhType, smoothstep} from '../style/pyhStyle';
import {
  ARTERY_FLOW_PATH, ARTERY_WIDE, ATTRIBUTION, BILE_FLOW_PATH, CELL_BOX, CELL_CLOSE, CELL_POINTS,
  CLOSING_POSES, CREDITS_START, DOTS, DOTS_APPEAR, GLOSSARY, IMAGES,
  INJURY_RING, LITERATURE, LIVER_LOCATOR_START,
  LIVER_ZOOM, LOBULE_LOCATOR_START, LOBULE_POINTS,
  LOBULE_ZOOM_IN, MERGED_SINUSOID_PATH, MITO_SPOTS, OPENING_POSES, PORTAL_FLOW_PATH, SINUSOID_PATH,
  SINUSOID_WIDE, STEPS, TOTAL_FRAMES, TRANSITION_LOBULE_TO_SOURCES, asset, captionTiming, dotScreenPosition,
  imageToScreen, lobuleBoxAt, pathPoint, sceneChain, sceneGeometry, sceneLabels,
  type Box, type ImageId, type Label, type Point, type SceneFormat,
} from './liverEnzymeLeak';

const DOT_COLOR = {ALT: pyhColors.accent, AST: pyhColors.alert} as const;
const latinFontFor = (format: SceneFormat) => (format === 'landscape' ? 26 : 28);

const Picture: React.FC<{image: ImageId; box: Box; opacity?: number; style?: React.CSSProperties}> = ({image, box, opacity = 1, style}) =>
  <Img src={staticFile(asset(IMAGES[image].file))} data-medanim-image={image}
    style={{position: 'absolute', left: box.left, top: box.top, width: box.width, height: box.height, opacity, ...style}} />;

const fadeIn = (frame: number, start: number, frames: number = pyhTiming.labelFadeFrames) => smoothstep((frame - start) / frames);

const center = (b: Box): Point => ({x: b.left + b.width / 2, y: b.top + b.height / 2});
const toSvgPath = (pts: readonly Point[]) => `M${pts.map((p) => `${p.x} ${p.y}`).join(' L')}`;

// ------------------------------------------------------------------------------------------------
const LiverScene: React.FC<{format: SceneFormat}> = ({format}) => {
  const frame = useCurrentFrame();
  const g = sceneGeometry(format);
  const opacity = fadeIn(frame, 0, 10) * magnifierOverviewOpacity(frame, LIVER_ZOOM);
  const captionStyle: React.CSSProperties = format === 'landscape'
    ? {left: 1180, top: 680, width: 360, textAlign: 'right'}
    : {left: 90, top: 930, width: 900, textAlign: 'center'};
  return <AbsoluteFill data-medanim-scene="liver" style={{opacity}}>
    <Picture image="liver" box={g.liverBox} />
    <div style={{
      position: 'absolute', ...captionStyle,
      fontFamily: pyhType.fontFamily, color: pyhColors.ink,
    }}>
      <div style={{fontSize: pyhType[format].label, fontWeight: pyhType.labelWeight}}>Gan (Hepar)</div>
      <div style={{fontSize: format === 'landscape' ? 28 : 32, fontWeight: pyhType.bodyWeight, marginTop: 6}}>
        Cấu tạo từ nhiều tiểu thùy
      </div>
    </div>
  </AbsoluteFill>;
};

const flowDots = (frame: number, start: number, count: number, travel: number, box: Box, path: readonly Point[] = SINUSOID_PATH) =>
  Array.from({length: count}, (_, i) => {
    const t = (frame - start - i * 7) / travel;
    if (t < 0 || t > 1) return null;
    const p = imageToScreen(box, 'lobule', pathPoint(path, t));
    return {i, p, t};
  }).filter((d): d is {i: number; p: Point; t: number} => d !== null);

const LobuleScene: React.FC<{format: SceneFormat; inMagnifier?: boolean}> = ({format, inMagnifier = false}) => {
  const frame = useCurrentFrame();
  const g = sceneGeometry(format);
  const box = lobuleBoxAt(frame, format);
  const overviewOpacity = inMagnifier ? 1 : magnifierOverviewOpacity(frame, LOBULE_ZOOM_IN, CELL_CLOSE);
  const exitOpacity = !inMagnifier && frame >= TRANSITION_LOBULE_TO_SOURCES.start
    ? 1 - smoothstep((frame - TRANSITION_LOBULE_TO_SOURCES.start) / 6) : 1;

  const portalPts = PORTAL_FLOW_PATH.map((p) => imageToScreen(box, 'lobule', p));
  const arteryPts = ARTERY_FLOW_PATH.map((p) => imageToScreen(box, 'lobule', p));
  const mergedPts = MERGED_SINUSOID_PATH.map((p) => imageToScreen(box, 'lobule', p));
  const fullSinusoidPts = SINUSOID_PATH.map((p) => imageToScreen(box, 'lobule', p));
  const bilePts = BILE_FLOW_PATH.map((p) => imageToScreen(box, 'lobule', p));
  const confluence = mergedPts[0];

  const portalDraw = clamp01((frame - 260) / 36);
  const arteryDraw = clamp01((frame - 314) / 36);
  const mergedDraw = clamp01((frame - 368) / 20);
  const bileDraw = clamp01((frame - 368) / 22);
  const b5Draw = clamp01((frame - 1120) / 16);

  const showB2Flow = frame >= 260 && frame < 507;
  const showB5Flow = frame >= 1120 && frame < 1250;
  const rbcSize = box.width * 0.036;
  const portalRbcs = flowDots(frame, 372, 5, 28, box, SINUSOID_WIDE);
  const arteryRbcs = flowDots(frame, 376, 3, 24, box, ARTERY_WIDE);
  const b5Rbcs = flowDots(frame, 1126, 4, 26, box, SINUSOID_WIDE);
  const enzymes = flowDots(frame, 1130, 5, 40, box);
  const rbcFade = (u: number) => 1 - clamp01((u - 0.8) / 0.2);

  const panelBox: Box = format === 'landscape' ? {left: 72, top: 86, width: 1776, height: 784} : g.lobuleDetailBox;
  const insetBox = format === 'landscape'
    ? {outer: {left: 1320, top: 300, width: 280, height: 270}, inner: {width: 280, height: 220}, img: {left: -115, top: -38, width: 510, height: 382}}
    : {outer: {left: 72, top: 1030, width: 250, height: 242}, inner: {width: 250, height: 195}, img: {left: -102, top: -34, width: 454, height: 340}};
  const bileCallout: React.CSSProperties = format === 'landscape'
    ? {left: 1210, top: 685, width: 575, fontSize: 28}
    : {left: 72, top: 1336, width: 936, fontSize: 32, textAlign: 'center'};

  return <AbsoluteFill data-medanim-scene="lobule" style={{opacity: overviewOpacity * exitOpacity}}>
    {!inMagnifier && frame < 1214 ? <div data-medanim-panel="b2-lobule" style={{
      position: 'absolute', ...panelBox,
      borderRadius: pyhStroke.radius, border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
      backgroundColor: pyhColors.background, boxSizing: 'border-box',
    }} /> : null}
    <Picture image="lobule" box={box} />
    {inMagnifier ? <div data-medanim-inset="hex-lobule" style={{
      position: 'absolute', ...insetBox.outer,
      borderRadius: pyhStroke.radius, border: `3px solid ${hexToRgba(pyhColors.ink, 0.35)}`,
      backgroundColor: pyhColors.background, boxSizing: 'border-box', overflow: 'hidden',
    }}>
      <div style={{
        position: 'relative', ...insetBox.inner, overflow: 'hidden',
      }}>
        <Img src={staticFile(asset(IMAGES.lobuleHex.file))} data-medanim-image="lobuleHex"
          style={{position: 'absolute', ...insetBox.img}} />
      </div>
      <div style={{
        textAlign: 'center', fontSize: 22, fontWeight: 700,
        fontFamily: pyhType.fontFamily, color: pyhColors.ink, marginTop: 4,
      }}>Mặt cắt lục giác</div>
    </div> : null}
    <svg width={g.frame.width} height={g.frame.height} style={{position: 'absolute', left: 0, top: 0}}>
      <defs>
        <marker id="blood-direction" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
          <path d="M0 0 L5 2.5 L0 5" fill={pyhColors.accent} />
        </marker>
        <marker id="bile-direction" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0 0 L6 3 L0 6" fill={pyhColors.ink} />
        </marker>
      </defs>
      {showB2Flow ? <>
        <path data-medanim-flow="portal-branch" d={toSvgPath(portalPts)} fill="none" stroke={pyhColors.accent}
          strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" opacity={0.9}
          pathLength={1} strokeDasharray={1} strokeDashoffset={1 - portalDraw} />
        {arteryDraw > 0 ? <path data-medanim-flow="artery-branch" d={toSvgPath(arteryPts)} fill="none" stroke={pyhColors.accent}
          strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" opacity={0.9}
          pathLength={1} strokeDasharray={1} strokeDashoffset={1 - arteryDraw} /> : null}
        {arteryDraw > 0.85 ? <circle data-medanim-flow="confluence" cx={confluence.x} cy={confluence.y} r={7}
          fill={pyhColors.accent} stroke={pyhColors.ink} strokeWidth={2.5} /> : null}
        {mergedDraw > 0 ? <path data-medanim-flow="sinusoid" d={toSvgPath(mergedPts)}
          markerEnd={mergedDraw > 0.85 ? 'url(#blood-direction)' : undefined}
          fill="none" stroke={pyhColors.accent} strokeWidth={7} strokeLinecap="round" strokeLinejoin="round"
          opacity={0.95} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - mergedDraw} /> : null}
      </> : null}
      {showB5Flow ? <path data-medanim-flow="sinusoid" d={toSvgPath(fullSinusoidPts)} markerEnd="url(#blood-direction)"
        fill="none" stroke={pyhColors.accent} strokeWidth={6} strokeLinecap="round" strokeLinejoin="round"
        opacity={0.85} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - b5Draw} /> : null}
      {frame >= 1120 ? enzymes.map(({i, p}) => <circle key={`e${i}`} cx={p.x} cy={p.y} r={7}
        fill={i % 2 ? DOT_COLOR.AST : DOT_COLOR.ALT} stroke={pyhColors.ink} strokeWidth={2} />) : null}
      {frame >= 368 && frame < 480 ? <path data-medanim-flow="bile" d={toSvgPath(bilePts)} fill="none"
        stroke={pyhColors.ink} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round"
        pathLength={1} strokeDasharray={1} strokeDashoffset={1 - bileDraw}
        markerEnd={bileDraw > 0.85 ? 'url(#bile-direction)' : undefined} /> : null}
    </svg>
    {frame >= 368 && frame < 480 ? <div data-medanim-callout="bile" style={{
      position: 'absolute', ...bileCallout, padding: '12px 20px', boxSizing: 'border-box',
      border: `3px solid ${pyhColors.ink}`, borderRadius: 12, backgroundColor: pyhColors.background,
      fontWeight: 700, fontFamily: pyhType.fontFamily, color: pyhColors.ink,
      opacity: fadeIn(frame, 368, 10),
    }}>Mật → khoảng cửa (ngược chiều máu)</div> : null}
    {[...portalRbcs, ...arteryRbcs, ...b5Rbcs].map(({i, p, t}, idx) => <Picture key={`r${idx}-${i}`} image="rbc" opacity={rbcFade(t)}
      box={{left: p.x - rbcSize / 2, top: p.y - rbcSize / 2, width: rbcSize, height: rbcSize}} />)}
  </AbsoluteFill>;
};

const CellScene: React.FC<{format: SceneFormat}> = ({format}) => {
  const frame = useCurrentFrame();
  const g = sceneGeometry(format);
  const cellBox = g.cellBox;
  const scaleRatio = cellBox.width / CELL_BOX.width;
  const mitoBox = Math.round(124 * scaleRatio);
  const rbcSize = format === 'landscape' ? 60 : 56;
  const lane = Array.from({length: 7}, (_, i) => {
    const x = format === 'landscape'
      ? 765 + ((frame * 3.0 + i * 155) % 1060)
      : 90 + ((frame * 2.8 + i * 145) % 900);
    return {i, x};
  });
  const ring = imageToScreen(cellBox, 'cell', CELL_POINTS.injury);
  const ringT = fadeIn(frame, INJURY_RING);
  const cellBreach = frame >= INJURY_RING ? smoothstep((frame - INJURY_RING) / 16) : 0;
  const mitoBreach = frame >= 850 ? smoothstep((frame - 850) / 16) : 0;
  const uiFade = frame >= CELL_CLOSE.start - 8 ? 1 - smoothstep((frame - (CELL_CLOSE.start - 8)) / 8) : 1;
  const primaryMito = imageToScreen(cellBox, 'cell', MITO_SPOTS[0]);
  const mitoFocusT = frame >= 850 ? smoothstep((frame - 850) / 14) : 0;

  const vesselOuter = format === 'landscape'
    ? {left: 722, top: 134, width: 1138, height: 158}
    : {left: 68, top: 174, width: 944, height: 150};
  const vesselInner = format === 'landscape'
    ? {left: 318, top: -168, transform: 'scale(2.64, 0.72) rotate(-11deg)'}
    : {left: 222, top: -172, transform: 'scale(2.24, 0.70) rotate(-11deg)'};
  const lumenHeader = format === 'landscape'
    ? {left: 730, top: 98, fontSize: 28}
    : {left: 72, top: 132, fontSize: 30};

  return <AbsoluteFill data-medanim-scene="cell">
    {/* Preload SVGs via Remotion Img so delayRender awaits image load before frame capture. */}
    <Img src={staticFile(asset(IMAGES.cell.file))} aria-hidden="true"
      style={{position: 'absolute', left: 0, top: 0, width: 1, height: 1, opacity: 0, pointerEvents: 'none'}} />
    <Img src={staticFile(asset(IMAGES.mito.file))} aria-hidden="true"
      style={{position: 'absolute', left: 0, top: 0, width: 1, height: 1, opacity: 0, pointerEvents: 'none'}} />

    {/* Clean provisional blood-vessel SVG aligned horizontally above the hepatocyte (open_issues: not fenestrated LSEC). */}
    <div style={{position: 'absolute', ...vesselOuter, overflow: 'hidden', borderRadius: 10}}>
      <Img src={staticFile(asset(IMAGES.vessel.file))} data-medanim-image="vessel"
        style={{
          position: 'absolute', width: 500, height: 500, transformOrigin: '50% 50%', ...vesselInner,
        }} />
    </div>
    {frame >= 570 ? <div style={{
      position: 'absolute', ...lumenHeader, fontWeight: 700,
      color: pyhColors.ink, fontFamily: pyhType.fontFamily,
      opacity: fadeIn(frame, 570, 12) * uiFade,
    }}>Lòng xoang gan · Sinusoidal lumen</div> : null}

    {lane.map(({i, x}) => <Picture key={i} image="rbc"
      box={{left: x - rbcSize / 2, top: g.laneY - rbcSize * 0.56 + (i % 2) * 14, width: rbcSize, height: rbcSize}} />)}

    {/* Natural SVG <mask> at the microvilli / sinusoidal apical membrane (replaces hard polygon clip). */}
    <svg viewBox={`0 0 ${IMAGES.cell.width} ${IMAGES.cell.height}`} data-medanim-image="cell"
      data-injury-mask={cellBreach > 0 ? 'svg-mask' : 'intact'}
      style={{position: 'absolute', left: cellBox.left, top: cellBox.top, width: cellBox.width, height: cellBox.height}}>
      <defs>
        <filter id="cell-injury-blur" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="8" />
        </filter>
        <radialGradient id="cell-injury-grad" cx="50%" cy="52%" r="50%">
          <stop offset="0%" stopColor="black" stopOpacity="1" />
          <stop offset="62%" stopColor="black" stopOpacity="0.95" />
          <stop offset="85%" stopColor="black" stopOpacity="0.45" />
          <stop offset="100%" stopColor="black" stopOpacity="0" />
        </radialGradient>
        <mask id="cell-injury-mask" maskUnits="userSpaceOnUse" x="0" y="0" width={IMAGES.cell.width} height={IMAGES.cell.height}>
          <rect x="0" y="0" width={IMAGES.cell.width} height={IMAGES.cell.height} fill="white" />
          {cellBreach > 0 ? <g filter="url(#cell-injury-blur)" opacity={cellBreach}>
            <path d="M 910 -10 C 930 15, 918 55, 935 88 C 948 112, 964 132, 982 136 C 1002 138, 1020 116, 1030 92 C 1044 58, 1034 18, 1052 -10 Z"
              fill="black" />
            <ellipse cx={982} cy={92} rx={68 * cellBreach} ry={52 * cellBreach} fill="url(#cell-injury-grad)" />
          </g> : null}
        </mask>
      </defs>
      <image href={staticFile(asset(IMAGES.cell.file))} width={IMAGES.cell.width} height={IMAGES.cell.height}
        mask={cellBreach > 0 ? 'url(#cell-injury-mask)' : undefined} />
    </svg>

    {/* Mitochondria vector SVGs with natural SVG <mask> focal disruption during severe/necrotic stage (frame >= 850). */}
    {MITO_SPOTS.map((p, i) => {
      const s = imageToScreen(cellBox, 'cell', p);
      const maskId = `mito-injury-mask-${i}`;
      const blurId = `mito-injury-blur-${i}`;
      const gradId = `mito-injury-grad-${i}`;
      return <svg key={i} viewBox={`0 0 ${IMAGES.mito.width} ${IMAGES.mito.height}`} data-medanim-image="mito"
        data-mito-mask={mitoBreach > 0 ? 'svg-mask' : 'intact'}
        style={{position: 'absolute', left: s.x - mitoBox / 2, top: s.y - mitoBox / 2, width: mitoBox, height: mitoBox}}>
        <defs>
          <filter id={blurId} x="-25%" y="-25%" width="150%" height="150%">
            <feGaussianBlur stdDeviation="7" />
          </filter>
          <radialGradient id={gradId} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="black" stopOpacity="1" />
            <stop offset="60%" stopColor="black" stopOpacity="0.92" />
            <stop offset="100%" stopColor="black" stopOpacity="0" />
          </radialGradient>
          <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width={IMAGES.mito.width} height={IMAGES.mito.height}>
            <rect x="0" y="0" width={IMAGES.mito.width} height={IMAGES.mito.height} fill="white" />
            {mitoBreach > 0 ? <g filter={`url(#${blurId})`} opacity={mitoBreach}>
              <path d="M 208 122 C 228 144, 240 168, 266 178 C 292 184, 314 166, 326 146 C 300 130, 250 118, 208 122 Z" fill="black" />
              <ellipse cx={268} cy={154} rx={56 * mitoBreach} ry={34 * mitoBreach} fill={`url(#${gradId})`} />
            </g> : null}
          </mask>
        </defs>
        <image href={staticFile(asset(IMAGES.mito.file))} width={IMAGES.mito.width} height={IMAGES.mito.height}
          mask={mitoBreach > 0 ? `url(#${maskId})` : undefined} />
      </svg>;
    })}

    <svg width={g.frame.width} height={g.frame.height} style={{position: 'absolute', left: 0, top: 0}}>
      {DOTS.map((dot, i) => {
        const appear = fadeIn(frame, DOTS_APPEAR[dot.enzyme] + dot.delay, 10);
        if (appear <= 0) return null;
        const {p} = dotScreenPosition(dot, frame, cellBox, g.laneY);
        const radius = format === 'landscape' ? (dot.inMito ? 8 : 10) : (dot.inMito ? 10 : 12);
        return <circle key={i} data-enzyme={dot.enzyme} cx={p.x} cy={p.y} r={radius} opacity={appear}
          fill={DOT_COLOR[dot.enzyme]} stroke={pyhColors.ink} strokeWidth={2.5} />;
      })}
      {frame >= INJURY_RING ? <ellipse data-medanim-emphasis="injury" cx={ring.x} cy={ring.y}
        rx={52 * scaleRatio} ry={40 * scaleRatio} fill="none"
        stroke={pyhColors.accent} strokeWidth={pyhStroke.ringWidth} pathLength={1} strokeDasharray={1}
        strokeDashoffset={1 - ringT} opacity={uiFade} /> : null}
      {frame >= 850 ? <ellipse data-medanim-emphasis="mito-injury" cx={primaryMito.x} cy={primaryMito.y}
        rx={68 * scaleRatio} ry={40 * scaleRatio} fill="none"
        stroke={pyhColors.alert} strokeWidth={4} pathLength={1} strokeDasharray={1}
        strokeDashoffset={1 - mitoFocusT} opacity={uiFade} /> : null}
    </svg>

    {format === 'landscape' ? <InjuryCallouts format="landscape" /> : null}

    {frame >= DOTS_APPEAR.ALT ? <Legend frame={frame} format={format} opacity={uiFade} /> : null}
  </AbsoluteFill>;
};

const InjuryCallouts: React.FC<{format: SceneFormat}> = ({format}) => {
  const frame = useCurrentFrame();
  if (frame < 740 || frame >= CELL_CLOSE.start) return null;
  const uiFade = frame >= CELL_CLOSE.start - 8 ? 1 - smoothstep((frame - (CELL_CLOSE.start - 8)) / 8) : 1;
  const opacity = fadeIn(frame, 740, 10) * uiFade;
  const stageBox = format === 'landscape'
    ? {left: 1446, top: 468, width: 416, fontSize: 24}
    : {left: 60, top: 1320, width: 960, fontSize: 30};
  const scopeBox = format === 'landscape'
    ? {left: 1446, top: 588, width: 416, fontSize: 22}
    : {left: 60, top: 1446, width: 960, fontSize: 26};
  return <>
    <div data-injury-stage={frame < 850 ? 'cytosolic' : 'mitochondrial'} style={{
      position: 'absolute', ...stageBox, boxSizing: 'border-box',
      padding: '12px 16px', borderRadius: 12, border: `3px solid ${pyhColors.ink}`, backgroundColor: pyhColors.background,
      fontFamily: pyhType.fontFamily, fontWeight: 800, lineHeight: 1.3, color: pyhColors.ink, opacity,
    }}>
      {frame < 850 ? 'Tổn thương nhẹ: men bào tương (ALT, c-AST) thoát ra' : 'Tổn thương nặng / hoại tử: m-AST ty thể thoát thêm'}
    </div>
    <div data-medanim-scope="kamiike1989" style={{
      position: 'absolute', ...scopeBox, boxSizing: 'border-box',
      padding: '10px 16px', borderRadius: 10, border: `2px solid ${hexToRgba(pyhColors.ink, 0.35)}`,
      backgroundColor: pyhColors.background, fontFamily: pyhType.fontFamily, fontWeight: 600,
      lineHeight: 1.3, color: pyhColors.ink, opacity,
    }}>Minh họa cơ chế · mô hình gan chuột thiếu máu (Kamiike 1989)</div>
  </>;
};

const Legend: React.FC<{frame: number; format: SceneFormat; opacity?: number}> = ({frame, format, opacity = 1}) => {
  const pos = format === 'landscape' ? {left: 1640, top: 702} : {left: 710, top: 1030};
  const row = (enzyme: 'ALT' | 'AST', start: number) => <div style={{display: 'flex', alignItems: 'center', gap: 16,
    opacity: fadeIn(frame, start)}}>
    <span style={{width: 30, height: 30, borderRadius: 15, backgroundColor: DOT_COLOR[enzyme], border: `3px solid ${pyhColors.ink}`}} />
    {enzyme}
  </div>;
  return <div data-medanim-legend="true" style={{position: 'absolute', ...pos, display: 'flex', flexDirection: 'column', gap: 10,
    padding: '10px 18px', border: `${pyhStroke.width}px solid ${pyhColors.ink}`, borderRadius: pyhStroke.radius, backgroundColor: pyhColors.background,
    fontFamily: pyhType.fontFamily, fontWeight: pyhType.labelWeight, fontSize: pyhType[format].label, color: pyhColors.ink, opacity}}>
    {row('ALT', DOTS_APPEAR.ALT)}{row('AST', DOTS_APPEAR.AST)}
  </div>;
};

type SourceItem = {
  id: string; image: ImageId; vi: string; roleNote: string;
  panel: Box; imageBox: Box; textBox: Box; textAlign: 'center' | 'left';
};

const sourcesFor = (format: SceneFormat): SourceItem[] => format === 'landscape'
  ? [
    {id: 'liver', image: 'liver', vi: 'Gan', roleNote: 'ALT + AST',
      panel: {left: 380, top: 110, width: 450, height: 730},
      imageBox: {left: 410, top: 245, width: 390, height: 390 * 309.24 / 456.16},
      textBox: {left: 405, top: 690, width: 400, height: 120}, textAlign: 'center'},
    {id: 'muscle', image: 'muscle', vi: 'Cơ vân', roleNote: 'Nguồn AST chính',
      panel: {left: 855, top: 110, width: 450, height: 730},
      imageBox: {left: 885, top: 260, width: 390, height: 390 * 104 / 174},
      textBox: {left: 880, top: 690, width: 400, height: 120}, textAlign: 'center'},
    {id: 'heart', image: 'heart', vi: 'Cơ tim', roleNote: 'Nguồn AST chính',
      panel: {left: 1330, top: 110, width: 450, height: 730},
      imageBox: {left: 1427, top: 190, width: 360 * 289.44 / 406.42, height: 360},
      textBox: {left: 1355, top: 690, width: 400, height: 120}, textAlign: 'center'},
  ]
  : [
    {id: 'liver', image: 'liver', vi: 'Gan', roleNote: 'ALT + AST',
      panel: {left: 72, top: 120, width: 936, height: 350},
      imageBox: {left: 112, top: 173, width: 360, height: 360 * 309.24 / 456.16},
      textBox: {left: 530, top: 230, width: 430, height: 140}, textAlign: 'left'},
    {id: 'muscle', image: 'muscle', vi: 'Cơ vân', roleNote: 'Nguồn AST chính',
      panel: {left: 72, top: 500, width: 936, height: 350},
      imageBox: {left: 117, top: 571, width: 350, height: 350 * 104 / 174},
      textBox: {left: 530, top: 605, width: 430, height: 140}, textAlign: 'left'},
    {id: 'heart', image: 'heart', vi: 'Cơ tim', roleNote: 'Nguồn AST chính',
      panel: {left: 72, top: 880, width: 936, height: 390},
      imageBox: {left: 189, top: 931, width: 288 * 289.44 / 406.42, height: 288},
      textBox: {left: 530, top: 995, width: 430, height: 140}, textAlign: 'left'},
  ];

const SourcesScene: React.FC<{format: SceneFormat}> = ({format}) => {
  const frame = useCurrentFrame();
  const g = sceneGeometry(format);
  const t = frame - TRANSITION_LOBULE_TO_SOURCES.end;
  const enterOpacity = smoothstep((frame - (TRANSITION_LOBULE_TO_SOURCES.start + 6)) / 6);
  const sources = sourcesFor(format);
  const riseSpan = format === 'landscape' ? 140 : 70;
  return <AbsoluteFill data-medanim-scene="sources" style={{backgroundColor: pyhColors.background, opacity: enterOpacity}}>
    {sources.map((s) => <React.Fragment key={s.id}>
      <div data-medanim-panel={`b6-${s.id}`} style={{
        position: 'absolute', ...s.panel,
        borderRadius: pyhStroke.radius, border: `3px solid ${hexToRgba(pyhColors.ink, 0.22)}`,
        backgroundColor: pyhColors.background, boxSizing: 'border-box',
      }} />
      <Picture image={s.image} box={s.imageBox} />
      <div style={{position: 'absolute', left: s.textBox.left, top: s.textBox.top, width: s.textBox.width, textAlign: s.textAlign,
        fontFamily: pyhType.fontFamily, fontWeight: pyhType.labelWeight, fontSize: pyhType[format].label, color: pyhColors.ink}}>
        {s.vi}
        {s.id !== 'liver' && frame >= 1390 ? <div data-medanim-underline={s.id} style={{
          margin: s.textAlign === 'center' ? '4px auto 0' : '6px 0 0', height: pyhStroke.underlineWidth,
          width: 140 * smoothstep((frame - 1390) / 12), borderRadius: 4, backgroundColor: pyhColors.alert,
        }} /> : null}
        <div style={{fontSize: format === 'landscape' ? 24 : 28, fontWeight: pyhType.bodyWeight, marginTop: 8, opacity: 0.85}}>{s.roleNote}</div>
      </div>
    </React.Fragment>)}
    <svg width={g.frame.width} height={g.frame.height} style={{position: 'absolute', left: 0, top: 0}}>
      {sources.flatMap((s) => {
        const c = center(s.imageBox);
        const dots: React.ReactNode[] = [];
        for (let i = 0; i < 6; i++) {
          const k = ((t - i * 9) % 60 + 60) % 60 / 60;
          if (t - i * 9 < 0) continue;
          const isAlt = s.id === 'liver' ? i % 2 === 0 : i === 0;
          const x = c.x + (i - 2.5) * (s.imageBox.width / 7);
          dots.push(<circle key={`${s.id}${i}`} data-enzyme={isAlt ? 'ALT' : 'AST'} cx={x} cy={s.imageBox.top + s.imageBox.height * 0.5 - k * riseSpan}
            r={10} opacity={1 - k * 0.8} fill={isAlt ? DOT_COLOR.ALT : DOT_COLOR.AST} stroke={pyhColors.ink} strokeWidth={2} />);
        }
        return dots;
      })}
    </svg>
  </AbsoluteFill>;
};

const Credits: React.FC<{format: SceneFormat}> = ({format}) => {
  const frame = useCurrentFrame();
  const text = {fontFamily: pyhType.fontFamily, color: pyhColors.ink} as const;
  const box = format === 'landscape' ? {left: 410, top: 72, width: 1430} : {left: 72, top: 108, width: 936};
  const attrSize = format === 'landscape' ? 30 : 28;
  const litSize = format === 'landscape' ? 27 : 26;
  return <AbsoluteFill data-medanim-scene="credits" style={{backgroundColor: pyhColors.background, opacity: fadeIn(frame, 0)}}>
    <div style={{position: 'absolute', ...box}}>
      <div style={{...text, fontWeight: pyhType.titleWeight, fontSize: pyhType[format].title}}>Nguồn hình và y văn</div>
      <div style={{...text, fontWeight: pyhType.bodyWeight, fontSize: attrSize, lineHeight: 1.4, marginTop: 22}}>
        {ATTRIBUTION.map((l) => <div key={l}>{l}</div>)}
      </div>
      <div style={{...text, fontWeight: pyhType.bodyWeight, fontSize: litSize, lineHeight: 1.4, marginTop: 24}}>
        {LITERATURE.map((l) => <div key={l}>{l}</div>)}
      </div>
    </div>
  </AbsoluteFill>;
};

// ------------------------------------------------------------------------------------------------
export const cardSize = (l: {vi: string; viLines?: readonly [string, string]; latin: string}, format: SceneFormat = 'landscape') => {
  const labelFont = pyhType[format].label;
  const latinFont = latinFontFor(format);
  const maxViChars = l.viLines
    ? Math.max(...l.viLines.map((line) => Array.from(line).length))
    : Array.from(l.vi).length;
  const linesCount = l.viLines?.length ?? 1;
  return {
    width: Math.ceil(Math.max(maxViChars * labelFont * 0.6, Array.from(l.latin).length * latinFont * 0.56) + 52),
    height: Math.round(labelFont * (linesCount > 1 ? 1.18 : 1.25) * linesCount + latinFont * 1.3 + 26),
  };
};

const attachPoint = (card: Box, target: Point): Point => {
  if (target.x > card.left + card.width) return {x: card.left + card.width, y: card.top + card.height / 2};
  if (target.x < card.left) return {x: card.left, y: card.top + card.height / 2};
  return target.y < card.top ? {x: card.left + card.width / 2, y: card.top} : {x: card.left + card.width / 2, y: card.top + card.height};
};

export const labelTarget = (label: Label, frame: number, format: SceneFormat = 'landscape'): Point => {
  const t = label.target;
  if ('screen' in t) return t.screen;
  const g = sceneGeometry(format);
  return t.image === 'lobule' ? imageToScreen(lobuleBoxAt(frame, format), 'lobule', t.point) : imageToScreen(g.cellBox, 'cell', t.point);
};

const Card: React.FC<{vi: string; viLines?: readonly [string, string]; latin: string; at: Point; format: SceneFormat; opacity: number; rise?: number}> = ({
  vi, viLines, latin, at, format, opacity, rise = 0,
}) => {
  const size = cardSize({vi, viLines, latin}, format);
  const labelFont = pyhType[format].label;
  const latinFont = latinFontFor(format);
  return <div data-medanim-label={vi} style={{position: 'absolute', left: at.x, top: at.y, ...size, boxSizing: 'border-box', opacity,
    transform: `translateY(${rise}px) scale(${pyhTiming.labelStartScale + (1 - pyhTiming.labelStartScale) * opacity})`,
    backgroundColor: pyhColors.background, border: `${pyhStroke.width}px solid ${pyhColors.ink}`, borderRadius: pyhStroke.radius,
    color: pyhColors.ink, fontFamily: pyhType.fontFamily, display: 'flex', flexDirection: 'column', justifyContent: 'center',
    alignItems: 'center', whiteSpace: 'nowrap'}}>
    {(viLines ?? [vi]).map((line, i) => (
      <div key={i} style={{fontWeight: pyhType.labelWeight, fontSize: labelFont, lineHeight: viLines ? 1.18 : 1.2}}>{line}</div>
    ))}
    <div style={{fontWeight: pyhType.bodyWeight, fontSize: latinFont, lineHeight: 1.25, fontStyle: 'italic'}}>{latin}</div>
  </div>;
};

const Labels: React.FC<{format: SceneFormat}> = ({format}) => {
  const frame = useCurrentFrame();
  const g = sceneGeometry(format);
  const label = sceneLabels(format).find((l) => frame >= l.start && frame < l.end);
  if (!label) return null;
  const opacity = fadeIn(frame, label.start) * (1 - clamp01((frame - (label.end - 6)) / 6));
  const size = cardSize(label, format);
  const card = {left: label.at.x, top: label.at.y, ...size};
  const target = labelTarget(label, frame, format);
  const from = attachPoint(card, target);
  const draw = clamp01((frame - label.start - 4) / 12);
  return <>
    <svg width={g.frame.width} height={g.frame.height} style={{position: 'absolute', left: 0, top: 0, pointerEvents: 'none'}} data-medanim-leader={label.id}>
      <path d={`M${from.x} ${from.y} L${target.x} ${target.y}`} stroke={pyhColors.ink} strokeWidth={4} strokeLinecap="round"
        pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} opacity={opacity} />
      <circle cx={target.x} cy={target.y} r={10 * draw} fill={pyhColors.alert} stroke={pyhColors.ink} strokeWidth={3} opacity={opacity} />
      {label.ring ? (() => {
        const box = lobuleBoxAt(frame, format);
        const c = imageToScreen(box, 'lobule', label.ring.center);
        const k = box.width / IMAGES.lobule.width;
        return <ellipse data-medanim-emphasis={label.id} cx={c.x} cy={c.y} rx={label.ring.rx * k} ry={label.ring.ry * k} fill="none"
          stroke={pyhColors.accent} strokeWidth={pyhStroke.ringWidth} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} opacity={opacity} />;
      })() : null}
    </svg>
    <Card vi={label.vi} viLines={label.viLines} latin={label.latin} at={label.at} format={format} opacity={opacity} rise={(1 - opacity) * 8} />
  </>;
};

/** B5: central vein → hepatic veins → IVC → blood test, teal arrows drawn in 14 frames. */
const Chain: React.FC<{format: SceneFormat}> = ({format}) => {
  const frame = useCurrentFrame();
  const g = sceneGeometry(format);
  const chain = sceneChain(format);
  if (frame < chain[0].start - 14 || frame >= TRANSITION_LOBULE_TO_SOURCES.start) return null;
  const cv = imageToScreen(lobuleBoxAt(frame, format), 'lobule', LOBULE_POINTS.centralVein);
  const nodes = chain.map((n) => ({...n, size: cardSize(n, format)}));
  const anchors: Point[] = [cv, ...nodes.map((n) => ({x: n.at.x, y: n.at.y + n.size.height / 2}))];
  const tubeBox: Box = format === 'landscape'
    ? {left: chain[2].at.x + nodes[2].size.width + 32, top: chain[2].at.y - 75,
      width: 260 * IMAGES.tube.width / IMAGES.tube.height, height: 260}
    : g.chainTubeBox;
  return <>
    <svg width={g.frame.width} height={g.frame.height} style={{position: 'absolute', left: 0, top: 0}} data-medanim-chain="true">
      <defs><marker id="medanim-arrow" markerWidth="8" markerHeight="8" refX="5" refY="4" orient="auto">
        <path d="M0 0 L8 4 L0 8 z" fill={pyhColors.accent} /></marker></defs>
      {nodes.map((n, i) => {
        const a = i === 0 ? {x: cv.x + 30, y: cv.y} : {x: nodes[i - 1].at.x + 60, y: nodes[i - 1].at.y + nodes[i - 1].size.height};
        const b = i === 0 ? {x: n.at.x, y: anchors[1].y} : {x: n.at.x + 60, y: n.at.y};
        const draw = clamp01((frame - (n.start - 14)) / pyhTiming.arrowDrawFrames);
        return <path key={n.id} d={`M${a.x} ${a.y} L${b.x} ${b.y}`} stroke={pyhColors.accent} strokeWidth={8} fill="none"
          strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} markerEnd={draw > 0.95 ? 'url(#medanim-arrow)' : undefined} />;
      })}
    </svg>
    {nodes.map((n) => <Card key={n.id} vi={n.vi} viLines={n.viLines} latin={n.latin} at={n.at} format={format} opacity={fadeIn(frame, n.start)} />)}
    {frame >= chain[2].start ? <Picture image="tube" box={tubeBox} opacity={fadeIn(frame, chain[2].start)} /> : null}
  </>;
};

// ------------------------------------------------------------------------------------------------
export const MedAnimLiverEnzymeLeakBody: React.FC = () => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const format = formatOf(layout);
  const g = sceneGeometry(format);
  const labels = sceneLabels(format);
  const level = frame < LIVER_ZOOM.end ? 0 : frame < LOBULE_ZOOM_IN.end ? 1
    : frame < CELL_CLOSE.end ? 2 : 1;
  // Dissolve only the outer B1 liver overview + lens chrome between B1 (240) and B2 label (254)
  // over identical-coordinate LobuleScene underneath so there is zero jump or cross-scale blend.
  const b1ShellOpacity = frame >= 240 ? 1 - smoothstep((frame - 240) / 14) : 1;
  const miniMapPos: React.CSSProperties = format === 'landscape'
    ? {right: 38, top: 16}
    : {left: 160, top: 24, width: 760, justifyContent: 'center', boxSizing: 'border-box'};

  return <AbsoluteFill style={{backgroundColor: pyhColors.background}}>
    {frame >= 240 && frame < TRANSITION_LOBULE_TO_SOURCES.end ? <LobuleScene format={format} /> : null}

    {frame < 254 ? <AbsoluteFill style={{opacity: b1ShellOpacity}}>
      <LiverScene format={format} />
      <MagnifierZoom
        sourceRegion={g.liverSourceRegion}
        detailBox={g.lobuleDetailBox}
        locatorStart={LIVER_LOCATOR_START}
        open={LIVER_ZOOM}
      >
        <LobuleScene format={format} inMagnifier />
      </MagnifierZoom>
    </AbsoluteFill> : null}

    {frame >= LOBULE_LOCATOR_START && frame < CELL_CLOSE.end ? <MagnifierZoom
      sourceRegion={g.lobuleSourceRegion}
      detailBox={g.cellDetailBox}
      locatorStart={LOBULE_LOCATOR_START}
      open={LOBULE_ZOOM_IN}
      close={CELL_CLOSE}
    >
      <CellScene format={format} />
    </MagnifierZoom> : null}
    {format === 'portrait' ? <InjuryCallouts format="portrait" /> : null}

    {frame >= TRANSITION_LOBULE_TO_SOURCES.start && frame < CREDITS_START ? <SourcesScene format={format} /> : null}

    {frame < TRANSITION_LOBULE_TO_SOURCES.start ? <div data-mini-map="true" style={{
      position: 'absolute', ...miniMapPos, display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 16px', border: `2px solid ${pyhColors.accent}`, borderRadius: 12,
      backgroundColor: pyhColors.background, fontFamily: pyhType.fontFamily, fontSize: 28, color: pyhColors.ink,
    }}>
      {(['Gan', 'Tiểu thùy', 'Tế bào'] as const).map((label, i) => {
        const active = i === level;
        return <React.Fragment key={label}>
          {i > 0 ? <span aria-hidden="true" style={{opacity: 0.55}}>→</span> : null}
          <span
            data-mini-map-step={label}
            data-active-step={active ? 'true' : undefined}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: active ? '4px 14px' : '4px 8px',
              borderRadius: 999,
              backgroundColor: active ? hexToRgba(pyhColors.accent, 0.24) : 'transparent',
              border: active ? `2px solid ${pyhColors.accent}` : '2px solid transparent',
              fontWeight: active ? 800 : 600,
              opacity: active ? 1 : 0.72,
            }}
          >
            <Img src={staticFile(asset(IMAGES[(['liver', 'lobule', 'cell'] as const)[i]].file))}
              style={{width: 32, height: 34, objectFit: 'contain'}} />
            {label}
          </span>
        </React.Fragment>;
      })}
    </div> : null}

    <Labels format={format} />
    <Chain format={format} />
    {frame >= CREDITS_START ? <Sequence from={CREDITS_START}><Credits format={format} /></Sequence> : null}
    <Sequence from={0} durationInFrames={STEPS[0].end} name="Mascot mở">
      <MascotHost box={g.mascotBox} track={OPENING_POSES} speakingUntil={STEPS[0].end} />
    </Sequence>
    <Sequence from={STEPS[5].start} durationInFrames={TOTAL_FRAMES - STEPS[5].start} name="Mascot kết">
      <MascotHost box={g.mascotBox} track={CLOSING_POSES} speakingUntil={STEPS[5].end - STEPS[5].start} />
    </Sequence>
    {STEPS.map((step) => {
      const {firstFrame, framesPerWord} = captionTiming(step);
      const words = evenWordTiming(step.narration, firstFrame, framesPerWord);
      return <Sequence key={step.id} from={step.start} durationInFrames={step.end - step.start} name={`Phụ đề ${step.id}`}>
        <StyleCaptions text={step.narration} durationInFrames={step.end - step.start} words={words} glossary={GLOSSARY}
          previousText={STEPS.filter((s) => s.start < step.start).map((s) => s.narration).join(' ')}
          labelWindows={labels.map((l) => ({term: l.vi, start: l.start - step.start, end: l.end - step.start}))} />
      </Sequence>;
    })}
  </AbsoluteFill>;
};

export const MedAnimLiverEnzymeLeak: React.FC = () =>
  <LayoutContext.Provider value={LAYOUTS.youtube_long}><MedAnimLiverEnzymeLeakBody /></LayoutContext.Provider>;

export const MedAnimLiverEnzymeLeakVertical: React.FC = () =>
  <LayoutContext.Provider value={LAYOUTS.vertical_clip}><MedAnimLiverEnzymeLeakBody /></LayoutContext.Provider>;
