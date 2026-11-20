import {brand} from '../anatomy/palette';

export const MIN_LOGO_CONTRAST = 4.5;
export const DEEP_NIGHT_BG = '#061320';
export const PURE_WHITE_BG = '#FFFFFF';
export const OUTRO_LIGHT_BG = '#FFFDF7';

const parseHex = (hex: string): [number, number, number] => {
  const clean = hex.replace('#', '');
  const full = clean.length === 3
    ? clean.split('').map((c) => c + c).join('')
    : clean;
  return [
    parseInt(full.slice(0, 2), 16) / 255,
    parseInt(full.slice(2, 4), 16) / 255,
    parseInt(full.slice(4, 6), 16) / 255,
  ];
};

const linearize = (channel: number): number =>
  channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;

/** WCAG 2.1 relative luminance for a hex colour. */
export const relativeLuminance = (hex: string): number => {
  const [r, g, b] = parseHex(hex).map(linearize);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

/** WCAG 2.1 contrast ratio between two hex colours (1..21). */
export const contrastRatio = (fgHex: string, bgHex: string): number => {
  const l1 = relativeLuminance(fgHex);
  const l2 = relativeLuminance(bgHex);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
};

/**
 * Infers whether a logo asset path uses light (reverse) ink.
 * `clips/cta/logo.svg` is always generated with `LogoVariant.REVERSE` in Python.
 */
export const isReverseLogoPath = (path: string, defaultReverse = false): boolean => {
  if (/reverse|cta\/logo/i.test(path)) return true;
  if (/primary|one_color|monogram/i.test(path)) return false;
  return defaultReverse;
};

export type LogoBadgeSpec = {
  backgroundColor: string;
  borderColor: string;
  inkColor: string;
  boxShadow: string;
  imageFilter: string;
};

/**
 * Returns a high-contrast badge surface for PYH logo assets so both wordmark
 * and badge border maintain >= 4.5:1 WCAG contrast on light and dark scenes.
 */
export const logoBadgeSpec = ({reverse, onDark}: {reverse: boolean; onDark: boolean}): LogoBadgeSpec => {
  if (reverse) {
    return {
      backgroundColor: onDark ? DEEP_NIGHT_BG : brand.night,
      borderColor: brand.teal,
      inkColor: brand.off_white,
      boxShadow: onDark
        ? '0 4px 16px rgba(0, 0, 0, 0.45)'
        : '0 8px 24px rgba(10, 28, 46, 0.24)',
      imageFilter: 'contrast(1.06)',
    };
  }
  return {
    backgroundColor: PURE_WHITE_BG,
    borderColor: brand.navy,
    inkColor: brand.navy,
    boxShadow: onDark
      ? '0 4px 16px rgba(0, 0, 0, 0.4)'
      : '0 8px 24px rgba(18, 48, 74, 0.16)',
    imageFilter: 'contrast(1.12) saturate(1.15)',
  };
};
