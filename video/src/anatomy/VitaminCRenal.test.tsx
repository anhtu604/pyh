import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {ANATOMY_COMPONENTS, ANATOMY_CUE_ACTIONS} from './registry';
vi.mock('remotion', () => ({useCurrentFrame: () => 90, useVideoConfig: () => ({fps: 30})}));
it.each(['renal_tubule_oxalate','vitamin_c_transport','vitamin_c_oxalate_pathway','calcium_oxalate_crystal','intestinal_vitamin_c_absorption'] as const)('renders %s with process cues and distinct views', (subject) => {
 const Component=ANATOMY_COMPONENTS[subject];
 expect(Component).toBeDefined();
 expect(ANATOMY_CUE_ACTIONS[subject].length).toBeGreaterThan(0);
 const normal=renderToStaticMarkup(<Component state="normal" severity={0} />);
 const diseased=renderToStaticMarkup(<Component state="diseased" severity={1} cueProgress={{convert:1,crystallize:1,flow:1,reclaim:1,absorb:1}} />);
 expect(normal).not.toEqual(diseased);
 expect(diseased).toContain('viewBox="0 0 560 560"');
 expect(diseased).not.toMatch(/linearGradient|radialGradient|<filter/);
 expect(diseased).toContain('data-process-arrow');
});
