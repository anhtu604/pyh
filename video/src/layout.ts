import {createContext, useContext} from 'react';
import type {FormatProfile} from './format';

export type Box = {left: number; top: number; width: number; height: number};

export type FrameLayout = {
  frame: {width: number; height: number};
  captions: {left: number; bottom: number; width: number; height: number;
    fontSize: number; maxTextWidth: number; rowY: [number, number]; maxWords: number};
  narration: {left: number; right: number; top: number; fontSize: number};
  sourceMarker: {right: number; top: number; fontSize: number};
  whiteboardPath: string;
  chart: {image: Box; narrationBottom: number; narrationFontSize: number; narrationInset: number};
  outroText: {left: number; top: number; width: number; fontSize: number};
  quote: {bottom: number; inset: number; fontSize: number};
  assets: {brand: Box; outroBrand: Box; outroMascot: Box; whiteboard: Box; explain: Box; standard: Box};
};

export const LAYOUTS: Record<FormatProfile, FrameLayout> = {
  vertical_clip: {
    frame: {width: 1080, height: 1920},
    captions: {left: 72, bottom: 174, width: 936, height: 136, fontSize: 48,
      maxTextWidth: 900, rowY: [52, 116], maxWords: 6},
    narration: {left: 96, right: 96, top: 760, fontSize: 72},
    sourceMarker: {right: 72, top: 96, fontSize: 52},
    whiteboardPath: 'M150 570 C 350 400, 650 740, 930 530',
    chart: {image: {left: 70, top: 210, width: 940, height: 1040},
      narrationBottom: 430, narrationFontSize: 58, narrationInset: 84},
    outroText: {left: 90, top: 850, width: 900, fontSize: 54},
    quote: {bottom: 390, inset: 72, fontSize: 46},
    assets: {
      brand: {left: 210, top: 250, width: 660, height: 480},
      outroBrand: {left: 130, top: 250, width: 520, height: 340},
      outroMascot: {left: 650, top: 250, width: 320, height: 360},
      whiteboard: {left: 90, top: 190, width: 900, height: 980},
      explain: {left: 390, top: 650, width: 570, height: 690},
      standard: {left: 60, top: 650, width: 570, height: 690},
    },
  },
  youtube_long: {
    frame: {width: 1920, height: 1080},
    captions: {left: 360, bottom: 60, width: 1200, height: 120, fontSize: 44,
      maxTextWidth: 1160, rowY: [48, 104], maxWords: 10},
    narration: {left: 160, right: 160, top: 380, fontSize: 64},
    sourceMarker: {right: 72, top: 56, fontSize: 44},
    whiteboardPath: 'M260 300 C 620 180, 1180 460, 1660 280',
    chart: {image: {left: 260, top: 90, width: 1400, height: 700},
      narrationBottom: 210, narrationFontSize: 48, narrationInset: 160},
    outroText: {left: 360, top: 420, width: 1200, fontSize: 54},
    quote: {bottom: 200, inset: 160, fontSize: 40},
    assets: {
      brand: {left: 1320, top: 60, width: 520, height: 300},
      outroBrand: {left: 200, top: 200, width: 520, height: 340},
      outroMascot: {left: 1300, top: 200, width: 400, height: 400},
      whiteboard: {left: 460, top: 60, width: 1000, height: 760},
      explain: {left: 1380, top: 180, width: 460, height: 620},
      standard: {left: 80, top: 180, width: 460, height: 620},
    },
  },
};

export const LayoutContext = createContext<FrameLayout>(LAYOUTS.vertical_clip);
// Falls back to the vertical table when called outside a React render (unit tests call components directly).
export const useLayout = (): FrameLayout => {
  try {
    return useContext(LayoutContext);
  } catch {
    return LAYOUTS.vertical_clip;
  }
};
