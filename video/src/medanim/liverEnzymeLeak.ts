// Timeline for the medical mechanism animation "Tế bào gan tổn thương → ALT/AST vào máu".
// Narration, claims and sources live in cache/medanim/liver-enzyme-leak/script.yaml (B1–B6);
// every structure on screen is a licensed image listed in that folder's assets/manifest.yaml.
import {clamp01, smoothstep} from '../style/pyhStyle';

export const FPS = 30;
export const ASSET_DIR = 'medanim/liver-enzyme-leak';
export const asset = (file: string): string => `${ASSET_DIR}/${file}`;

export type ImageId =
  | 'liver'
  | 'lobule'
  | 'lobuleHex'
  | 'cell'
  | 'mito'
  | 'vessel'
  | 'rbc'
  | 'tube'
  | 'heart'
  | 'muscle';

/** Source viewBox / pixel size of each licensed image (manifest.yaml). */
export const IMAGES: Record<ImageId, {file: string; width: number; height: number; isSvg: boolean}> = {
  liver: {file: 'niaid-liver-230.svg', width: 456.16, height: 309.24, isSvg: true},
  lobule: {file: 'servier-liver-lobule.png', width: 847, height: 1084, isSvg: false},
  lobuleHex: {file: 'dbcls-hepatic-lobule.svg', width: 720, height: 540, isSvg: true},
  cell: {file: 'niaid-hepatocyte-203.svg', width: 1821, height: 1734, isSvg: true},
  mito: {file: 'niaid-mitochondria-352.svg', width: 500, height: 500, isSvg: true},
  vessel: {file: 'niaid-blood-vessel-55.svg', width: 500, height: 500, isSvg: true},
  rbc: {file: 'niaid-red-blood-cell-442.svg', width: 500, height: 500, isSvg: true},
  tube: {file: 'niaid-blood-vial-52.svg', width: 122.87, height: 454.45, isSvg: true},
  heart: {file: 'niaid-heart-228.svg', width: 289.44, height: 406.42, isSvg: true},
  muscle: {file: 'reactome-muscle-R-ICO-014108.svg', width: 174, height: 104, isSvg: true},
};

export type Step = {id: 'B1' | 'B2' | 'B3' | 'B4' | 'B5' | 'B6'; start: number; end: number; narration: string};
export const STEPS: readonly Step[] = [
  {id: 'B1', start: 0, end: 240,
    narration: 'Gan gồm nhiều tiểu thùy; giữa mỗi tiểu thùy là tĩnh mạch trung tâm, ở rìa là các khoảng cửa.'},
  {id: 'B2', start: 240, end: 480,
    narration: 'Máu từ tĩnh mạch cửa và động mạch gan hòa vào nhau, chảy qua xoang gan về tĩnh mạch trung tâm.'},
  {id: 'B3', start: 480, end: 720,
    narration: 'Trong tế bào gan, ALT chủ yếu nằm ở bào tương, còn AST có ở cả bào tương lẫn ty thể.'},
  {id: 'B4', start: 720, end: 1080,
    narration: 'Tổn thương nhẹ làm men bào tương thoát ra; tổn thương nặng, hoại tử có thể giải phóng thêm AST ty thể, như trong mô hình gan chuột thiếu máu.'},
  {id: 'B5', start: 1080, end: 1320,
    narration: 'Từ tĩnh mạch trung tâm, máu về tĩnh mạch gan rồi tĩnh mạch chủ dưới, nên xét nghiệm máu đo được men.'},
  {id: 'B6', start: 1320, end: 1500,
    narration: 'AST còn có nhiều ở cơ vân và cơ tim, nên AST tăng không chỉ do gan.'},
];
export const CREDITS_START = 1500;
export const TOTAL_FRAMES = 1590;

/** Terms labelled on screen; highlighted yellow in captions on first use. */
export const GLOSSARY = ['tiểu thùy', 'tĩnh mạch trung tâm', 'khoảng cửa', 'tĩnh mạch cửa', 'động mạch gan', 'xoang gan',
  'bào tương', 'ty thể', 'tĩnh mạch gan', 'tĩnh mạch chủ dưới', 'cơ vân', 'cơ tim'];

