export type FormatProfile = 'vertical_clip' | 'youtube_long';

export const FORMAT_SIZES: Record<FormatProfile, {width: number; height: number}> = {
  vertical_clip: {width: 1080, height: 1920},
  youtube_long: {width: 1920, height: 1080},
};
