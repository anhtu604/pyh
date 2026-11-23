import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {ENTITY_COLORS} from '../anatomy/entityColors';
import {brand} from '../anatomy/palette';
import type {AnatomySubject} from '../anatomy/registry';
import {FONT_FAMILY} from '../fonts';
import {hexToRgba} from '../style/pyhStyle';
import {asset, IMAGES, type ImageId} from './liverEnzymeLeak';

export const SCIENTIFIC_HEPATIC_SUBJECTS = [
  'liver_organ',
  'liver_lobule',
  'hepatocyte_sinusoid_unit',
  'alt_ast_tissue_distribution',
  'hepatic_synthesis_and_bile',
  'hepatic_fibrosis_section',
  'hepatic_toxic_injury',
] as const;

export type ScientificHepaticSubject = (typeof SCIENTIFIC_HEPATIC_SUBJECTS)[number];

const HEPATIC_SET: ReadonlySet<string> = new Set(SCIENTIFIC_HEPATIC_SUBJECTS);
const CELLULAR_HEPATIC_SET: ReadonlySet<string> = new Set([
  'hepatocyte_sinusoid_unit',
  'hepatic_toxic_injury',
  'hepatic_synthesis_and_bile',
  'hepatic_fibrosis_section',
]);

export const isScientificHepaticSubject = (subject: AnatomySubject | string): subject is ScientificHepaticSubject =>
  HEPATIC_SET.has(subject);

export const scientificAssetSrc = (id: ImageId): string => staticFile(asset(IMAGES[id].file));

export type ScientificHepaticArtworkProps = {
  subject: ScientificHepaticSubject;
  state: 'normal' | 'diseased';
  severity: number;
  mode?: 'single' | 'comparison' | 'timelapse';
  cueProgress?: Record<string, number>;
  lightBackground?: boolean;
  compact?: boolean;
  durationFrames?: number;
};

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));

const EnzymeParticle: React.FC<{cx: number; cy: number; leaked?: boolean; kind?: 'ALT' | 'AST'; r?: number}> = ({
  cx,
  cy,
  leaked = false,
  kind,
  r = 9.5,
}) => {
  const ring = kind === 'ALT'
    ? ENTITY_COLORS.blood_flow.hex
    : ENTITY_COLORS.warning_threshold.hex;
  return (
    <g data-enzyme={kind ?? 'true'} data-enzyme-leaked={leaked ? 'true' : 'false'}>
      {leaked || kind ? (
        <circle cx={cx} cy={cy} r={r + 5} fill={brand.off_white} fillOpacity={0.85} stroke={ring} strokeWidth={2.8} />
      ) : null}
      <circle cx={cx} cy={cy} r={r} fill={ENTITY_COLORS.enzyme_marker.hex} stroke={brand.off_white} strokeWidth={1.8} />
    </g>
  );
};

