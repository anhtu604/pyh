import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';
import {DiagramAnnotations, ProcessArrow, type DiagramLabels} from './annotations';
import {FacetedNeedle, fourTones, smoothstep} from './shade';

// Union of the joint capsule, exposed bone shafts and circular/square fluid inset.
export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 504};
export const CUE_ACTIONS = ['seed', 'grow', 'deposit'] as const;
export const urateGeometry = (state: OrganProps['state'], severity: number, frame: number, fps: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  const growth = smoothstep(Math.min(1, Math.max(0, frame / fps / 8)));
  return {level, growth, needles: Math.ceil(level * 8), length: 8 + 62 * growth * level};
};

const insetSites = [[369, 112], [425, 100], [465, 139], [355, 166], [412, 161], [474, 199], [377, 222], [429, 231]] as const;
const cartilageSites = [[105, 238], [150, 249], [198, 245], [237, 230], [110, 302], [166, 296], [220, 307]] as const;
const synovialSites = [[59, 215], [58, 274], [72, 332], [279, 252], [274, 319]] as const;
const synoviocyteSites = [
  [61, 188], [54, 222], [51, 258], [53, 294], [62, 330], [76, 364],
  [264, 192], [275, 228], [280, 265], [276, 302], [266, 338], [252, 370],
] as const;
const chondrocyteSites = [
  [104, 218], [134, 227], [166, 231], [198, 228], [228, 218],
  [106, 315], [136, 305], [166, 301], [196, 304], [226, 314],
] as const;
const capsuleTones = fourTones(c.adventitia);
const seedTones = fourTones(brand.yellow);

/** Qualitative joint section and fluid inset, not to scale. Deposits sit along
 * cartilage and within synovium; needle shape does not imply tissue puncture. */
