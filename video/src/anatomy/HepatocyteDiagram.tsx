import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {ENTITY_COLORS} from './entityColors';
import {brand} from './palette';
import {DiagramAnnotations, ProcessArrow} from './annotations';
import type {DiagramLabels} from './annotations';
import {hexToRgba} from '../style/pyhStyle';

export type HepaticView = 'unit' | 'function' | 'injury' | 'scar';

const clamp = (x: number) => Math.max(0, Math.min(1, x));

export const hepaticMechanics = (state: OrganProps['state'], severity: number, frame: number, fps: number, cues?: Record<string, number>) => {
  const p = (key: string) => {const x = clamp(cues ? (cues[key] ?? 0) : frame / fps / 5); return x * x * (3 - 2 * x);};
  const d = state === 'diseased' ? clamp(severity) : 0;
  return {
    flow: (frame / fps * 24) % 80,
    leak: d * p('leak'),
    toxic: d * p('toxic'),
    bile: d * p('block'),
    scar: d * p('scar'),
    export: p('export'),
    blockCue: cues ? p('block') : 0,
  };
};

type CalloutProps = {
  x: number;
  y: number;
  width: number;
  height: number;
  title: string;
  subtitle?: string;
  stroke?: string;
  strokeWidth?: number;
  titleColor?: string;
  titleSize?: number;
  subtitleSize?: number;
  leaderTo?: readonly [number, number];
  dotColor?: string;
};

const CalloutBox: React.FC<CalloutProps> = ({
  x, y, width, height, title, subtitle, stroke = brand.navy, strokeWidth = 1.8,
  titleColor = brand.navy, titleSize = 13, subtitleSize = 12, leaderTo, dotColor = ENTITY_COLORS.warning_threshold.hex,
}) => {
  const startX = leaderTo ? Math.max(x, Math.min(x + width, leaderTo[0])) : 0;
  const startY = leaderTo ? (leaderTo[1] < y ? y : leaderTo[1] > y + height ? y + height : y + height / 2) : 0;
  const cx = x + width / 2;
  const titleY = subtitle ? y + height * 0.41 : y + height / 2 + titleSize * 0.35;
  const subY = y + height * 0.78;
  return (
    <g data-callout={title} data-box={`${x} ${y} ${width} ${height}`}>
      {leaderTo && (
        <>
          <path d={`M${startX} ${startY} L${leaderTo[0]} ${leaderTo[1]}`} fill="none" stroke={brand.off_white} strokeWidth="3.5" />
          <path data-callout-leader="true" d={`M${startX} ${startY} L${leaderTo[0]} ${leaderTo[1]}`} fill="none" stroke={brand.navy} strokeWidth="1.6" />
          <circle cx={leaderTo[0]} cy={leaderTo[1]} r="3.2" fill={dotColor} stroke={brand.navy} strokeWidth="1" />
        </>
      )}
      <rect x={x} y={y} width={width} height={height} rx="8" fill={brand.off_white} stroke={stroke} strokeWidth={strokeWidth} />
      <text x={cx} y={titleY} textAnchor="middle" fontFamily="Be Vietnam Pro, sans-serif" fontSize={titleSize} fontWeight="800" fill={titleColor}>
        {title}
      </text>
      {subtitle && (
        <text x={cx} y={subY} textAnchor="middle" fontFamily="Be Vietnam Pro, sans-serif" fontSize={subtitleSize} fontWeight="700" fill={brand.navy}>
          {subtitle}
        </text>
      )}
    </g>
  );
};

