import type {EvidenceHighlight} from '../types';

type Frame = {width: number; height: number};
const VERTICAL_FRAME: Frame = {width: 1080, height: 1920};

export type ImageLayout = {left: number; top: number; width: number; height: number};

export const isHardenedCrop = (highlight: EvidenceHighlight): boolean =>
  highlight.crop_pixel_width != null && highlight.crop_pixel_height != null;

export const cropImageLayout = (pixelWidth: number, pixelHeight: number, frame: Frame = VERTICAL_FRAME): ImageLayout => {
  const scale = Math.min(frame.width / pixelWidth, frame.height / pixelHeight);
  const width = pixelWidth * scale;
  const height = pixelHeight * scale;
  return {
    left: (frame.width - width) / 2,
    top: (frame.height - height) / 2,
    width,
    height,
  };
};

export const highlightImageLayout = (highlight: EvidenceHighlight, frame: Frame = VERTICAL_FRAME): ImageLayout => {
  const pixelWidth = highlight.crop_pixel_width;
  const pixelHeight = highlight.crop_pixel_height;
  return pixelWidth != null && pixelHeight != null
    ? cropImageLayout(pixelWidth, pixelHeight, frame)
    : {left: 0, top: 0, width: frame.width, height: frame.height};
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