export const UrateFluid: React.FC<OrganProps> = ({state, severity, cueProgress, visibleLabels}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = urateGeometry(state, severity, frame, fps);
  const cue = (action: string) => Math.max(0, Math.min(1, cueProgress?.[action] ?? 0));
  if (cueProgress) {
    g.needles = Math.ceil(g.level * 8 * cue('seed'));
    g.growth = smoothstep(cue('grow'));
    g.length = 8 + 62 * g.growth * g.level;
  }
  const deposits = g.level * (cueProgress ? cue('deposit') : 1);
  const driftPhase = (frame / Math.max(1, fps)) * 0.75;

  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Synovial joint section with magnified urate in fluid" data-state={state} data-severity={g.level}>
    {/* 1. Fibrous joint capsule (4 flat tones + soft shadow + collagen fibre bundles) */}
    <g data-layer="joint-capsule">
      <path d="M102 32 H226 C230 115 298 143 308 235 C322 348 248 414 235 532 H93 C90 425 32 363 32 278 C32 159 95 130 102 32Z" fill={brand.night} opacity="0.18"/>
      <path d="M98 28 H222 C226 111 294 139 304 231 C318 344 244 410 231 532 H89 C86 423 28 359 28 274 C28 155 91 126 98 28Z" fill={capsuleTones[3]}/>
      <path d="M98 28 H214 C218 111 284 140 294 231 C307 342 236 408 223 532 H89 C86 423 28 359 28 274 C28 155 91 126 98 28Z" fill={capsuleTones[1]}/>
      <path d="M98 28 H158 L154 532 H89 C86 423 28 359 28 274 C28 155 91 126 98 28Z" fill={capsuleTones[2]}/>
      <path d="M98 28 H120 C114 126 52 158 50 274 C50 356 96 418 102 532 H89 C86 423 28 359 28 274 C28 155 91 126 98 28Z" fill={capsuleTones[0]} opacity="0.75"/>
      <path d="M94 118 C54 168 38 218 38 274 C38 332 56 382 92 442 M226 118 C268 168 292 216 294 274 C294 334 268 386 228 442" fill="none" stroke={capsuleTones[0]} strokeWidth="0.85" opacity="0.65"/>
      <path d="M98 104 C62 156 44 212 44 274 C44 336 62 390 96 452 M222 104 C260 156 284 212 286 274 C286 336 260 390 224 452" fill="none" stroke={capsuleTones[3]} strokeWidth="0.9" opacity="0.7"/>
    </g>

    {/* 2. Synovial membrane (4 flat tones + villous folds + subintimal capillaries + lining nuclei) */}
    <g data-layer="synovial-membrane">
      <path d="M100 97 H220 C230 148 277 177 285 239 C298 331 235 396 225 459 H95 C84 394 46 342 46 275 C46 187 86 151 100 97Z" fill={c.synoviumDeep}/>
      <path d="M102 102 H216 C226 150 271 178 279 239 C291 328 231 392 221 453 H97 C86 390 50 340 50 275 C50 189 88 154 102 102Z" fill={c.synoviumShade}/>
      <path d="M104 108 H210 C220 154 264 181 272 240 C283 324 226 386 217 446 H100 C89 385 55 337 55 275 C55 193 91 157 104 108Z" fill={c.synoviumMid}/>
      <path d="M104 114 C92 162 60 198 60 275 C60 334 91 380 102 440 L110 434 C98 378 72 334 72 275 C72 204 98 168 110 120Z" fill={c.synoviumLight}/>
      <path d="M64 242 Q82 250 66 262 Q84 272 65 284 Q81 294 67 306 M266 244 Q248 253 264 265 Q246 275 265 287 Q249 297 262 309" fill="none" stroke={c.synoviumLight} strokeWidth="0.9" strokeLinecap="round"/>
      {[[54, 204], [50, 312], [278, 210], [280, 316]].map(([cx, cy], i) => <g key={i}>
        <ellipse cx={cx} cy={cy} rx="5.5" ry="3.8" fill={c.bloodInset} stroke={c.synoviumLight} strokeWidth="0.6"/>
        <ellipse cx={cx - 0.8} cy={cy - 0.6} rx="2.8" ry="1.8" fill={c.bloodLight}/>
      </g>)}
      {synoviocyteSites.map(([cx, cy], i) => <ellipse key={i} cx={cx} cy={cy} rx="3.2" ry="5.2"
        transform={`rotate(${i < 6 ? -12 + i * 5 : 12 - (i - 6) * 5} ${cx} ${cy})`}
        fill={c.chamber} stroke={c.synoviumLight} strokeWidth="0.6"/>)}
    </g>

    {/* 3. Synovial fluid cavity (4 flat tones + subtle contour lines) */}
    <g data-layer="synovial-fluid">
      <path d="M106 129 H213 C230 176 263 189 266 243 C279 320 222 378 213 427 H108 C97 377 65 335 65 275 C65 200 94 168 106 129Z" fill={c.fluidDeep}/>
      <path d="M110 138 H209 C225 180 256 193 259 244 C270 315 217 370 209 418 H112 C101 370 72 331 72 275 C72 204 99 173 110 138Z" fill={c.fluidShade}/>
      <path d="M114 148 H204 C219 186 248 198 251 245 C260 308 212 360 204 406 H116 C106 360 80 325 80 275 C80 209 104 180 114 148Z" fill={c.fluidMid}/>
      <ellipse cx="166" cy="268" rx="76" ry="30" fill={c.fluidLight} opacity="0.55"/>
      <path d="M84 262 Q166 276 248 260 M88 278 Q166 264 244 280" fill="none" stroke={c.cartilageLight} strokeWidth="0.75" opacity="0.45"/>
    </g>

    {/* 4. Articular bone ends (upper & lower epiphyses in 4 flat tones + cortical highlight) */}
    <g data-layer="bone-ends">
      {/* Soft shadow cast by bone ends into cavity */}
      <path d="M79 208 C96 233 229 241 257 208 L255 224 C234 261 98 266 77 224Z" fill={brand.night} opacity="0.22"/>
      {/* Upper bone end: deep right cortex -> shade -> mid -> lit left cortex */}
      <path d="M107 28 H213 L215 139 C216 165 255 178 255 202 C255 225 217 236 167 237 C115 238 77 223 77 202 C77 177 105 165 106 139Z" fill={c.boneDeep}/>
      <path d="M107 28 H203 L205 139 C206 165 244 178 244 201 C244 222 208 233 163 234 C114 235 77 221 77 202 C77 177 105 165 106 139Z" fill={c.boneShade}/>
      <path d="M107 28 H191 L193 139 C194 165 228 178 228 200 C228 219 196 229 156 230 C112 231 80 218 80 200 C80 177 106 165 107 139Z" fill={c.boneMid}/>
      <path d="M107 28 H146 L144 142 C142 168 116 180 114 202 C112 216 128 225 148 228 C108 227 80 215 80 200 C80 177 106 165 107 139Z" fill={c.boneLight}/>
      <path d="M109 30 L108 139 C107 165 80 177 80 201 C80 218 112 232 162 233" fill="none" stroke={c.crystalLight} strokeWidth="0.85" opacity="0.8"/>

      {/* Lower bone end: deep right cortex -> shade -> mid -> lit left cortex */}
      <path d="M98 532 H222 L224 396 C225 365 254 351 253 330 C252 308 213 292 166 292 C120 292 78 309 78 332 C78 355 99 368 98 396Z" fill={c.boneDeep}/>
      <path d="M98 532 H211 L213 396 C214 365 242 351 241 331 C240 310 204 295 161 295 C118 295 78 311 78 332 C78 355 99 368 98 396Z" fill={c.boneShade}/>
      <path d="M98 532 H198 L200 396 C201 366 226 352 225 332 C224 313 192 299 154 299 C116 299 81 313 81 332 C81 355 100 368 99 396Z" fill={c.boneMid}/>
      <path d="M98 532 H144 L142 394 C140 366 114 352 114 331 C114 316 130 305 150 301 C112 303 82 315 82 332 C82 355 100 368 98 396Z" fill={c.boneLight}/>
      <path d="M100 530 L100 396 C101 368 81 355 81 332 C81 313 116 297 162 297" fill="none" stroke={c.crystalLight} strokeWidth="0.85" opacity="0.8"/>
    </g>

    {/* 5. Trabecular bone architecture (spongy bone struts + marrow lacunae terminating at cortex) */}
    <g data-layer="trabecular-bone">
      <g fill={c.boneDeep} opacity="0.55">
        {[[126, 74, 9, 16], [156, 70, 10, 18], [184, 78, 9, 15], [116, 128, 10, 16], [148, 124, 12, 18], [180, 128, 10, 16], [104, 178, 12, 12], [138, 180, 14, 13], [174, 180, 14, 13], [208, 178, 11, 11],
          [106, 344, 12, 11], [140, 340, 14, 12], [176, 340, 14, 12], [208, 346, 11, 11], [118, 392, 10, 17], [150, 388, 12, 18], [182, 392, 10, 17], [122, 456, 11, 20], [154, 452, 12, 22], [186, 456, 11, 20],
        ].map(([cx, cy, rx, ry], i) => <ellipse key={i} cx={cx} cy={cy} rx={rx} ry={ry}/>)}
      </g>
      <g stroke={brand.yellow} strokeWidth="1.2" fill="none" opacity="0.62" strokeLinecap="round">
        {[0, 1, 2, 3, 4].map(i => <path key={i} d={`M${114 + i * 22} 36 C${110 + i * 22} 88 ${118 + i * 22} 138 ${96 + i * 32} 196 M${110 + i * 24} 524 C${114 + i * 22} 462 ${110 + i * 22} 404 ${96 + i * 32} 336`}/>)}
        <path d="M108 82 Q160 102 206 82 M106 136 Q160 158 212 136 M88 182 Q166 206 238 182 M90 348 Q166 324 236 348 M104 398 Q160 376 214 398 M104 458 Q160 436 214 458"/>
      </g>
    </g>

    {/* 6. Articular cartilage (4 flat zones + tidemark + chondrocyte lacunae + lamina splendens highlight) */}
    <g data-layer="cartilage">
      {/* Upper articular cartilage */}
      <path d="M77 201 C94 226 227 234 255 201 L255 219 C235 258 98 263 77 221Z" fill={c.cartilageDeep}/>
      <path d="M77 204 C94 228 227 236 255 204 L255 219 C235 257 98 262 77 220Z" fill={c.cartilageShade}/>
      <path d="M77 208 C95 232 226 239 255 208 L255 219 C235 256 98 261 77 219Z" fill={c.cartilageMid}/>
      <path d="M78 213 C96 237 225 244 254 213 L255 219 C235 256 98 261 77 219Z" fill={c.cartilageLight}/>
      <path d="M78 218 C99 257 234 252 254 216" fill="none" stroke={c.crystalLight} strokeWidth="0.9" opacity="0.85"/>
      {/* Lower articular cartilage */}
      <path d="M78 332 C99 303 222 300 253 330 L253 312 C227 278 104 277 78 313Z" fill={c.cartilageDeep}/>
      <path d="M78 329 C99 300 222 297 253 327 L253 313 C227 279 104 278 78 314Z" fill={c.cartilageShade}/>
      <path d="M78 325 C99 296 222 293 253 323 L253 314 C227 280 104 279 78 315Z" fill={c.cartilageMid}/>
      <path d="M79 320 C100 291 221 288 252 318 L253 314 C227 280 104 279 78 315Z" fill={c.cartilageLight}/>
      <path d="M79 315 C104 281 226 282 252 314" fill="none" stroke={c.crystalLight} strokeWidth="0.9" opacity="0.85"/>
      {/* Chondrocyte lacunae in upper and lower hyaline cartilage */}
      {chondrocyteSites.map(([cx, cy], i) => <g key={i}>
        <ellipse cx={cx} cy={cy} rx="5.2" ry="2.4" fill={c.cartilageDeep}/>
        <ellipse cx={cx - 0.8} cy={cy} rx="2.2" ry="1.2" fill={c.cartilageLight}/>
      </g>)}
    </g>

    {/* 7. Cartilage surface urate deposits */}
    <g data-layer="cartilage-deposits" fill={brand.off_white}>
      {cartilageSites.slice(0, deposits >= .6 ? Math.ceil((deposits - .5) * 14) : 0).map(([x, y], i) =>
        <g key={i} data-crystal="true" data-deposit-site="cartilage" transform={`translate(${x} ${y}) rotate(${i % 2 ? -8 : 8})`}>
          <FacetedNeedle halfLen={13} halfWidth={2.4}/>
        </g>)}
    </g>

    {/* 8. Synovial membrane urate deposits */}
    <g data-layer="synovial-deposits" fill={brand.off_white}>
      {synovialSites.slice(0, deposits >= .7 ? Math.ceil((deposits - .6) * 12.5) : 0).map(([x, y], i) =>
        <g key={i} data-crystal="true" data-deposit-site="synovium" transform={`translate(${x} ${y}) rotate(${70 + i * 7})`}>
          <FacetedNeedle halfLen={10} halfWidth={2.2}/>
        </g>)}
    </g>

    {/* 9. Sample connector from joint fluid cavity to square inset */}
    <g data-layer="sample-connector" fill="none">
      <circle cx="248" cy="268" r="11" fill={c.fluidDeep} opacity="0.5"/>
      <circle cx="248" cy="268" r="9" stroke={c.cartilageLight} strokeWidth="2.2"/>
      <circle cx="248" cy="268" r="4" fill={brand.teal}/>
      <path d="M256 263 L296 226 M256 273 L296 262" stroke={brand.navy} strokeWidth="3.2" strokeLinecap="round"/>
      <path d="M256 263 L296 226 M256 273 L296 262" stroke={c.cartilageLight} strokeWidth="1.4" strokeLinecap="round"/>
    </g>

    {/* 10. Square magnified fluid inset window (4 flat tones + bezel + optical ticks) */}
    <rect x="300" y="56" width="232" height="232" rx="30" fill={brand.night} opacity="0.22"/>
    <rect data-layer="sample-window" x="296" y="52" width="236" height="236" rx="30" fill={c.cartilageShade}/>
    <rect x="299" y="55" width="230" height="230" rx="28" fill={brand.teal}/>
    <rect x="303" y="59" width="222" height="222" rx="24" fill={c.fluidDeep}/>
    <rect x="309" y="65" width="210" height="210" rx="20" fill={brand.navy}/>
    <circle cx="414" cy="170" r="92" fill={c.fluidMid} opacity="0.65"/>
    <circle cx="414" cy="170" r="62" fill={c.fluidLight} opacity="0.35"/>
    <rect x="305" y="61" width="218" height="218" rx="22" fill="none" stroke={c.cartilageLight} strokeWidth="0.8" opacity="0.65"/>
    <path d="M316 170 H326 M502 170 H512 M414 72 V82 M414 258 V268" stroke={c.cartilageLight} strokeWidth="0.9" opacity="0.55" strokeLinecap="round"/>

    {/* 11. Dissolved urate solute particles */}
    <g data-layer="dissolved-urate" fill={brand.teal}>
      {Array.from({length: 32}, (_, i) => {
        const angle = i * 2.4, radius = 18 + 76 * Math.sqrt(i / 31);
        const cx = 414 + radius * Math.cos(angle) + 2.6 * Math.sin(driftPhase + i);
        const cy = 170 + radius * Math.sin(angle) + 2.6 * Math.cos(driftPhase + i);
        return <g key={i}>
          <circle r="4.2" cx={cx} cy={cy} fill={c.cartilageShade} opacity="0.45"/>
          <circle r="2.6" cx={cx} cy={cy} fill={c.cartilageLight}/>
          <circle r="1.1" cx={cx - 0.7} cy={cy - 0.7} fill={c.crystalLight}/>
        </g>;
      })}
    </g>

    {/* 12. Crystal nucleation seeds (4 flat tones of warm yellow) */}
    <g data-layer="crystal-seeds" fill={brand.yellow}>
      {insetSites.slice(0, g.needles).map(([x, y], i) => <g key={i} data-seed="true" transform={`translate(${x} ${y})`}>
        <circle r="6" cy="1" fill={brand.night} opacity="0.28"/>
        <polygon points="0,-5.5 5,-2 4,4.5 -4,4.5 -5,-2" fill={seedTones[2]} stroke={seedTones[3]} strokeWidth="0.6"/>
        <polygon points="0,-5.5 5,-2 0,1 -5,-2" fill={seedTones[1]}/>
        <polygon points="0,-4 3,-1.2 0,1.2 -3,-1.2" fill={seedTones[0]}/>
      </g>)}
    </g>

    {/* 13. Multi-faceted acicular urate crystals */}
    <g data-layer="needle-crystals" fill={brand.off_white}>
      {insetSites.slice(0, cueProgress && g.growth <= 0 ? 0 : g.needles).map(([x, y], i) => <g key={i} data-crystal="true"
        transform={`translate(${x} ${y}) rotate(${i * 37 + 20})`}>
        <FacetedNeedle halfLen={g.length / 2} halfWidth={2.9} accent/>
      </g>)}
    </g>

    <ProcessArrow d="M280 300 L310 315 L300 302 M310 315 L294 315" visible={g.level > 0}/>
    <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
  </svg>;
};

