import React from 'react';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {useLayout, type Box} from '../layout';
import type {Scene} from '../types';

/** Tabs are authored column stops in entrance text. Plain entrances retain their legacy layout. */
export const panelRows = (scene: Scene, columns: number) => {
  const rows = scene.entrances ?? [];
  if (!rows.length || !rows.every(row => row.text.split('\t').length === columns)) return [];
  // Mechanism beats are resolved against the real narration by the existing timing pipeline.
  return rows.map((row, index) => ({...row, start_frame: scene.beats?.length === rows.length
    ? scene.beats[index].start_frame ?? row.start_frame : row.start_frame}));
};
export const activePanelIndex = (rows: NonNullable<Scene['entrances']>, frame: number) =>
  rows.reduce((active, row, index) => row.start_frame <= frame ? index : active, -1);

export const AuthoredStep: React.FC<{scene: Scene; frame: number; box?: Box}> = ({scene, frame, box}) => {
  const rows = panelRows(scene, 2);
  const index = activePanelIndex(rows, frame);
  if (index < 0) return null;
  const [heading, detail] = rows[index].text.split('\t');
  return <section data-authored-step={index} style={{...box, position: box ? 'absolute' : 'relative',
    boxSizing: 'border-box', padding: 14, borderLeft: `8px solid ${brand.teal}`,
    borderRadius: 12, background: brand.off_white, color: brand.navy, fontFamily: FONT_FAMILY}}>
    <strong style={{display: 'block', fontSize: 32, lineHeight: 1.3}}>{heading}</strong>
    <div style={{fontSize: 30, lineHeight: 1.3}}>{detail}</div>
  </section>;
};

/** A date rail / document worksheet, with one focus per authored entrance, no implied causal arrows. */
export const AuthoredWorksheet: React.FC<{scene: Scene; frame: number}> = ({scene, frame}) => {
  const layout = useLayout();
  const box = layout.sourceCard;
  const rows = panelRows(scene, 3);
  const active = activePanelIndex(rows, frame);
  const innerWidth = box.width - 64;
  const rowHeight = (box.height - 208) / Math.max(1, rows.length);
  const widths = [innerWidth * .24, innerWidth * .32, innerWidth * .38];
  return <section aria-label={scene.on_screen_text ?? 'Phiếu minh họa'} data-worksheet="true" data-active-row={active}
    style={{...box, position: 'absolute', boxSizing: 'border-box', padding: 32,
      border: `3px solid ${brand.teal}`, borderRadius: 24, background: brand.off_white,
      color: brand.navy, fontFamily: FONT_FAMILY}}>
    <h2 style={{margin: '0 0 24px', height: 100, fontSize: 34, lineHeight: 1.3}}>{scene.on_screen_text}</h2>
    <div style={{position: 'relative'}}>
      <svg aria-hidden="true" width={innerWidth} height={rows.length * rowHeight} style={{position: 'absolute', inset: 0}}>
        <path d={`M12 ${rowHeight / 2} V${(rows.length - .5) * rowHeight}`} stroke={brand.teal} strokeWidth="3" fill="none"/>
        {rows.map((row, index) => frame >= row.start_frame ? <g key={index}>
          <path data-leader={index} d={`M12 ${(index + .5) * rowHeight} H32`} stroke={brand.navy} strokeWidth="2"/>
          <circle cx="12" cy={(index + .5) * rowHeight} r="7" fill={index === active ? brand.yellow : brand.teal}/>
        </g> : null)}
      </svg>
      {rows.map((row, index) => <div key={index} style={{height: rowHeight, paddingLeft: 40, boxSizing: 'border-box', display: 'flex', alignItems: 'center',
        visibility: frame >= row.start_frame ? 'visible' : 'hidden',
        background: index === active ? `${brand.teal}18` : 'transparent', borderRadius: 12}}>
        {frame >= row.start_frame ? row.text.split('\t').map((cell, column) => {
          let size = 32;
          while (size > 1 && Math.ceil(Array.from(cell).length / Math.max(1, Math.floor((widths[column] - 16) / size))) * size * 1.3 > rowHeight - 20) size--;
          return <div key={column} style={{width: widths[column], padding: 8, boxSizing: 'border-box',
            fontWeight: column === 0 ? 800 : 600, lineHeight: 1.3, overflowWrap: 'anywhere', whiteSpace: 'pre-line',
            fontSize: size}}>{cell}</div>;
        }) : null}
      </div>)}
    </div>
  </section>;
};
