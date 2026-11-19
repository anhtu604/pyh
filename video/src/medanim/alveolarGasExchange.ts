// Timeline and geometry for "Trao đổi khí O₂ và CO₂ qua màng phế nang – mao mạch".
// Sources & verbatim quotes live in library/medanim/alveolar-gas-exchange/animation.yaml.
import type {AssetSpec, Box, LabelSpec, MedAnimStep, Point, PoseBeat} from './medAnimShared';

export const ASSET_DIR = 'medanim/alveolar-gas-exchange';

export type ImageId =
  | 'lung'
  | 'alveoli'
  | 'capillary'
  | 'alveolusCell'
  | 'endothelial'
  | 'rbc'
  | 'edema';

export const IMAGES: Record<ImageId, AssetSpec & {isSvg: boolean}> = {
  lung: {file: 'bioicons-healthy-lung.svg', width: 366.69, height: 417.109, isSvg: true},
  alveoli: {file: 'niaid-alveoli-14.svg', width: 581.4, height: 544.45, isSvg: true},
  capillary: {file: 'bioicons-capillary.svg', width: 556.082, height: 317.934, isSvg: true},
  alveolusCell: {file: 'reactome-alveolus-R-ICO-014769.svg', width: 95, height: 103, isSvg: true},
  endothelial: {file: 'reactome-endothelial-R-ICO-014492.svg', width: 125, height: 34, isSvg: true},
  rbc: {file: 'bioicons-erythrocyte.svg', width: 98.419, height: 95.395, isSvg: true},
  edema: {file: 'bioicons-edema-capillaries.svg', width: 419.49, height: 285.014, isSvg: true},
};

export const STEPS: readonly MedAnimStep[] = [
  {
    id: 'B1',
    start: 0,
    end: 240,
    narration: 'Không khí hít vào đi qua cây phế quản tới hàng triệu phế nang bao quanh bởi mạng lưới mao mạch phổi.',
  },
  {
    id: 'B2',
    start: 240,
    end: 480,
    narration: 'Qua màng phế nang mao mạch mỏng, khí oxy đi vào máu còn khí cacbonic thoát ngược ra phế nang.',
  },
  {
    id: 'B3',
    start: 480,
    end: 720,
    narration: 'Trong mao mạch phổi, dòng hồng cầu nhận phân tử oxy để gắn lên hemoglobin rồi thải cacbonic ra ngoài.',
  },
  {
    id: 'B4',
    start: 720,
    end: 960,
    narration: 'Khi phổi bị phù nề, dịch ứ ở khoảng kẽ làm rào trao đổi dày lên, khiến oxy khó vào máu.',
  },
];

export const CREDITS_START = 960;
export const TOTAL_FRAMES = 1050;

export const GLOSSARY = [
  'phế nang',
  'mao mạch phổi',
  'màng phế nang mao mạch',
  'hồng cầu',
  'hemoglobin',
  'khoảng kẽ',
] as const;

export const LUNG_LOCATOR_START = 24;
export const LUNG_ZOOM = {start: 48, end: 78} as const;
export const ALVEOLI_LOCATOR_START = 264;
export const ALVEOLI_ZOOM = {start: 288, end: 318} as const;

// Symmetric panels >= 60% frame width (>= 1152 px), cleanly clear of mini-map (y <= 84), captions (y >= 876), and corner mascot.
export const B1_PANEL: Box = {left: 380, top: 92, width: 1160, height: 774};
export const LUNG_BOX: Box = {left: 416, top: 108, width: 646, height: 735};
export const B1_CAP_INSET: Box = {left: 1096, top: 245, width: 410, height: 234};
export const LUNG_SOURCE_REGION: Box = {left: 432, top: 470, width: 88, height: 88};
export const ALVEOLI_DETAIL_BOX: Box = {left: 556, top: 92, width: 1324, height: 774};
export const ALVEOLI_IMAGE_BOX: Box = {left: 690, top: 150, width: 620, height: 580};