// --- Scene windows (which picture is on screen) -------------------------------------------------
/** Magnifier zoom windows (no semi-transparent cross-fade of different scales) and clean scene cuts. */
export const IRIS = {
  liverToLobule: {start: 48, end: 78},
  lobuleToCell: {start: 480, end: 510},
  cellToLobule: {start: 1080, end: 1110},
  lobuleToSources: {start: 1320, end: 1332},
} as const;
export const LIVER_LOCATOR_START = 24;
export const LOBULE_LOCATOR_START = 456;
export const LIVER_ZOOM = IRIS.liverToLobule;
export const LOBULE_ZOOM_IN = IRIS.lobuleToCell;
export const CELL_CLOSE = IRIS.cellToLobule;
export const TRANSITION_LOBULE_TO_SOURCES = IRIS.lobuleToSources;
export const irisProgress = (frame: number, w: {start: number; end: number}): number =>
  smoothstep((frame - w.start) / (w.end - w.start));

// --- Geometry ------------------------------------------------------------------------------------
export type Box = {left: number; top: number; width: number; height: number};
export type Point = {x: number; y: number};
export type SceneFormat = 'landscape' | 'portrait';

/** Vector SVG liver fills >=60% frame width symmetrically (380..1540) with zero bitmap blur. */
export const B1_OVERVIEW_PANEL: Box = {left: 380, top: 86, width: 1160, height: 784};
export const LIVER_BOX: Box = {left: 380, top: 88, width: 1160, height: 1160 * 309.24 / 456.16};
/** Magnifier detail frames (>=60% frame width) positioned above captions (y < 876) and below mini-map. */
export const LOBULE_DETAIL_BOX: Box = {left: 542, top: 86, width: 1338, height: 784};
export const CELL_DETAIL_BOX: Box = {left: 702, top: 86, width: 1182, height: 784};

/** Where the lobule sits on screen at rest (scenes B1, B2), aligned cleanly inside LOBULE_DETAIL_BOX (<=0.7x PNG). */
export const LOBULE_BOX: Box = {left: 552, top: 102, width: 750 * 847 / 1084, height: 750};
/** Lobule after it moves left to make room for the drainage chain (B5, from frame 1214). */
export const LOBULE_BOX_SMALL: Box = {left: 160, top: 115, width: 680 * 847 / 1084, height: 680};
export const LOBULE_SHIFT = {start: 1214, end: 1254} as const;
/** Hepatocyte SVG centered across CELL_DETAIL_BOX center (1293, 478) so open/close lens always shows cell anatomy. */
export const CELL_BOX: Box = {left: 885, top: 296, width: 545, height: 545 * 1734 / 1821};

/** Map a point in source-image pixels into a screen box that shows the whole image. */
export const imageToScreen = (box: Box, image: ImageId, p: Point): Point => ({
  x: box.left + (p.x / IMAGES[image].width) * box.width,
  y: box.top + (p.y / IMAGES[image].height) * box.height,
});

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
export const lerpBox = (a: Box, b: Box, t: number): Box => ({
  left: lerp(a.left, b.left, t), top: lerp(a.top, b.top, t), width: lerp(a.width, b.width, t), height: lerp(a.height, b.height, t),
});

const squareAround = (center: Point, size: number): Box => ({
  left: Math.round(center.x - size / 2),
  top: Math.round(center.y - size / 2),
  width: size,
  height: size,
});

/** Locator source region on the Liver for Zoom 1 (right-lobe parenchyma, non-overlapping with LOBULE_DETAIL_BOX). */
export const LIVER_SOURCE_REGION: Box = squareAround(imageToScreen(LIVER_BOX, 'liver', {x: 40, y: 145}), 80);

/** Structures in the Servier lobule picture (source px), identified against Kietzmann 2017 Fig. 1A. */
export const LOBULE_POINTS = {
  centralVein: {x: 400, y: 120},
  portalTriad: {x: 470, y: 900},
  portalVein: {x: 478, y: 950},
  hepaticArtery: {x: 716, y: 905},
  sinusoid: {x: 424, y: 600},
  plate: {x: 118, y: 520},
} as const;

/** Locator source region on the Lobule for Zoom 2 (hepatocyte plate beside sinusoid, left of CELL_DETAIL_BOX). */
export const LOBULE_SOURCE_REGION: Box = squareAround(imageToScreen(LOBULE_BOX, 'lobule', LOBULE_POINTS.plate), 80);

/** Centerline y of the sinusoidal blood vessel lumen above the cell inside CELL_DETAIL_BOX. */
export const LANE_Y = 205;

