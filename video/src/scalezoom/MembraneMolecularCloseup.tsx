import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {ENTITY_COLORS} from '../anatomy/entityColors';
import {brand} from '../anatomy/palette';
import type {Box} from '../layout';
import {hexToRgba} from '../style/pyhStyle';

export type MembraneMolecularCloseupProps = {
  state: 'normal' | 'diseased';
  severity: number;
  lightBackground?: boolean;
};

/** ViewBox anchors for Scale Zoom labels when zoomed into the ~10 nm molecular tier. */
export const MOLECULAR_LABEL_ANCHORS: Readonly<
  Record<string, {text: string; anchor: readonly [number, number]; preferred: readonly [number, number]}>
> = {
  enzyme: {text: 'Men ALT / AST', anchor: [324, 388], preferred: [478, 362]},
  cell: {text: 'Màng lipid kép', anchor: [118, 224], preferred: [118, 128]},
  membrane: {text: 'Chỗ màng tổn thương', anchor: [280, 226], preferred: [440, 128]},
  blood: {text: 'Dòng máu xoang mạch', anchor: [446, 434], preferred: [452, 502]},
  bile: {text: 'Trong tế bào gan', anchor: [130, 96], preferred: [140, 74]},
};

/** Keep-out zones in 560x560 viewBox coordinates so leader lines never cut across the breach or flow arrow. */
export const MOLECULAR_LEADER_OBSTACLES: readonly Box[] = [
  {left: 224, top: 204, width: 112, height: 152}, // Membrane breach & exiting enzyme stream
  {left: 60, top: 452, width: 274, height: 30}, // Sinusoidal blood flow arrow
];

/** Stylized globular enzyme protein icon (no specific crystal-structure claim). */
const StylizedEnzymeProtein: React.FC<{
  x: number;
  y: number;
  scale?: number;
  leaked?: boolean;
}> = ({x, y, scale = 1, leaked = false}) => {
  const enzymeFill = ENTITY_COLORS.enzyme_marker.hex; // navy
  const warnRing = ENTITY_COLORS.warning_threshold.hex; // yellow
  return (
    <g
      data-enzyme="true"
      data-enzyme-leaked={leaked ? 'true' : 'false'}
      transform={`translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${scale})`}
    >
      {leaked ? (
        <circle cx={0} cy={0} r={22} fill="none" stroke={warnRing} strokeWidth={3.4} />
      ) : null}
      {/* Multi-lobed stylized globular protein silhouette */}
      <path
        d="M-12 -5 C-14 -14 -2 -18 5 -12 C13 -15 19 -5 14 3 C18 11 8 18 0 13 C-9 17 -18 9 -14 1 Z"
        fill={enzymeFill}
        stroke={brand.off_white}
        strokeWidth={2}
        strokeLinejoin="round"
      />
      {/* Stylized internal fold line */}
      <path
        d="M-6 -2 Q0 -8 6 -1 Q2 6 -5 4"
        fill="none"
        stroke={brand.off_white}
        strokeOpacity={0.72}
        strokeWidth={1.8}
        strokeLinecap="round"
      />
    </g>
  );
};

/**
 * Stylized ~10 nm closeup of the hepatocyte–sinusoid lipid bilayer interface.
 * Strictly stylized illustration: ALT/AST are enzymes inside hepatocytes that
 * leak into the bloodstream when the cell membrane is injured.
 */