const SingleHepaticArtwork: React.FC<{
  subject: ScientificHepaticSubject;
  state: 'normal' | 'diseased';
  severity: number;
  cueProgress?: Record<string, number>;
  lightBackground: boolean;
  compact: boolean;
  frame: number;
  fps: number;
}> = ({subject, state, severity, cueProgress, lightBackground, compact, frame, fps}) => {
  const level = state === 'normal' ? 0 : clamp01(severity);
  const ink = lightBackground ? brand.navy : brand.off_white;
  const flowPhase = ((frame / Math.max(1, fps)) * 36) % 100;

  const cue = (name: string) => clamp01(cueProgress?.[name] ?? (level > 0 ? level : 0));
  const leakActive = state === 'diseased' && (cueProgress ? cue('leak') > 0 : level > 0);
  const leakProgress = state === 'diseased' ? (cueProgress ? cue('leak') : level) : 0;
  const toxicProgress = state === 'diseased' ? (cueProgress ? cue('toxic') : level) : 0;
  const blockProgress = state === 'diseased' ? (cueProgress ? cue('block') : level) : 0;
  const scarProgress = subject === 'hepatic_fibrosis_section' && state === 'diseased'
    ? (cueProgress ? Math.max(0.4, cue('scar')) : Math.max(0.4, level))
    : 0;

  // 1. Liver Organ
  if (subject === 'liver_organ') {
    return (
      <div
        data-scientific-artwork={subject}
        data-state={state}
        data-severity={level}
        style={{position: 'relative', width: '100%', height: '100%'}}
      >
        <div
          style={{
            position: 'absolute',
            left: '9%',
            top: '14%',
            width: '82%',
            height: '66%',
            borderRadius: 28,
            backgroundColor: level > 0
              ? hexToRgba(ENTITY_COLORS.tissue_injured.hex, 0.14)
              : hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.10),
            border: `2px solid ${level > 0 ? ENTITY_COLORS.tissue_injured.hex : hexToRgba(brand.teal, 0.36)}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '6%',
            boxSizing: 'border-box',
          }}
        >
          <Img
            src={scientificAssetSrc('liver')}
            data-medanim-image="liver"
            style={{width: '92%', height: '92%', objectFit: 'contain'}}
          />
        </div>
        <svg viewBox="0 0 560 560" width="100%" height="100%" style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
          {level > 0 ? (
            <circle cx="205" cy="245" r={36 + level * 22} fill={hexToRgba(ENTITY_COLORS.tissue_injured.hex, 0.24)} stroke={ENTITY_COLORS.warning_threshold.hex} strokeWidth="3" strokeDasharray="8 6" />
          ) : null}
        </svg>
      </div>
    );
  }

  // 2. Liver Lobule
  if (subject === 'liver_lobule') {
    return (
      <div
        data-scientific-artwork={subject}
        data-state={state}
        data-severity={level}
        style={{position: 'relative', width: '100%', height: '100%'}}
      >
        <div
          style={{
            position: 'absolute',
            left: '6%',
            top: '6%',
            width: '68%',
            height: '86%',
            borderRadius: 22,
            backgroundColor: brand.off_white,
            border: `2px solid ${hexToRgba(brand.navy, 0.18)}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2%',
            boxSizing: 'border-box',
          }}
        >
          <Img
            src={scientificAssetSrc('lobule')}
            data-medanim-image="lobule"
            style={{width: '100%', height: '100%', objectFit: 'contain'}}
          />
        </div>
        <div
          style={{
            position: 'absolute',
            right: '4%',
            bottom: '10%',
            width: '32%',
            height: '34%',
            borderRadius: 16,
            backgroundColor: brand.off_white,
            border: `2.5px solid ${brand.teal}`,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 6,
            boxSizing: 'border-box',
          }}
        >
          <Img
            src={scientificAssetSrc('lobuleHex')}
            data-medanim-image="lobuleHex"
            style={{width: '100%', height: '82%', objectFit: 'contain'}}
          />
          <div style={{fontFamily: FONT_FAMILY, fontSize: compact ? 11 : 13, fontWeight: 800, color: brand.navy}}>
            Mặt cắt lục giác
          </div>
        </div>
        <svg viewBox="0 0 560 560" width="100%" height="100%" style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
          {level > 0 ? (
            <path
              d="M120 190 Q190 240 245 275 M115 330 Q180 300 245 285"
              fill="none"
              stroke={ENTITY_COLORS.warning_threshold.hex}
              strokeWidth="4"
              strokeDasharray="8 6"
            />
          ) : null}
        </svg>
      </div>
    );
  }

  // 3. ALT / AST Tissue Distribution
  if (subject === 'alt_ast_tissue_distribution') {
    const cards = [
      {id: 'liver', img: 'liver' as ImageId, title: 'Gan', badge: 'ALT + AST', left: '4%', top: '12%', width: '44%', height: '38%', hasAlt: true, hasAst: true},
      {id: 'muscle', img: 'muscle' as ImageId, title: 'Cơ vân', badge: 'AST', left: '4%', top: '54%', width: '44%', height: '38%', hasAlt: false, hasAst: true},
      {id: 'heart', img: 'heart' as ImageId, title: 'Cơ tim', badge: 'AST', left: '53%', top: '18%', width: '43%', height: '68%', hasAlt: false, hasAst: true},
    ];
    return (
      <div
        data-scientific-artwork={subject}
        data-state={state}
        data-severity={level}
        style={{position: 'relative', width: '100%', height: '100%'}}
      >
        {cards.map((c) => (
          <div
            key={c.id}
            data-tissue-card={c.id}
            style={{
              position: 'absolute',
              left: c.left,
              top: c.top,
              width: c.width,
              height: c.height,
              borderRadius: 18,
              backgroundColor: brand.off_white,
              border: `2px solid ${hexToRgba(brand.navy, 0.2)}`,
              padding: compact ? 8 : 12,
              boxSizing: 'border-box',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
              <span style={{fontFamily: FONT_FAMILY, fontSize: compact ? 14 : 18, fontWeight: 800, color: brand.navy}}>
                {c.title}
              </span>
              <span
                style={{
                  fontFamily: FONT_FAMILY,
                  fontSize: compact ? 11 : 13,
                  fontWeight: 800,
                  padding: '2px 8px',
                  borderRadius: 8,
                  backgroundColor: c.hasAlt ? hexToRgba(brand.teal, 0.16) : hexToRgba(brand.yellow, 0.28),
                  color: brand.navy,
                }}
              >
                {c.badge}
              </span>
            </div>
            <Img
              src={scientificAssetSrc(c.img)}
              data-medanim-image={c.img}
              style={{width: '86%', height: '74%', objectFit: 'contain'}}
            />
          </div>
        ))}
        <svg viewBox="0 0 560 560" width="100%" height="100%" style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
          <EnzymeParticle cx={110} cy={175} kind="ALT" r={9} />
          <EnzymeParticle cx={190} cy={195} kind="AST" r={9} />
          <EnzymeParticle cx={150} cy={412} kind="AST" r={9} />
          <EnzymeParticle cx={420} cy={270} kind="AST" r={9.5} />
        </svg>
      </div>
    );
  }

  // 4-7. Cellular hepatic subjects (hepatocyte_sinusoid_unit, hepatic_toxic_injury, hepatic_synthesis_and_bile, hepatic_fibrosis_section)
  const showMito = subject === 'hepatic_toxic_injury' || subject === 'hepatic_synthesis_and_bile';
  const showVial = leakActive;
  const rbcOffsets = [0, 1, 2].map((i) => 16 + ((i * 28 + flowPhase * 0.7) % 72));
  const leakDrops = [0, 1, 2].map((i) => ({
    x: 196 + i * 74,
    y: 325 + leakProgress * (102 + (i % 2) * 14),
    inBlood: leakProgress > 0.35,
  }));

  return (
    <div
      data-scientific-artwork={subject}
      data-state={state}
      data-severity={level}
      style={{position: 'relative', width: '100%', height: '100%'}}
    >
      {/* Top bile canaliculus band */}
      <div
        data-layer="bile-canaliculus"
        style={{
          position: 'absolute',
          left: '14%',
          top: '5%',
          width: '72%',
          height: '8%',
          borderRadius: 999,
          backgroundColor: ENTITY_COLORS.bile_flow.rgba,
          border: `2.5px solid ${ENTITY_COLORS.bile_flow.hex}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: FONT_FAMILY,
          fontSize: compact ? 12 : 14,
          fontWeight: 800,
          color: brand.navy,
        }}
      >
        {blockProgress > 0.2 ? 'Đường mật (ứ trệ)' : 'Đường mật'}
      </div>

      {/* Main NIAID Hepatocyte illustration */}
      <div
        style={{
          position: 'absolute',
          left: '10%',
          top: '15%',
          width: '80%',
          height: '52%',
          borderRadius: 24,
          backgroundColor: leakActive || toxicProgress > 0
            ? hexToRgba(ENTITY_COLORS.tissue_injured.hex, 0.14)
            : hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.12),
          border: `3px solid ${leakActive || toxicProgress > 0 ? ENTITY_COLORS.tissue_injured.hex : brand.teal}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2%',
          boxSizing: 'border-box',
        }}
      >
        <Img
          src={scientificAssetSrc('cell')}
          data-medanim-image="cell"
          style={{width: '90%', height: '94%', objectFit: 'contain'}}
        />
        {showMito ? (
          <div
            style={{
              position: 'absolute',
              right: '6%',
              top: '18%',
              width: '24%',
              height: '44%',
              borderRadius: 14,
              backgroundColor: toxicProgress > 0 ? hexToRgba(brand.yellow, 0.25) : hexToRgba(brand.off_white, 0.92),
              border: `2px solid ${toxicProgress > 0 ? brand.yellow : brand.teal}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 4,
            }}
          >
            <Img
              src={scientificAssetSrc('mito')}
              data-medanim-image="mito"
              style={{width: '92%', height: '92%', objectFit: 'contain'}}
            />
          </div>
        ) : null}
      </div>

      {/* Sinusoidal blood vessel band ("Dòng máu xoang gan") */}
      <div
        data-layer="sinusoid"
        style={{
          position: 'absolute',
          left: '8%',
          top: '72%',
          width: showVial ? '66%' : '84%',
          height: '20%',
          borderRadius: 18,
          backgroundColor: hexToRgba(brand.teal, 0.14),
          border: `2.5px solid ${brand.teal}`,
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          padding: '0 14px',
          boxSizing: 'border-box',
        }}
      >
        <Img
          src={scientificAssetSrc('vessel')}
          data-medanim-image="vessel"
          style={{width: compact ? 52 : 68, height: compact ? 52 : 68, objectFit: 'contain', flexShrink: 0}}
        />
        <div style={{position: 'relative', flex: 1, height: '100%'}}>
          {rbcOffsets.map((leftPct, idx) => (
            <Img
              key={idx}
              src={scientificAssetSrc('rbc')}
              data-medanim-image="rbc"
              style={{
                position: 'absolute',
                left: `${leftPct}%`,
                top: idx % 2 === 0 ? '26%' : '48%',
                width: compact ? 24 : 30,
                height: compact ? 24 : 30,
                objectFit: 'contain',
              }}
            />
          ))}
          <div
            style={{
              position: 'absolute',
              right: 8,
              bottom: 6,
              fontFamily: FONT_FAMILY,
              fontSize: compact ? 11 : 14,
              fontWeight: 800,
              color: ink,
              backgroundColor: lightBackground ? hexToRgba(brand.off_white, 0.85) : hexToRgba(brand.night, 0.78),
              padding: '1px 8px',
              borderRadius: 6,
            }}
          >
            Dòng máu xoang gan
          </div>
        </div>
      </div>

      {showVial ? (
        <div
          style={{
            position: 'absolute',
            right: '6%',
            top: '71%',
            width: '18%',
            height: '22%',
            borderRadius: 14,
            backgroundColor: brand.off_white,
            border: `2.5px solid ${brand.yellow}`,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 4,
            boxSizing: 'border-box',
          }}
        >
          <Img
            src={scientificAssetSrc('tube')}
            data-medanim-image="tube"
            style={{width: '74%', height: '72%', objectFit: 'contain'}}
          />
          <div style={{fontFamily: FONT_FAMILY, fontSize: compact ? 10 : 12, fontWeight: 800, color: brand.navy}}>
            ALT / AST ↑
          </div>
        </div>
      ) : null}

      {/* Vector overlay for membrane pole, enzymes, export/synthesis, and fibrosis */}
      <svg viewBox="0 0 560 560" width="100%" height="100%" style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
        <g data-layer="hepatocyte-membrane" data-leak={leakProgress}>
          <line
            x1="108"
            y1="374"
            x2="452"
            y2="374"
            stroke={leakActive ? ENTITY_COLORS.warning_threshold.hex : brand.teal}
            strokeWidth="4.5"
            strokeLinecap="round"
            strokeDasharray={leakActive ? '14 8' : undefined}
          />
          {leakActive ? (
            <path
              d="M210 374 l10 -10 10 18 10 -16 10 14 10 -8"
              fill="none"
              stroke={ENTITY_COLORS.warning_threshold.hex}
              strokeWidth="4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null}
        </g>

        {/* Intracellular baseline enzyme particles */}
        <EnzymeParticle cx={166} cy={278} r={8} />
        <EnzymeParticle cx={312} cy={258} r={8.5} />
        <EnzymeParticle cx={376} cy={292} r={9} />

        {/* Exiting ALT / AST enzymes into sinusoidal blood flow when leaking */}
        {leakActive ? leakDrops.map((d, idx) => (
          <EnzymeParticle key={idx} cx={d.x} cy={d.y} leaked={d.inBlood} r={8.5} />
        )) : null}

        {/* Synthesis & bile transport cues */}
        {subject === 'hepatic_synthesis_and_bile' ? (
          <g data-layer="protein-export">
            <path d="M168 320 V406 M158 394 L168 406 L178 394" fill="none" stroke={brand.teal} strokeWidth="3.5" strokeLinecap="round" />
            <rect x="136" y="290" width="64" height="24" rx="6" fill={brand.off_white} stroke={brand.teal} strokeWidth="2" />
            <text x="168" y="306" textAnchor="middle" fontFamily="Be Vietnam Pro, sans-serif" fontSize="11" fontWeight="800" fill={brand.navy}>Albumin</text>
            <path d="M350 320 V406 M340 394 L350 406 L360 394" fill="none" stroke={brand.yellow} strokeWidth="3.5" strokeLinecap="round" />
            <rect x="314" y="290" width="72" height="24" rx="6" fill={brand.off_white} stroke={brand.yellow} strokeWidth="2" />
            <text x="350" y="306" textAnchor="middle" fontFamily="Be Vietnam Pro, sans-serif" fontSize="11" fontWeight="800" fill={brand.navy}>Đông máu</text>
          </g>
        ) : null}

        {/* Fibrosis septa cross-hatching */}
        {scarProgress > 0 ? (
          <g data-layer="fibrous-septa" opacity={scarProgress}>
            {[136, 224, 344, 424].map((x) => (
              <g key={x}>
                <path
                  d={`M${x} 94 Q${x + 22} 225 ${x} 366`}
                  fill="none"
                  stroke={ENTITY_COLORS.scar_fibrosis.hex}
                  strokeOpacity="0.55"
                  strokeWidth="12"
                  strokeDasharray="10 7"
                  strokeLinecap="round"
                />
                {[136, 186, 236, 286, 336].map((y) => (
                  <line
                    key={y}
                    x1={x - 6}
                    y1={y}
                    x2={x + 14}
                    y2={y + 10}
                    stroke={ENTITY_COLORS.scar_fibrosis.hex}
                    strokeWidth="2.4"
                    strokeLinecap="round"
                  />
                ))}
              </g>
            ))}
          </g>
        ) : null}
      </svg>
    </div>
  );
};

export const ScientificHepaticArtwork: React.FC<ScientificHepaticArtworkProps> = ({
  subject,
  state,
  severity,
  mode = 'single',
  cueProgress,
  lightBackground = true,
  compact = false,
  durationFrames = 180,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = interpolate(frame, [0, Math.max(1, durationFrames - 1)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const effectiveSeverity = mode === 'timelapse' ? clamp01(severity * (0.25 + 0.75 * progress)) : severity;
  const effectiveState = mode === 'timelapse' ? 'diseased' : state;
  const isCellular = CELLULAR_HEPATIC_SET.has(subject);

  return (
    <div
      data-scientific-hepatic="true"
      data-scientific-subject={subject}
      data-scientific-mode={mode}
      style={{position: 'relative', width: '100%', height: '100%'}}
    >
      {mode === 'comparison' ? (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: compact ? 12 : 24,
            paddingBottom: compact ? 0 : 28,
            boxSizing: 'border-box',
          }}
        >
          {[
            {label: 'Bình thường', colState: 'normal' as const, colSev: 0, accent: brand.teal},
            {label: 'Tổn thương', colState: 'diseased' as const, colSev: Math.max(0.45, severity), accent: brand.yellow},
          ].map((col) => (
            <div
              key={col.label}
              data-comparison-panel={col.colState}
              style={{
                position: 'relative',
                borderRadius: 20,
                backgroundColor: hexToRgba(brand.off_white, 0.96),
                border: `2.5px solid ${col.accent}`,
                padding: '38px 10px 10px',
                boxSizing: 'border-box',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  left: 14,
                  top: 8,
                  fontFamily: FONT_FAMILY,
                  fontSize: compact ? 16 : 20,
                  fontWeight: 800,
                  color: brand.navy,
                }}
              >
                {col.label}
              </div>
              <SingleHepaticArtwork
                subject={subject}
                state={col.colState}
                severity={col.colSev}
                cueProgress={col.colState === 'normal' ? undefined : cueProgress}
                lightBackground={true}
                compact={true}
                frame={frame}
                fps={fps}
              />
            </div>
          ))}
        </div>
      ) : (
        <SingleHepaticArtwork
          subject={subject}
          state={effectiveState}
          severity={effectiveSeverity}
          cueProgress={cueProgress}
          lightBackground={lightBackground}
          compact={compact}
          frame={frame}
          fps={fps}
        />
      )}

      {!compact ? (
        <div
          data-scientific-credit="true"
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 2,
            textAlign: 'center',
            fontFamily: FONT_FAMILY,
            fontSize: 13,
            fontWeight: 600,
            color: hexToRgba(lightBackground ? brand.navy : brand.off_white, 0.65),
            pointerEvents: 'none',
          }}
        >
          Hình giải phẫu: NIAID NIH BioArt · Servier · DBCLS · Reactome
        </div>
      ) : null}
    </div>
  );
};
