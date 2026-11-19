// Timeline and geometry for "Đại thực bào nhận diện, nuốt vi khuẩn và hợp nhất phagolysosome".
// Sources & verbatim quotes live in library/medanim/macrophage-phagocytosis/animation.yaml.
import type {AssetSpec, Box, LabelSpec, MedAnimStep, PoseBeat} from './medAnimShared';

export const ASSET_DIR = 'medanim/macrophage-phagocytosis';

export type ImageId =
  | 'macrophage'
  | 'bacterium'
  | 'engulfing'
  | 'phago2d'
  | 'vacuole'
  | 'lysosome'
  | 'cycle';

export const IMAGES: Record<ImageId, AssetSpec & {isSvg: boolean}> = {
  macrophage: {file: 'niaid-macrophage-308.svg', width: 445.46, height: 462.88, isSvg: true},
  bacterium: {file: 'bioicons-generic-bacterium.svg', width: 66.88, height: 51.83, isSvg: true},
  engulfing: {file: 'bioicons-engulfing-membrane.svg', width: 183.1416, height: 52.348209, isSvg: true},
  phago2d: {file: 'bioicons-phagocytosis-2d.svg', width: 269.858, height: 257.197, isSvg: true},
  vacuole: {file: 'bioicons-vacuole-blue.svg', width: 145.701, height: 142.564, isSvg: true},
  lysosome: {file: 'reactome-lysosome-R-ICO-012966.svg', width: 13, height: 13, isSvg: true},
  cycle: {file: 'bioicons-phagocytosis.svg', width: 378.86, height: 245.82, isSvg: true},
};

export const STEPS: readonly MedAnimStep[] = [
  {
    id: 'B1',
    start: 0,
    end: 240,
    narration: 'Đại thực bào tuần tra mô, dùng thụ thể nhận diện khuôn mẫu gắn lên phân tử bề mặt vi khuẩn.',
  },
  {
    id: 'B2',
    start: 240,
    end: 480,
    narration: 'Màng tế bào vươn chân giả bao bọc vi khuẩn rồi khép kín, tạo thành túi thực bào bên trong.',
  },
  {
    id: 'B3',
    start: 480,
    end: 720,
    narration: 'Túi thực bào trưởng thành hợp nhất với lysosome, bơm proton axit hóa lòng túi tạo phagolysosome.',
  },
  {
    id: 'B4',
    start: 720,
    end: 960,
    narration: 'Gốc oxy hóa mạnh và enzym thủy phân tiêu hủy vi khuẩn an toàn, không làm vỡ màng tế bào.',
  },
];

export const CREDITS_START = 960;
export const TOTAL_FRAMES = 1050;

export const GLOSSARY = [
  'đại thực bào',
  'vi khuẩn',
  'chân giả',
  'túi thực bào',
  'lysosome',
  'phagolysosome',
  'enzym thủy phân',
] as const;

export const PRR_LOCATOR_START = 24;
export const PRR_ZOOM = {start: 48, end: 78} as const;
export const FUSION_LOCATOR_START = 492;
export const FUSION_ZOOM = {start: 516, end: 546} as const;

// Symmetric stages >= 60% width (>= 1152 px), clear of mini-map (top <= 84), caption (bottom <= 866), and Mascot.
export const B1_PANEL: Box = {left: 380, top: 92, width: 1160, height: 774};
export const MACROPHAGE_BOX: Box = {left: 615, top: 155, width: 580, height: 602};
export const B1_BACTERIUM_BOX: Box = {left: 425, top: 350, width: 155, height: 120};
export const PRR_SOURCE_REGION: Box = {left: 550, top: 365, width: 88, height: 88};
export const PRR_DETAIL_BOX: Box = {left: 675, top: 92, width: 1205, height: 774};

export const B2_PANEL: Box = {left: 440, top: 92, width: 1420, height: 774};
export const FUSION_SOURCE_REGION: Box = {left: 1280, top: 430, width: 88, height: 88};
export const FUSION_DETAIL_BOX: Box = {left: 48, top: 92, width: 1188, height: 774};

export const B4_STAGE_BOX: Box = {left: 525, top: 92, width: 1355, height: 774};
export const CYCLE_INSET_BOX: Box = {left: 1305, top: 245, width: 510, height: 331};

export const LABELS: readonly LabelSpec[] = [
  {
    id: 'prr-pamp',
    vi: 'Thụ thể gắn vi khuẩn',
    viLines: ['Thụ thể gắn', 'vi khuẩn'],
    latin: 'PRR – PAMP recognition',
    start: 138,
    end: 240,
    at: {x: 42, y: 175},
    target: {x: 1180, y: 425},
    ring: {center: {x: 1200, y: 425}, rx: 140, ry: 110},
  },
  {
    id: 'pseudopods',
    vi: 'Chân giả actin',
    latin: 'F-actin pseudopodia',
    start: 262,
    end: 368,
    at: {x: 42, y: 175},
    target: {x: 785, y: 385},
  },
  {
    id: 'phagosome',
    vi: 'Túi thực bào',
    latin: 'Nascent phagosome',
    start: 368,
    end: 480,
    at: {x: 42, y: 455},
    target: {x: 1324, y: 474},
    ring: {center: {x: 1324, y: 474}, rx: 165, ry: 155},
  },
  {
    id: 'phagolysosome',
    vi: 'Hợp nhất phagolysosome',
    viLines: ['Hợp nhất', 'phagolysosome'],
    latin: 'Phagosome–lysosome fusion',
    start: 606,
    end: 720,
    at: {x: 1295, y: 175},
    target: {x: 690, y: 460},
    ring: {center: {x: 620, y: 460}, rx: 230, ry: 185},
  },
  {
    id: 'digestion',
    vi: 'Tiêu hủy vi khuẩn trong túi',
    viLines: ['Tiêu hủy vi khuẩn', 'bằng ROS & enzym'],
    latin: 'Intraphagosomal killing',
    start: 756,
    end: 940,
    at: {x: 36, y: 185},
    target: {x: 895, y: 495},
    ring: {center: {x: 895, y: 495}, rx: 190, ry: 175},
  },
];

export const MINI_MAP_LEVELS: readonly {label: string; asset: AssetSpec}[] = [
  {label: 'Đại thực bào', asset: IMAGES.macrophage},
  {label: 'Túi thực bào', asset: IMAGES.phago2d},
  {label: 'Phagolysosome', asset: IMAGES.lysosome},
];

export const OPENING_POSES: readonly PoseBeat[] = [
  {frame: 0, pose: 'welcome'},
  {frame: 138, pose: 'point_up'},
];

export const CLOSING_POSES: readonly PoseBeat[] = [
  {frame: 0, pose: 'explain'},
  {frame: 168, pose: 'thumbs_up'},
];

export const ATTRIBUTION: readonly string[] = [
  'Hình y khoa: NIAID NIH BioArt Source (bioart.niaid.nih.gov), Public Domain — đại thực bào.',
  'Bioicons (Pauline Franz, CC0; Helicase 11, CC BY 4.0; Servier, CC BY 3.0) — vi khuẩn, chân giả, túi thực bào.',
  'Reactome Icon Library (reactome.org/icon-lib), CC BY 4.0 — lysosome.',
];

export const LITERATURE: readonly string[] = [
  'Uribe-Querol & Rosales 2020, Front Immunol (PMID 32582172; PMC7280488)',
  'Vieira, Botelho & Grinstein 2002, Biochem J (PMID 12061891; PMC1222826)',
];