const ProteinExportAndBileLayer: React.FC<{flow: number; exportProg: number; blocked: boolean}> = ({flow, exportProg, blocked}) => {
  const t = flow / 80;
  const flowBoost = 0.55 + 0.45 * exportProg;
  const flowHex = ENTITY_COLORS.blood_flow.hex;
  const warnHex = ENTITY_COLORS.warning_threshold.hex;
  const bileHex = ENTITY_COLORS.bile_flow.hex;
  return (
    <>
      <g data-layer="protein-export">
        <g opacity={flowBoost}>
          <ProcessArrow d="M135 328 V406 M125 394 L135 406 L145 394" />
          <g transform={`translate(135 ${344 + t * 44})`}>
            <rect x="-15" y="-8" width="30" height="16" rx="6" fill={flowHex} stroke={brand.navy} strokeWidth="1.6" />
            <text x="0" y="3.5" textAnchor="middle" fontFamily="Be Vietnam Pro, sans-serif" fontSize="9.5" fontWeight="800" fill={brand.off_white}>ALB</text>
          </g>
          <ProcessArrow d="M405 328 V406 M395 394 L405 406 L415 394" />
          <polygon points={`405,${336 + t * 44} 417,${346 + t * 44} 405,${356 + t * 44} 393,${346 + t * 44}`} fill={warnHex} stroke={brand.navy} strokeWidth="1.6" />
        </g>
        <CalloutBox
          x={52} y={276} width={190} height={46}
          title="Albumin (đạm gan)" subtitle="Tổng hợp → giữ dịch mạch"
          titleSize={13} subtitleSize={12} stroke={flowHex} strokeWidth={2}
          leaderTo={[135, 344]} dotColor={flowHex}
        />
        <CalloutBox
          x={304} y={276} width={204} height={46}
          title="Yếu tố đông máu" subtitle="Đánh giá đông máu: INR"
          titleSize={13} subtitleSize={12} stroke={warnHex} strokeWidth={2}
          leaderTo={[405, 344]} dotColor={warnHex}
        />
      </g>
      <g data-layer="bilirubin-bile-flow" data-bile-blocked={blocked ? 'true' : 'false'}>
        {!blocked && <g data-layer="bilirubin-uptake">
          <path d="M276 412 V364 Q292 344 292 246 Q292 198 276 176" fill="none" stroke={bileHex} strokeWidth="3" />
          <path d="M268 188 L276 176 L284 188" fill="none" stroke={bileHex} strokeWidth="3" />
          <circle cx={290} cy={386 - t * 194} r="7.5" fill={bileHex} stroke={brand.navy} strokeWidth="1.5" />
        </g>}
        {!blocked ? (
          <>
            <path data-layer="bilirubin-excretion" d="M276 176 V108 L268 86 V54" fill="none" stroke={bileHex} strokeWidth="3" />
            <circle cx={268} cy={112 - t * 42} r="7.5" fill={bileHex} stroke={brand.navy} strokeWidth="1.5" />
            <polygon points={`312,${104 - t * 38} 319,${109 - t * 38} 319,${117 - t * 38} 312,${122 - t * 38} 305,${117 - t * 38} 305,${109 - t * 38}`} fill={flowHex} stroke={brand.navy} strokeWidth="1.4" />
            <CalloutBox
              x={52} y={114} width={202} height={44}
              title="Bilirubin (sắc tố vàng)" subtitle="Thu gom → bài tiết xuống mật"
              titleSize={12.5} subtitleSize={11.5} stroke={bileHex} strokeWidth={2}
              leaderTo={[268, 86]} dotColor={bileHex}
            />
            <CalloutBox
              x={298} y={114} width={210} height={44}
              title="Axit mật (BA)" subtitle="Bài tiết thông suốt xuống mật"
              titleSize={12.5} subtitleSize={11.5} stroke={flowHex} strokeWidth={2}
              leaderTo={[312, 86]} dotColor={flowHex}
            />
          </>
        ) : (
          <>
            <rect x={256} y={54} width={64} height={15} rx="4" fill={warnHex} stroke={brand.navy} strokeWidth="2" />
            {/* Route reflux cleanly down the center corridor (x=274..294) clear of both lower callout boxes (x<=242 and x>=304). */}
            <path d="M276 92 L276 164 Q292 184 292 224 L292 332 Q292 362 276 382 V412" fill="none" stroke={warnHex} strokeWidth="3.5" strokeDasharray="6 4" />
            <path d="M267 402 L276 414 L285 402" fill="none" stroke={warnHex} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx={292} cy={196 + t * 116} r="7.5" fill={warnHex} stroke={brand.navy} strokeWidth="1.5" />
            <circle cx={276} cy={416} r="7.5" fill={warnHex} stroke={brand.navy} strokeWidth="1.5" />
            <polygon points="326,90 333,95 333,103 326,108 319,103 319,95" fill={flowHex} stroke={brand.navy} strokeWidth="1.4" />
            <CalloutBox
              x={52} y={114} width={202} height={44}
              title="Bilirubin (sắc tố vàng)" subtitle="Bị chặn đường thoát mật"
              titleSize={12.5} subtitleSize={11.5} stroke={warnHex} strokeWidth={2}
              leaderTo={[274, 88]} dotColor={warnHex}
            />
            <CalloutBox
              x={298} y={114} width={210} height={44}
              title="Khi tắc mật / suy tế bào:" subtitle="Bilirubin dội ngược vào máu"
              titleSize={12.5} subtitleSize={11.5} stroke={warnHex} strokeWidth={2.2}
              titleColor={brand.navy} leaderTo={[288, 62]} dotColor={warnHex}
            />
          </>
        )}
      </g>
    </>
  );
};

