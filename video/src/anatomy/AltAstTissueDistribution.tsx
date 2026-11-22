import React from 'react';
import {useCurrentFrame} from 'remotion';
import type {OrganProps} from './ArterySection';
import {DiagramAnnotations, type DiagramLabels} from './annotations';
import {ENTITY_COLORS} from './entityColors';
import {brand} from './palette';
import {hexToRgba} from '../style/pyhStyle';

// Separate tissue sites, not a transport pathway or a quantitative concentration map.
export const CONTENT_BOX = {left: 28, top: 44, width: 504, height: 472};
export const FOCUS_REGIONS = {overview: {left: 0, top: 0, width: 560, height: 560}};
export const CUE_ACTIONS: readonly string[] = ['liver', 'muscle'];
export const LABELS: DiagramLabels = {
  liver: {text: 'Gan', region: 'overview', x: 32, y: 12, width: 112, height: 34, anchor: [118, 92]},
  alt: {text: 'ALT', region: 'overview', x: 168, y: 12, width: 108, height: 34, anchor: [188, 174]},
  ast: {text: 'AST', region: 'overview', x: 396, y: 12, width: 116, height: 34, anchor: [436, 252]},
  muscle: {text: 'Cơ vân', region: 'overview', x: 64, y: 514, width: 156, height: 34, anchor: [148, 456]},
  heart: {text: 'Cơ tim', region: 'overview', x: 356, y: 514, width: 156, height: 34, anchor: [420, 424]},
};

/** Reusable enzyme marker badge: strictly enzyme_marker (navy) core; teal ring for ALT, yellow ring for AST. */
const EnzymeDot: React.FC<{cx: number; cy: number; kind: 'ALT' | 'AST'; r?: number}> = ({
  cx,
  cy,
  kind,
  r = 10.5,
}) => {
  const enzymeFill = ENTITY_COLORS.enzyme_marker.hex;
  const ringHex = kind === 'AST' ? ENTITY_COLORS.warning_threshold.hex : ENTITY_COLORS.blood_flow.hex;
  return (
    <g data-enzyme={kind}>
      <circle cx={cx} cy={cy} r={r + 5.5} fill={brand.off_white} fillOpacity={0.86} stroke={ringHex} strokeWidth={3} />
      <circle cx={cx} cy={cy} r={r} fill={enzymeFill} stroke={brand.off_white} strokeWidth={1.6} />
      <circle cx={cx - r * 0.3} cy={cy - r * 0.3} r={r * 0.26} fill={brand.off_white} fillOpacity={0.45} />
    </g>
  );
};

