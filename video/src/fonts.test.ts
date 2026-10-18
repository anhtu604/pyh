import {afterEach, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({delay: vi.fn(() => 123), resume: vi.fn(), cancel: vi.fn()}));
vi.mock('remotion', () => ({staticFile: (path: string) => `/static/${path}`,
  delayRender: mocks.delay, continueRender: mocks.resume, cancelRender: mocks.cancel}));
afterEach(() => {vi.unstubAllGlobals(); vi.resetModules(); vi.clearAllMocks();});

it('loads both bundled weights once and waits for them before rendering Vietnamese', async () => {
  const faces: {family: string; source: string; weight: string}[] = [];
  const resolvers: (() => void)[] = [];
  const add = vi.fn();
  vi.stubGlobal('document', {fonts: {add}});
  vi.stubGlobal('FontFace', class {
    constructor(family: string, source: string, descriptors: {weight: string}) {
      faces.push({family, source, weight: descriptors.weight});
    }
    load() {return new Promise((resolve) => resolvers.push(() => resolve(this)));}
  });
  const fonts = await import('./fonts');
  expect(fonts.FONT_FAMILY).toBe("'Be Vietnam Pro', Arial, sans-serif");
  expect(faces).toEqual([
    {family: 'Be Vietnam Pro', source: 'url(/static/fonts/BeVietnamPro-SemiBold.woff2)', weight: '600'},
    {family: 'Be Vietnam Pro', source: 'url(/static/fonts/BeVietnamPro-ExtraBold.woff2)', weight: '800'},
  ]);
  expect(mocks.delay).toHaveBeenCalledTimes(1);
  expect(mocks.resume).not.toHaveBeenCalled();
  resolvers.forEach((resolve) => resolve());
  await fonts.fontsReady;
  await import('./fonts');
  expect(add).toHaveBeenCalledTimes(2);
  expect(mocks.resume).toHaveBeenCalledExactlyOnceWith(123);
});

it('cancels rendering if a local font cannot load', async () => {
  vi.stubGlobal('document', {fonts: {add: vi.fn()}});
  vi.stubGlobal('FontFace', class {load() {return Promise.reject(new Error('font unavailable'));}});
  const fonts = await import('./fonts');
  await fonts.fontsReady;
  expect(mocks.cancel).toHaveBeenCalledWith(expect.objectContaining({message: 'font unavailable'}));
  expect(mocks.resume).not.toHaveBeenCalled();
});
