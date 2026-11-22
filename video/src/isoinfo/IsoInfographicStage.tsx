import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {
  ANATOMY_COMPONENTS,
  ANATOMY_LABELS,
  ANATOMY_VIEW_BOXES,
  type AnatomySubject,
} from '../anatomy/registry';
import {ENTITY_COLORS} from '../anatomy/entityColors';
import {brand} from '../anatomy/palette';
import {Captions, CAPTION_BACKGROUND_COLOR, shouldRenderCaptions} from '../components/Captions';
import {MascotGuide} from '../components/MascotGuide';
import {FONT_FAMILY} from '../fonts';
import {boxesIntersect, captionBox, shortsCaptionSafeBox, useLayout, type Box} from '../layout';
import {hexToRgba} from '../style/pyhStyle';
import type {Scene} from '../types';

export const ISO_ANGLE_DEG = 30;
export const ISO_TRACK_DRAW_FRAMES = 18;
export const MAX_ISOPIN_LABELS = 6;

const COS_30 = Math.cos((ISO_ANGLE_DEG * Math.PI) / 180);
const SIN_30 = Math.sin((ISO_ANGLE_DEG * Math.PI) / 180);

export type IsoPoint = {readonly x: number; readonly y: number};

/** Pure 30-degree isometric projection from local (u, v, z) into 2D screen coordinates. */
export const isoProject = (
  u: number,
  v: number,
  z = 0,
  origin: IsoPoint = {x: 0, y: 0},
): IsoPoint => ({
  x: origin.x + (u - v) * COS_30,
  y: origin.y + (u + v) * SIN_30 - z,
});

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));

/** Pre-draws the isometric pathway completely BEFORE the traveling marker begins moving along it. */
export const computeIsoPathMotion = (
  frame: number,
  durationFrames: number,
): {readonly trackDrawProgress: number; readonly travelerProgress: number} => {
  const trackDrawProgress = clamp01(frame / ISO_TRACK_DRAW_FRAMES);
  if (frame <= ISO_TRACK_DRAW_FRAMES) {
    return {trackDrawProgress, travelerProgress: 0};
  }
  const remaining = Math.max(1, durationFrames - ISO_TRACK_DRAW_FRAMES);
  const travelerProgress = clamp01((frame - ISO_TRACK_DRAW_FRAMES) / remaining);
  return {trackDrawProgress, travelerProgress};
};

/** Orthogonal vertical-then-horizontal pin leader: never cuts diagonally across the organ. */
export const orthogonalLeaderPoints = (
  anchorX: number,
  anchorY: number,
  box: Box,
): readonly [IsoPoint, IsoPoint, IsoPoint] => {
  const boxMidY = box.top + box.height / 2;
  const edgeX = anchorX < box.left ? box.left : anchorX > box.left + box.width ? box.left + box.width : box.left;
  return [
    {x: anchorX, y: anchorY},
    {x: anchorX, y: boxMidY},
    {x: edgeX, y: boxMidY},
  ];
};

const FALLBACK_SUBJECT_LABEL_VI: Readonly<Partial<Record<AnatomySubject, string>>> = {
  liver_organ: 'Gan (cơ quan)',
  liver_lobule: 'Tiểu thùy gan',
  hepatocyte_sinusoid_unit: 'Tế bào gan & mao mạch',
  hepatic_toxic_injury: 'Tổn thương tế bào gan',
  hepatic_synthesis_and_bile: 'Tổng hợp đạm & đường mật',
  hepatic_fibrosis_section: 'Mô xơ gan',
  alt_ast_tissue_distribution: 'Phân bố men ALT / AST',
  artery_cross_section: 'Thành động mạch',
  heart: 'Tim',
};

export type IsoPinLabel = {
  readonly id: string;
  readonly text: string;
  readonly anchorX: number;
  readonly anchorY: number;
  readonly box: Box;
  readonly points: readonly [IsoPoint, IsoPoint, IsoPoint];
  readonly primary: boolean;
};

const estimatePinBox = (text: string, primary: boolean): {width: number; height: number} => {
  const fontSize = primary ? 22 : 18;
  const chars = Array.from(text).length;
  return {
    width: Math.max(primary ? 150 : 120, Math.min(300, Math.round(chars * fontSize * 0.62 + 30))),
    height: primary ? 46 : 38,
  };
};

