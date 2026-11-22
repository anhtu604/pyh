// @ts-expect-error @types/node is not installed in video workspace
import fs from 'node:fs';
// @ts-expect-error @types/node is not installed in video workspace
import path from 'node:path';
// @ts-expect-error @types/node is not installed in video workspace
import {fileURLToPath} from 'node:url';
import {describe, expect, it} from 'vitest';
import {
  contrastRatio,
  ENTITY_COLORS,
  surfaceBackgroundHex,
  surfaceCardBackgroundHex,
  surfaceLabelTextHex,
  type MedicalEntityKey,
} from './entityColors';
import {brand} from './palette';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..', '..');

const parseBrandColors = (yamlText: string): Record<string, string> => {
  const result: Record<string, string> = {};
  let inColors = false;
  for (const rawLine of yamlText.split(/\r?\n/)) {
    const line = rawLine.replace(/\s+#.*$/, '');
    if (/^colors:\s*$/.test(line)) {
      inColors = true;
      continue;
    }
    if (inColors && /^\S/.test(line) && line.trim()) {
      inColors = false;
      continue;
    }
    if (inColors) {
      const match = line.match(/^\s{2}([a-z_]+):\s*"?(#[0-9A-Fa-f]{6})"?\s*$/);
      if (match) result[match[1]] = match[2].toUpperCase();
    }
  }
  return result;
};

const parseMedicalEntities = (
  yamlText: string,
): Record<string, {color: string; opacity: number}> => {
  const result: Record<string, {color: string; opacity: number}> = {};
  let inEntities = false;
  let currentKey: string | null = null;
  for (const rawLine of yamlText.split(/\r?\n/)) {
    const line = rawLine.replace(/\s+#.*$/, '');
    if (/^entities:\s*$/.test(line)) {
      inEntities = true;
      continue;
    }
    if (!inEntities) continue;
    const keyMatch = line.match(/^\s{2}([a-z_]+):\s*$/);
    if (keyMatch) {
      currentKey = keyMatch[1];
      result[currentKey] = {color: '', opacity: 1};
      continue;
    }
    if (currentKey) {
      const colorMatch = line.match(/^\s{4}color:\s*([a-z_]+)\s*$/);
      if (colorMatch) result[currentKey].color = colorMatch[1];
      const opacityMatch = line.match(/^\s{4}opacity:\s*([0-9.]+)\s*$/);
      if (opacityMatch) result[currentKey].opacity = Number(opacityMatch[1]);
    }
  }
  return result;
};

describe('medical entity color palette', () => {
  it('matches profiles/brand.vi.yaml and profiles/medical-entity-colors.vi.yaml exactly', () => {
    const brandYaml = fs.readFileSync(path.join(REPO_ROOT, 'profiles', 'brand.vi.yaml'), 'utf8');
    const entityYaml = fs.readFileSync(
      path.join(REPO_ROOT, 'profiles', 'medical-entity-colors.vi.yaml'),
      'utf8',
    );

    const yamlBrand = parseBrandColors(brandYaml);
    const yamlEntities = parseMedicalEntities(entityYaml);

    for (const [token, hex] of Object.entries(brand)) {
      expect(yamlBrand[token]).toBe(hex.toUpperCase());
    }

    const yamlKeys = Object.keys(yamlEntities).sort();
    const tsKeys = Object.keys(ENTITY_COLORS).sort();
    expect(tsKeys).toEqual(yamlKeys);

    const allowedHex = new Set(Object.values(brand).map((h) => h.toUpperCase()));
    for (const key of yamlKeys as MedicalEntityKey[]) {
      const spec = ENTITY_COLORS[key];
      const expected = yamlEntities[key];
      expect(spec.token).toBe(expected.color);
      expect(spec.opacity).toBeCloseTo(expected.opacity, 5);
      expect(spec.hex.toUpperCase()).toBe(yamlBrand[expected.color]);
      expect(allowedHex.has(spec.hex.toUpperCase())).toBe(true);
    }
  });

  it('maintains WCAG AA (>= 4.5:1) text contrast on both night and off_white surfaces', () => {
    for (const surface of ['night', 'off_white'] as const) {
      const ink = surfaceLabelTextHex(surface);
      const bg = surfaceBackgroundHex(surface);
      const card = surfaceCardBackgroundHex(surface);
      expect(contrastRatio(ink, bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(ink, card)).toBeGreaterThanOrEqual(4.5);
    }
  });
});
