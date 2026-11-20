import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {brand} from '../anatomy/palette';
import {LAYOUTS, LayoutContext} from '../layout';
import {VisualAsset} from './VisualAsset';
import {YouTubeEndCard} from '../scenes/YouTubeEndCard';
import {
  MIN_LOGO_CONTRAST,
  OUTRO_LIGHT_BG,
  contrastRatio,
  isReverseLogoPath,
  logoBadgeSpec,
} from './logoContrast';

vi.mock('remotion', async (original) => ({
  ...await original<typeof import('remotion')>(),
  AbsoluteFill: 'div',
  Img: 'img',
  staticFile: (path: string) => path,
  useCurrentFrame: () => 30,
  useVideoConfig: () => ({fps: 30}),
}));

describe('PYH logo contrast across all surfaces', () => {
  it('confirms why unframed reverse/teal marks were pale on the light outro background', () => {
    expect(contrastRatio(brand.off_white, OUTRO_LIGHT_BG)).toBeLessThan(1.2);
    expect(contrastRatio(brand.teal, OUTRO_LIGHT_BG)).toBeLessThan(3.5);
  });

  it('guarantees >= 4.5:1 WCAG contrast on every logo badge and scene background', () => {
    // Primary logo on light OutroScene (#FFFDF7)
    const primaryLight = logoBadgeSpec({reverse: false, onDark: false});
    expect(contrastRatio(primaryLight.inkColor, primaryLight.backgroundColor)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);
    expect(contrastRatio(brand.charcoal, primaryLight.backgroundColor)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);
    expect(contrastRatio(primaryLight.borderColor, OUTRO_LIGHT_BG)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);

    // Reverse logo on light OutroScene (#FFFDF7)
    const reverseLight = logoBadgeSpec({reverse: true, onDark: false});
    expect(contrastRatio(reverseLight.inkColor, reverseLight.backgroundColor)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);
    expect(contrastRatio(brand.teal, reverseLight.backgroundColor)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);
    expect(contrastRatio(reverseLight.backgroundColor, OUTRO_LIGHT_BG)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);

    // Reverse logo on dark YouTubeEndCard (#0A1C2E)
    const reverseDark = logoBadgeSpec({reverse: true, onDark: true});
    expect(contrastRatio(reverseDark.inkColor, reverseDark.backgroundColor)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);
    expect(contrastRatio(brand.teal, reverseDark.backgroundColor)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);
    expect(contrastRatio(reverseDark.borderColor, brand.night)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);

    // Primary logo on dark YouTubeEndCard (#0A1C2E)
    const primaryDark = logoBadgeSpec({reverse: false, onDark: true});
    expect(contrastRatio(primaryDark.inkColor, primaryDark.backgroundColor)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);
    expect(contrastRatio(primaryDark.backgroundColor, brand.night)).toBeGreaterThanOrEqual(MIN_LOGO_CONTRAST);
  });

  it('detects reverse vs primary logo paths reliably', () => {
    expect(isReverseLogoPath('clips/cta/logo.svg', false)).toBe(true);
    expect(isReverseLogoPath('brand/reverse.svg', false)).toBe(true);
    expect(isReverseLogoPath('assets/pyh-primary.svg', true)).toBe(false);
    expect(isReverseLogoPath('assets/pyh.svg', false)).toBe(false);
    expect(isReverseLogoPath('custom/logo.svg', true)).toBe(true);
  });

  it('renders a high-contrast badge for VisualAsset brand logos and YouTubeEndCard', () => {
    const outroPrimaryHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <VisualAsset asset={{path: 'assets/pyh.svg', role: 'brand'}} outro />
      </LayoutContext.Provider>,
    );
    expect(outroPrimaryHtml).toContain('aria-label="PYH brand"');
    expect(outroPrimaryHtml).toContain('data-brand-badge="true"');
    expect(outroPrimaryHtml).toContain('data-brand-variant="primary"');
    expect(outroPrimaryHtml).toContain(`border:3px solid ${brand.navy}`);

    const outroReverseHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.youtube_long}>
        <VisualAsset asset={{path: 'clips/cta/logo.svg', role: 'brand'}} outro />
      </LayoutContext.Provider>,
    );
    expect(outroReverseHtml).toContain('data-brand-variant="reverse"');
    expect(outroReverseHtml).toContain(`background-color:${brand.night}`);

    const endCardHtml = renderToStaticMarkup(
      <LayoutContext.Provider value={LAYOUTS.vertical_clip}>
        <YouTubeEndCard text="Xem bản đầy đủ trên YouTube" mascotPath="clips/cta/welcome.svg" />
      </LayoutContext.Provider>,
    );
    expect(endCardHtml).toContain('data-end-card-logo-badge="true"');
    expect(endCardHtml).toContain(`border:2px solid ${brand.teal}`);
  });
});
