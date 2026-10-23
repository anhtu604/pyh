import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {Captions, CAPTION_ACTIVE_COLOR} from './Captions';
const clock = vi.hoisted(() => ({frame: 10}));
vi.mock('remotion', () => ({useCurrentFrame: () => clock.frame}));

it('uses aligned words and their real intervals instead of uniform timing', () => {
  const words = [{text: 'Chất', start_frame: 0, end_frame: 5}, {text: 'urat', start_frame: 8, end_frame: 25}];
  const render = () => renderToStaticMarkup(<Captions text="Chất urat" durationInFrames={300} words={words}/>);
  expect(render()).toContain(`<tspan fill="${CAPTION_ACTIVE_COLOR}">urat`);
  clock.frame = 6;
  expect(render()).not.toContain(`<tspan fill="${CAPTION_ACTIVE_COLOR}">`);
  clock.frame = 26;
  expect(render()).not.toContain(`<tspan fill="${CAPTION_ACTIVE_COLOR}">`);
});

it('keeps the preceding page during a silence and switches at the next word start', () => {
  const words = Array.from({length: 9}, (_, index) => ({text: `word${index}`,
    start_frame: 20 + index * 20, end_frame: 30 + index * 20}));
  const render = (frame: number) => {
    clock.frame = frame;
    return renderToStaticMarkup(<Captions text="unused" durationInFrames={500} words={words}/>);
  };
  expect(render(139)).toContain('word0');
  expect(render(139)).not.toContain('word6');
  expect(render(140)).toContain('word6');
  expect(render(140)).not.toContain('word0');
  expect(render(140)).toContain(`<tspan fill="${CAPTION_ACTIVE_COLOR}">word6`);
});

it('keeps uniform legacy highlighting when timing is absent or empty', () => {
  clock.frame = 60;
  const render = (words?: []) => renderToStaticMarkup(<Captions text="Một hai ba" durationInFrames={90} words={words}/>);
  expect(render()).toContain(`<tspan fill="${CAPTION_ACTIVE_COLOR}">ba`);
  expect(render([])).toEqual(render());
});
