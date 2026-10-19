import {createContext, useContext} from 'react';
import type {FormatProfile} from './format';

export type Box = {left: number; top: number; width: number; height: number};

export type FrameLayout = {
  mechanism: {subject: Box; comparison: [Box, Box]; axis: 'row' | 'column'; mascot: Box};
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
    mechanism: {
      subject: {left: 300, top: 160, width: 560, height: 800},
      comparison: [{left: 360, top: 100, width: 500, height: 420}, {left: 360, top: 560, width: 500, height: 420}],
      axis: 'column', mascot: {left: 48, top: 1034, width: 660, height: 576},
    },
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
      outroMascot: {left: 48, top: 1034, width: 660, height: 576},
      whiteboard: {left: 90, top: 190, width: 900, height: 980},
      explain: {left: 48, top: 1034, width: 660, height: 576},
      standard: {left: 48, top: 1034, width: 660, height: 576},
    },
  },
  youtube_long: {
    mechanism: {
      subject: {left: 590, top: 130, width: 850, height: 800},
      comparison: [{left: 500, top: 160, width: 600, height: 680}, {left: 1180, top: 160, width: 600, height: 680}],
      axis: 'row', mascot: {left: 0, top: 669.6, width: 470, height: 410.4},
    },
    frame: {width: 1920, height: 1080},
    captions: {left: 500, bottom: 60, width: 1200, height: 120, fontSize: 44,
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
      outroMascot: {left: 0, top: 669.6, width: 470, height: 410.4},
      whiteboard: {left: 460, top: 60, width: 1000, height: 760},
      explain: {left: 0, top: 669.6, width: 470, height: 410.4},
      standard: {left: 0, top: 669.6, width: 470, height: 410.4},
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
