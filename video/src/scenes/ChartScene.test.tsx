import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {ChartScene} from './ChartScene';

const {staticFile} = vi.hoisted(() => ({staticFile: vi.fn((path: string) => path)}));
vi.mock('remotion', () => ({Img: 'img', staticFile}));

describe('ChartScene', () => {
  it('renders exactly the declared SVG path and keeps narration and marker', () => {
    const scene = {
      id: 'S01', start_frame: 0, duration_frames: 90, narration: 'Số liệu đã duyệt',
      source_marker: '[1]', visual: 'chart' as const,
      visual_assets: [{path: 'assets/chart.svg', role: 'chart' as const}],
    };

    const root = ChartScene({scene}) as React.ReactElement<{children: React.ReactNode}>;
    const children = React.Children.toArray(root.props.children);
    const images = children.filter(
      (child) => React.isValidElement(child) && child.type === 'img',
    ) as React.ReactElement<{src: string}>[];
    expect(images).toHaveLength(1);
    expect(images[0].props.src).toBe('assets/chart.svg');
    expect(staticFile).toHaveBeenCalledTimes(1);
  });
});
