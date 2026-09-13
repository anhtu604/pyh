import type {EvidenceHighlight} from '../types';

const FRAME_WIDTH = 1080;
const FRAME_HEIGHT = 1920;

export type ImageLayout = {left: number; top: number; width: number; height: number};

export const isHardenedCrop = (highlight: EvidenceHighlight): boolean =>
  highlight.crop_pixel_width != null && highlight.crop_pixel_height != null;

export const cropImageLayout = (pixelWidth: number, pixelHeight: number): ImageLayout => {
  const scale = Math.min(FRAME_WIDTH / pixelWidth, FRAME_HEIGHT / pixelHeight);
  const width = pixelWidth * scale;
  const height = pixelHeight * scale;
  return {
    left: (FRAME_WIDTH - width) / 2,
    top: (FRAME_HEIGHT - height) / 2,
    width,
    height,
  };
};

export const highlightImageLayout = (highlight: EvidenceHighlight): ImageLayout => {
  const pixelWidth = highlight.crop_pixel_width;
  const pixelHeight = highlight.crop_pixel_height;
  return pixelWidth != null && pixelHeight != null
    ? cropImageLayout(pixelWidth, pixelHeight)
    : {left: 0, top: 0, width: FRAME_WIDTH, height: FRAME_HEIGHT};
};

export const highlightObjectFit = (highlight: EvidenceHighlight): 'contain' | 'cover' =>
  isHardenedCrop(highlight) ? 'contain' : 'cover';

export const localHighlightRect = (highlight: EvidenceHighlight) => {
  const cropWidth = highlight.crop_width ?? 1;
  const cropHeight = highlight.crop_height ?? 1;
  return {
    x: (highlight.x - (highlight.crop_x ?? 0)) / cropWidth,
    y: (highlight.y - (highlight.crop_y ?? 0)) / cropHeight,
    width: highlight.width / cropWidth,
    height: highlight.height / cropHeight,
  };
};
