import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';
import {DiagramAnnotations, ProcessArrow, type DiagramLabels} from './annotations';
import {FacetedNeedle, fourTones, smoothstep} from './shade';

// Tissue sample boundary contains all vessel, cell and signal motion.
export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 504};
export const CUE_ACTIONS = ['engulf', 'alarm', 'recruit'] as const;
export const signalGeometry = (state: OrganProps['state'], severity: number, frame: number, fps: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  return {
    level,
    recruited: Math.ceil(level * 6),
    phase: ((frame / fps) % 4) / 4,
    capillaryRadius: 25 + 13 * level,
    engulfment: Math.min(1, Math.max(0, frame / fps / 2)),
    migration: Math.min(1, Math.max(0, frame / fps / 7)),
  };
};

const liningY = [302.5, 295.8, 295.8, 302.2, 312, 316.5, 314.2, 304.5, 292.5, 289.7, 297.6] as const;
const stromalCells = [[96, 362, -8], [238, 368, 6], [388, 358, -5], [164, 496, 4], [428, 498, -7]] as const;
const macrophageLysosomes = [[102, 152, 5.5], [148, 128, 4.8], [182, 144, 5.2], [104, 242, 5], [168, 256, 4.6], [224, 242, 5]] as const;
const signalTones = fourTones(brand.yellow);

/** Synovial lining with subsynovial microvasculature, not to scale. Activated
 * disease presupposes priming as well as activation; crystal presence alone
 * does not imply an acute flare. Normal is a clean, resting reference. */
