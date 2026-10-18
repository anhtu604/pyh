import {cancelRender, continueRender, delayRender, staticFile} from 'remotion';

export const FONT_FAMILY = "'Be Vietnam Pro', Arial, sans-serif";

// Module caching keeps the render barrier and local font requests shared by all scenes.
export const fontsReady: Promise<void> = typeof document === 'undefined' || typeof FontFace === 'undefined'
  ? Promise.resolve()
  : (() => {
    const handle = delayRender('Loading Be Vietnam Pro');
    return Promise.all([
      ['SemiBold', '600'], ['ExtraBold', '800'],
    ].map(async ([name, weight]) => {
      const face = new FontFace('Be Vietnam Pro', `url(${staticFile(`fonts/BeVietnamPro-${name}.woff2`)})`, {weight});
      document.fonts.add(await face.load());
    })).then(() => {continueRender(handle);}).catch((error: unknown) => {
      cancelRender(error instanceof Error ? error : new Error(String(error)));
    });
  })();
