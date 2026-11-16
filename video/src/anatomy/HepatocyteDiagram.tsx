import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {brand, anatomyColors as c} from './palette';
import {DiagramAnnotations, ProcessArrow} from './annotations';
import type {DiagramLabels} from './annotations';

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
  titleColor = brand.navy, titleSize = 13, subtitleSize = 12, leaderTo, dotColor = brand.yellow,
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
  return (
    <>
      <g data-layer="protein-export">
        <g opacity={flowBoost}>
          <ProcessArrow d="M135 328 V406 M125 394 L135 406 L145 394" />
          <g transform={`translate(135 ${344 + t * 44})`}>
            <rect x="-15" y="-8" width="30" height="16" rx="6" fill={brand.teal} stroke={brand.navy} strokeWidth="1.6" />
            <text x="0" y="3.5" textAnchor="middle" fontFamily="Be Vietnam Pro, sans-serif" fontSize="9.5" fontWeight="800" fill={brand.off_white}>ALB</text>
          </g>
          <ProcessArrow d="M405 328 V406 M395 394 L405 406 L415 394" />
          <polygon points={`405,${336 + t * 44} 417,${346 + t * 44} 405,${356 + t * 44} 393,${346 + t * 44}`} fill={brand.yellow} stroke={brand.navy} strokeWidth="1.6" />
        </g>
        <CalloutBox
          x={52} y={276} width={190} height={46}
          title="Albumin (đạm gan)" subtitle="Tổng hợp → giữ dịch mạch"
          titleSize={13} subtitleSize={12} stroke={brand.teal} strokeWidth={2}
          leaderTo={[135, 344]} dotColor={brand.teal}
        />
        <CalloutBox
          x={304} y={276} width={204} height={46}
          title="Yếu tố đông máu" subtitle="Đánh giá đông máu: INR"
          titleSize={13} subtitleSize={12} stroke={brand.yellow} strokeWidth={2}
          leaderTo={[405, 344]} dotColor={brand.yellow}
        />
      </g>
      <g data-layer="bilirubin-bile-flow" data-bile-blocked={blocked ? 'true' : 'false'}>
        {!blocked && <g data-layer="bilirubin-uptake">
          <path d="M280 412 V368 Q300 348 280 328 V176" fill="none" stroke={brand.yellow} strokeWidth="3" />
          <path d="M272 188 L280 176 L288 188" fill="none" stroke={brand.yellow} strokeWidth="3" />
          <circle cx={280} cy={402 - t * 210} r="7.5" fill={brand.yellow} stroke={brand.navy} strokeWidth="1.5" />
        </g>}
        {!blocked ? (
          <>
            <path data-layer="bilirubin-excretion" d="M280 176 V108 L268 86 V54" fill="none" stroke={brand.yellow} strokeWidth="3" />
            <circle cx={268} cy={112 - t * 42} r="7.5" fill={brand.yellow} stroke={brand.navy} strokeWidth="1.5" />
            <polygon points={`312,${104 - t * 38} 319,${109 - t * 38} 319,${117 - t * 38} 312,${122 - t * 38} 305,${117 - t * 38} 305,${109 - t * 38}`} fill={brand.teal} stroke={brand.navy} strokeWidth="1.4" />
            <CalloutBox
              x={52} y={114} width={202} height={44}
              title="Bilirubin (sắc tố vàng)" subtitle="Thu gom → bài tiết xuống mật"
              titleSize={12.5} subtitleSize={11.5} stroke={brand.yellow} strokeWidth={2}
              leaderTo={[268, 86]} dotColor={brand.yellow}
            />
            <CalloutBox
              x={298} y={114} width={210} height={44}
              title="Axit mật (BA)" subtitle="Bài tiết thông suốt xuống mật"
              titleSize={12.5} subtitleSize={11.5} stroke={brand.teal} strokeWidth={2}
              leaderTo={[312, 86]} dotColor={brand.teal}
            />
          </>
        ) : (
          <>
            <rect x={256} y={54} width={64} height={15} rx="4" fill={c.bloodInset} stroke={brand.navy} strokeWidth="2" />
            <path d="M276 92 L276 154 Q349 162 349 218 L349 292 Q349 340 282 372 V412" fill="none" stroke={brand.yellow} strokeWidth="3.5" strokeDasharray="6 4" />
            <path d="M273 402 L282 414 L291 402" fill="none" stroke={brand.yellow} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx={349} cy={196 + t * 88} r="7.5" fill={brand.yellow} stroke={brand.navy} strokeWidth="1.5" />
            <circle cx={282} cy={416} r="7.5" fill={brand.yellow} stroke={brand.navy} strokeWidth="1.5" />
            <polygon points="326,90 333,95 333,103 326,108 319,103 319,95" fill={brand.teal} stroke={brand.navy} strokeWidth="1.4" />
            <CalloutBox
              x={52} y={114} width={202} height={44}
              title="Bilirubin (sắc tố vàng)" subtitle="Bị chặn đường thoát mật"
              titleSize={12.5} subtitleSize={11.5} stroke={brand.yellow} strokeWidth={2}
              leaderTo={[274, 88]} dotColor={brand.yellow}
            />
            <CalloutBox
              x={298} y={114} width={210} height={44}
              title="Khi tắc mật / suy tế bào:" subtitle="Bilirubin dội ngược vào máu"
              titleSize={12.5} subtitleSize={11.5} stroke={c.bloodInset} strokeWidth={2.2}
              titleColor={c.bloodInset} leaderTo={[288, 62]} dotColor={c.bloodInset}
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

  return (
    <>
      {state === 'normal' && (
        <g data-layer="bile-pump-flow" data-pump="open">
          <rect x={256} y={78} width={48} height={22} rx="6" fill={brand.teal} stroke={brand.navy} strokeWidth="2" />
          <rect x={274} y={76} width={12} height={26} fill={c.vesselLight} />
          <polygon points={`266,${104 - t * 36} 272,${108 - t * 36} 272,${115 - t * 36} 266,${119 - t * 36} 260,${115 - t * 36} 260,${108 - t * 36}`} fill={brand.teal} stroke={brand.navy} strokeWidth="1.3" />
          <circle cx={294} cy={112 - t * 36} r="6.5" fill={brand.yellow} stroke={brand.navy} strokeWidth="1.3" />
          <CalloutBox
            x={130} y={114} width={300} height={44}
            title="Bơm mật mở bình thường" subtitle="Bài tiết Axit mật (BA) & Bilirubin (BIL)"
            titleSize={13} subtitleSize={12} stroke={brand.teal} strokeWidth={2}
            leaderTo={[280, 90]} dotColor={brand.teal}
          />
        </g>
      )}
      {state === 'diseased' && bile > 0 && !isS23 && !isS29 && (
        <g data-layer="bile-pump-flow" data-pump="locked">
          <rect x={254} y={76} width={52} height={24} rx="6" fill={c.bloodInset} stroke={brand.navy} strokeWidth="2.4" />
          <path d="M268 81 L292 95 M292 81 L268 95" stroke={brand.off_white} strokeWidth="3.5" strokeLinecap="round" />
          {[104, 128, 152].map((bx, idx) => (
            <polygon
              key={bx}
              points={`${bx},${172 + (idx % 2) * 14} ${bx + 7},${177 + (idx % 2) * 14} ${bx + 7},${185 + (idx % 2) * 14} ${bx},${190 + (idx % 2) * 14} ${bx - 7},${185 + (idx % 2) * 14} ${bx - 7},${177 + (idx % 2) * 14}`}
              fill={brand.teal} stroke={brand.navy} strokeWidth="1.4"
            />
          ))}
          <path d="M168 178 Q188 164 164 156" fill="none" stroke={brand.teal} strokeWidth="2.8" strokeLinecap="round" />
          <path d="M349 162 V288 Q349 342 284 374 V412" fill="none" stroke={brand.yellow} strokeWidth="3.5" strokeDasharray="6 4" />
          <path d="M276 402 L284 414 L292 402" fill="none" stroke={brand.yellow} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx={349} cy={190 + t * 88} r="7" fill={brand.yellow} stroke={brand.navy} strokeWidth="1.5" />
          <circle cx={284} cy={416} r="7" fill={brand.yellow} stroke={brand.navy} strokeWidth="1.5" />
          <CalloutBox
            x={52} y={114} width={210} height={44}
            title="Axit mật (BA) ứ kẹt" subtitle="Khóa bơm mật → ứ trong tế bào"
            titleSize={12.5} subtitleSize={11.5} stroke={brand.teal} strokeWidth={2}
            leaderTo={[128, 174]} dotColor={brand.teal}
          />
          <CalloutBox
            x={298} y={114} width={212} height={44}
            title="Bilirubin (BIL) dội ngược" subtitle="tràn ngược vào dòng máu"
            titleSize={12.5} subtitleSize={11.5} stroke={brand.yellow} strokeWidth={2.2}
            leaderTo={[349, 174]} dotColor={brand.yellow}
          />

        </g>
      )}
      {isS23 && (
        <g data-layer="chronic-acute-overlay">
          <g data-layer="chronic-liver-context">
            <path d="M76 203 Q82 166 132 174 L177 183 Q164 218 118 230 Q80 233 76 203Z"
              fill={c.boneDeep} stroke={brand.navy} strokeWidth="2.5" />
            <path d="M129 178 L121 222 M92 192 Q115 184 143 190 M88 207 Q112 201 145 207"
              fill="none" stroke={c.boneLight} strokeWidth="2.5" />
          </g>
          <path d="M462 140 L422 182 L434 186 L404 210" fill="none" stroke={c.bloodInset} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx={404} cy={210} r="6" fill={brand.yellow} stroke={c.bloodInset} strokeWidth="2.5" />
          <CalloutBox
            x={48} y={258} width={216} height={46}
            title="Nền bệnh gan mạn sẵn có" subtitle="Bệnh nền có trước đợt độc chất"
            titleSize={12.5} subtitleSize={11.5} stroke={c.boneDeep} strokeWidth={2.4}
            leaderTo={[113, 211]} dotColor={c.boneDeep}
          />
          <CalloutBox
            x={294} y={258} width={218} height={46}
            title="+ Đợt độc chất cấp chồng lên" subtitle="Suy gan cấp/nền mạn: 36/91 ca"
            titleSize={12} subtitleSize={11.5} stroke={c.bloodInset} strokeWidth={2.4}
            titleColor={c.bloodInset} leaderTo={[416, 198]} dotColor={c.bloodInset}
          />
        </g>
      )}
      {isS29 && (
        <g data-layer="contaminant-panel">
          <CalloutBox
            x={58} y={154} width={444} height={46}
            title="386 mẫu từ 91 ca tổn thương gan [E03]" subtitle="Tỷ lệ trong mẫu nghiên cứu" leaderTo={[74, 208]}
            titleSize={12.5} stroke={brand.navy} strokeWidth={2}
          />
          {/* Kim loại nặng (Hg) */}
          <polygon points="74,208 92,217 92,236 74,245 56,236 56,217" fill={brand.charcoal} stroke={brand.navy} strokeWidth="2" />
          <text x={74} y={231} textAnchor="middle" fontFamily="Be Vietnam Pro, sans-serif" fontSize="11.5" fontWeight="800" fill={brand.off_white}>Hg</text>
          <path d="M92 226 H104" stroke={c.bloodInset} strokeWidth="2.5" strokeLinecap="round" />
          <CalloutBox
            x={44} y={254} width={226} height={58}
            title="34% mẫu vượt ngưỡng thủy ngân" subtitle="Kim loại nặng • theo chuẩn WHO"
            titleSize={11.5} subtitleSize={11.5} stroke={c.bloodInset} strokeWidth={2.2}
            titleColor={c.bloodInset} leaderTo={[74, 245]} dotColor={c.bloodInset}
          />
          {/* Tân dược trộn lén */}
          <g transform="translate(470 226) rotate(-18)">
            <rect x="-18" y="-9" width="18" height="18" rx="7" fill={brand.yellow} stroke={brand.navy} strokeWidth="1.8" />
            <rect x="-2" y="-9" width="20" height="18" rx="7" fill={c.bloodInset} stroke={brand.navy} strokeWidth="1.8" />
          </g>
          <path d="M450 226 H438" stroke={brand.yellow} strokeWidth="2.5" strokeLinecap="round" />
          <CalloutBox
            x={290} y={254} width={226} height={58}
            title="Trộn lén thuốc tây: 27,7% mẫu" subtitle="(tân dược không khai báo nhãn)"
            titleSize={11.5} subtitleSize={11.5} stroke={brand.yellow} strokeWidth={2.2}
            leaderTo={[470, 238]} dotColor={brand.yellow}
          />
        </g>
      )}
    </>
  );
};

/** Original schematic. No progression speed or particle count is a clinical measurement. */
export const HepatocyteDiagram: React.FC<OrganProps & {view: HepaticView; labels: DiagramLabels}> = ({
  state, severity, emphasizeFlow, cueProgress, visibleLabels, view, labels,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = hepaticMechanics(state, severity, frame, fps, cueProgress);
  return (
    <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Tế bào gan cạnh dòng máu và đường mật" data-view={view} data-state={state}>
      <g data-layer="sinusoid">
        <path d="M30 395 Q280 365 530 395 L530 485 Q280 455 30 485Z" fill={c.bloodInset} stroke={brand.navy} strokeWidth="3" />
        <path d="M30 411 Q280 381 530 411 L530 468 Q280 438 30 468Z" fill={c.bloodLight} />
        {[0, 1, 2, 3, 4, 5].map(i => (
          <ellipse key={i} cx={45 + i * 80 + g.flow} cy={433 + (i % 2) * 8} rx="15" ry="7" fill={c.blood} stroke={c.bloodInset} strokeWidth="2" />
        ))}
        <ProcessArrow d="M70 501 H490 M476 491 L490 501 L476 511" />
      </g>
      <g data-layer="hepatocyte-membrane" data-leak={g.leak}>
        <path d="M45 112 Q280 55 510 112 L510 345 Q280 397 45 345Z" fill={c.media} stroke={brand.navy} strokeWidth="4" />
        <path d="M57 122 Q280 70 498 122 L498 335 Q280 381 57 335Z" fill={c.intima} />
        <path d="M70 132 Q280 85 485 132 L485 321 Q280 364 70 321Z" fill={c.heartLight} />
        <path d="M81 140 Q280 100 472 140" fill="none" stroke={c.boneLight} strokeWidth="2" />
        <ellipse cx="268" cy="221" rx="62" ry="53" fill={c.adventitia} stroke={brand.navy} strokeWidth="3" />
        <ellipse cx="255" cy="208" rx="40" ry="32" fill={c.media} />
        <circle cx="275" cy="221" r="13" fill={c.lumen} />
        {Array.from({length: 12}, (_, i) => <path key={i} d={`M${90 + i * 28} 155 q14 -12 28 0`} fill="none" stroke={c.media} strokeWidth="3" />)}
        {Array.from({length: 10}, (_, i) => <circle key={i} cx={95 + (i % 5) * 83} cy={280 + Math.floor(i / 5) * 25} r="5" fill={i % 2 ? brand.yellow : brand.teal} />)}
        {(view === 'unit' || view === 'injury') && Array.from({length: 8}, (_, i) => {
          const x = 90 + i * 53;
          const y = 315 + g.leak * (100 + (i % 2) * 30);
          return <circle data-enzyme="true" key={i} cx={x} cy={y} r="6" fill={i % 2 ? brand.yellow : brand.teal} />;
        })}
        {g.leak > 0 && <path data-layer="membrane-breach" d="M165 357 l12 -13 10 19 10 -15" stroke={brand.off_white} strokeWidth={4 + g.leak * 8} fill="none" />}
      </g>
      {(view === 'function' || view === 'injury') && (
        <g data-layer="mitochondria" data-toxic={g.toxic}>
          {[135, 405].map(x => (
            <g key={x} transform={`translate(${x} 225)`}>
              <ellipse rx="37" ry="23" fill={g.toxic > 0 ? c.bloodInset : brand.teal} stroke={brand.navy} strokeWidth="2" />
              <path d="M-24 0 l8 -10 8 20 8 -20 8 20 8 -10" fill="none" stroke={c.boneLight} strokeWidth="3" />
            </g>
          ))}
        </g>
      )}
      <g data-layer="bile-canaliculus" data-block={g.bile}>
        <path d="M46 68 Q280 24 511 68" fill="none" stroke={brand.navy} strokeWidth="24" />
        <path d="M46 68 Q280 24 511 68" fill="none" stroke={brand.teal} strokeWidth="18" />
        <ProcessArrow d="M285 87 V52 M275 63 L285 52 L295 63" />
        {g.bile > 0 && <path d="M390 42 l19 19 m0 -19 l-19 19" stroke={c.bloodInset} strokeWidth={g.bile * 7} />}
      </g>
      {view === 'function' && <ProteinExportAndBileLayer flow={g.flow} exportProg={g.export} blocked={g.blockCue > 0 || g.bile > 0} />}
      {view === 'injury' && <InjuryMechanismsLayer state={state} severity={severity} emphasizeFlow={emphasizeFlow} flow={g.flow} bile={g.bile} />}
      {view === 'scar' && (
        <g data-layer="fibrous-septa" opacity={g.scar}>
          {[110, 195, 360, 445].map(x => (
            <g key={x}>
              <path d={`M${x} 94 Q${x + 30} 220 ${x} 365`} fill="none" stroke={c.boneDeep} strokeWidth="17" />
              <path d={`M${x - 3} 94 Q${x + 27} 220 ${x - 3} 365`} fill="none" stroke={c.boneLight} strokeWidth="5" />
            </g>
          ))}
        </g>
      )}
      <DiagramAnnotations labels={labels} visibleLabels={visibleLabels} />
    </svg>
  );
};