export const InflammationSignal: React.FC<OrganProps> = ({state, severity, cueProgress, visibleLabels}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = signalGeometry(state, severity, frame, fps);
  const cue = (action: string) => Math.max(0, Math.min(1, cueProgress?.[action] ?? 0));
  const alarm = g.level * (cueProgress ? cue('alarm') : 1);
  if (cueProgress) {
    g.engulfment = cue('engulf');
    g.migration = cue('recruit');
    g.recruited = Math.ceil(g.level * 6 * cue('recruit'));
    g.capillaryRadius = 25 + 13 * alarm;
  }
  const easedEngulf = smoothstep(g.engulfment);

  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Synovial lining, macrophage signalling and neutrophil recruitment" data-state={state} data-severity={g.level}>
    {/* 1. Synovial cavity window (4 flat tones + inner rim) */}
    <rect x="32" y="32" width="500" height="500" rx="32" fill={brand.night} opacity="0.22"/>
    <rect data-layer="sample-window" x="28" y="28" width="504" height="504" rx="32" fill={c.fluidDeep}/>
    <rect x="34" y="34" width="492" height="280" rx="26" fill={c.fluidShade}/>
    <ellipse cx="280" cy="168" rx="228" ry="118" fill={brand.navy}/>
    <ellipse cx="235" cy="162" rx="164" ry="86" fill={c.fluidMid}/>
    <path d="M48 84 Q180 66 312 88 T512 78 M44 248 Q190 232 340 254 T516 244" fill="none" stroke={c.fluidLight} strokeWidth="0.8" opacity="0.55"/>

    {/* 2. Subsynovial connective tissue (4 flat tones from intimal basement membrane to deep stroma) */}
    <g data-layer="subsynovial-tissue">
      <path d="M28 321 Q113 290 204 319 T379 315 T532 319 V500 Q532 532 500 532 H60 Q28 532 28 500Z" fill={c.chamber}/>
      <path d="M28 334 Q113 304 204 332 T379 328 T532 332 V500 Q532 532 500 532 H60 Q28 532 28 500Z" fill={c.synoviumDeep}/>
      <path d="M28 352 Q113 326 204 350 T379 346 T532 350 V488 Q410 498 280 492 T28 488Z" fill={c.adventitia} opacity="0.55"/>
      <path d="M28 321 Q113 290 204 319 T379 315 T532 319 V338 Q458 313 379 334 T204 338 T28 340Z" fill={c.synoviumShade}/>
    </g>

    {/* 3. Subsynovial collagen & elastin fibres + resident stromal fibroblasts */}
    <g data-layer="tissue-fibres">
      <path d="M44 352 Q120 330 196 354 T348 350 T516 346 M46 374 Q124 352 200 376 T352 372 T514 368 M48 492 Q132 474 218 494 T384 490 T512 488 M56 510 Q140 494 226 512 T392 508 T506 506"
        stroke={c.synoviumShade} strokeWidth="1.4" fill="none" strokeLinecap="round"/>
      <path d="M52 362 Q128 340 204 364 T356 360 T510 356 M58 501 Q136 483 214 502 T388 498 T504 496"
        stroke={c.synoviumLight} strokeWidth="0.75" fill="none" opacity="0.55" strokeLinecap="round"/>
      {stromalCells.map(([cx, cy, deg], i) => <g key={i} transform={`translate(${cx} ${cy}) rotate(${deg})`}>
        <path d="M-22 0 Q-8 -5 0 -5 Q8 -5 22 0 Q8 5 0 5 Q-8 5 -22 0Z" fill={c.synoviumMid} stroke={c.synoviumLight} strokeWidth="0.6"/>
        <ellipse rx="5.5" ry="2.4" fill={c.chamber}/>
      </g>)}
    </g>

    {/* 4. Synovial intimal membrane (4 flat tones + synoviocyte cell bodies + nuclei) */}
    <g data-layer="synovial-membrane">
      <path d="M28 298 Q113 267 204 296 T379 292 T532 296 V324 Q458 299 379 320 T204 324 T28 326Z" fill={brand.night} opacity="0.22"/>
      <path d="M28 294 Q113 263 204 292 T379 288 T532 292 V320 Q458 295 379 316 T204 320 T28 322Z" fill={c.synoviumDeep}/>
      <path d="M28 294 Q113 263 204 292 T379 288 T532 292 V314 Q458 289 379 310 T204 314 T28 316Z" fill={c.synoviumShade}/>
      <path d="M28 294 Q113 263 204 292 T379 288 T532 292 V307 Q458 282 379 303 T204 307 T28 309Z" fill={c.synoviumMid}/>
      <path d="M28 294 Q113 263 204 292 T379 288 T532 292" fill="none" stroke={c.synoviumLight} strokeWidth="1.1"/>
      <path d="M28 321 Q113 290 204 319 T379 315 T532 319" fill="none" stroke={c.chamber} strokeWidth="0.9"/>
      {liningY.map((y, i) => {
        const cx = 49 + i * 46;
        return <g key={i}>
          <ellipse cx={cx} cy={y} rx="18" ry="10.5" fill={c.synoviumMid} stroke={c.synoviumLight} strokeWidth="0.65"/>
          <ellipse cx={cx} cy={y - 2.2} rx="14" ry="5.5" fill={c.synoviumLight} opacity="0.65"/>
          <ellipse cx={cx} cy={y + 0.5} rx="10.5" ry="6" fill={c.chamber}/>
          <ellipse cx={cx - 2.5} cy={y - 1} rx="3.2" ry="1.8" fill={c.synoviumLight} opacity="0.75"/>
        </g>;
      })}
    </g>

    {/* 5. Subsynovial capillary / post-capillary venule (4 flat tones + endothelium + biconcave RBCs) */}
    <g data-layer="capillary" data-lumen-radius={g.capillaryRadius}>
      <rect x="42" y={436 - g.capillaryRadius - 10} width="476" height={2 * g.capillaryRadius + 22} rx={g.capillaryRadius + 10} fill={brand.night} opacity="0.25"/>
      <rect x="44" y={436 - g.capillaryRadius - 7} width="472" height={2 * g.capillaryRadius + 14} rx={g.capillaryRadius + 7} fill={alarm > 0 ? c.bloodInset : c.adventitia} stroke={c.synoviumLight} strokeWidth="0.75"/>
      <rect x="48" y={436 - g.capillaryRadius - 3} width="464" height={2 * g.capillaryRadius + 6} rx={g.capillaryRadius + 3} fill={alarm > 0 ? c.heartDeep : c.synoviumShade}/>
      <rect x="50" y={436 - g.capillaryRadius} width="460" height={2 * g.capillaryRadius} rx={g.capillaryRadius} fill={alarm > 0 ? c.blood : c.heartDeep}/>
      <rect x="58" y={436 - g.capillaryRadius * 0.55} width="444" height={g.capillaryRadius * 1.1} rx={g.capillaryRadius * 0.55} fill={alarm > 0 ? c.heartMid : c.bloodInset} opacity="0.65"/>
      {/* Intraluminal biconcave red blood cells */}
      {[0, 1, 2, 3, 4, 5, 6].map(i => <g key={i} transform={`translate(${79 + ((i * 60 + frame / fps * 9) % 395)} ${438 + (i % 2 ? 5 : -4)}) rotate(${(i % 3 - 1) * 8})`}>
        <ellipse rx="14" ry="8.8" cy="1.2" fill={brand.night} opacity="0.22"/>
        <ellipse rx="13.5" ry="8.2" fill={c.bloodInset}/>
        <ellipse rx="12" ry="7" cy="-0.6" fill={c.bloodLight}/>
        <ellipse rx="6" ry="3.2" fill={c.bloodInset}/>
        <path d="M-8 -3.5 Q0 -6 8 -3.5" fill="none" stroke={c.crystalLight} strokeWidth="0.65" opacity="0.65"/>
      </g>)}
      {/* Upper and lower endothelial cells & nuclei */}
      {[0, 1, 2, 3, 4, 5].map(i => {
        const cx = 92 + i * 73;
        const topY = 434 - g.capillaryRadius;
        const botY = 438 + g.capillaryRadius;
        return <g key={i}>
          <path d={`M${cx - 28} ${topY} Q${cx} ${topY - 3} ${cx + 28} ${topY}`} fill="none" stroke={c.synoviumLight} strokeWidth="0.8"/>
          <ellipse cx={cx} cy={topY} rx="12" ry="3.4" fill={c.chamber} stroke={c.synoviumLight} strokeWidth="0.55"/>
          <ellipse cx={cx + 18} cy={botY} rx="11" ry="3.2" fill={c.chamber} stroke={c.synoviumLight} strokeWidth="0.55"/>
        </g>;
      })}
    </g>

    {/* 6. Resident synovial macrophage (4 flat tones + reniform nucleus + organelles + NLRP3 inflammasome) */}
    <g data-layer="resident-cell">
      <path d="M82 212 C74 171 98 123 139 115 C168 98 207 111 221 132 C234 143 254 125 267 138 C284 159 257 180 253 193 C276 225 249 264 221 276 C189 295 154 275 132 285 C98 278 76 247 82 212Z"
        fill={brand.night} opacity="0.26"/>
      <path data-phagocytosis={g.level > 0 && (!cueProgress || g.engulfment > 0) ? 'true' : undefined}
        d="M78 206 C70 165 94 117 135 109 C164 92 203 105 217 126 C230 137 250 119 263 132 C280 153 253 174 249 187 C272 219 245 258 217 270 C185 289 150 269 128 279 C94 272 72 241 78 206Z"
        fill={c.cartilageDeep}/>
      <path d="M82 204 C75 166 97 121 136 113 C163 97 200 109 214 129 C226 139 245 123 257 135 C272 154 248 173 244 186 C265 216 240 252 214 263 C184 281 151 263 130 272 C98 265 77 236 82 204Z"
        fill={c.vesselDeep}/>
      <path d="M88 200 C82 166 101 126 136 118 C161 104 195 115 208 133 C218 142 235 129 245 139 C257 155 238 172 234 184 C252 210 230 242 206 252 C179 268 150 252 131 260 C102 254 83 228 88 200Z"
        fill={brand.teal}/>
      <path d="M94 192 C90 163 106 130 136 123 C158 111 186 120 198 136 C174 134 146 146 132 168 C118 190 114 218 124 242 C102 234 90 214 94 192Z"
        fill={c.cartilageLight} opacity="0.55"/>
      <path d="M82 204 C75 166 97 121 136 113 C163 97 200 109 214 129" fill="none" stroke={c.cartilageLight} strokeWidth="0.9" opacity="0.85"/>
      {/* Reniform macrophage nucleus (3 flat tones + nucleolus) */}
      <path d="M114 179 C96 196 108 232 131 242 C152 250 184 232 174 216 C150 222 147 200 153 187 C146 172 126 170 114 179Z" fill={brand.night}/>
      <path d="M116 181 C100 196 111 229 132 239 C151 246 180 230 171 216 C148 221 146 201 151 189 C145 175 127 173 116 181Z" fill={brand.navy}/>
      <path d="M120 185 C108 197 116 222 132 230 C142 234 156 228 156 220 C140 221 136 204 141 191 C136 182 126 180 120 185Z" fill={c.fluidLight}/>
      <circle cx="131" cy="208" r="5.5" fill={c.cartilageShade} opacity="0.75"/>
      <path d="M108 168 Q128 158 148 166 M112 248 Q138 258 164 248" fill="none" stroke={c.cartilageLight} strokeWidth="0.75" opacity="0.6"/>
      {/* Intracellular lysosomes / endosomes */}
      {macrophageLysosomes.map(([lx, ly, lr], i) => <g key={i}>
        <circle cx={lx} cy={ly} r={lr} fill={c.fluidDeep} stroke={c.cartilageLight} strokeWidth="0.55"/>
        <circle cx={lx - 1.2} cy={ly - 1.2} r={lr * 0.42} fill={c.cartilageMid}/>
      </g>)}
      {/* NLRP3 inflammasome wheel complex */}
      <g data-layer="inflammasome">
        {alarm > 0 && <g data-activation="true" opacity={.55 + .45 * alarm}>
          <circle cx="206" cy="201" r={25 + 2.5 * Math.sin(frame / fps * 2)} fill={brand.night} opacity="0.35"/>
          <circle cx="206" cy="201" r={22 + 2.5 * Math.sin(frame / fps * 2)} fill="none" stroke={signalTones[2]} strokeWidth="3.2"/>
          <circle cx="206" cy="201" r={17 + 1.5 * Math.sin(frame / fps * 2)} fill="none" stroke={signalTones[0]} strokeWidth="0.9" strokeDasharray="3 2"/>
          {[0, 1, 2, 3, 4, 5].map(i => {
            const ang = i * Math.PI / 3 + frame / fps * 0.35;
            const sx = 206 + 13 * Math.cos(ang), sy = 201 + 13 * Math.sin(ang);
            return <g key={i}>
              <path d={`M206 201 L${sx} ${sy}`} stroke={signalTones[1]} strokeWidth="1.2"/>
              <circle cx={sx} cy={sy} r="4.2" fill={signalTones[2]} stroke={signalTones[0]} strokeWidth="0.6"/>
              <circle cx={sx - 0.8} cy={sy - 0.8} r="1.8" fill={signalTones[0]}/>
            </g>;
          })}
          <circle cx="206" cy="201" r="5.5" fill={signalTones[1]} stroke={signalTones[0]} strokeWidth="0.8"/>
          <circle cx="204.5" cy="199.5" r="2" fill={c.crystalLight}/>
        </g>}
      </g>
    </g>

    {/* 7. Engulfed urate crystal inside phagolysosome */}
    <g data-layer="crystal-cue" fill={brand.off_white}>
      {g.level > 0 && (!cueProgress || g.engulfment > 0) && <g transform={`translate(${267 - 37 * easedEngulf} ${132 + 22 * easedEngulf}) rotate(-35)`}>
        <ellipse rx="33" ry="13.5" fill={c.fluidDeep} stroke={c.cartilageLight} strokeWidth="0.75"/>
        <ellipse rx="29" ry="10.5" fill={c.vesselDeep}/>
        <ellipse rx="24" ry="7.5" fill={c.fluidMid}/>
        <g data-crystal="true">
          <FacetedNeedle halfLen={25} halfWidth={3.2} accent/>
        </g>
      </g>}
    </g>

    {/* 8. Secreted IL-1β alarm signal cascade */}
    <g data-layer="alarm-signal" fill={brand.yellow}>
      {alarm > 0 && <>
        <path d="M248 206 Q298 248 344 334 M262 196 Q322 242 378 338" fill="none" stroke={signalTones[1]} strokeWidth="0.8" strokeDasharray="3 3" opacity="0.5"/>
        {Array.from({length: Math.ceil(alarm * 7)}, (_, i) => {
          const t = (g.phase + i / 7) % 1;
          const sx = 264 + t * 122;
          const sy = 210 + t * 155 + 14 * Math.sin(i * 2);
          const r = 4 + g.level * 2;
          return <g key={i} opacity={1 - .52 * t}>
            <circle cx={sx} cy={sy} r={r + 3.2} fill={signalTones[2]} opacity="0.35"/>
            <circle data-signal="true" cx={sx} cy={sy} r={r} fill={brand.yellow} stroke={signalTones[0]} strokeWidth="0.6"/>
            <circle cx={sx - r * 0.3} cy={sy - r * 0.3} r={r * 0.38} fill={c.crystalLight}/>
          </g>;
        })}
      </>}
    </g>

    {/* 9. Recruited neutrophils undergoing transendothelial migration */}
    <g data-layer="recruited-cells">
      {Array.from({length: g.recruited}, (_, i) => {
        // Staggered, one-way transit: lumen -> endothelium -> lining -> joint fluid.
        const t = Math.max(0, Math.min(1, g.migration * 1.5 - i * .13));
        const x = 99 + i * 70 + (260 - (99 + i * 70)) * t * .35;
        const y = 431 - (183 + (i % 3) * 27) * t;
        const rx = 19 - 3.5 * Math.sin(t * Math.PI);
        const ry = 19 + 3 * Math.sin(t * Math.PI);
        return <g key={i} data-neutrophil="true" data-migration="transendothelial" transform={`translate(${x} ${y})`}>
          <ellipse rx={rx + 1.5} ry={ry + 1.5} cy="2" fill={brand.night} opacity="0.24"/>
          <ellipse rx={rx} ry={ry} fill={c.synoviumShade} stroke={brand.off_white} strokeWidth="1.2"/>
          <ellipse rx={rx * 0.88} ry={ry * 0.88} cy="-1" fill={c.heartLight}/>
          <ellipse rx={rx * 0.62} ry={ry * 0.54} cx="-2" cy="-4" fill={c.synoviumLight} opacity="0.7"/>
          {/* Cytoplasmic granules */}
          {[[-10, 4], [10, 5], [0, -11], [-6, -9], [7, -8]].map(([gx, gy], k) =>
            <circle key={k} cx={gx} cy={gy} r="1.4" fill={c.synoviumDeep} opacity="0.65"/>)}
          <g data-layer="multilobed-nuclei" fill={c.chamber}>
            <path d="M-8 -5 L2 6 L8 -5" fill="none" stroke={c.chamber} strokeWidth="2.4"/>
            {[[-8, -5], [0, 6], [8, -5]].map(([nx, ny], j) => <ellipse key={j} data-nucleus-lobe="true" cx={nx} cy={ny} rx="5" ry="6" stroke={c.synoviumLight} strokeWidth="0.5"/>)}
          </g>
        </g>;
      })}
    </g>

    <ProcessArrow d="M270 222 L318 270 L314 254 M318 270 L302 266" visible={alarm > 0}/>
    <ProcessArrow d="M445 403 L445 354 L435 367 M445 354 L455 367" visible={g.recruited > 0}/>
    <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
  </svg>;
};

