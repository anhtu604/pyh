import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {FONT_FAMILY} from '../fonts';
import {useLayout} from '../layout';
import type {Scene} from '../types';

export const OUTRO_LINE_HEIGHT = 1.35;
const OUTRO_GLYPH_EM = 0.62;
const MIN_OUTRO_FONT_SIZE = 16;

export const estimateOutroTextHeight = (text: string, width: number, fontSize: number): number => {
  const maxCharsPerLine = Math.max(1, Math.floor(width / (fontSize * OUTRO_GLYPH_EM)));
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return fontSize * OUTRO_LINE_HEIGHT;
  let lines = 1;
  let currentLineChars = 0;
  for (const word of words) {
    const wordLen = Array.from(word).length;
    if (currentLineChars === 0) {
      if (wordLen > maxCharsPerLine) {
        lines += Math.ceil(wordLen / maxCharsPerLine) - 1;
        currentLineChars = wordLen % maxCharsPerLine || maxCharsPerLine;
      } else {
        currentLineChars = wordLen;
      }
    } else if (currentLineChars + 1 + wordLen <= maxCharsPerLine) {
      currentLineChars += 1 + wordLen;
    } else {
      lines += 1;
      if (wordLen > maxCharsPerLine) {
        lines += Math.ceil(wordLen / maxCharsPerLine) - 1;
        currentLineChars = wordLen % maxCharsPerLine || maxCharsPerLine;
      } else {
        currentLineChars = wordLen;
      }
    }
  }
  return lines * fontSize * OUTRO_LINE_HEIGHT;
};

export const outroFontSize = (text: string, width: number, height: number, preferred: number): number => {
  for (let size = preferred; size >= MIN_OUTRO_FONT_SIZE; size -= 1) {
    if (estimateOutroTextHeight(text, width, size) <= height) return size;
  }
  return MIN_OUTRO_FONT_SIZE;
};

export const OutroScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const t = useLayout().outroText;
  const opacity = interpolate(frame, [0, 12], [0, 1], {extrapolateRight: 'clamp'});
  const fontSize = outroFontSize(scene.narration, t.width, t.height, t.fontSize);
  return (
    <AbsoluteFill style={{backgroundColor: '#FFFDF7'}}>
      <div
        data-outro-text="true"
        style={{
          position: 'absolute',
          top: t.top,
          left: t.left,
          width: t.width,
          height: t.height,
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          overflowWrap: 'anywhere',
          fontFamily: FONT_FAMILY,
          textAlign: 'center',
          fontSize,
          lineHeight: OUTRO_LINE_HEIGHT,
          color: '#202124',
          opacity,
        }}
      >
        <span>{scene.narration}</span>
      </div>
    </AbsoluteFill>
  );
};
