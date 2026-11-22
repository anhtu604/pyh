// Medical entity color tokens mirroring profiles/medical-entity-colors.vi.yaml
// and profiles/brand.vi.yaml. Do not add hex values outside brand.
import {brand} from './palette';
import {hexToRgba} from '../style/pyhStyle';

export type BrandColorToken = keyof typeof brand;

export type MedicalEntityKey =
  | 'tissue_normal'
  | 'tissue_injured'
  | 'enzyme_marker'
  | 'blood_flow'
  | 'bile_flow'
  | 'drug_or_supplement'
  | 'scar_fibrosis'
  | 'lab_value'
  | 'warning_threshold'
  | 'label_text';

export type EntityColorSpec = {
  readonly token: BrandColorToken;
  readonly hex: string;
  readonly opacity: number;
  readonly rgba: string;
  readonly note: string;
};

const makeSpec = (token: BrandColorToken, opacity: number, note: string): EntityColorSpec => {
  const hex = brand[token];
  return {token, hex, opacity, rgba: hexToRgba(hex, opacity), note};
};

export const ENTITY_COLORS: Readonly<Record<MedicalEntityKey, EntityColorSpec>> = {
  tissue_normal: makeSpec('teal', 0.30, 'Mô/cơ quan bình thường (nền mô gan, thành mạch).'),
  tissue_injured: makeSpec('yellow', 0.85, 'Tế bào/mô đang bị tổn thương hoặc quá tải; chỉ dùng khi lời đọc nói tới tổn thương.'),
  enzyme_marker: makeSpec('navy', 1.0, 'Hạt men ALT/AST; khi thoát ra máu thêm vòng yellow, không đổi màu hạt.'),
  blood_flow: makeSpec('teal', 1.0, 'Dòng máu và mũi tên đi theo dòng máu (nét, không tô khối).'),
  bile_flow: makeSpec('yellow', 0.40, 'Mật và đường mật.'),
  drug_or_supplement: makeSpec('charcoal', 1.0, 'Viên thuốc/chế phẩm: thân off_white, viền charcoal; vòng yellow chỉ khi lời đọc nói tới nguy cơ.'),
  scar_fibrosis: makeSpec('charcoal', 0.50, 'Mô xơ/sẹo, vẽ bằng nét gạch chéo, không tô đặc.'),
  lab_value: makeSpec('navy', 1.0, 'Con số xét nghiệm trên thẻ off_white; điểm được nhấn dùng teal.'),
  warning_threshold: makeSpec('yellow', 1.0, 'Mốc cảnh báo, giới hạn trên bình thường, khi nào đi khám.'),
  label_text: makeSpec('navy', 1.0, 'Nhãn và đường dẫn; trên nền night đổi thành off_white.'),
};

export type ScaleSurface = 'night' | 'off_white';

export const surfaceBackgroundHex = (surface: ScaleSurface): string =>
  surface === 'night' ? brand.night : brand.off_white;

export const surfaceLabelTextHex = (surface: ScaleSurface): string =>
  surface === 'night' ? brand.off_white : ENTITY_COLORS.label_text.hex;

export const surfaceCardBackgroundHex = (surface: ScaleSurface): string =>
  surface === 'night' ? brand.navy : brand.off_white;

const channelLuminance = (channel255: number): number => {
  const c = channel255 / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
};

export const relativeLuminance = (hex: string): number => {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 0.2126 * channelLuminance(r) + 0.7152 * channelLuminance(g) + 0.0722 * channelLuminance(b);
};

export const contrastRatio = (hexA: string, hexB: string): number => {
  const l1 = relativeLuminance(hexA);
  const l2 = relativeLuminance(hexB);
  const [bright, dark] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (bright + 0.05) / (dark + 0.05);
};