export const FOCUS_REGIONS = {"macrophage": {"left": 64, "top": 86, "width": 220, "height": 205}, "nlrp3": {"left": 174, "top": 171, "width": 66, "height": 66}, "il1b": {"left": 252, "top": 188, "width": 150, "height": 165}, "vessel": {"left": 44, "top": 390, "width": 472, "height": 100}, "neutrophil": {"left": 128, "top": 215, "width": 330, "height": 230}, "synovium": {"left": 28, "top": 263, "width": 504, "height": 70}};
export const LABELS: DiagramLabels = {"macrophage": {"text": "Đại thực bào", "region": "macrophage", "x": 34, "y": 36, "width": 180, "height": 34, "anchor": [120, 135]}, "nlrp3": {"text": "NLRP3", "region": "nlrp3", "x": 346, "y": 82, "width": 172, "height": 34, "anchor": [206, 201]}, "il1b": {"text": "IL-1β", "region": "il1b", "x": 346, "y": 138, "width": 172, "height": 34, "anchor": [301, 260]}, "neutrophil": {"text": "BC trung tính", "region": "neutrophil", "x": 346, "y": 194, "width": 172, "height": 34, "anchor": [334, 308]}, "vessel": {"text": "Mạch máu", "region": "vessel", "x": 346, "y": 492, "width": 172, "height": 34, "anchor": [416, 435]}};
