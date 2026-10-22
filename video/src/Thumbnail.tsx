import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {brand} from './anatomy/palette';
import {FONT_FAMILY} from './fonts';

export type ThumbnailProps = {
  headline: string;
  background: string;
  logo: string;
  mascot?: string;
  colors?: {navy: string; night: string; teal: string; yellow: string; off_white: string; charcoal: string};
};

// Each advance is bounded by 1.25 em (including W and Vietnamese diacritics).
// Explicit SVG rows avoid browser wrapping differences and leave 1.55 em for accents.
export const headlineLayout = (headline: string) => {
  const text = headline.normalize('NFC').trim().replace(/\s+/g, ' ');
  for (let fontSize = 88; fontSize >= 20; fontSize--) {
    const limit = Math.floor(780 / (fontSize * 1.25));
    const lines: string[] = [];
    let row = '';
    for (const word of text.split(' ')) {
      if (row && Array.from(`${row} ${word}`).length <= limit) {row += ` ${word}`; continue;}
      if (row) {lines.push(row); row = '';}
      const chars = Array.from(word);
      while (chars.length > limit) lines.push(chars.splice(0, limit).join(''));
      row = chars.join('');
    }
    if (row) lines.push(row);
    if (lines.length * fontSize * 1.55 <= 488) return {lines, fontSize};
  }
  throw new Error('Thumbnail headline exceeds the safe area');
};

export const Thumbnail: React.FC<ThumbnailProps> = ({headline, background, logo, mascot, colors = brand}) => {
  const {lines, fontSize} = headlineLayout(headline);
  return (
    <AbsoluteFill style={{backgroundColor: colors.navy}}>
      <Img src={staticFile(background)} style={{position: 'absolute', width: 1280, height: 720, objectFit: 'cover'}} />
      <AbsoluteFill style={{background: `linear-gradient(90deg, ${colors.night} 0%, ${colors.night}ee 45%, ${colors.night}22 100%)`}} />
      <Img src={staticFile(logo)} style={{position: 'absolute', left: 48, top: 16, width: 300, height: 118, objectFit: 'contain'}} />
      <div style={{position: 'absolute', left: 64, top: 148, width: 100, height: 8, background: colors.teal}} />
      <svg width={1280} height={720} style={{position: 'absolute', inset: 0}} aria-label={headline}>
        {lines.map((line, i) => <text key={i} x={64} y={196 + fontSize * 1.215 + i * fontSize * 1.55}
          fontFamily={FONT_FAMILY} fontWeight={800} fontSize={fontSize}
          fill={i === lines.length - 1 ? colors.yellow : colors.off_white}>{line}</text>)}
      </svg>
      {mascot ? <Img src={staticFile(mascot)} style={{position: 'absolute', right: 40, bottom: 36, width: 260, height: 300, objectFit: 'contain'}} /> : null}
    </AbsoluteFill>
  );
};