export const MembraneMolecularCloseup: React.FC<MembraneMolecularCloseupProps> = ({
  state,
  severity,
  lightBackground = false,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = (frame / Math.max(1, fps)) * 0.45;
  const leakStrength = state === 'diseased' ? Math.max(0.15, Math.min(1, severity)) : 0;

  const tissueHex = ENTITY_COLORS.tissue_normal.hex;
  const injuredHex = ENTITY_COLORS.tissue_injured.hex;
  const bloodHex = ENTITY_COLORS.blood_flow.hex;
  const warnHex = ENTITY_COLORS.warning_threshold.hex;

  // Lipid bilayer columns across x = 44..516; when leaking, columns in [228..332] open into a breach.
  const lipidXs = Array.from({length: 21}, (_, i) => 46 + i * 23.4);
  const isBreachSlot = (x: number) => leakStrength > 0 && x > 228 && x < 332;
  const isBreachEdge = (x: number) => leakStrength > 0 && ((x >= 186 && x <= 228) || (x >= 332 && x <= 374));

  // Animated enzymes exiting through the breach into the bloodstream.
  const exitingEnzymes = [
    {phase: 0.12, driftX: -26},
    {phase: 0.48, driftX: 4},
    {phase: 0.82, driftX: 34},
  ].map((item, idx) => {
    const cycle = (t + item.phase) % 1;
    const y = 178 + cycle * 246;
    const x = 280 + item.driftX * (0.4 + 0.6 * cycle) + (y > 330 ? (y - 330) * 0.65 : 0);
    return {key: idx, x, y, leaked: y > 290};
  });

  // Rich intracellular pool of stylized ALT/AST enzymes inside the hepatocyte (above the bilayer).
  const intracellularEnzymes = [
    {x: 84, y: 74, scale: 0.88},
    {x: 176, y: 66, scale: 0.96},
    {x: 294, y: 78, scale: 0.92},
    {x: 410, y: 68, scale: 0.94},
    {x: 478, y: 112, scale: 0.86},
    {x: 116, y: 146, scale: 1.02},
    {x: 204, y: 158, scale: 0.98},
    {x: 368, y: 152, scale: 1.0},
    {x: 446, y: 168, scale: 0.9},
  ];

  const flowShift = ((frame / Math.max(1, fps)) * 42) % 96;

  return (
    <svg
      data-scalezoom-molecular-closeup="true"
      data-state={state}
      data-severity={leakStrength}
      viewBox="0 0 560 560"
      width="100%"
      height="100%"
      role="img"
      aria-label="Minh họa cách điệu vùng màng tế bào gan và dòng máu ở mức phân tử"
    >
      {/* Top zone: Intracellular cytoplasm */}
      <g data-layer="intracellular-zone">
        <rect
          x={24}
          y={24}
          width={512}
          height={196}
          rx={18}
          fill={hexToRgba(tissueHex, lightBackground ? 0.14 : 0.18)}
          stroke={hexToRgba(tissueHex, 0.36)}
          strokeWidth={1.8}
        />
        {/* Subtle cytoplasmic ambient speckles (stylized intracellular milieu, on-palette) */}
        {[
          [66, 114], [148, 104], [242, 118], [336, 112], [444, 92],
          [78, 184], [164, 188], [326, 182], [496, 152], [254, 54],
        ].map(([dx, dy], i) => (
          <circle
            key={`cyto-${i}`}
            cx={dx}
            cy={dy}
            r={i % 2 === 0 ? 4 : 2.8}
            fill={tissueHex}
            fillOpacity={0.28}
          />
        ))}
      </g>

      {/* Bottom zone: Sinusoidal blood stream */}
      <g data-layer="blood-stream">
        <rect
          x={24}
          y={312}
          width={512}
          height={192}
          rx={18}
          fill={hexToRgba(bloodHex, lightBackground ? 0.12 : 0.14)}
          stroke={hexToRgba(bloodHex, 0.45)}
          strokeWidth={2}
        />
        {/* Laminar flow lines (stroke only, not filled blocks) */}
        {[356, 396, 430].map((y, row) =>
          Array.from({length: 5}, (_, i) => {
            const x1 = 44 + ((i * 106 + flowShift + row * 28) % 452);
            return (
              <line
                key={`${row}-${i}`}
                x1={x1}
                y1={y}
                x2={Math.min(516, x1 + 44)}
                y2={y}
                stroke={bloodHex}
                strokeOpacity={0.55}
                strokeWidth={2.6}
                strokeLinecap="round"
              />
            );
          }),
        )}
        {/* Directional blood-flow arrow kept well left of x=330 so right-side labels never touch it */}
        <path
          data-process-arrow="true"
          d="M68 466 H322 M308 457 L322 466 L308 475"
          fill="none"
          stroke={bloodHex}
          strokeWidth={3.6}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>

      {/* Middle band: Stylized phospholipid bilayer */}
      <g data-layer="lipid-bilayer">
        {lipidXs.map((x, idx) => {
          if (isBreachSlot(x)) return null;
          const edge = isBreachEdge(x);
          const headFill = edge ? injuredHex : tissueHex;
          const tailStroke = edge ? hexToRgba(injuredHex, 0.72) : hexToRgba(tissueHex, 0.52);
          const tilt = edge ? (x < 280 ? -12 : 12) : 0;
          return (
            <g key={idx} transform={`translate(${x.toFixed(1)} 264) rotate(${tilt})`}>
              {/* Hydrophobic tails facing inward */}
              <path d="M-3 -32 Q-6 -16 -2 -4 M3 -32 Q6 -16 2 -4" fill="none" stroke={tailStroke} strokeWidth={2.2} strokeLinecap="round" />
              <path d="M-3 32 Q-6 16 -2 4 M3 32 Q6 16 2 4" fill="none" stroke={tailStroke} strokeWidth={2.2} strokeLinecap="round" />
              {/* Hydrophilic heads (top & bottom leaflets) */}
              <circle cx={0} cy={-38} r={8.5} fill={headFill} stroke={brand.navy} strokeWidth={1.6} />
              <circle cx={0} cy={38} r={8.5} fill={headFill} stroke={brand.navy} strokeWidth={1.6} />
            </g>
          );
        })}

        {/* Membrane injury breach highlight */}
        {leakStrength > 0 ? (
          <g data-layer="membrane-breach">
            <path
              d="M224 220 Q236 264 224 308"
              fill="none"
              stroke={warnHex}
              strokeWidth={3.5}
              strokeDasharray="6 5"
              strokeLinecap="round"
            />
            <path
              d="M336 220 Q324 264 336 308"
              fill="none"
              stroke={warnHex}
              strokeWidth={3.5}
              strokeDasharray="6 5"
              strokeLinecap="round"
            />
            {/* Downward leak trajectory guide */}
            <path
              d="M280 214 V332 M270 320 L280 334 L290 320"
              fill="none"
              stroke={warnHex}
              strokeOpacity={0.78}
              strokeWidth={3}
              strokeDasharray="7 5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </g>
        ) : null}
      </g>

      {/* Stylized ALT/AST enzyme proteins */}
      <g data-layer="enzyme-proteins">
        {intracellularEnzymes.map((pos, idx) => (
          <StylizedEnzymeProtein
            key={`in-${idx}`}
            x={pos.x}
            y={pos.y + Math.sin(t * 2 + idx) * 4}
            scale={pos.scale}
            leaked={false}
          />
        ))}
        {leakStrength > 0
          ? exitingEnzymes.map((e) => (
              <StylizedEnzymeProtein key={`out-${e.key}`} x={e.x} y={e.y} scale={1.08} leaked={e.leaked} />
            ))
          : (
              <StylizedEnzymeProtein x={280} y={142 + Math.sin(t * 2) * 4} scale={1.05} leaked={false} />
            )}
      </g>
    </svg>
  );
};
