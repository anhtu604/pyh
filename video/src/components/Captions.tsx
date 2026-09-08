import React from 'react';
import {useCurrentFrame} from 'remotion';

type CaptionsProps = {
  text: string;
  durationInFrames: number;
};

const MAX_CAPTION_WORDS = 6;

type CaptionWord = {
  index: number;
  text: string;
};

export const captionRows = (
  words: readonly string[],
  activeIndex: number,
  maxWords: number,
): {startIndex: number; rows: CaptionWord[][]} => {
  const pageSize = Math.max(1, Math.floor(maxWords));
  const safeIndex = Math.max(0, Math.min(activeIndex, Math.max(words.length - 1, 0)));
  const startIndex = Math.floor(safeIndex / pageSize) * pageSize;
  const page = words
    .slice(startIndex, startIndex + pageSize)
    .map((text, offset) => ({index: startIndex + offset, text}));
  const firstRowLength = Math.ceil(page.length / 2);
  const rows = [page.slice(0, firstRowLength), page.slice(firstRowLength)].filter(
    (row) => row.length > 0,
  );

  return {startIndex, rows};
};

export const Captions: React.FC<CaptionsProps> = ({text, durationInFrames}) => {
  const frame = useCurrentFrame();
  const words = text.trim().split(/\s+/).filter(Boolean);
  const activeWord = words.length === 0
    ? -1
    : Math.min(words.length - 1, Math.floor((frame / Math.max(durationInFrames, 1)) * words.length));
  const layout = captionRows(words, activeWord, MAX_CAPTION_WORDS);

  return (
    <svg
      aria-label="Phụ đề đang đọc"
      viewBox="0 0 936 136"
      style={{
        bottom: 174,
        height: 136,
        left: 72,
        position: 'absolute',
        right: 72,
        width: 936,
      }}
    >
      {layout.rows.map((row, rowIndex) => (
        <text
          key={row[0]?.index}
          fill="#202124"
          fontFamily="Arial, sans-serif"
          fontSize="48"
          fontWeight="700"
          lengthAdjust="spacingAndGlyphs"
          textAnchor="middle"
          textLength="900"
          x="468"
          y={rowIndex === 0 ? 52 : 116}
        >
          {row.map((word, index) => (
            <tspan fill={word.index === activeWord ? '#D97706' : undefined} key={word.index}>
              {word.text}{index < row.length - 1 ? ' ' : null}
            </tspan>
          ))}
        </text>
      ))}
    </svg>
  );
};
