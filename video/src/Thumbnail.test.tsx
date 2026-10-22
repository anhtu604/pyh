import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {headlineLayout, Thumbnail} from './Thumbnail';

vi.mock('remotion', () => ({
  AbsoluteFill: ({children}: {children: React.ReactNode}) => <div>{children}</div>,
  Img: ({src}: {src: string}) => <img src={src} />,
  staticFile: (s: string) => s,
}));

it.each(['Ắ'.repeat(60), 'Tại sao huyết áp tăng âm thầm khiến chúng ta khó nhận ra dấu?!!'.padEnd(60, 'ế').slice(0, 60), 'W'.repeat(60)])(
  'renders sixty Vietnamese characters inside the safe headline box: %s', (headline) => {
    expect(headline).toHaveLength(60);
    const layout = headlineLayout(headline);
    expect(layout.lines.join('').replace(/\s/g, '')).toBe(headline.replace(/\s/g, ''));
    // Conservative advance bound is wider than every glyph in the bundled font.
    for (const line of layout.lines) expect(Array.from(line).length * layout.fontSize * 1.25).toBeLessThanOrEqual(780);
    expect(layout.lines.length * layout.fontSize * 1.55).toBeLessThanOrEqual(488);
    const html = renderToStaticMarkup(<Thumbnail headline={headline} background="bg.png" logo="logo.svg" />);
    expect(html).toContain('bg.png');
    expect(html).toContain('logo.svg');
    expect(html).not.toContain('claim:');
  },
);