export type SceneGeometry = {
  frame: {width: number; height: number};
  mascotBox: Box;
  overviewPanel: Box;
  liverBox: Box;
  lobuleDetailBox: Box;
  cellDetailBox: Box;
  lobuleBox: Box;
  lobuleBoxSmall: Box;
  cellBox: Box;
  liverSourceRegion: Box;
  lobuleSourceRegion: Box;
  laneY: number;
  chainTubeBox: Box;
};

const LANDSCAPE_GEOMETRY: SceneGeometry = {
  frame: {width: 1920, height: 1080},
  mascotBox: {left: 20, top: 783, width: 340, height: 297},
  overviewPanel: B1_OVERVIEW_PANEL,
  liverBox: LIVER_BOX,
  lobuleDetailBox: LOBULE_DETAIL_BOX,
  cellDetailBox: CELL_DETAIL_BOX,
  lobuleBox: LOBULE_BOX,
  lobuleBoxSmall: LOBULE_BOX_SMALL,
  cellBox: CELL_BOX,
  liverSourceRegion: LIVER_SOURCE_REGION,
  lobuleSourceRegion: LOBULE_SOURCE_REGION,
  laneY: LANE_Y,
  chainTubeBox: {left: 1490, top: 545, width: 260 * IMAGES.tube.width / IMAGES.tube.height, height: 260},
};

const PORTRAIT_LIVER_BOX: Box = {left: 80, top: 250, width: 920, height: 920 * 309.24 / 456.16};
const PORTRAIT_LOBULE_BOX: Box = {left: 228, top: 230, width: 800 * 847 / 1084, height: 800};

export const PORTRAIT_GEOMETRY: SceneGeometry = {
  frame: {width: 1080, height: 1920},
  // Spec section 6 row 15: portrait mascot <= 28% frame width (<= 302 px); 280 px = 25.9%.
  mascotBox: {left: 24, top: 1336, width: 280, height: Math.round(280 * 297 / 340)},
  overviewPanel: {left: 48, top: 116, width: 984, height: 1180},
  liverBox: PORTRAIT_LIVER_BOX,
  lobuleDetailBox: {left: 48, top: 116, width: 984, height: 1180},
  cellDetailBox: {left: 48, top: 116, width: 984, height: 1180},
  lobuleBox: PORTRAIT_LOBULE_BOX,
  lobuleBoxSmall: {left: 52, top: 170, width: 420, height: 420 * 1084 / 847},
  cellBox: {left: 190, top: 320, width: 700, height: 700 * 1734 / 1821},
  liverSourceRegion: squareAround(imageToScreen(PORTRAIT_LIVER_BOX, 'liver', {x: 40, y: 145}), 80),
  lobuleSourceRegion: squareAround(imageToScreen(PORTRAIT_LOBULE_BOX, 'lobule', LOBULE_POINTS.plate), 80),
  laneY: 249,
  chainTubeBox: {left: 220, top: 800, width: 380 * IMAGES.tube.width / IMAGES.tube.height, height: 380},
};

export const sceneGeometry = (format: SceneFormat): SceneGeometry =>
  format === 'portrait' ? PORTRAIT_GEOMETRY : LANDSCAPE_GEOMETRY;

export const lobuleBoxAt = (frame: number, format: SceneFormat = 'landscape'): Box => {
  const g = sceneGeometry(format);
  return lerpBox(g.lobuleBox, g.lobuleBoxSmall, smoothstep((frame - LOBULE_SHIFT.start) / (LOBULE_SHIFT.end - LOBULE_SHIFT.start)));
};

