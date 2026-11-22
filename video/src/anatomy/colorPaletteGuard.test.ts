// @ts-expect-error @types/node is not installed in video workspace
import fs from 'node:fs';
// @ts-expect-error @types/node is not installed in video workspace
import path from 'node:path';
// @ts-expect-error @types/node is not installed in video workspace
import {fileURLToPath} from 'node:url';
import {describe, expect, it} from 'vitest';
import {brand} from './palette';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(HERE, '..');

const ALLOWED_BRAND_HEX = new Set(Object.values(brand).map((hex) => hex.toUpperCase()));

/**
 * Legacy non-hepatic anatomy files from earlier topics (gout, vitamin C/oxalate,
 * esophagus, cancer/muscle, cardiovascular) that still reference `anatomyColors`
 * or pre-standardization hexes pending topic-by-topic migration.
 * ZERO hepatic / PYH-003 components and ZERO files under `video/src/scalezoom/**`
 * are permitted here.
 */
const LEGACY_ANATOMY_ALLOWLIST: Readonly<Record<string, string>> = {
  'anatomy/ArterySection.tsx': 'Legacy cardiovascular topic (pre-S5); uses anatomyColors',
  'anatomy/CalciumOxalateCrystal.tsx': 'Legacy vitamin-C/oxalate topic (pre-S5); uses local crystal hexes',
  'anatomy/EsophagusDiagram.tsx': 'Legacy esophagus topic (pre-S5); uses anatomyColors',
  'anatomy/GoutFootOverview.tsx': 'Legacy gout topic (pre-S5); uses anatomyColors + local skin hexes',
  'anatomy/Heart.tsx': 'Legacy cardiovascular topic (pre-S5); uses anatomyColors',
  'anatomy/InflammationSignal.tsx': 'Legacy gout topic (pre-S5); uses anatomyColors',
  'anatomy/IntestinalVitaminCAbsorption.tsx': 'Legacy vitamin-C topic (pre-S5); uses local tissue hexes',
  'anatomy/MuscleProteinTurnover.tsx': 'Legacy cancer/muscle topic (pre-S5); uses anatomyColors',
  'anatomy/MuscleTumorAminoAcidBalance.tsx': 'Legacy cancer/muscle topic (pre-S5); uses anatomyColors',
  'anatomy/MuscleWastingSection.tsx': 'Legacy cancer/muscle topic (pre-S5); uses anatomyColors',
  'anatomy/RenalTubuleOxalate.tsx': 'Legacy vitamin-C/oxalate topic (pre-S5); uses local renal hexes',
  'anatomy/TumorProteinUptake.tsx': 'Legacy cancer/muscle topic (pre-S5); uses anatomyColors',
  'anatomy/UrateCrystalCloseUp.tsx': 'Legacy gout topic (pre-S5); uses anatomyColors',
  'anatomy/UrateDeposition.tsx': 'Legacy gout topic (pre-S5); uses anatomyColors',
  'anatomy/UrateFluid.tsx': 'Legacy gout topic (pre-S5); uses anatomyColors',
  'anatomy/VitaminCOxalatePathway.tsx': 'Legacy vitamin-C/oxalate topic (pre-S5); uses local hexes',
  'anatomy/VitaminCTransport.tsx': 'Legacy vitamin-C topic (pre-S5); uses local hexes',
};

const HEX_PATTERN = /#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/g;
const RGB_PATTERN = /\brgba?\s*\([^)]*\)/g;
const LEGACY_PALETTE_PATTERN = /\banatomyColors\b/g;

export type ColorViolation = {
  readonly kind: 'hex' | 'rgb' | 'legacy_palette';
  readonly token: string;
};

/**
 * Pure source scanner that detects hardcoded hex/rgb(a) literals outside the
 * approved brand palette and any legacy `anatomyColors` usage.
 */
export const findForbiddenColorLiterals = (
  source: string,
  allowedHexes: ReadonlySet<string> = ALLOWED_BRAND_HEX,
): readonly ColorViolation[] => {
  // Strip single-line and multi-line comments so doc comments do not false-positive.
  const withoutComments = source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/[^\r\n]*/g, '');

  const violations: ColorViolation[] = [];

  for (const match of withoutComments.matchAll(HEX_PATTERN)) {
    const raw = match[0].toUpperCase();
    const normalized =
      raw.length === 4
        ? `#${raw[1]}${raw[1]}${raw[2]}${raw[2]}${raw[3]}${raw[3]}`
        : raw;
    if (!allowedHexes.has(normalized)) {
      violations.push({kind: 'hex', token: match[0]});
    }
  }

  for (const match of withoutComments.matchAll(RGB_PATTERN)) {
    violations.push({kind: 'rgb', token: match[0]});
  }

  for (const match of withoutComments.matchAll(LEGACY_PALETTE_PATTERN)) {
    violations.push({kind: 'legacy_palette', token: match[0]});
  }

  return violations;
};

const walkFiles = (dir: string, predicate: (filePath: string) => boolean): string[] => {
  const results: string[] = [];
  for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkFiles(full, predicate));
    } else if (predicate(full)) {
      results.push(full);
    }
  }
  return results.sort();
};

describe('anatomy and scalezoom entity-color guard', () => {
  it('flags off-palette hex, raw rgb/rgba, and legacy anatomyColors literals', () => {
    expect(findForbiddenColorLiterals('const bad = "#FF00AA";')).toEqual([
      {kind: 'hex', token: '#FF00AA'},
    ]);
    expect(findForbiddenColorLiterals('const bad = "rgb(255, 0, 128)";')).toEqual([
      {kind: 'rgb', token: 'rgb(255, 0, 128)'},
    ]);
    expect(findForbiddenColorLiterals('import {anatomyColors as c} from "./palette";')).toEqual([
      {kind: 'legacy_palette', token: 'anatomyColors'},
    ]);
    // Brand hexes and ENTITY_COLORS / hexToRgba helpers pass cleanly.
    expect(
      findForbiddenColorLiterals(
        'const ok = ENTITY_COLORS.enzyme_marker.hex; const alpha = hexToRgba(brand.teal, 0.3); const brandHex = "#18A6A6";',
      ),
    ).toEqual([]);
  });

  it('enforces zero off-palette colors across all hepatic anatomy components and all scalezoom modules', () => {
    const anatomyTsx = walkFiles(
      path.join(SRC_ROOT, 'anatomy'),
      (file) => file.endsWith('.tsx') && !file.endsWith('.test.tsx'),
    );
    const scalezoomFiles = walkFiles(
      path.join(SRC_ROOT, 'scalezoom'),
      (file) => (file.endsWith('.ts') || file.endsWith('.tsx')) && !file.endsWith('.test.ts') && !file.endsWith('.test.tsx'),
    );

    const targets = [...anatomyTsx, ...scalezoomFiles];
    expect(targets.length).toBeGreaterThan(10);

    const failures: string[] = [];
    for (const fullPath of targets) {
      const rel = path.relative(SRC_ROOT, fullPath).replace(/\\/g, '/');
      if (rel in LEGACY_ANATOMY_ALLOWLIST) continue;
      const source = fs.readFileSync(fullPath, 'utf8');
      const violations = findForbiddenColorLiterals(source);
      if (violations.length > 0) {
        failures.push(`${rel}: ${violations.map((v) => `${v.kind}(${v.token})`).join(', ')}`);
      }
    }

    expect(failures).toEqual([]);
  });
});
