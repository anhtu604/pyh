import {FONT_FAMILY} from '../fonts';
import React from 'react';
import {AbsoluteFill, Img, staticFile, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {brand} from '../anatomy/palette';
import {useLayout} from '../layout';

export const endCardGeometry = (width: number, height: number) => {
  const vertical = height > width;
  const groupWidth = vertical ? 740 : 1200;
  const mascotHeight = vertical ? height * 0.30 : 300;
  const mascotWidth = mascotHeight * 998 / 1351;
  const logoHeight = vertical ? 64 : 48;
  const logoWidth = logoHeight * 760 / 300;
  const groupHeight = 174 + 16 + mascotHeight + 32 + logoHeight;
  return {group: {left: (width - groupWidth) / 2, top: (height - groupHeight) / 2,
    width: groupWidth, height: groupHeight},
  mascot: {left: (groupWidth - mascotWidth) / 2, top: 190, width: mascotWidth, height: mascotHeight},
  logo: {left: (groupWidth - logoWidth) / 2, top: 190 + mascotHeight + 32, width: logoWidth, height: logoHeight}};
};

export const YouTubeEndCard: React.FC<{text: string; mascotPath: string; logoPath?: string}> = ({text, mascotPath, logoPath = 'clips/cta/logo.svg'}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {width, height} = useLayout().frame;
  const {group, mascot, logo} = endCardGeometry(width, height);
  const entrance = spring({frame, fps, config: {damping: 18, stiffness: 140, mass: 0.8}});
  return <AbsoluteFill style={{backgroundColor: brand.night, color: brand.off_white}}>
    <div data-end-card-group="true" style={{...group, position: 'absolute', opacity: entrance,
      transform: `translateY(${(1 - entrance) * 40}px)`}}>
      <div data-end-card-text="true" style={{height: 174, display: 'flex', alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', fontFamily: FONT_FAMILY, fontSize: 72, fontWeight: 800,
        lineHeight: 1.2, overflowWrap: 'anywhere'}}>
        <span>{text.split('YouTube').map((part, i) => <React.Fragment key={i}>
          {i > 0 && <span style={{color: brand.yellow}}>YouTube</span>}{part}
        </React.Fragment>)}</span>
      </div>
      <Img aria-label="PYH mascot welcome" src={staticFile(mascotPath)} style={{...mascot, position: 'absolute', objectFit: 'contain'}} />
      <Img aria-label="PYH logo" src={staticFile(logoPath)} style={{...logo, position: 'absolute', objectFit: 'contain'}} />
    </div>
  </AbsoluteFill>;
};