/** Portal-vein branch flowing up to the arterial-portal confluence at {375, 395} (source px). */
export const PORTAL_FLOW_PATH: readonly Point[] = [
  {x: 478, y: 880}, {x: 465, y: 760}, {x: 440, y: 635}, {x: 416, y: 515}, {x: 400, y: 440}, {x: 375, y: 395},
];
/** Hepatic-artery branch flowing up-left to merge with the portal-vein stream at {375, 395} (source px). */
export const ARTERY_FLOW_PATH: readonly Point[] = [
  {x: 716, y: 880}, {x: 712, y: 730}, {x: 688, y: 642}, {x: 655, y: 584},
  {x: 585, y: 526}, {x: 510, y: 476}, {x: 442, y: 436}, {x: 405, y: 410}, {x: 375, y: 395},
];
/** Merged sinusoidal flow from confluence {375, 395} into the central vein (source px). */
export const MERGED_SINUSOID_PATH: readonly Point[] = [
  {x: 375, y: 395}, {x: 358, y: 340}, {x: 356, y: 265}, {x: 364, y: 205}, {x: 372, y: 160},
];
/** Continuous portal-to-central-vein route (source px), used for B5 enzyme drainage. */
export const SINUSOID_PATH: readonly Point[] = [
  ...PORTAL_FLOW_PATH.slice(0, -1),
  ...MERGED_SINUSOID_PATH,
];
/** Part of the portal route wide enough for a red cell at picture scale; artery mouth uses ARTERY_WIDE. */
export const SINUSOID_WIDE: readonly Point[] = PORTAL_FLOW_PATH.slice(0, 4);
export const ARTERY_WIDE: readonly Point[] = ARTERY_FLOW_PATH.slice(0, 3);
/** Bile canaliculus to portal bile duct: flows downward, opposite to sinusoidal blood (source px). */
export const BILE_FLOW_PATH: readonly Point[] = [
  {x: 295, y: 360}, {x: 274, y: 480}, {x: 252, y: 620}, {x: 238, y: 760}, {x: 235, y: 920},
];

/** Hepatocyte picture (NIAID, normalized to 1821×1734 grid): top edge with microvilli faces the sinusoid. */
export const CELL_POINTS = {
  cytosol: {x: 520, y: 640},
  mitochondrion: {x: 1210, y: 560},
  injury: {x: 980, y: 95},
} as const;
export const MITO_SPOTS: readonly Point[] = [
  {x: 1210, y: 560}, {x: 560, y: 980}, {x: 1380, y: 1000}, {x: 900, y: 760},
];

/** Point at fraction t (0..1) along a polyline. */
export const pathPoint = (path: readonly Point[], t: number): Point => {
  const lengths = path.slice(1).map((p, i) => Math.hypot(p.x - path[i].x, p.y - path[i].y));
  const total = lengths.reduce((a, b) => a + b, 0);
  if (t >= 1) return path[path.length - 1];
  let d = clamp01(t) * total;
  for (let i = 0; i < lengths.length; i++) {
    if (d <= lengths[i] || i === lengths.length - 1) {
      const k = lengths[i] === 0 ? 0 : Math.min(1, d / lengths[i]);
      return {x: lerp(path[i].x, path[i + 1].x, k), y: lerp(path[i].y, path[i + 1].y, k)};
    }
    d -= lengths[i];
  }
  return path[path.length - 1];
};

// --- Labels: one lit at a time ------------------------------------------------------------------
export type LabelTarget = {image: 'lobule' | 'cell'; point: Point} | {screen: Point};
export type Label = {
  id: string; vi: string; latin: string; start: number; end: number;
  /** Optional two-line Vietnamese display inside the card (keeps `vi` intact for caption matching). */
  viLines?: readonly [string, string];
  /** Top-left of the label card on screen. */
  at: Point; target: LabelTarget;
  /** Optional teal ring around a structure group in the lobule picture (source px). */
  ring?: {center: Point; rx: number; ry: number};
};
export const LABELS: readonly Label[] = [
  {id: 'central-vein', vi: 'Tĩnh mạch trung tâm', latin: 'Vena centralis', start: 138, end: 186,
    at: {x: 1230, y: 145}, target: {image: 'lobule', point: LOBULE_POINTS.centralVein}},
  {id: 'portal-triad', vi: 'Khoảng cửa', latin: 'Portal triad', start: 186, end: 240,
    at: {x: 1240, y: 600}, target: {image: 'lobule', point: LOBULE_POINTS.portalTriad},
    ring: {center: {x: 465, y: 900}, rx: 330, ry: 165}},
  {id: 'portal-vein', vi: 'Tĩnh mạch cửa', latin: 'Vena portae (nhánh)', start: 254, end: 308,
    at: {x: 100, y: 630}, target: {image: 'lobule', point: LOBULE_POINTS.portalVein}},
  {id: 'hepatic-artery', vi: 'Động mạch gan', latin: 'Arteria hepatica (nhánh)', start: 308, end: 364,
    at: {x: 1245, y: 510}, target: {image: 'lobule', point: LOBULE_POINTS.hepaticArtery}},
  {id: 'sinusoid', vi: 'Xoang gan', latin: 'Sinusoid', start: 364, end: 480,
    at: {x: 130, y: 535}, target: {image: 'lobule', point: LOBULE_POINTS.sinusoid}},
  {id: 'cytosol', vi: 'Bào tương', latin: 'Cytosol', start: 570, end: 624,
    at: {x: 1475, y: 310}, target: {image: 'cell', point: CELL_POINTS.cytosol}},
  {id: 'mitochondrion', vi: 'Ty thể', latin: 'Mitochondrion', start: 624, end: 731,
    at: {x: 1475, y: 310}, target: {image: 'cell', point: CELL_POINTS.mitochondrion}},
  {id: 'membrane', vi: 'Màng tế bào tổn thương', viLines: ['Màng tế bào', 'tổn thương'], latin: 'Plasma membrane injury', start: 747, end: 901,
    at: {x: 1465, y: 294}, target: {image: 'cell', point: CELL_POINTS.injury}},
  {id: 'sinusoid-lumen', vi: 'Lòng xoang gan', viLines: ['Lòng xoang', 'gan'], latin: 'Sinusoidal lumen', start: 901, end: 1080,
    at: {x: 1475, y: 294}, target: {screen: {x: 1220, y: LANE_Y}}},
  {id: 'central-vein-2', vi: 'Tĩnh mạch trung tâm', latin: 'Vena centralis', start: 1170, end: 1214,
    at: {x: 1230, y: 145}, target: {image: 'lobule', point: LOBULE_POINTS.centralVein}},
];

