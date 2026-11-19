// Timeline and geometry for "Tích tụ LDL dưới nội mô, mảng xơ vữa và huyết khối khi nứt vỡ bao xơ".
// Sources & verbatim quotes live in library/medanim/atherosclerotic-plaque-rupture/animation.yaml.
import type {AssetSpec, Box, LabelSpec, MedAnimStep, PoseBeat} from './medAnimShared';

export const ASSET_DIR = 'medanim/atherosclerotic-plaque-rupture';

export type ImageId =
  | 'heart'
  | 'artery'
  | 'endothelial'
  | 'ldl'
  | 'oxldl'
  | 'monocyte'
  | 'foam'
  | 'smc'
  | 'collagen'
  | 'platelet'
  | 'plateletBioart'
  | 'fibrin'
  | 'rbc';

export const IMAGES: Record<ImageId, AssetSpec & {isSvg: boolean}> = {
  heart: {file: 'niaid-heart-228.svg', width: 289.44, height: 406.42, isSvg: true},
  artery: {file: 'bioicons-vascular-tunic-artery.svg', width: 154.431, height: 393.222, isSvg: true},
  endothelial: {file: 'reactome-endothelial-R-ICO-014492.svg', width: 125, height: 34, isSvg: true},
  ldl: {file: 'bioicons-ldl-1.svg', width: 161.953, height: 142.639, isSvg: true},
  oxldl: {file: 'bioicons-lipid-ldl-1.svg', width: 97.739, height: 103.408, isSvg: true},
  monocyte: {file: 'bioicons-monocyte.svg', width: 127.219, height: 148.611, isSvg: true},
  foam: {file: 'bioicons-foam-cell-1.svg', width: 136.252, height: 152.126, isSvg: true},
  smc: {file: 'bioicons-smooth-muscle-fiber.svg', width: 646.488, height: 110.06, isSvg: true},
  collagen: {file: 'bioicons-collagen-1.svg', width: 527.773, height: 67.313, isSvg: true},
  platelet: {file: 'reactome-platelet-active-R-ICO-014907.svg', width: 89, height: 84, isSvg: true},
  plateletBioart: {file: 'niaid-platelet-415.svg', width: 500, height: 500, isSvg: true},
  fibrin: {file: 'bioicons-fibrin-1.svg', width: 323.074, height: 48.945, isSvg: true},
  rbc: {file: 'niaid-red-blood-cell-442.svg', width: 500, height: 500, isSvg: true},
};

export const STEPS: readonly MedAnimStep[] = [
  {
    id: 'B1',
    start: 0,
    end: 240,
    narration: 'Khi lớp nội mô động mạch vành suy yếu, nhiều hạt LDL thấm xuống dưới và bị oxy hóa.',
  },
  {
    id: 'B2',
    start: 240,
    end: 480,
    narration: 'Bạch cầu đơn nhân xuyên qua thành mạch, nuốt LDL oxy hóa và biến thành tế bào bọt.',
  },
  {
    id: 'B3',
    start: 480,
    end: 720,
    narration: 'Tế bào bọt tụ thành lõi hoại tử giàu mỡ, phía trên được che bởi bao xơ sợi collagen.',
  },
  {
    id: 'B4',
    start: 720,
    end: 960,
    narration: 'Khi bao xơ mỏng nứt vỡ, tiểu cầu kết tập cùng sợi fibrin lập tức tạo cục huyết khối bít lòng mạch.',
  },
];

export const CREDITS_START = 960;
export const TOTAL_FRAMES = 1050;

export const GLOSSARY = [
  'nội mô',
  'LDL',
  'bạch cầu đơn nhân',
  'tế bào bọt',
  'lõi hoại tử',
  'bao xơ',
  'tiểu cầu',
  'huyết khối',
] as const;

export const CORONARY_LOCATOR_START = 24;
export const CORONARY_ZOOM = {start: 48, end: 78} as const;

// Symmetric stages >= 60% width (>= 1152 px), cleanly clear of mini-map, captionBox, and corner Mascot.
export const B1_PANEL: Box = {left: 380, top: 92, width: 1160, height: 774};
export const HEART_BOX: Box = {left: 416, top: 135, width: 470, height: 660};
export const ARTERY_TUNIC_BOX: Box = {left: 1125, top: 155, width: 220, height: 560};
export const CORONARY_SOURCE_REGION: Box = {left: 565, top: 365, width: 88, height: 88};
export const INTIMA_DETAIL_BOX: Box = {left: 690, top: 92, width: 1190, height: 774};

