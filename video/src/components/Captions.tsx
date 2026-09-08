import React from 'react';
import {useCurrentFrame} from 'remotion';

type CaptionsProps = {
  text: string;
  durationInFrames: number;
};

const MAX_CAPTION_WORDS = 6;

export const captionWindow = (
  words: readonly string[],
  activeIndex: number,
  maxWords: number,
): {startIndex: number; words: string[]} => {
  const pageSize = Math.max(1, Math.floor(maxWords));
  const safeIndex = Math.max(0, Math.min(activeIndex, Math.max(words.length - 1, 0)));
  const startIndex = Math.floor(safeIndex / pageSize) * pageSize;

  return {startIndex, words: words.slice(startIndex, startIndex + pageSize)};
};

export const Captions: React.FC<CaptionsProps> = ({text, durationInFrames}) => {
  const frame = useCurrentFrame();
  const words = text.trim().split(/\s+/).filter(Boolean);
  const activeWord = words.length === 0
    ? -1
    : Math.min(words.length - 1, Math.floor((frame / Math.max(durationInFrames, 1)) * words.length));
  const visible = captionWindow(words, activeWord, MAX_CAPTION_WORDS);

  return (
    <div
      style={{
        bottom: 174,
        color: '#202124',
        fontFamily: 'Arial, sans-serif',
        fontSize: 48,
        fontWeight: 700,
        left: 72,
        lineHeight: 1.2,
        maxHeight: '2.4em',
        overflow: 'hidden',
        position: 'absolute',
        right: 72,
        textAlign: 'center',
        display: '-webkit-box',
        WebkitBoxOrient: 'vertical',
        WebkitLineClamp: 2,
      }}
    >
      {visible.words.map((word, index) => {
        const wordIndex = visible.startIndex + index;
        return (
          <React.Fragment key={`${word}-${wordIndex}`}>
            <span style={{color: wordIndex === activeWord ? '#D97706' : undefined}}>{word}</span>
            {index < visible.words.length - 1 ? ' ' : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};