const PORTRAIT_LABEL_OVERRIDES: Record<string, Partial<Pick<Label, 'at' | 'viLines' | 'target'>>> = {
  'central-vein': {viLines: ['Tĩnh mạch', 'trung tâm'], at: {x: 670, y: 126}},
  'portal-triad': {at: {x: 600, y: 1060}},
  'portal-vein': {viLines: ['Tĩnh mạch', 'cửa'], at: {x: 72, y: 1070}},
  'hepatic-artery': {viLines: ['Động mạch', 'gan'], at: {x: 590, y: 1070}},
  'sinusoid': {at: {x: 56, y: 1060}},
  'cytosol': {at: {x: 72, y: 1040}},
  'mitochondrion': {at: {x: 72, y: 1040}},
  'membrane': {at: {x: 72, y: 1025}},
  'sinusoid-lumen': {at: {x: 72, y: 1025}, target: {screen: {x: 540, y: PORTRAIT_GEOMETRY.laneY}}},
  'central-vein-2': {viLines: ['Tĩnh mạch', 'trung tâm'], at: {x: 670, y: 126}},
};

export const sceneLabels = (format: SceneFormat = 'landscape'): readonly Label[] =>
  format === 'landscape' ? LABELS : LABELS.map((l) => ({...l, ...PORTRAIT_LABEL_OVERRIDES[l.id]}));

/** The single label lit at this frame, if any. */
export const litLabel = (frame: number): Label | undefined => LABELS.find((l) => frame >= l.start && frame < l.end);

// --- Drainage chain (B5): text nodes + teal arrows, no drawn anatomy -----------------------------
export type ChainNode = {id: string; vi: string; viLines?: readonly [string, string]; latin: string; start: number; at: Point};
export const CHAIN: readonly ChainNode[] = [
  {id: 'hepatic-veins', vi: 'Tĩnh mạch gan', latin: 'Venae hepaticae', start: 1234, at: {x: 940, y: 120}},
  {id: 'ivc', vi: 'Tĩnh mạch chủ dưới', latin: 'Vena cava inferior', start: 1262, at: {x: 940, y: 370}},
  {id: 'blood-test', vi: 'Xét nghiệm máu: ALT, AST', latin: 'Serum aminotransferases', start: 1290, at: {x: 940, y: 620}},
];

const PORTRAIT_CHAIN_OVERRIDES: Record<string, Partial<Pick<ChainNode, 'at' | 'viLines'>>> = {
  'hepatic-veins': {at: {x: 540, y: 210}},
  'ivc': {viLines: ['Tĩnh mạch', 'chủ dưới'], at: {x: 540, y: 520}},
  'blood-test': {viLines: ['Xét nghiệm máu:', 'ALT, AST'], at: {x: 460, y: 900}},
};

export const sceneChain = (format: SceneFormat = 'landscape'): readonly ChainNode[] =>
  format === 'landscape' ? CHAIN : CHAIN.map((n) => ({...n, ...PORTRAIT_CHAIN_OVERRIDES[n.id]}));

