import React from 'react';
import {brand} from './palette';
export type FocusRegion = {left: number; top: number; width: number; height: number};
export type DiagramLabel = {text: string; region: string; x: number; y: number; width: number; height: number; anchor: readonly [number, number]};
export type DiagramLabels = Record<string, DiagramLabel>;
/** Fixed terminology only. Screen-space overlay may reuse this renderer after camera motion. */
export const DiagramAnnotations: React.FC<{labels: DiagramLabels; visibleLabels?: readonly string[]}> = ({labels, visibleLabels = []}) => <g data-layer="annotations" pointerEvents="none">
  {[...new Set(visibleLabels)].slice(0, 6).map(id => {
    const label = labels[id];
    if (!label) return null;
    const {x, y, width, height, anchor} = label;
    const startX = Math.max(x, Math.min(x + width, anchor[0]));
    const startY = anchor[1] < y ? y : anchor[1] > y + height ? y + height : y + height / 2;
    return <g key={id} data-label={id}>
      <path data-leader={id} d={`M${startX} ${startY} L${anchor[0]} ${anchor[1]}`} fill="none" stroke={brand.off_white} strokeWidth="4"/>
      <path d={`M${startX} ${startY} L${anchor[0]} ${anchor[1]}`} fill="none" stroke={brand.navy} strokeWidth="1.6"/>
      <circle cx={anchor[0]} cy={anchor[1]} r="3" fill={brand.yellow}/>
      <rect x={x} y={y} width={width} height={height} rx="7" fill={brand.off_white} stroke={brand.navy} strokeWidth="1.5"/>
      <text x={x + width / 2} y={y + height / 2 + 6} textAnchor="middle" fontFamily="Be Vietnam Pro, sans-serif" fontSize="18" fontWeight="800" fill={brand.navy} stroke={brand.off_white} strokeWidth="2" paintOrder="stroke fill">{label.text}</text>
    </g>;
  })}
</g>;
export const ProcessArrow: React.FC<{d: string; visible?: boolean}> = ({d, visible = true}) => visible ? <path data-process-arrow="true" d={d} fill="none" stroke={brand.yellow} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/> : null;

