import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';
import {DiagramAnnotations, type DiagramLabels} from './annotations';
import {fourTones, mixHex, smoothstep} from './shade';

export const CONTENT_BOX = {left: 26, top: 44, width: 508, height: 472};
export const CUE_ACTIONS = ['swell'] as const;
export const FOCUS_REGIONS = {
  foot: {left: 30, top: 48, width: 500, height: 464},
  mtp1: {left: 300, top: 326, width: 190, height: 170},
};
export const LABELS: DiagramLabels = {
  mtp1: {text: 'Khớp MTP1', region: 'mtp1', x: 306, y: 72, width: 206, height: 36, anchor: [402, 405]},
  bone: {text: 'Xương bàn chân', region: 'foot', x: 42, y: 72, width: 218, height: 36, anchor: [258, 349]},
};

const normalSkin = fourTones('#E8DFC8');
const heelLobules = [[78, 458, 12, 6], [104, 468, 14, 6.5], [134, 472, 15, 6.5], [164, 470, 13, 6], [358, 444, 12, 5.5], [386, 446, 13, 5.5], [416, 444, 12, 5.5]] as const;

/** Example anatomic location only; not a diagnostic image or a claim that every flare affects MTP1. */
export const GoutFootOverview: React.FC<OrganProps> = ({state, severity, cueProgress, visibleLabels}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const rawLevel = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity)) * (cueProgress ? cueProgress.swell ?? 0 : 1);
  const level = smoothstep(rawLevel);
  const pulse = 0.6 + 0.15 * Math.sin(frame / Math.max(1, fps) * 2);
  const skinBase = level > 0 ? mixHex('#E8DFC8', c.intima, 0.45 * level) : normalSkin[1];
  const skinShade = level > 0 ? mixHex(normalSkin[2], c.media, 0.45 * level) : normalSkin[2];
  const skinDeep = level > 0 ? mixHex(normalSkin[3], c.adventitia, 0.5 * level) : normalSkin[3];

  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Schematic foot with first metatarsophalangeal joint highlighted" data-state={state}>
    {/* 1. Foot & ankle soft-tissue envelope (4 flat tones + ground shadow + plantar fat pad + tendons) */}
    <g data-layer="foot-silhouette">
      <ellipse cx="276" cy="502" rx="236" ry="12" fill={brand.night} opacity="0.16"/>
      {/* Outer deep contour */}
      <path d="M91 48 H214 L220 236 Q231 285 306 318 L454 355 Q493 356 514 383 Q528 402 519 429 Q506 448 477 450 L207 492 Q158 508 100 492 Q44 476 34 432 Q30 398 52 364 L84 294Z"
        fill={skinDeep} stroke={c.adventitia} strokeWidth="2.5"/>
      {/* Mid-shade contour */}
      <path d="M95 52 H210 L216 236 Q227 285 304 318 L452 356 Q489 357 509 383 Q522 401 513 426 Q501 443 474 445 L206 485 Q158 500 102 485 Q49 470 40 428 Q36 396 57 364 L88 294Z"
        fill={skinShade}/>
      {/* Main soft-tissue body */}
      <path d="M100 54 H204 L210 236 Q221 286 300 320 L448 358 Q484 359 503 383 Q514 399 506 421 Q495 436 470 438 L206 475 Q158 489 105 475 Q56 461 48 422 Q44 394 64 364 L94 294Z"
        fill={skinBase}/>
      {/* Dorsal & anterior tibial lit surface */}
      <path d="M138 56 H200 L206 236 Q217 286 296 320 L444 358 Q478 360 496 382 Q472 374 436 368 L288 334 Q208 298 194 238 L188 56Z"
        fill={normalSkin[0]} opacity="0.8"/>
      {/* Plantar fibrofatty heel and forefoot pad lobules */}
      {heelLobules.map(([cx, cy, rx, ry], i) =>
        <ellipse key={i} cx={cx} cy={cy} rx={rx} ry={ry} fill={skinDeep} opacity="0.42" stroke={normalSkin[0]} strokeWidth="0.5"/>)}
      {/* Plantar aponeurosis (fascia) band from calcaneal tubercle to forefoot */}
      <path d="M142 452 Q256 446 382 432 M148 456 Q258 450 378 436" fill="none" stroke={normalSkin[0]} strokeWidth="1.1" opacity="0.7"/>
      {/* Extensor hallucis longus tendon & dorsal venous arch */}
      <path d="M192 72 L198 242 Q208 286 282 322 L478 386" fill="none" stroke={normalSkin[0]} strokeWidth="1.6" opacity="0.85"/>
      <path d="M188 238 L216 248 M194 256 L224 264" fill="none" stroke={c.adventitia} strokeWidth="1.2" opacity="0.65"/>
      {/* Hallux nail plate */}
      <path d="M484 378 Q502 380 509 392 Q496 396 480 390Z" fill={c.boneLight} stroke={c.adventitia} strokeWidth="0.7"/>
    </g>

    {/* 2. Articulated foot & ankle skeleton (drawn back-to-front, 4 flat tones per bone) */}
    <g data-layer="foot-bones">
      {/* Background lateral rays (Fibula, Cuboid, Lateral/Intermediate Cuneiforms, Metatarsals II–IV & lesser toes) */}
      <g fill={c.boneDeep} stroke={c.adventitia} strokeWidth="0.85" opacity="0.88">
        {/* Distal Fibula behind Tibia */}
        <path d="M98 68 H122 L126 276 Q126 300 110 306 Q96 302 96 278Z" fill={c.boneShade}/>
        {/* Cuboid & lateral cuneiforms */}
        <path d="M214 358 L266 350 L272 382 L218 390Z"/>
        <path d="M254 316 L296 322 L292 352 L250 346Z" fill={c.boneShade}/>
        {/* Metatarsals II, III, IV */}
        <path d="M286 330 L388 358 Q398 361 396 372 Q394 381 382 379 L282 350Z" fill={c.boneShade}/>
        <path d="M278 344 L380 370 Q390 373 388 382 Q386 390 374 388 L274 362Z"/>
        <path d="M268 358 L368 382 Q376 385 374 393 Q372 400 362 398 L264 374Z"/>
        {/* Lesser toe phalanges */}
        <path d="M402 362 L444 370 Q452 372 450 380 Q448 386 438 385 L400 377Z" fill={c.boneShade}/>
        <path d="M394 374 L434 382 Q442 384 440 391 Q438 397 428 395 L392 388Z"/>
      </g>

      {/* Distal Tibia (4 flat tones + plafond cartilage + trabeculae) */}
      <g>
        <path d="M112 64 H184 L190 252 Q202 280 184 294 Q152 284 118 294 Q98 282 108 252Z" fill={c.boneDeep} stroke={c.adventitia} strokeWidth="1.1"/>
        <path d="M115 64 H178 L184 252 Q194 276 178 289 Q150 280 120 289 Q104 278 112 252Z" fill={c.boneShade}/>
        <path d="M120 64 H170 L175 250 Q183 272 170 283 Q148 275 124 283 Q111 273 117 250Z" fill={c.boneMid}/>
        <path d="M148 64 H168 L172 248 Q178 266 168 276 L152 274Z" fill={c.boneLight}/>
        <path d="M116 291 Q150 281 184 291" fill="none" stroke={c.cartilageMid} strokeWidth="3" strokeLinecap="round"/>
        <path d="M126 196 L124 274 M142 192 L142 272 M158 192 L160 272 M172 198 L176 274 M118 238 Q150 248 180 238 M114 264 Q150 274 184 264"
          fill="none" stroke={c.boneDeep} strokeWidth="0.75" opacity="0.65"/>
      </g>

      {/* Calcaneus (heel bone in 4 flat tones + arcuate trabecular lines) */}
      <g>
        <path d="M56 388 Q48 352 84 342 L198 346 Q220 350 222 376 L218 418 Q214 440 186 446 L104 456 Q62 452 56 414Z"
          fill={c.boneDeep} stroke={c.adventitia} strokeWidth="1.1"/>
        <path d="M60 388 Q53 356 86 346 L194 350 Q214 354 216 376 L212 414 Q208 434 182 440 L106 449 Q67 445 60 412Z" fill={c.boneShade}/>
        <path d="M66 388 Q60 360 90 352 L188 355 Q206 359 208 378 L204 410 Q200 427 176 432 L108 440 Q74 436 66 408Z" fill={c.boneMid}/>
        <path d="M76 376 Q82 358 108 356 L182 358 Q198 362 198 376 Q152 384 102 388 Q80 388 76 376Z" fill={c.boneLight}/>
        <path d="M72 420 Q128 386 202 396 M78 432 Q136 402 204 412 M96 362 Q132 398 118 440 M142 360 Q164 396 154 436"
          fill="none" stroke={c.boneDeep} strokeWidth="0.75" opacity="0.65"/>
      </g>

      {/* Talus (trochlear dome, neck, and rounded head in 4 flat tones) */}
      <g>
        <path d="M114 302 Q148 282 184 298 L226 310 Q244 316 242 338 Q238 358 216 360 L126 354 Q104 346 106 322Z"
          fill={c.boneDeep} stroke={c.adventitia} strokeWidth="1.1"/>
        <path d="M118 304 Q148 286 182 300 L222 312 Q238 318 236 336 Q232 353 212 355 L128 349 Q110 342 112 322Z" fill={c.boneShade}/>
        <path d="M122 307 Q148 291 180 304 L218 315 Q231 320 229 335 Q226 348 208 350 L132 344 Q116 338 118 322Z" fill={c.boneMid}/>
        <path d="M126 309 Q150 295 178 306 L212 316 Q222 320 220 330 Q176 326 128 324Z" fill={c.boneLight}/>
        <path d="M238 314 Q246 334 234 354" fill="none" stroke={c.cartilageMid} strokeWidth="2.4" strokeLinecap="round"/>
      </g>

      {/* Navicular & Medial Cuneiform (4 flat tones + articular cartilage lines) */}
      <g>
        {/* Navicular */}
        <path d="M238 310 Q258 306 266 318 L262 358 Q252 368 234 362 Q244 336 238 310Z"
          fill={c.boneDeep} stroke={c.adventitia} strokeWidth="1"/>
        <path d="M241 313 Q256 310 262 320 L259 354 Q250 362 238 357 Q246 336 241 313Z" fill={c.boneMid}/>
        <path d="M243 315 Q254 313 259 321 L257 336 L244 334Z" fill={c.boneLight}/>
        {/* Medial Cuneiform */}
        <path d="M266 320 L304 330 Q312 336 308 372 Q302 384 262 374 L266 320Z"
          fill={c.boneDeep} stroke={c.adventitia} strokeWidth="1"/>
        <path d="M269 324 L300 332 Q307 338 303 368 Q298 378 266 370Z" fill={c.boneShade}/>
        <path d="M272 327 L297 334 Q302 339 299 362 L270 356Z" fill={c.boneMid}/>
        <path d="M274 329 L295 335 L293 348 L272 342Z" fill={c.boneLight}/>
      </g>

      {/* First Metatarsal (MT1) + Plantar Sesamoids + Articular Cartilage Cap */}
      <g>
        {/* Medial & lateral plantar sesamoids under MT1 head */}
        <ellipse cx="368" cy="428" rx="10" ry="5.5" fill={c.boneDeep} stroke={c.adventitia} strokeWidth="0.8"/>
        <ellipse cx="368" cy="427" rx="7.5" ry="3.8" fill={c.boneMid}/>
        <ellipse cx="382" cy="431" rx="10.5" ry="5.8" fill={c.boneShade} stroke={c.adventitia} strokeWidth="0.8"/>
        <ellipse cx="382" cy="430" rx="8" ry="4" fill={c.boneLight}/>
        {/* MT1 bone shaft & head in 4 flat tones */}
        <path d="M308 334 C326 340 350 358 376 372 C392 380 398 394 395 410 C392 424 376 428 360 422 C338 412 320 396 304 384 C298 376 300 346 308 334Z"
          fill={c.boneDeep} stroke={c.adventitia} strokeWidth="1.15"/>
        <path d="M310 337 C327 343 350 360 374 374 C389 381 394 394 391 408 C388 420 374 424 360 418 C338 408 321 393 306 381 C301 373 303 348 310 337Z"
          fill={c.boneShade}/>
        <path d="M313 340 C329 346 350 362 372 376 C385 383 390 394 387 406 C384 416 372 419 360 414 C339 404 322 390 309 378 C305 370 307 350 313 340Z"
          fill={c.boneMid}/>
        <path d="M316 342 C332 348 352 364 372 377 C382 383 386 391 384 399 C362 392 336 376 312 358Z"
          fill={c.boneLight}/>
        {/* Cancellous trabeculae in MT1 base and head */}
        <path d="M314 348 L326 378 M322 346 L312 374 M366 382 Q380 396 370 416 M358 390 Q376 394 386 404"
          fill="none" stroke={c.boneDeep} strokeWidth="0.75" opacity="0.65"/>
        {/* Hyaline articular cartilage cap on MT1 head */}
        <path d="M388 380 C399 390 400 408 389 420 C395 408 394 392 385 382Z" fill={c.cartilageShade}/>
        <path d="M390 382 C399 391 400 407 390 418" fill="none" stroke={c.cartilageLight} strokeWidth="2.4" strokeLinecap="round"/>
      </g>

      {/* Hallux Proximal & Distal Phalanges (4 flat tones + articular base cartilage) */}
      <g>
        {/* Proximal Phalanx */}
        <path d="M408 384 C418 382 436 386 452 390 C462 392 466 400 464 410 C462 420 454 424 444 422 C430 418 416 418 406 420 C401 412 402 392 408 384Z"
          fill={c.boneDeep} stroke={c.adventitia} strokeWidth="1.1"/>
        <path d="M410 386 C419 385 436 388 450 392 C459 394 462 401 460 409 C458 417 451 420 442 418 C429 415 416 415 408 417 C404 410 405 393 410 386Z"
          fill={c.boneShade}/>
        <path d="M412 388 C421 387 436 390 448 394 C456 396 458 401 457 408 C455 414 449 416 441 415 C429 412 417 412 410 413 C407 407 408 394 412 388Z"
          fill={c.boneMid}/>
        <path d="M414 389 C424 389 438 392 448 395 C453 397 455 400 454 404 C438 402 424 399 411 396Z"
          fill={c.boneLight}/>
        {/* Articular cartilage on proximal phalanx base facing MTP1 cleft */}
        <path d="M406 386 C401 396 401 410 406 419" fill="none" stroke={c.cartilageLight} strokeWidth="2.4" strokeLinecap="round"/>

        {/* Distal Phalanx */}
        <path d="M466 392 L494 396 Q506 400 504 412 Q500 422 488 420 L464 418 Q460 406 466 392Z"
          fill={c.boneDeep} stroke={c.adventitia} strokeWidth="1"/>
        <path d="M468 395 L492 398 Q501 401 499 411 Q496 418 486 417 L466 415Z" fill={c.boneMid}/>
        <path d="M470 396 L490 399 Q496 401 495 406 L468 404Z" fill={c.boneLight}/>
      </g>
    </g>

    {/* 3. First metatarsophalangeal (MTP1) joint capsule & target highlight */}
    <g>
      <circle cx="399" cy="404" r={30 + level * 8} fill={level > 0 ? c.bloodInset : c.fluidDeep} fillOpacity={level > 0 ? 0.22 : 0.14}/>
      {level > 0 && <g fill={c.crystalLight} opacity="0.9">
        <path d="M393 388 L398 386 L395 392Z M395 398 L401 397 L397 403Z M394 409 L400 408 L396 414Z"/>
      </g>}
      <circle data-layer="mtp1-highlight" cx="399" cy="404" r={43 + level * 10}
        fill={level > 0 ? c.blood : 'none'} fillOpacity={level > 0 ? .2 : 1}
        stroke={level > 0 ? c.blood : brand.teal} strokeWidth="3.5"/>
      <circle cx="399" cy="404" r={36 + level * 8} fill="none"
        stroke={level > 0 ? c.bloodLight : c.cartilageLight} strokeWidth="0.9" strokeDasharray="4 3"/>
    </g>

    {/* 4. Acute inflammatory halo & warmth waves (only when swell > 0 in disease) */}
    {rawLevel > 0 && <g data-layer="inflammatory-halo" fill="none" stroke={c.blood} strokeWidth="3" opacity={pulse}>
      <circle cx="399" cy="404" r={56 + level * 6} stroke={c.bloodLight} strokeWidth="1.4"/>
      <circle cx="399" cy="404" r={64 + level * 8} stroke={c.blood} strokeWidth="2.5"/>
      <circle cx="399" cy="404" r={72 + level * 10} stroke={c.bloodInset} strokeWidth="1" strokeDasharray="6 4"/>
      <path d="M374 327 Q365 312 376 299 M401 323 Q392 306 403 290 M428 329 Q419 313 430 300" strokeLinecap="round"/>
    </g>}

    <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
  </svg>;
};