const InjuryMechanismsLayer: React.FC<{
  state: OrganProps['state'];
  severity: number;
  emphasizeFlow?: boolean;
  flow: number;
  bile: number;
}> = ({state, severity, emphasizeFlow, flow, bile}) => {
  const t = flow / 80;
  const isS23 = state === 'diseased' && severity === 0.85 && !emphasizeFlow;
  const isS29 = state === 'diseased' && Boolean(emphasizeFlow) && severity === 0.8;
  const flowHex = ENTITY_COLORS.blood_flow.hex;
  const warnHex = ENTITY_COLORS.warning_threshold.hex;
  const drugHex = ENTITY_COLORS.drug_or_supplement.hex;
  const scarHex = ENTITY_COLORS.scar_fibrosis.hex;

  return (
    <>
      {state === 'normal' && (
        <g data-layer="bile-pump-flow" data-pump="open">
          <rect x={256} y={78} width={48} height={22} rx="6" fill={flowHex} stroke={brand.navy} strokeWidth="2" />
          <rect x={274} y={76} width={12} height={26} fill={brand.off_white} fillOpacity="0.85" />
          <polygon points={`266,${104 - t * 36} 272,${108 - t * 36} 272,${115 - t * 36} 266,${119 - t * 36} 260,${115 - t * 36} 260,${108 - t * 36}`} fill={flowHex} stroke={brand.navy} strokeWidth="1.3" />
          <circle cx={294} cy={112 - t * 36} r="6.5" fill={warnHex} stroke={brand.navy} strokeWidth="1.3" />
          <CalloutBox
            x={130} y={114} width={300} height={44}
            title="Bơm mật mở bình thường" subtitle="Bài tiết Axit mật (BA) & Bilirubin (BIL)"
            titleSize={13} subtitleSize={12} stroke={flowHex} strokeWidth={2}
            leaderTo={[280, 90]} dotColor={flowHex}
          />
        </g>
      )}
      {state === 'diseased' && bile > 0 && !isS23 && !isS29 && (
        <g data-layer="bile-pump-flow" data-pump="locked">
          <rect x={254} y={76} width={52} height={24} rx="6" fill={warnHex} stroke={brand.navy} strokeWidth="2.4" />
          <path d="M268 81 L292 95 M292 81 L268 95" stroke={brand.navy} strokeWidth="3.5" strokeLinecap="round" />
          {[104, 128, 152].map((bx, idx) => (
            <polygon
              key={bx}
              points={`${bx},${172 + (idx % 2) * 14} ${bx + 7},${177 + (idx % 2) * 14} ${bx + 7},${185 + (idx % 2) * 14} ${bx},${190 + (idx % 2) * 14} ${bx - 7},${185 + (idx % 2) * 14} ${bx - 7},${177 + (idx % 2) * 14}`}
              fill={flowHex} stroke={brand.navy} strokeWidth="1.4"
            />
          ))}
          <path d="M168 178 Q188 164 164 156" fill="none" stroke={flowHex} strokeWidth="2.8" strokeLinecap="round" />
          <path d="M349 162 V284 Q349 346 312 374 V412" fill="none" stroke={warnHex} strokeWidth="3.5" strokeDasharray="6 4" />
          <path d="M304 402 L312 414 L320 402" fill="none" stroke={warnHex} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx={349} cy={190 + t * 88} r="7" fill={warnHex} stroke={brand.navy} strokeWidth="1.5" />
          <circle cx={312} cy={416} r="7" fill={warnHex} stroke={brand.navy} strokeWidth="1.5" />
          <CalloutBox
            x={52} y={114} width={210} height={44}
            title="Axit mật (BA) ứ kẹt" subtitle="Khóa bơm mật → ứ trong tế bào"
            titleSize={12.5} subtitleSize={11.5} stroke={flowHex} strokeWidth={2}
            leaderTo={[128, 174]} dotColor={flowHex}
          />
          <CalloutBox
            x={298} y={114} width={212} height={44}
            title="Bilirubin (BIL) dội ngược" subtitle="tràn ngược vào dòng máu"
            titleSize={12.5} subtitleSize={11.5} stroke={warnHex} strokeWidth={2.2}
            leaderTo={[349, 174]} dotColor={warnHex}
          />
        </g>
      )}
      {isS23 && (
        <g data-layer="chronic-acute-overlay">
          <g data-layer="chronic-liver-context">
            <path d="M76 203 Q82 166 132 174 L177 183 Q164 218 118 230 Q80 233 76 203Z"
              fill={hexToRgba(scarHex, 0.72)} stroke={brand.navy} strokeWidth="2.5" />
            <path d="M129 178 L121 222 M92 192 Q115 184 143 190 M88 207 Q112 201 145 207"
              fill="none" stroke={brand.off_white} strokeWidth="2.2" strokeDasharray="5 3" />
          </g>
          <path d="M462 140 L422 182 L434 186 L404 210" fill="none" stroke={warnHex} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx={404} cy={210} r="6" fill={warnHex} stroke={brand.navy} strokeWidth="2.5" />
          <CalloutBox
            x={48} y={258} width={216} height={46}
            title="Nền bệnh gan mạn sẵn có" subtitle="Bệnh nền có trước đợt độc chất"
            titleSize={12.5} subtitleSize={11.5} stroke={scarHex} strokeWidth={2.4}
            leaderTo={[113, 211]} dotColor={scarHex}
          />
          <CalloutBox
            x={294} y={258} width={218} height={46}
            title="+ Đợt độc chất cấp chồng lên" subtitle="Suy gan cấp/nền mạn: 36/91 ca"
            titleSize={12} subtitleSize={11.5} stroke={warnHex} strokeWidth={2.4}
            titleColor={brand.navy} leaderTo={[416, 198]} dotColor={warnHex}
          />
        </g>
      )}
      {isS29 && (
        <g data-layer="contaminant-panel">
          <CalloutBox
            x={58} y={154} width={444} height={46}
            title="386 mẫu từ 91 ca tổn thương gan" subtitle="Tỷ lệ trong mẫu nghiên cứu" leaderTo={[74, 208]}
            titleSize={12.5} stroke={brand.navy} strokeWidth={2}
          />
          {/* Kim loại nặng (Hg): charcoal with yellow warning ring */}
          <circle cx={74} cy={226} r="22" fill="none" stroke={warnHex} strokeWidth="2.5" />
          <polygon points="74,208 92,217 92,236 74,245 56,236 56,217" fill={drugHex} stroke={brand.off_white} strokeWidth="1.8" />
          <text x={74} y={231} textAnchor="middle" fontFamily="Be Vietnam Pro, sans-serif" fontSize="11.5" fontWeight="800" fill={brand.off_white}>Hg</text>
          <path d="M96 226 H108" stroke={warnHex} strokeWidth="2.5" strokeLinecap="round" />
          <CalloutBox
            x={44} y={254} width={226} height={58}
            title="34% mẫu vượt ngưỡng thủy ngân" subtitle="Kim loại nặng • theo chuẩn WHO"
            titleSize={11.5} subtitleSize={11.5} stroke={warnHex} strokeWidth={2.2}
            titleColor={brand.navy} leaderTo={[74, 245]} dotColor={warnHex}
          />
          {/* Tân dược trộn lén: drug_or_supplement (off_white body, charcoal outline) + yellow risk ring */}
          <g transform="translate(470 226)">
            <circle r="22" fill="none" stroke={warnHex} strokeWidth="2.5" />
            <g transform="rotate(-18)">
              <rect x="-16" y="-8" width="16" height="16" rx="7" fill={brand.off_white} stroke={drugHex} strokeWidth="2" />
              <rect x="-2" y="-8" width="18" height="16" rx="7" fill={drugHex} stroke={drugHex} strokeWidth="2" />
            </g>
          </g>
          <path d="M446 226 H434" stroke={warnHex} strokeWidth="2.5" strokeLinecap="round" />
          <CalloutBox
            x={290} y={254} width={226} height={58}
            title="Trộn lén thuốc tây: 27,7% mẫu" subtitle="(tân dược không khai báo nhãn)"
            titleSize={11.5} subtitleSize={11.5} stroke={warnHex} strokeWidth={2.2}
            leaderTo={[470, 238]} dotColor={warnHex}
          />
        </g>
      )}
    </>
  );
};