export const FOCUS_REGIONS = {"bone": {"left": 80, "top": 28, "width": 180, "height": 210}, "cartilage": {"left": 60, "top": 193, "width": 220, "height": 154}, "synovium": {"left": 28, "top": 134, "width": 285, "height": 270}, "fluid": {"left": 60, "top": 222, "width": 225, "height": 110}, "capsule": {"left": 28, "top": 28, "width": 285, "height": 504}, "crystal": {"left": 296, "top": 52, "width": 236, "height": 236}};
export const LABELS: DiagramLabels = {"bone": {"text": "Xương", "region": "bone", "x": 330, "y": 310, "width": 180, "height": 34, "anchor": [170, 170]}, "cartilage": {"text": "Sụn khớp", "region": "cartilage", "x": 330, "y": 352, "width": 180, "height": 34, "anchor": [166, 242]}, "synovium": {"text": "Màng hoạt dịch", "region": "synovium", "x": 330, "y": 394, "width": 180, "height": 34, "anchor": [278, 320]}, "fluid": {"text": "Dịch khớp", "region": "fluid", "x": 330, "y": 436, "width": 180, "height": 34, "anchor": [185, 270]}, "capsule": {"text": "Bao khớp", "region": "capsule", "x": 330, "y": 478, "width": 180, "height": 34, "anchor": [285, 360]}, "crystal": {"text": "Tinh thể urat", "region": "crystal", "x": 330, "y": 8, "width": 180, "height": 34, "anchor": [415, 155]}};
