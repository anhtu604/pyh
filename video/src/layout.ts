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
  whiteboardText: Box;
  illustrationText: Box;
  chart: {image: Box};
  outroText: {left: number; top: number; width: number; fontSize: number};
  quote: {bottom: number; inset: number; fontSize: number};
  assets: {brand: Box; outroBrand: Box; outroMascot: Box; whiteboard: Box; explain: Box; standard: Box};
};

export const LAYOUTS: Record<FormatProfile, FrameLayout> = {
  vertical_clip: {
    mechanism: {
      subject: {left: 40, top: 180, width: 1000, height: 1100},
      comparison: [{left: 290, top: 180, width: 500, height: 530}, {left: 290, top: 740, width: 500, height: 530}],
      axis: 'column', mascot: {left: 48, top: 1280, width: 378.125, height: 330},
    },
    frame: {width: 1080, height: 1920},
    // Preserve the caption band's top while padding the bundled font's stacked accents.
    captions: {left: 72, bottom: 150, width: 936, height: 160, fontSize: 48,
      maxTextWidth: 900, rowY: [64, 140], maxWords: 6},
    narration: {left: 96, right: 96, top: 760, fontSize: 72},
    sourceMarker: {right: 72, top: 96, fontSize: 52},
    whiteboardText: {left: 96, top: 760, width: 888, height: 240},
    illustrationText: {left: 96, top: 760, width: 888, height: 240},
    whiteboardPath: 'M180 1050 C 420 1010, 680 1090, 900 1040',
    chart: {image: {left: 40, top: 210, width: 1000, height: 1368}},
    outroText: {left: 90, top: 850, width: 900, fontSize: 54},
    quote: {bottom: 390, inset: 72, fontSize: 46},
    assets: {
      brand: {left: 210, top: 250, width: 660, height: 480},
      outroBrand: {left: 130, top: 250, width: 520, height: 340},
      outroMascot: {left: 48, top: 1034, width: 660, height: 576},
      whiteboard: {left: 90, top: 180, width: 900, height: 550},
      explain: {left: 48, top: 1034, width: 660, height: 576},
      standard: {left: 48, top: 1034, width: 660, height: 576},
    },
  },
  youtube_long: {
    mechanism: {
      subject: {left: 520, top: 40, width: 880, height: 820},
      comparison: [{left: 500, top: 160, width: 600, height: 680}, {left: 1180, top: 160, width: 600, height: 680}],
      axis: 'row', mascot: {left: 0, top: 669.6, width: 470, height: 410.4},
    },
    frame: {width: 1920, height: 1080},
    captions: {left: 500, bottom: 32, width: 1200, height: 148, fontSize: 44,
      maxTextWidth: 1160, rowY: [60, 130], maxWords: 10},
    narration: {left: 160, right: 160, top: 380, fontSize: 64},
    sourceMarker: {right: 72, top: 56, fontSize: 44},
    whiteboardText: {left: 500, top: 300, width: 1200, height: 300},
    illustrationText: {left: 500, top: 650, width: 1200, height: 210},
    whiteboardPath: 'M620 640 C 900 600, 1300 680, 1580 630',
    chart: {image: {left: 70, top: 60, width: 1780, height: 808}},
    outroText: {left: 360, top: 420, width: 1200, fontSize: 54},
    quote: {bottom: 200, inset: 160, fontSize: 40},
    assets: {
      brand: {left: 1320, top: 60, width: 520, height: 300},
      outroBrand: {left: 200, top: 200, width: 520, height: 340},
      outroMascot: {left: 0, top: 669.6, width: 470, height: 410.4},
      whiteboard: {left: 500, top: 80, width: 1200, height: 540},
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
