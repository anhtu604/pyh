import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it} from 'vitest';
import {LiverLobule, CONTENT_BOX} from './LiverLobule';

const render = (severity: number, state: 'normal' | 'diseased' = 'diseased') =>
  renderToStaticMarkup(<LiverLobule state={state} severity={severity} />);
it('shows a central vein, six portal triads, radial cords and sinusoids without labels', () => {
  const html = render(0, 'normal');
  for (const layer of ['central-vein', 'portal-triads', 'hepatocyte-cords', 'sinusoids']) expect(html).toContain(`data-layer="${layer}"`);
  expect(html.match(/data-portal-triad=/g)).toHaveLength(6);
  expect(html).not.toMatch(/<text|gradient|filter=/i);
  expect(CONTENT_BOX).toEqual({left: 22, top: 22, width: 516, height: 516});
  expect(html).toContain('points="280,22 538,151 538,409 280,538 22,409 22,151"');
});
it('keeps fat intracellular, with separate inflammatory foci and thin portal fibrosis at high severity', () => {
  const count = (s: number) => (render(s).match(/data-fat-droplet=/g) ?? []).length;
  expect(count(0)).toBe(0);
  expect(count(.3)).toBeGreaterThan(0);
  expect(count(1)).toBeGreaterThan(count(.3));
  expect(render(.3)).not.toContain('data-layer="inflammation"');
  expect(render(1)).toContain('data-layer="inflammation"');
  expect(render(1)).toContain('data-layer="portal-fibrosis"');
  expect(render(1, 'normal')).toBe(render(0, 'normal'));
});
