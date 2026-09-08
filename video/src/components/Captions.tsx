import React from 'react';
import {useCurrentFrame} from 'remotion';

type CaptionsProps = {
  text: string;
  durationInFrames: number;
};

export const Captions: React.FC<CaptionsProps> = ({text, durationInFrames}) => {
  const frame = useCurrentFrame();
  const words = text.trim().split(/\s+/).filter(Boolean);
  const activeWord = Math.min(
    words.length - 1,
    Math.floor((frame / Math.max(durationInFrames, 1)) * words.length),
  );

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
      }}
    >
      {words.map((word, index) => (
        <React.Fragment key={`${word}-${index}`}>
          <span style={{color: index === activeWord ? '#D97706' : undefined}}>{word}</span>
          {index < words.length - 1 ? ' ' : null}
        </React.Fragment>
      ))}
    </div>
  );
};