/** Original schematic. No progression speed or particle count is a clinical measurement. */
export const HepatocyteDiagram: React.FC<OrganProps & {view: HepaticView; labels: DiagramLabels}> = ({
  state, severity, emphasizeFlow, lightBackground = false, cueProgress, visibleLabels, view, labels,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = hepaticMechanics(state, severity, frame, fps, cueProgress);

  const tissueHex = ENTITY_COLORS.tissue_normal.hex;
  const injuredHex = ENTITY_COLORS.tissue_injured.hex;
  const enzymeHex = ENTITY_COLORS.enzyme_marker.hex;
  const bloodHex = ENTITY_COLORS.blood_flow.hex;
  const bileHex = ENTITY_COLORS.bile_flow.hex;
  const warnHex = ENTITY_COLORS.warning_threshold.hex;
  const scarHex = ENTITY_COLORS.scar_fibrosis.hex;

  const isInjured = g.leak > 0 || g.toxic > 0;
  const membraneStroke = isInjured ? injuredHex : bloodHex;
  const cytoplasmFill = hexToRgba(tissueHex, lightBackground ? 0.24 : 0.30);
  const injuredWashOpacity = Math.min(0.32, Math.max(g.leak, g.toxic) * 0.32);
  const innerRimStroke = hexToRgba(brand.off_white, lightBackground ? 0.55 : 0.35);

  // Rounded hexagonal hepatocyte polygon (generous cellular silhouette, subtle organic asymmetry)
  const outerCellPath =
    'M118 98 L442 98 Q482 98 500 136 L522 206 Q532 238 522 270 L498 336 Q480 370 442 370 L118 370 Q80 370 62 336 L38 270 Q28 238 38 206 L60 136 Q78 98 118 98 Z';
  const innerCellPath =
    'M126 110 L434 110 Q468 110 484 142 L504 208 Q512 238 504 268 L482 328 Q468 358 434 358 L126 358 Q92 358 78 328 L56 268 Q48 238 56 208 L76 142 Q92 110 126 110 Z';

  // Asymmetric focal cluster of intracellular ALT/AST enzyme granules (navy core, crisp rim)
  // Positioned to draw the eye from nucleus toward the emphasized sinusoidal membrane.
  const baselineEnzymes: readonly {cx: number; cy: number; r: number}[] =
    view === 'unit'
      ? [
          {cx: 124, cy: 274, r: 9},
          {cx: 176, cy: 302, r: 10.5},
          {cx: 356, cy: 266, r: 11.5},
          {cx: 416, cy: 254, r: 10},
          {cx: 392, cy: 294, r: 12},
          {cx: 454, cy: 288, r: 9.5},
        ]
      : [
          {cx: 136, cy: 286, r: 7.5},
          {cx: 232, cy: 292, r: 7.5},
          {cx: 332, cy: 292, r: 7.5},
          {cx: 428, cy: 286, r: 7.5},
        ];

  const activeEnzymeSlots: readonly {x: number; y: number; r: number}[] = [
    {x: 112, y: 328, r: 9.5},
    {x: 164, y: 336, r: 10.5},
    {x: 222, y: 324, r: 9.5},
    {x: 286, y: 334, r: 11},
    {x: 344, y: 322, r: 10.5},
    {x: 398, y: 334, r: 11.5},
    {x: 450, y: 322, r: 10},
  ];

  // Slightly off-center nucleus in unit view creates a natural focal hierarchy with the enzyme cluster.
  const nucleusCx = view === 'unit' ? 248 : 278;
  const nucleusCy = view === 'unit' ? 208 : 224;

  return (
    <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Tế bào gan cạnh dòng máu và đường mật" data-view={view} data-state={state}>
      {/* Sinusoid (bottom vascular pole): blood_flow teal lines + subtle translucent lumen */}
      <g data-layer="sinusoid">
        <rect x="28" y="398" width="504" height="82" rx="18" fill={hexToRgba(bloodHex, lightBackground ? 0.16 : 0.22)} stroke={bloodHex} strokeWidth="3.5" />
        {/* Fenestrated sinusoidal endothelial inner lining */}
        <line x1="44" y1="408" x2="516" y2="408" stroke={bloodHex} strokeOpacity="0.65" strokeWidth="2.5" strokeDasharray="16 10" strokeLinecap="round" />
        <line x1="44" y1="470" x2="516" y2="470" stroke={bloodHex} strokeOpacity="0.65" strokeWidth="2.5" strokeDasharray="16 10" strokeLinecap="round" />
        {/* Streamlines showing laminar sinusoidal flow */}
        {[0, 1, 2, 3, 4, 5].map(i => {
          const cx = 56 + ((i * 80 + g.flow) % 456);
          const cy = 433 + (i % 2) * 14;
          return (
            <g key={i}>
              <line x1={cx - 18} y1={cy} x2={cx + 18} y2={cy} stroke={bloodHex} strokeOpacity="0.78" strokeWidth="3" strokeLinecap="round" />
              <ellipse cx={cx} cy={cy} rx="12" ry="5.5" fill={hexToRgba(bloodHex, 0.34)} stroke={bloodHex} strokeWidth="1.8" />
            </g>
          );
        })}
        {/* Blood flow arrow kept cleanly left of x=430 so 'Dòng máu' leader at x=490 never crosses it */}
        <path data-process-arrow="true" d="M74 498 H416 M402 489 L416 498 L402 507" fill="none" stroke={bloodHex} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      </g>

      {/* Subtle flanking edges of adjacent hepatocytes in the hepatic plate */}
      <g opacity="0.20" fill="none" stroke={tissueHex} strokeWidth="2.5">
        <path d="M12 142 L34 142 L20 238 L34 332 L12 332" />
        <path d="M548 142 L526 142 L540 238 L526 332 L548 332" />
      </g>

      {/* Hepatocyte body: rounded hexagonal cell with emphasized sinusoidal membrane, nucleus, and focal enzymes */}
      <g data-layer="hepatocyte-membrane" data-leak={g.leak}>
        <path d={outerCellPath} fill={hexToRgba(membraneStroke, 0.24)} stroke={membraneStroke} strokeWidth="5" strokeLinejoin="round" />
        <path d={innerCellPath} fill={cytoplasmFill} stroke={innerRimStroke} strokeWidth="2" strokeLinejoin="round" />
        {injuredWashOpacity > 0 && (
          <path d={innerCellPath} fill={injuredHex} fillOpacity={injuredWashOpacity} />
        )}
        {/* Emphasized sinusoidal (basolateral) membrane highlight band */}
        <path
          d="M116 364 L444 364"
          fill="none"
          stroke={isInjured ? warnHex : brand.off_white}
          strokeOpacity={isInjured ? 0.85 : 0.65}
          strokeWidth="4"
          strokeLinecap="round"
        />
        {/* Sinusoidal microvilli ticks along bottom inner membrane */}
        {Array.from({length: 12}, (_, i) => (
          <line key={i} x1={116 + i * 30} y1={356} x2={116 + i * 30} y2={367} stroke={membraneStroke} strokeOpacity="0.72" strokeWidth="2.4" strokeLinecap="round" />
        ))}
        {/* Cell nucleus: navy nuclear envelope + subtle teal chromatin highlight + night nucleolus */}
        <g data-layer="hepatocyte-nucleus">
          <ellipse cx={nucleusCx} cy={nucleusCy} rx="56" ry="46" fill={brand.navy} stroke={hexToRgba(brand.off_white, 0.72)} strokeWidth="2.5" />
          <ellipse cx={nucleusCx - 12} cy={nucleusCy - 12} rx="32" ry="24" fill={hexToRgba(tissueHex, 0.28)} />
          <circle cx={nucleusCx + 10} cy={nucleusCy + 2} r="13" fill={brand.night} stroke={hexToRgba(brand.off_white, 0.38)} strokeWidth="1.5" />
        </g>

        {/* Intracellular ALT/AST enzyme granules: strictly enzyme_marker (navy) with crisp rim & highlight */}
        {baselineEnzymes.map((e, i) => (
          <g key={`base-${i}`} data-enzyme-baseline="true">
            <circle cx={e.cx} cy={e.cy} r={e.r} fill={enzymeHex} stroke={brand.off_white} strokeWidth="2" />
            <circle cx={e.cx - e.r * 0.28} cy={e.cy - e.r * 0.28} r={e.r * 0.26} fill={brand.off_white} fillOpacity="0.42" />
          </g>
        ))}

        {/* Active ALT/AST enzyme markers: navy particle; adds yellow outer ring ONLY when leaked into blood */}
        {(view === 'unit' || view === 'injury') && activeEnzymeSlots.map((slot, i) => {
          const x = slot.x;
          const y = slot.y + g.leak * (96 + (i % 2) * 24);
          const inBlood = g.leak > 0 && y > 374;
          const r = view === 'unit' ? slot.r : 7.5;
          return (
            <g key={i} data-enzyme="true" data-enzyme-leaked={inBlood ? 'true' : 'false'}>
              {inBlood && (
                <circle cx={x} cy={y} r={r + 5.5} fill="none" stroke={warnHex} strokeWidth="3" />
              )}
              <circle cx={x} cy={y} r={r} fill={enzymeHex} stroke={brand.off_white} strokeWidth="2" />
              <circle cx={x - r * 0.28} cy={y - r * 0.28} r={r * 0.26} fill={brand.off_white} fillOpacity="0.45" />
            </g>
          );
        })}

        {/* Membrane breach at sinusoidal pole when leaking */}
        {g.leak > 0 && (
          <g data-layer="membrane-breach">
            <rect x={166} y={356} width={56} height={18} rx={4} fill={lightBackground ? brand.off_white : brand.night} />
            <path d="M164 366 l12 -12 10 18 12 -16 10 14 12 -10" stroke={warnHex} strokeWidth={3.8 + g.leak * 2.5} strokeLinecap="round" strokeLinejoin="round" fill="none" />
          </g>
        )}
      </g>

      {/* Mitochondria (only in function / injury views, preserving existing medical meaning) */}
      {(view === 'function' || view === 'injury') && (
        <g data-layer="mitochondria" data-toxic={g.toxic}>
          {[142, 412].map(x => (
            <g key={x} transform={`translate(${x} 224)`}>
              <ellipse rx="36" ry="22" fill={g.toxic > 0 ? injuredHex : tissueHex} fillOpacity={g.toxic > 0 ? 0.85 : 0.72} stroke={brand.navy} strokeWidth="2.2" />
              <path d="M-22 0 l7 -9 8 18 8 -18 8 18 7 -9" fill="none" stroke={brand.off_white} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
            </g>
          ))}
        </g>
      )}

      {/* Bile canaliculus (top biliary pole): bile_flow yellow */}
      <g data-layer="bile-canaliculus" data-block={g.bile}>
        <rect x="68" y="44" width="424" height="24" rx="12" fill={ENTITY_COLORS.bile_flow.rgba} stroke={bileHex} strokeWidth="2.8" />
        {/* Subtle canalicular lumen dashes */}
        <line x1="92" y1="56" x2="468" y2="56" stroke={bileHex} strokeOpacity="0.5" strokeWidth="2" strokeDasharray="12 12" strokeLinecap="round" />
        <ProcessArrow d="M280 94 V60 M270 71 L280 60 L290 71" />
        {g.bile > 0 && (
          <g>
            <circle cx="398" cy="56" r="13" fill={brand.navy} stroke={warnHex} strokeWidth="2.5" />
            <path d="M391 49 l14 14 m0 -14 l-14 14" stroke={warnHex} strokeWidth={2.5 + g.bile * 2} strokeLinecap="round" />
          </g>
        )}
      </g>

      {view === 'function' && <ProteinExportAndBileLayer flow={g.flow} exportProg={g.export} blocked={g.blockCue > 0 || g.bile > 0} />}
      {view === 'injury' && <InjuryMechanismsLayer state={state} severity={severity} emphasizeFlow={emphasizeFlow} flow={g.flow} bile={g.bile} />}

      {/* Fibrous septa (scar view): charcoal cross-hatched strokes, never solid fill */}
      {view === 'scar' && (
        <g data-layer="fibrous-septa" opacity={g.scar}>
          {[116, 198, 362, 444].map(x => (
            <g key={x}>
              <path d={`M${x} 96 Q${x + 26} 230 ${x} 370`} fill="none" stroke={lightBackground ? scarHex : brand.off_white} strokeOpacity={ENTITY_COLORS.scar_fibrosis.opacity} strokeWidth="14" strokeDasharray="10 7" strokeLinecap="round" />
              <path d={`M${x - 4} 102 Q${x + 22} 230 ${x - 4} 364`} fill="none" stroke={scarHex} strokeOpacity="0.85" strokeWidth="3.5" strokeDasharray="6 6" />
              {[136, 178, 220, 262, 304, 342].map(y => (
                <line key={y} x1={x - 2} y1={y} x2={x + 18} y2={y + 10} stroke={lightBackground ? scarHex : brand.off_white} strokeOpacity="0.55" strokeWidth="2.2" strokeLinecap="round" />
              ))}
            </g>
          ))}
        </g>
      )}
      <DiagramAnnotations labels={labels} visibleLabels={visibleLabels} />
    </svg>
  );
};