export const B2_PANEL: Box = {left: 160, top: 92, width: 1320, height: 774};
export const B2_ALVEOLI_BOX: Box = {left: 185, top: 175, width: 440, height: 412};
export const B2_CAPILLARY_BOX: Box = {left: 650, top: 215, width: 580, height: 332};
export const ALVEOLI_SOURCE_REGION: Box = {left: 410, top: 340, width: 92, height: 92};
export const MEMBRANE_DETAIL_BOX: Box = {left: 540, top: 92, width: 1340, height: 774};

export const B4_STAGE_BOX: Box = {left: 440, top: 92, width: 1420, height: 774};
export const EDEMA_IMAGE_BOX: Box = {left: 468, top: 190, width: 470, height: 319};

export const LABELS: readonly LabelSpec[] = [
  {
    id: 'alveoli',
    vi: 'Chùm phế nang',
    latin: 'Alveoli',
    start: 138,
    end: 240,
    at: {x: 1360, y: 170},
    target: {x: 990, y: 490},
    ring: {center: {x: 995, y: 455}, rx: 225, ry: 205},
  },
  {
    id: 'membrane',
    vi: 'Màng phế nang mao mạch',
    viLines: ['Màng phế nang', 'mao mạch'],
    latin: 'Blood-gas barrier',
    start: 378,
    end: 480,
    at: {x: 1390, y: 170},
    target: {x: 1090, y: 465},
    ring: {center: {x: 1090, y: 465}, rx: 250, ry: 48},
  },
  {
    id: 'hemoglobin',
    vi: 'Hồng cầu & hemoglobin',
    viLines: ['Hồng cầu mang', 'hemoglobin'],
    latin: 'Erythrocyte hemoglobin',
    start: 500,
    end: 610,
    at: {x: 56, y: 165},
    target: {x: 1090, y: 585},
  },
  {
    id: 'co2-exp',
    vi: 'Khí cacbonic thải ra',
    viLines: ['Khí cacbonic', 'thải ra'],
    latin: 'Expired carbon dioxide',
    start: 610,
    end: 720,
    at: {x: 56, y: 165},
    target: {x: 960, y: 235},
  },
  {
    id: 'edema-barrier',
    vi: 'Dịch kẽ làm dày màng',
    viLines: ['Dịch kẽ làm', 'dày màng'],
    latin: 'Interstitial edema barrier',
    start: 750,
    end: 940,
    at: {x: 36, y: 195},
    target: {x: 1210, y: 475},
    ring: {center: {x: 1390, y: 475}, rx: 250, ry: 68},
  },
];

export const MINI_MAP_LEVELS: readonly {label: string; asset: AssetSpec}[] = [
  {label: 'Phổi', asset: IMAGES.lung},
  {label: 'Phế nang', asset: IMAGES.alveoli},
  {label: 'Màng trao đổi', asset: IMAGES.alveolusCell},
];

export const OPENING_POSES: readonly PoseBeat[] = [
  {frame: 0, pose: 'welcome'},
  {frame: 138, pose: 'point_up'},
];

export const CLOSING_POSES: readonly PoseBeat[] = [
  {frame: 0, pose: 'caution'},
  {frame: 170, pose: 'thumbs_up'},
];

export const ATTRIBUTION: readonly string[] = [
  'Hình y khoa: NIAID NIH BioArt Source (bioart.niaid.nih.gov), Public Domain — chùm phế nang.',
  'Servier Medical Art / Bioicons (smart.servier.com), CC BY 3.0 — phổi, mao mạch, hồng cầu, phù kẽ.',
  'Reactome Icon Library (reactome.org/icon-lib), CC BY 4.0 — phế nang và tế bào nội mô.',
];

export const LITERATURE: readonly string[] = [
  'Powers & Dhamoon 2023, StatPearls (PMID 30969729) · Petersson 2023, Semin Respir Crit Care Med (PMID 37816345)',
  'Makanya et al. 2013, Biomed Res Int (PMID 23484070) · Patel et al. 2023, StatPearls (PMID 30969637)',
  'Doyle & Cooper 2023, StatPearls (PMID 30422582) · Tetaj et al. 2026, J Cardiovasc Dev Dis (PMID 41590881)',
  'Fermoyle et al. 2021, J Am Heart Assoc (PMID 34369164)',
];