export const ARTERY_STAGE_BOX: Box = {left: 456, top: 92, width: 1404, height: 774};

export const LABELS: readonly LabelSpec[] = [
  {
    id: 'ldl-oxldl',
    vi: 'LDL thấm dưới nội mô',
    viLines: ['LDL thấm dưới', 'nội mô & oxy hóa'],
    latin: 'Subendothelial oxLDL',
    start: 138,
    end: 240,
    at: {x: 42, y: 175},
    target: {x: 1210, y: 515},
    ring: {center: {x: 1245, y: 525}, rx: 205, ry: 92},
  },
  {
    id: 'monocyte',
    vi: 'Bạch cầu đơn nhân',
    viLines: ['Bạch cầu', 'đơn nhân'],
    latin: 'Monocyte recruitment',
    start: 262,
    end: 368,
    at: {x: 36, y: 195},
    target: {x: 840, y: 390},
  },
  {
    id: 'foam-cell',
    vi: 'Tế bào bọt',
    latin: 'Macrophage foam cell',
    start: 368,
    end: 480,
    at: {x: 36, y: 455},
    target: {x: 1160, y: 560},
    ring: {center: {x: 1160, y: 560}, rx: 190, ry: 95},
  },
  {
    id: 'necrotic-core',
    vi: 'Lõi hoại tử',
    latin: 'Lipid-rich necrotic core',
    start: 500,
    end: 605,
    at: {x: 36, y: 470},
    target: {x: 1185, y: 495},
    ring: {center: {x: 1185, y: 500}, rx: 245, ry: 115},
  },
  {
    id: 'fibrous-cap',
    vi: 'Bao xơ collagen',
    viLines: ['Bao xơ', 'collagen'],
    latin: 'Collagen fibrous cap',
    start: 605,
    end: 720,
    at: {x: 36, y: 195},
    target: {x: 1185, y: 318},
    ring: {center: {x: 1185, y: 318}, rx: 265, ry: 42},
  },
  {
    id: 'thrombus',
    vi: 'Vỡ bao xơ, huyết khối',
    viLines: ['Vỡ bao xơ,', 'huyết khối'],
    latin: 'Plaque rupture & thrombus',
    start: 765,
    end: 940,
    at: {x: 36, y: 195},
    target: {x: 1185, y: 248},
    ring: {center: {x: 1185, y: 252}, rx: 235, ry: 88},
  },
];

export const MINI_MAP_LEVELS: readonly {label: string; asset: AssetSpec}[] = [
  {label: 'Động mạch vành', asset: IMAGES.heart},
  {label: 'Nội mô & LDL', asset: IMAGES.ldl},
  {label: 'Mảng xơ vữa', asset: IMAGES.foam},
];

export const OPENING_POSES: readonly PoseBeat[] = [
  {frame: 0, pose: 'welcome'},
  {frame: 138, pose: 'point_up'},
];

export const CLOSING_POSES: readonly PoseBeat[] = [
  {frame: 0, pose: 'caution'},
  {frame: 168, pose: 'thumbs_up'},
];

export const ATTRIBUTION: readonly string[] = [
  'Hình y khoa: NIAID NIH BioArt Source (Ryan Kissinger, Courtesy of NIAID), Public Domain — tim, tiểu cầu, hồng cầu.',
  'Servier Medical Art / Bioicons (smart.servier.com), CC BY 3.0 — thành mạch, LDL, bạch cầu, tế bào bọt, cơ trơn, collagen, fibrin.',
  'Reactome Icon Library (reactome.org/icon-lib), CC BY 4.0 — tế bào nội mô và tiểu cầu hoạt hóa.',
];

export const LITERATURE: readonly string[] = [
  'Jebari-Benslaiman et al. 2022, Int J Mol Sci (PMID 35328769; PMC8954705)',
  'Henein et al. 2022, Int J Mol Sci (PMID 36361701; PMC9658900)',
  'Borén et al. 2020, Eur Heart J (PMID 32052833) · Wirka et al. 2019, Nat Med (PMID 31359001)',
];