// --- Enzyme dots ---------------------------------------------------------------------------------
export type Enzyme = 'ALT' | 'AST';
export type Dot = {enzyme: Enzyme; home: Point; inMito: boolean; delay: number};
/** Deterministic dot layout in hepatocyte coordinate space. ALT/c-AST stay strictly clear of MITO_SPOTS. */
export const DOTS: readonly Dot[] = [
  ...[[420, 470], [640, 410], [860, 390], [1040, 370], [1460, 460], [470, 680], [1510, 730], [960, 1020], [1130, 980], [600, 570]]
    .map(([x, y], i) => ({enzyme: 'ALT' as const, home: {x, y}, inMito: false, delay: i * 4})),
  ...[[520, 510], [760, 495], [1475, 595], [340, 790], [1260, 790], [870, 1080]]
    .map(([x, y], i) => ({enzyme: 'AST' as const, home: {x, y}, inMito: false, delay: 2 + i * 5})),
  ...MITO_SPOTS.map((p, i) => ({enzyme: 'AST' as const, home: p, inMito: true, delay: i * 4})),
];
export const DOTS_APPEAR = {ALT: 570, AST: 624} as const;
export const LEAK = {start: 758, travel: 85} as const;
export const INJURY_RING = 740;

/** Cytosolic dots leave through the injury into the lumen, then drift downstream (to the right). Mito AST stays until 880. */
export const dotScreenPosition = (dot: Dot, frame: number, cellBox: Box, laneY: number = LANE_Y): {p: Point; leaked: number} => {
  const home = imageToScreen(cellBox, 'cell', dot.home);
  if (dot.inMito && frame < 880) return {p: home, leaked: 0};
  const gate = imageToScreen(cellBox, 'cell', CELL_POINTS.injury);
  const t = clamp01((frame - (dot.inMito ? 880 : LEAK.start) - dot.delay) / LEAK.travel);
  const toGate = smoothstep(Math.min(1, t * 1.6));
  const drift = Math.max(0, t * 1.6 - 1) / 0.6;
  const atGate = {x: lerp(home.x, gate.x, toGate), y: lerp(home.y, gate.y, toGate)};
  const lane = {x: gate.x + drift * (240 + dot.delay * 9), y: lerp(gate.y, laneY + ((dot.delay % 3) - 1) * 14, Math.min(1, drift * 2))};
  return {p: drift > 0 ? lane : atGate, leaked: t};
};

// --- Mascot (corner, opening and closing only; frames relative to each appearance) ---------------
export type PoseBeat = {frame: number; pose: 'welcome' | 'point_up' | 'myth_bust' | 'thumbs_up'};
export const OPENING_POSES: PoseBeat[] = [{frame: 0, pose: 'welcome'}, {frame: 141, pose: 'point_up'}];
export const CLOSING_POSES: PoseBeat[] = [{frame: 0, pose: 'myth_bust'}, {frame: 168, pose: 'thumbs_up'}];

// --- Captions ------------------------------------------------------------------------------------
/** Simulated even timing inside a step (no TTS yet). */
export const captionTiming = (step: Step): {firstFrame: number; framesPerWord: number} => {
  const words = step.narration.trim().split(/\s+/).length;
  const firstFrame = 4;
  return {firstFrame, framesPerWord: Math.max(4, Math.floor((step.end - step.start - firstFrame - 8) / words))};
};

export const ATTRIBUTION = [
  'Hình y khoa: NIAID NIH BioArt Source (bioart.niaid.nih.gov; Ryan Kissinger, Courtesy of NIAID), Public Domain —',
  'lá gan (230), tế bào gan (203), ty thể (352), mạch máu (55), hồng cầu (442), ống máu (52), tim (228).',
  'Tiểu thùy gan: Servier Medical Art (smart.servier.com), CC BY 4.0; lục giác: DBCLS (Wikimedia Commons), CC BY 4.0.',
  'Cơ vân: Reactome Icon Library (R-ICO-014108, Cristoffer Sevilla), CC BY 4.0.',
] as const;
export const LITERATURE = [
  'Kietzmann 2017, Redox Biol (PMID 28126520) · Vernon 2022, StatPearls (PMID 29763190)',
  'McGill 2016, EXCLI J (PMID 28337112) · Moriles 2024, StatPearls (PMID 32644704)',
  'Kamiike 1989, Clin Chim Acta (PMID 2620458; mô hình gan chuột thiếu máu)',
  'Panteghini 1990, Clin Biochem (PMID 2225456) · Turamanlar 2012, Balkan Med J (PMID 25206997)',
] as const;
