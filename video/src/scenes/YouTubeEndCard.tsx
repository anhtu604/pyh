import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {brand} from '../anatomy/palette';
import {MascotGuide} from '../components/MascotGuide';
import {useLayout} from '../layout';

export const endCardGeometry = (width: number, height: number) => {
  const vertical = height > width;
  const groupWidth = vertical ? 740 : 1200;
  const mascotHeight = vertical ? 450 : 300;
  const mascotWidth = mascotHeight * 380 / 450;
  const groupHeight = 174 + 16 + mascotHeight;
  return {group: {left: (width - groupWidth) / 2, top: (height - groupHeight) / 2,
    width: groupWidth, height: groupHeight},
  mascot: {left: (groupWidth - mascotWidth) / 2, top: 190, width: mascotWidth, height: mascotHeight}};
};

export const YouTubeEndCard: React.FC<{text: string; mascotPath: string}> = ({text, mascotPath}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {width, height} = useLayout().frame;
  const {group, mascot} = endCardGeometry(width, height);
  const entrance = spring({frame, fps, config: {damping: 18, stiffness: 140, mass: 0.8}});
  return <AbsoluteFill style={{backgroundColor: brand.night, color: brand.off_white}}>
    <div data-end-card-group="true" style={{...group, position: 'absolute', opacity: entrance,
      transform: `translateY(${(1 - entrance) * 40}px)`}}>
      <div data-end-card-text="true" style={{height: 174, display: 'flex', alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', fontFamily: 'Arial, sans-serif', fontSize: 72, fontWeight: 700,
        lineHeight: 1.2, overflowWrap: 'anywhere'}}>
        <span>{text.split('YouTube').map((part, i) => <React.Fragment key={i}>
          {i > 0 && <span style={{color: brand.yellow}}>YouTube</span>}{part}
        </React.Fragment>)}</span>
      </div>
      <MascotGuide box={mascot} groupEntrance scene={{visual_assets: [{path: mascotPath, role: 'mascot', pose: 'welcome'}]}} />
    </div>
  </AbsoluteFill>;
};
