import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {ANATOMY_COMPONENTS, ANATOMY_FOCUS_REGIONS, ANATOMY_LABELS, ANATOMY_VIEW_BOXES} from './registry';
vi.mock('remotion', () => ({useCurrentFrame: () => 120, useVideoConfig: () => ({fps: 30})}));
it('test_component_labels_within_frame_and_non_overlapping', () => {
  for (const subject of Object.keys(ANATOMY_COMPONENTS) as (keyof typeof ANATOMY_COMPONENTS)[]) {
    const labels = Object.entries(ANATOMY_LABELS[subject]);
    const box = ANATOMY_VIEW_BOXES[subject];
    expect(labels.length).toBeLessThanOrEqual(6);
    for (const [id, a] of labels) {
      expect(ANATOMY_FOCUS_REGIONS[subject][a.region], `${subject}/${id} focus`).toBeDefined();
      expect(a.x).toBeGreaterThanOrEqual(box.left);
      expect(a.y).toBeGreaterThanOrEqual(box.top);
      expect(a.x + a.width).toBeLessThanOrEqual(box.left + box.width);
      expect(a.y + a.height).toBeLessThanOrEqual(box.top + box.height);
      for (const [otherId, b] of labels) if (otherId !== id) {
        expect(a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y, `${subject}: ${id}/${otherId}`).toBe(false);
      }
    }
    const Component = ANATOMY_COMPONENTS[subject];
    const rendered = renderToStaticMarkup(<Component state="diseased" severity={1} visibleLabels={labels.map(([id]) => id)} />);
    for (const [id, label] of labels) {
      expect(rendered).toContain(`data-label="${id}"`);
      expect(rendered).toContain(label.text);
      expect(rendered).toContain(`data-leader="${id}"`);
    }
  }
});
it('has five gout views and bounded focus regions', () => {
  for (const key of ['gout_foot_overview', 'joint_fluid_urate_to_inflammation', 'urate_crystal_close_up', 'immune_cell_alarm', 'urate_deposition']) {
    expect(ANATOMY_COMPONENTS).toHaveProperty(key);
  }
  for (const regions of Object.values(ANATOMY_FOCUS_REGIONS)) for (const box of Object.values(regions)) {
    expect(box.width).toBeGreaterThan(0); expect(box.height).toBeGreaterThan(0);
    expect(box.left).toBeGreaterThanOrEqual(0); expect(box.top).toBeGreaterThanOrEqual(0);
    expect(box.left + box.width).toBeLessThanOrEqual(600);
    expect(box.top + box.height).toBeLessThanOrEqual(560);
  }
});