export type IsoInfographicStageProps = {
  scene: Scene;
  kind: 'anatomy' | 'process';
  cueProgress?: Record<string, number>;
};

export const IsoInfographicStage: React.FC<IsoInfographicStageProps> = ({
  scene,
  kind,
  cueProgress,
}) => {
  const frame = useCurrentFrame();
  const frameLayout = useLayout();
  if (!scene.anatomy) throw new Error(`${scene.visual} requires anatomy`);

  const anatomy = scene.anatomy;
  const Organ = ANATOMY_COMPONENTS[anatomy.subject];
  if (!Organ) throw new Error(`Unsupported anatomy subject: ${anatomy.subject}`);

  const width = frameLayout.frame.width;
  const height = frameLayout.frame.height;
  const isVertical = height > width;
  const hasMascot = Boolean(scene.visual_assets?.some((asset) => asset.role === 'mascot'));

  const progress = interpolate(frame, [0, Math.max(1, scene.duration_frames - 1)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const severity = cueProgress
    ? anatomy.state === 'normal'
      ? 0
      : anatomy.severity
    : anatomy.state === 'normal'
      ? 0
      : kind === 'anatomy'
        ? anatomy.severity * (0.4 + 0.6 * progress)
        : anatomy.severity;

  // Layout zones
  const mascotBox: Box = isVertical
    ? {left: 32, top: 1350, width: 220, height: 192}
    : {left: 28, top: 842, width: 240, height: 210};

  const takeawayBox: Box | null = scene.visualTakeaway
    ? isVertical
      ? {left: 36, top: 32, width: width - 72, height: 84}
      : {left: 44, top: 28, width: 880, height: 74}
    : null;

  const badgeBox: Box = isVertical
    ? {left: width - 356, top: takeawayBox ? 128 : 32, width: 320, height: 54}
    : {left: width - 380, top: 28, width: 336, height: 60};

  const subjectArea: Box = isVertical
    ? {left: 88, top: 250, width: width - 176, height: 900}
    : {left: hasMascot ? 360 : 320, top: 170, width: width - (hasMascot ? 720 : 640), height: 760};

  const subjectSize = Math.min(subjectArea.width * 0.78, subjectArea.height * 0.78);
  const subjectBox: Box = {
    left: subjectArea.left + (subjectArea.width - subjectSize) / 2,
    top: subjectArea.top + (subjectArea.height - subjectSize) / 2,
    width: subjectSize,
    height: subjectSize,
  };

  // Isometric 30-degree plinth geometry centered behind the cutaway organ
  const cx = subjectBox.left + subjectBox.width / 2;
  const cy = subjectBox.top + subjectBox.height / 2;
  const uSpan = subjectBox.width * 0.62;
  const vSpan = subjectBox.height * 0.62;
  const depthZ = isVertical ? 48 : 54;
  const isoOrigin: IsoPoint = {x: cx, y: cy - (uSpan + vSpan) * SIN_30 * 0.5 + 12};

  const pTopN = isoProject(0, 0, 0, isoOrigin);
  const pTopE = isoProject(uSpan, 0, 0, isoOrigin);
  const pTopS = isoProject(uSpan, vSpan, 0, isoOrigin);
  const pTopW = isoProject(0, vSpan, 0, isoOrigin);
  const pBotE = isoProject(uSpan, 0, -depthZ, isoOrigin);
  const pBotS = isoProject(uSpan, vSpan, -depthZ, isoOrigin);
  const pBotW = isoProject(0, vSpan, -depthZ, isoOrigin);

  const toPoly = (pts: readonly IsoPoint[]) => pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');

  // Peel-back cutaway layers (3 flat tones on light surface)
  const peelTone1 = hexToRgba(brand.teal, 0.14);
  const peelTone2 = hexToRgba(brand.teal, 0.28);
  const peelTone3 = hexToRgba(brand.navy, 0.18);
  const injuredAccent = anatomy.state === 'diseased' ? ENTITY_COLORS.tissue_injured.hex : brand.teal;

  // Pre-drawn isometric pathway + traveling marker
  const {trackDrawProgress, travelerProgress} = computeIsoPathMotion(frame, scene.duration_frames);
  const trackStart = isoProject(uSpan * 0.15, vSpan * 0.88, 8, isoOrigin);
  const trackMid = isoProject(uSpan * 0.5, vSpan * 0.5, 16, isoOrigin);
  const trackEnd = isoProject(uSpan * 0.88, vSpan * 0.15, 8, isoOrigin);
  const trackD = `M${trackStart.x.toFixed(1)} ${trackStart.y.toFixed(1)} L${trackMid.x.toFixed(1)} ${trackMid.y.toFixed(1)} L${trackEnd.x.toFixed(1)} ${trackEnd.y.toFixed(1)}`;
  const travelerPt = travelerProgress <= 0.5
    ? {
        x: trackStart.x + (trackMid.x - trackStart.x) * (travelerProgress * 2),
        y: trackStart.y + (trackMid.y - trackStart.y) * (travelerProgress * 2),
      }
    : {
        x: trackMid.x + (trackEnd.x - trackMid.x) * ((travelerProgress - 0.5) * 2),
        y: trackMid.y + (trackEnd.y - trackMid.y) * ((travelerProgress - 0.5) * 2),
      };

  // Pin + orthogonal vertical-horizontal labels outside the cutaway subject
  const view = ANATOMY_VIEW_BOXES[anatomy.subject];
  const rawLabels = ANATOMY_LABELS[anatomy.subject];
  const activeBeat = (scene.beats ?? [])
    .filter((b) => b.start_frame === undefined || b.start_frame <= frame)
    .at(-1);
  const labelIds = (
    activeBeat?.labels?.length ? activeBeat.labels : Object.keys(rawLabels).slice(0, 3)
  ).slice(0, MAX_ISOPIN_LABELS);

  const obstacles: Box[] = [
    subjectBox,
    badgeBox,
    ...(takeawayBox ? [takeawayBox] : []),
    ...(hasMascot ? [mascotBox] : []),
    ...(shouldRenderCaptions(frameLayout)
      ? [scene.words?.length ? shortsCaptionSafeBox(frameLayout, hasMascot) : captionBox(frameLayout)]
      : []),
  ];

  const placedPins: IsoPinLabel[] = [];
  const scale = Math.min(subjectBox.width / view.width, subjectBox.height / view.height);

  const addPin = (id: string, text: string, vx: number, vy: number, primary: boolean) => {
    const ax = subjectBox.left + (vx - view.left) * scale;
    const ay = subjectBox.top + (vy - view.top) * scale;
    const {width: bw, height: bh} = estimatePinBox(text, primary);
    const placeRight = ax >= cx;
    const candidateSlots: Box[] = isVertical
      ? [
          {left: Math.max(24, Math.min(width - bw - 24, ax - bw / 2)), top: subjectBox.top - bh - 38, width: bw, height: bh},
          {left: Math.max(24, Math.min(width - bw - 24, ax - bw / 2)), top: subjectBox.top + subjectBox.height + 42, width: bw, height: bh},
        ]
      : [
          {
            left: placeRight ? Math.min(width - bw - 28, subjectBox.left + subjectBox.width + 44) : Math.max(28, subjectBox.left - bw - 44),
            top: Math.max(120, Math.min(height - bh - 36, ay - bh / 2)),
            width: bw,
            height: bh,
          },
          {
            left: placeRight ? Math.min(width - bw - 28, subjectBox.left + subjectBox.width + 44) : Math.max(28, subjectBox.left - bw - 44),
            top: Math.max(120, Math.min(height - bh - 36, subjectBox.top + placedPins.length * (bh + 18))),
            width: bw,
            height: bh,
          },
        ];

    const chosen = candidateSlots.find(
      (slot) =>
        !obstacles.some((o) => boxesIntersect(slot, o)) &&
        !placedPins.some((p) => boxesIntersect(slot, p.box)),
    ) ?? candidateSlots[0];

    placedPins.push({
      id,
      text,
      anchorX: ax,
      anchorY: ay,
      box: chosen,
      points: orthogonalLeaderPoints(ax, ay, chosen),
      primary,
    });
  };

  labelIds.forEach((id, idx) => {
    const def = rawLabels[id];
    if (!def) return;
    addPin(id, def.text, def.anchor[0], def.anchor[1], idx === 0);
  });

  if (placedPins.length === 0) {
    const fallback = FALLBACK_SUBJECT_LABEL_VI[anatomy.subject] ?? 'Mặt cắt giải phẫu';
    addPin(anatomy.subject, fallback, view.left + view.width * 0.62, view.top + view.height * 0.42, true);
  }

  const caption = frameLayout.captions;
  const gridStep = 72;
  const gridLines: {x1: number; y1: number; x2: number; y2: number}[] = [];
  for (let i = -8; i <= 16; i++) {
    const startA = isoProject(i * gridStep, -600, 0, {x: cx, y: cy});
    const endA = isoProject(i * gridStep, 1200, 0, {x: cx, y: cy});
    gridLines.push({x1: startA.x, y1: startA.y, x2: endA.x, y2: endA.y});
    const startB = isoProject(-600, i * gridStep, 0, {x: cx, y: cy});
    const endB = isoProject(1200, i * gridStep, 0, {x: cx, y: cy});
    gridLines.push({x1: startB.x, y1: startB.y, x2: endB.x, y2: endB.y});
  }

  return (
    <AbsoluteFill
      data-isoinfo-stage="true"
      data-iso-angle={ISO_ANGLE_DEG}
      style={{backgroundColor: brand.off_white, color: brand.navy, overflow: 'hidden'}}
    >
      {/* Subtle 30-degree isometric reference grid */}
      <svg
        data-iso-grid="true"
        viewBox={`0 0 ${width} ${height}`}
        style={{position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none'}}
      >
        {gridLines.map((l, idx) => (
          <line
            key={idx}
            x1={l.x1.toFixed(1)}
            y1={l.y1.toFixed(1)}
            x2={l.x2.toFixed(1)}
            y2={l.y2.toFixed(1)}
            stroke={hexToRgba(brand.navy, 0.05)}
            strokeWidth="1.5"
          />
        ))}

        {/* Three-tone flat-shaded 30-degree isometric cutaway plinth */}
        <g data-iso-plinth="true" data-iso-angle="30">
          <polygon points={toPoly([pTopN, pTopE, pTopS, pTopW])} fill={peelTone1} stroke={brand.teal} strokeWidth="2.5" strokeLinejoin="round" />
          <polygon points={toPoly([pTopW, pTopS, pBotS, pBotW])} fill={peelTone2} stroke={brand.navy} strokeWidth="2" strokeLinejoin="round" />
          <polygon points={toPoly([pTopS, pTopE, pBotE, pBotS])} fill={peelTone3} stroke={brand.navy} strokeWidth="2" strokeLinejoin="round" />
        </g>

        {/* Peel-back cutaway depth corner tabs (outer -> middle -> core) */}
        <g data-iso-peel="true">
          {[0, 1, 2].map((layer) => {
            const inset = layer * 16;
            const p1 = isoProject(inset, vSpan - 60 + inset * 0.5, 6 + layer * 4, isoOrigin);
            const p2 = isoProject(inset + 58, vSpan - 60 + inset * 0.5, 6 + layer * 4, isoOrigin);
            const p3 = isoProject(inset + 58, vSpan - 18 + inset * 0.5, 6 + layer * 4, isoOrigin);
            const p4 = isoProject(inset, vSpan - 18 + inset * 0.5, 6 + layer * 4, isoOrigin);
            const tone = layer === 0 ? peelTone1 : layer === 1 ? peelTone2 : hexToRgba(injuredAccent, 0.45);
            return (
              <polygon
                key={layer}
                points={toPoly([p1, p2, p3, p4])}
                fill={tone}
                stroke={brand.navy}
                strokeWidth="1.8"
                strokeLinejoin="round"
              />
            );
          })}
        </g>
      </svg>

      {/* Main anatomy subject inside the cutaway stage */}
      <div
        data-iso-cutaway="true"
        style={{
          position: 'absolute',
          left: subjectBox.left,
          top: subjectBox.top,
          width: subjectBox.width,
          height: subjectBox.height,
        }}
      >
        <Organ
          state={anatomy.state}
          severity={severity}
          emphasizeFlow={kind === 'process'}
          lightBackground={true}
          cueProgress={cueProgress}
          visibleLabels={[]}
        />
      </div>

      {/* Pre-drawn isometric path + traveling marker (track completes before traveler moves) */}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 4}}
      >
        <path
          data-iso-track="true"
          d={trackD}
          fill="none"
          pathLength="1"
          stroke={brand.teal}
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="1"
          strokeDashoffset={1 - trackDrawProgress}
          opacity="0.82"
        />
        {travelerProgress > 0 ? (
          <circle
            data-iso-traveler="true"
            cx={travelerPt.x}
            cy={travelerPt.y}
            r="9"
            fill={brand.yellow}
            stroke={brand.navy}
            strokeWidth="3"
          />
        ) : null}

        {/* Orthogonal vertical-horizontal leaders + pins */}
        <g data-isoinfo-labels="true">
          {placedPins.map((pin) => {
            const [a, b, c] = pin.points;
            return (
              <g key={pin.id}>
                <polyline
                  data-iso-orthogonal-leader="true"
                  points={`${a.x.toFixed(1)},${a.y.toFixed(1)} ${b.x.toFixed(1)},${b.y.toFixed(1)} ${c.x.toFixed(1)},${c.y.toFixed(1)}`}
                  fill="none"
                  stroke={brand.navy}
                  strokeWidth={pin.primary ? 2.8 : 2}
                  strokeLinejoin="round"
                />
                <circle
                  data-iso-pin="true"
                  cx={pin.anchorX}
                  cy={pin.anchorY}
                  r={pin.primary ? 7 : 5}
                  fill={pin.primary ? brand.yellow : brand.teal}
                  stroke={brand.navy}
                  strokeWidth="2.2"
                />
              </g>
            );
          })}
        </g>
      </svg>

      {/* Crisp label pills matching orthogonal leader endpoints */}
      {placedPins.map((pin) => (
        <div
          key={`pill-${pin.id}`}
          data-isoinfo-pin-label={pin.id}
          style={{
            position: 'absolute',
            left: pin.box.left,
            top: pin.box.top,
            width: pin.box.width,
            height: pin.box.height,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 10,
            backgroundColor: brand.off_white,
            border: `${pin.primary ? 2.5 : 2}px solid ${pin.primary ? brand.yellow : brand.navy}`,
            fontFamily: FONT_FAMILY,
            fontSize: pin.primary ? 21 : 18,
            fontWeight: 800,
            color: brand.navy,
            boxSizing: 'border-box',
            padding: '0 12px',
            zIndex: 5,
            pointerEvents: 'none',
          }}
        >
          {pin.text}
        </div>
      ))}

      {/* Visual takeaway pill */}
      {takeawayBox && scene.visualTakeaway ? (
        <div
          data-isoinfo-takeaway="true"
          style={{
            position: 'absolute',
            left: takeawayBox.left,
            top: takeawayBox.top,
            maxWidth: takeawayBox.width,
            padding: '12px 22px 14px',
            borderRadius: 12,
            backgroundColor: brand.off_white,
            border: `2px solid ${brand.teal}`,
            fontFamily: FONT_FAMILY,
            fontSize: isVertical ? 22 : 24,
            fontWeight: 800,
            color: brand.navy,
            zIndex: 6,
            pointerEvents: 'none',
          }}
        >
          {scene.visualTakeaway}
        </div>
      ) : null}

      {/* Top-right style badge */}
      <div
        data-isoinfo-badge="true"
        style={{
          position: 'absolute',
          left: badgeBox.left,
          top: badgeBox.top,
          width: badgeBox.width,
          height: badgeBox.height,
          borderRadius: 12,
          backgroundColor: brand.off_white,
          border: `2px solid ${hexToRgba(brand.navy, 0.24)}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 10,
          fontFamily: FONT_FAMILY,
          fontSize: 18,
          fontWeight: 800,
          color: brand.navy,
          zIndex: 6,
          pointerEvents: 'none',
        }}
      >
        <span style={{width: 12, height: 12, borderRadius: 3, backgroundColor: brand.teal, display: 'inline-block'}} />
        Mặt cắt đẳng cự 30°
      </div>

      <div style={{position: 'absolute', inset: 0, zIndex: 6, pointerEvents: 'none'}}>
        <MascotGuide scene={scene} box={mascotBox} />
      </div>

      {shouldRenderCaptions(frameLayout) && !scene.words?.length ? (
        <div
          data-mechanism-caption-band="true"
          style={{
            position: 'absolute',
            left: caption.left,
            bottom: caption.bottom,
            width: caption.width,
            height: caption.height,
            backgroundColor: CAPTION_BACKGROUND_COLOR,
            borderRadius: 16,
            zIndex: 7,
          }}
        />
      ) : null}
      <Captions
        variant={scene.words?.length ? 'shorts' : undefined}
        hasMascot={hasMascot}
        text={scene.narration}
        words={scene.words}
        durationInFrames={scene.duration_frames}
      />
    </AbsoluteFill>
  );
};
