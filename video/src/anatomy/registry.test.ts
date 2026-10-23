// @ts-expect-error @types/node is not installed
import {existsSync, readFileSync} from 'node:fs';
import {describe, expect, it} from 'vitest';
import {AnatomySchema} from '../types';
import library from './library.json';
import {ANATOMY_COMPONENTS, ANATOMY_SUBJECTS} from './registry';

describe('anatomy registry', () => {
  it('maps every library.json key to a component and vice versa', () => {
    const libraryKeys = Object.keys(library.components).sort();
    const registryKeys = Object.keys(ANATOMY_COMPONENTS).sort();
    expect(registryKeys).toEqual(libraryKeys);
    expect([...ANATOMY_SUBJECTS].sort()).toEqual(libraryKeys);
    for (const key of ANATOMY_SUBJECTS) {
      expect(typeof ANATOMY_COMPONENTS[key as keyof typeof ANATOMY_COMPONENTS]).toBe('function');
    }
  });

  it('keeps types.ts subject enum in sync with library.json keys', () => {
    const schemaOptions = [...AnatomySchema.shape.subject.options].sort();
    const libraryKeys = Object.keys(library.components).sort();
    expect(schemaOptions).toEqual(libraryKeys);
  });

  it('rejects unknown subjects with the mechanism diagnostic', () => {
    expect(() => AnatomySchema.shape.subject.parse('unknown')).toThrow(/Unsupported anatomy subject/);
  });

  it('points to existing component files with declared layers present in source', () => {
    for (const [subject, entry] of Object.entries(library.components)) {
      const fileUrl = new URL(`./${entry.file}`, import.meta.url);
      expect(existsSync(fileUrl), `${subject} missing file ${entry.file}`).toBe(true);
      expect(entry.layers.length, `${subject} must declare at least one layer`).toBeGreaterThan(0);
      const source = readFileSync(fileUrl, 'utf8');
      for (const layer of entry.layers) {
        expect(source, `${entry.file} missing layer ${layer}`).toContain(layer);
      }
    }
  });
});