export const AltAstTissueDistribution: React.FC<OrganProps> = ({visibleLabels = [], cueProgress}) => {
  const frame = useCurrentFrame();
  const liverOpacity = 0.55 + 0.45 * (cueProgress?.liver ?? (Math.sin(frame / 28) + 1) / 2);
  const muscleOpacity = 0.55 + 0.45 * (cueProgress?.muscle ?? (Math.sin(frame / 31) + 1) / 2);

  // Distinct value & texture hierarchy across the three tissues (all strictly on-palette):
  // 1. Liver: smooth solid-medium teal parenchyma + falciform ligament
  // 2. Skeletal muscle: lighter tapered fusiform bundle with crisp vertical parallel fibers + horizontal cross-striations
  // 3. Cardiac muscle: recognizable anterior heart silhouette with deeper teal/navy myocardial density + branching fiber arcs
  const liverFill = hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.44);
  const liverLeftLobe = hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.26);
  const muscleFill = hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.20);
  const muscleFiber = hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.42);
  const muscleStriation = hexToRgba(brand.navy, 0.36);
  const heartWallDeep = hexToRgba(brand.navy, 0.24);
  const heartWallMid = hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.56);
  const heartVessel = hexToRgba(ENTITY_COLORS.blood_flow.hex, 0.72);
  const tissueStroke = hexToRgba(brand.navy, 0.72);

  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="ALT ở gan; AST ở gan, cơ vân và cơ tim">
    {/* 1. Liver (top-left): recognizable anterior bilobed organ silhouette */}
    <g data-layer="liver-tissue" opacity={liverOpacity}>
      <path
        d="M34 148 C34 94 74 62 132 62 C172 62 194 76 218 92 C244 108 264 114 274 138 C268 184 234 214 182 228 C154 234 134 252 104 256 C62 260 34 226 34 148 Z"
        fill={liverFill}
        stroke={tissueStroke}
        strokeWidth="3.2"
        strokeLinejoin="round"
      />
      {/* Left lobe lighter plane */}
      <path
        d="M174 78 C206 98 248 112 264 138 C252 174 222 200 176 214 L156 218 Z"
        fill={liverLeftLobe}
      />
      {/* Falciform ligament */}
      <path d="M172 74 Q168 148 154 216" fill="none" stroke={brand.off_white} strokeWidth="5" strokeLinecap="round" />
      {/* Dome highlight */}
      <path d="M62 108 C84 82 118 74 150 82" fill="none" stroke={brand.off_white} strokeOpacity="0.5" strokeWidth="4" strokeLinecap="round" />
      {/* ALT markers (2) + AST marker (1) in liver */}
      <EnzymeDot cx={104} cy={156} kind="ALT" />
      <EnzymeDot cx={188} cy={174} kind="ALT" />
      <EnzymeDot cx={92} cy={208} kind="AST" r={9.5} />
    </g>

    {/* 2. Skeletal muscle (bottom-left): organic fusiform bundle of vertical parallel fibers with horizontal cross-striations */}
    <g data-layer="skeletal-muscle" opacity={muscleOpacity}>
      {/* Smooth fusiform muscle belly tapering into top/bottom tendon ends */}
      <path
        d="M116 292 C140 288 156 288 180 292 C214 302 246 324 252 362 C256 388 256 400 252 426 C246 462 214 480 180 488 C156 492 140 492 116 488 C82 480 50 462 44 426 C40 400 40 388 44 362 C50 324 82 302 116 292 Z"
        fill={muscleFill}
        stroke={tissueStroke}
        strokeWidth="3.2"
        strokeLinejoin="round"
      />
      {/* Parallel vertical muscle fascicles */}
      {[72, 102, 132, 162, 192, 222].map((fx, i) => (
        <g key={fx}>
          <path
            d={`M${fx} 326 Q${fx + (i < 3 ? -7 : 7)} 390 ${fx} 454`}
            fill="none"
            stroke={i % 2 === 0 ? muscleFiber : hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.28)}
            strokeWidth="15"
            strokeLinecap="round"
          />
          {/* Crisp horizontal sarcomere cross-striations */}
          {[338, 358, 378, 398, 418, 438].map((sy) => (
            <line
              key={sy}
              x1={fx - 8.5}
              y1={sy}
              x2={fx + 8.5}
              y2={sy}
              stroke={muscleStriation}
              strokeWidth="2.4"
              strokeLinecap="round"
            />
          ))}
        </g>
      ))}
      {/* AST marker in skeletal muscle */}
      <EnzymeDot cx={148} cy={392} kind="AST" />
    </g>

    {/* 3. Cardiac muscle (right): recognizable stylized anterior heart silhouette with myocardial fiber arcs */}
    <g data-layer="cardiac-muscle" opacity={muscleOpacity}>
      {/* Superior vena cava (behind aortic arch) */}
      <path
        d="M342 126 L372 126 L376 212 L346 218 Z"
        fill={brand.off_white}
      />
      <path
        d="M342 126 L372 126 L376 212 L346 218 Z"
        fill={heartVessel}
        stroke={tissueStroke}
        strokeWidth="2.6"
        strokeLinejoin="round"
      />
      {/* Aortic arch + 3 superior branches (clean opaque backing over SVC) */}
      <path
        d="M394 114 L388 86 L402 84 L408 110 M416 108 L416 78 L430 78 L430 108 M438 114 L448 86 L460 92 L450 120"
        fill={heartWallMid}
        stroke={tissueStroke}
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path
        d="M448 214 L444 150 C443 122 428 104 406 104 C378 104 362 122 362 148 L362 204 L388 204 L388 150 C388 134 396 128 408 128 C418 128 422 138 422 152 L426 214 Z"
        fill={brand.off_white}
      />
      <path
        d="M448 214 L444 150 C443 122 428 104 406 104 C378 104 362 122 362 148 L362 204 L388 204 L388 150 C388 134 396 128 408 128 C418 128 422 138 422 152 L426 214 Z"
        fill={heartWallMid}
        stroke={tissueStroke}
        strokeWidth="2.8"
        strokeLinejoin="round"
      />
      {/* Main ventricular & atrial heart body (tilted cone leaning toward apex down-right) */}
      <path
        d="M366 202 C332 214 316 254 328 298 C340 348 380 406 436 446 C446 452 458 446 464 434 C494 378 516 312 504 252 C496 214 468 192 432 194 C406 194 384 196 366 202 Z"
        fill={brand.off_white}
      />
      <path
        d="M366 202 C332 214 316 254 328 298 C340 348 380 406 436 446 C446 452 458 446 464 434 C494 378 516 312 504 252 C496 214 468 192 432 194 C406 194 384 196 366 202 Z"
        fill={heartWallMid}
        stroke={tissueStroke}
        strokeWidth="3.4"
        strokeLinejoin="round"
      />
      {/* Deeper myocardial shading on right-ventricular / septal plane for unmistakable volume */}
      <path
        d="M412 204 C452 200 486 224 494 264 C502 314 480 374 452 430 C414 394 396 334 402 268 Z"
        fill={heartWallDeep}
      />
      {/* Pulmonary trunk crossing anteriorly with clean occlusion */}
      <path
        d="M416 228 C402 210 404 190 416 174 L478 164 L484 186 L434 194 C426 206 428 216 438 228 Z"
        fill={brand.off_white}
      />
      <path
        d="M416 228 C402 210 404 190 416 174 L478 164 L484 186 L434 194 C426 206 428 216 438 228 Z"
        fill={heartVessel}
        stroke={tissueStroke}
        strokeWidth="2.6"
        strokeLinejoin="round"
      />
      {/* Subtle stylized branching myocardial fiber lines inside the heart wall */}
      <g fill="none" stroke={brand.off_white} strokeOpacity="0.46" strokeWidth="2.4" strokeLinecap="round">
        <path d="M352 276 Q388 318 444 374" />
        <path d="M368 248 Q408 292 464 344" />
        <path d="M398 300 Q432 288 476 302" />
        <path d="M372 332 Q410 342 448 398" />
      </g>
      {/* AST marker on cardiac myocardium */}
      <EnzymeDot cx={436} cy={252} kind="AST" />
    </g>
    <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
  </svg>;
};
