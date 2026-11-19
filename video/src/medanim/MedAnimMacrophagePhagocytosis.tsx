import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {MagnifierZoom, magnifierOverviewOpacity} from '../components/MagnifierZoom';
import {LayoutContext, LAYOUTS} from '../layout';
import {clamp01, hexToRgba, pyhColors, pyhStroke, pyhType, smoothstep} from '../style/pyhStyle';
import {
  ASSET_DIR,
  ATTRIBUTION,
  B1_BACTERIUM_BOX,
  B1_PANEL,
  B2_PANEL,
  B4_STAGE_BOX,
  CLOSING_POSES,
  CREDITS_START,
  CYCLE_INSET_BOX,
  FUSION_DETAIL_BOX,
  FUSION_LOCATOR_START,
  FUSION_SOURCE_REGION,
  FUSION_ZOOM,
  GLOSSARY,
  IMAGES,
  LABELS,
  LITERATURE,
  MACROPHAGE_BOX,
  MINI_MAP_LEVELS,
  OPENING_POSES,
  PRR_DETAIL_BOX,
  PRR_LOCATOR_START,
  PRR_SOURCE_REGION,
  PRR_ZOOM,
  STEPS,
  TOTAL_FRAMES,
} from './macrophagePhagocytosis';
import {
  AssetImage,
  LegendCard,
  MEDANIM_W,
  MEDANIM_H,
  MedAnimChrome,
  MiniMapPillBar,
  fadeIn,
  lerp,
} from './medAnimShared';

const MacrophagePatrolScene: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = fadeIn(frame, 0, 10) * magnifierOverviewOpacity(frame, PRR_ZOOM);
  const drift = smoothstep(frame / 48) * 32;
  return (
    <AbsoluteFill data-medanim-scene="macrophage-patrol" style={{opacity}}>
      <div
        data-medanim-panel="b1-patrol"
        style={{
          position: 'absolute',
          ...B1_PANEL,
          borderRadius: pyhStroke.radius,
          border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      />
      <AssetImage assetDir={ASSET_DIR} asset={IMAGES.macrophage} id="macrophage" box={MACROPHAGE_BOX} />
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.bacterium}
        id="bacterium-approach"
        box={{...B1_BACTERIUM_BOX, left: B1_BACTERIUM_BOX.left + drift}}
      />
      <div
        style={{
          position: 'absolute',
          left: 1185,
          top: 230,
          width: 310,
          fontFamily: pyhType.fontFamily,
          color: pyhColors.ink,
        }}
      >
        <div style={{fontSize: pyhType.landscape.label, fontWeight: pyhType.labelWeight}}>Đại thực bào</div>
        <div style={{fontSize: 28, fontWeight: pyhType.bodyWeight, marginTop: 8}}>
          Tuần tra và bắt giữ mầm bệnh
        </div>
      </div>
    </AbsoluteFill>
  );
};

const ReceptorBindingDetail: React.FC = () => {
  const frame = useCurrentFrame();
  const dock = smoothstep((frame - 56) / 48);
  const bacX = lerp(915, 1085, dock);
  return (
    <AbsoluteFill data-medanim-scene="prr-binding">
      <div
        data-medanim-panel="prr-detail"
        style={{
          position: 'absolute',
          ...PRR_DETAIL_BOX,
          borderRadius: pyhStroke.radius,
          backgroundColor: pyhColors.background,
        }}
      />
      {/* Enlarged macrophage plasma membrane sector at right side of detail lens */}
      <div
        style={{
          position: 'absolute',
          left: 1210,
          top: 165,
          width: 600,
          height: 620,
          borderRadius: '260px 24px 24px 260px',
          backgroundColor: hexToRgba(pyhColors.accent, 0.14),
          border: `5px solid ${pyhColors.ink}`,
          boxSizing: 'border-box',
        }}
      />
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.engulfing}
        id="prr-membrane"
        box={{left: 1095, top: 380, width: 320, height: 92}}
        style={{transform: 'rotate(-90deg)'}}
      />
      {/* Pattern-recognition receptors & bacterial PAMP ligands */}
      <svg width={MEDANIM_W} height={MEDANIM_H} style={{position: 'absolute', left: 0, top: 0, pointerEvents: 'none'}}>
        {[340, 420, 505].map((y) => (
          <g key={y}>
            <path
              d={`M 1245 ${y} L 1185 ${y} M 1185 ${y} L 1158 ${y - 16} M 1185 ${y} L 1158 ${y + 16}`}
              stroke={pyhColors.accent}
              strokeWidth={6}
              strokeLinecap="round"
              fill="none"
            />
            <circle cx={bacX + 205} cy={y} r={10} fill={pyhColors.alert} stroke={pyhColors.ink} strokeWidth={2.5} />
          </g>
        ))}
      </svg>
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.bacterium}
        id="bacterium-pamp"
        box={{left: bacX, top: 345, width: 230, height: 178}}
      />
      <div
        style={{
          position: 'absolute',
          left: 1280,
          top: 625,
          width: 480,
          textAlign: 'center',
          fontFamily: pyhType.fontFamily,
          fontSize: pyhType.landscape.label,
          fontWeight: pyhType.labelWeight,
          color: pyhColors.ink,
        }}
      >
        Bào tương đại thực bào
      </div>
    </AbsoluteFill>
  );
};

const EngulfmentScene: React.FC = () => {
  const frame = useCurrentFrame();
  const overviewOpacity = frame >= 240 ? magnifierOverviewOpacity(frame, FUSION_ZOOM) : 1;
  const cupProgress = clamp01((frame - 252) / 96);
  const sealProgress = clamp01((frame - 350) / 80);

  return (
    <AbsoluteFill data-medanim-scene="engulfment" style={{opacity: overviewOpacity}}>
      <div
        data-medanim-panel="b2-engulfment"
        style={{
          position: 'absolute',
          ...B2_PANEL,
          borderRadius: pyhStroke.radius,
          border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      />

      {/* Left panel: F-actin pseudopod extension closing around the bacterium */}
      <div
        style={{
          position: 'absolute',
          left: 485,
          top: 150,
          fontFamily: pyhType.fontFamily,
          fontSize: pyhType.landscape.label,
          fontWeight: pyhType.labelWeight,
          color: pyhColors.ink,
        }}
      >
        Vươn chân giả (F-actin)
      </div>
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.engulfing}
        id="engulfing"
        box={{left: 515, top: 390, width: 520, height: 149}}
      />
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.bacterium}
        id="bacterium-cup"
        box={{
          left: 695,
          top: lerp(235, 345, smoothstep(cupProgress)),
          width: 175,
          height: 136,
        }}
      />
      <svg width={MEDANIM_W} height={MEDANIM_H} style={{position: 'absolute', left: 0, top: 0, pointerEvents: 'none'}}>
        <path
          data-medanim-actin="true"
          d="M 555 445 Q 640 315 705 290"
          stroke={pyhColors.accent}
          strokeWidth={7}
          strokeLinecap="round"
          fill="none"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - cupProgress}
        />
        <path
          data-medanim-actin="true"
          d="M 1005 445 Q 920 315 860 290"
          stroke={pyhColors.accent}
          strokeWidth={7}
          strokeLinecap="round"
          fill="none"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - cupProgress}
        />
      </svg>

      {/* Right panel: Sealed phagosome vesicle enclosing bacterium */}
      <div
        style={{
          position: 'absolute',
          left: 1105,
          top: 150,
          fontFamily: pyhType.fontFamily,
          fontSize: pyhType.landscape.label,
          fontWeight: pyhType.labelWeight,
          color: pyhColors.ink,
        }}
      >
        Khép kín túi thực bào
      </div>
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.phago2d}
        id="phago2d"
        box={{left: 1080, top: 245, width: 490, height: 467}}
        opacity={fadeIn(frame, 330)}
      />
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.bacterium}
        id="bacterium-trapped"
        box={{left: 1260, top: 425, width: 130, height: 101}}
        opacity={sealProgress}
      />
    </AbsoluteFill>
  );
};

const PhagolysosomeFusionScene: React.FC<{inMagnifier?: boolean; digestMode?: boolean}> = ({
  inMagnifier = false,
  digestMode = false,
}) => {
  const frame = useCurrentFrame();
  const startF = digestMode ? 720 : 516;
  const fuseT = digestMode ? 1 : smoothstep((frame - 560) / 72);
  const digestT = digestMode ? smoothstep((frame - 742) / 145) : 0;
  const box = digestMode ? {left: 545, top: 150, width: 700, height: 640} : FUSION_DETAIL_BOX;
  const vacuoleCx = box.left + box.width * 0.48;
  const vacuoleCy = box.top + box.height * 0.54;
  const vacuoleSize = digestMode ? 380 : 410;

  const lysoAngles = [0.2, 2.2, 4.1];
  const lysoDots = lysoAngles.map((ang, i) => {
    const r = lerp(digestMode ? 185 : 275, digestMode ? 175 : 192, fuseT);
    const x = vacuoleCx + Math.cos(ang + (frame - startF) * 0.008) * r - 38;
    const y = vacuoleCy + Math.sin(ang + (frame - startF) * 0.008) * r - 38;
    return {i, x, y};
  });

  // ROS / acid micro-dots active after lysosome fusion
  const rosActive = digestMode || fuseT > 0.7;
  const rosParticles = Array.from({length: 8}, (_, i) => {
    const ang = (i / 8) * Math.PI * 2 + frame * 0.05;
    const r = digestMode ? 95 + Math.sin(frame * 0.14 + i) * 28 : 135;
    return {i, x: vacuoleCx + Math.cos(ang) * r, y: vacuoleCy + Math.sin(ang) * r};
  });

  const exitOpacity = !inMagnifier && !digestMode && frame >= 712 ? 1 - smoothstep((frame - 712) / 8) : 1;

  return (
    <AbsoluteFill data-medanim-scene={digestMode ? 'phagolysosome-killing' : 'phagolysosome-fusion'} style={{opacity: exitOpacity}}>
      {!digestMode ? (
        <div
          data-medanim-panel="b3-fusion"
          style={{
            position: 'absolute',
            ...FUSION_DETAIL_BOX,
            borderRadius: pyhStroke.radius,
            border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
            backgroundColor: pyhColors.background,
            boxSizing: 'border-box',
          }}
        />
      ) : null}

      {/* Preload bacterium SVG for masked SVG image reference in B4 */}
      <Img
        src={staticFile(`${ASSET_DIR}/${IMAGES.bacterium.file}`)}
        aria-hidden="true"
        style={{position: 'absolute', left: 0, top: 0, width: 1, height: 1, opacity: 0, pointerEvents: 'none'}}
      />

      <div
        style={{
          position: 'absolute',
          left: box.left + 30,
          top: digestMode ? 122 : box.top + 38,
          fontFamily: pyhType.fontFamily,
          fontSize: pyhType.landscape.label,
          fontWeight: pyhType.labelWeight,
          color: pyhColors.ink,
        }}
      >
        {digestMode ? 'Phagolysosome hoạt hóa' : 'Hợp nhất túi thực bào với lysosome'}
      </div>

      {/* Intact outer vesicle */}
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.vacuole}
        id="vacuole"
        box={{
          left: vacuoleCx - vacuoleSize / 2,
          top: vacuoleCy - vacuoleSize / 2,
          width: vacuoleSize,
          height: vacuoleSize,
        }}
      />

      {/* Intact bacterium inside phagosome (B3) OR soft SVG <mask> bacterial lysis inside phagolysosome (B4) */}
      <svg
        width={190}
        height={148}
        viewBox={`0 0 ${IMAGES.bacterium.width} ${IMAGES.bacterium.height}`}
        data-medanim-image="bacterium-phagolysosome"
        data-digestion-mask={digestMode && digestT > 0.05 ? 'svg-mask' : 'intact'}
        style={{
          position: 'absolute',
          left: vacuoleCx - 95,
          top: vacuoleCy - 74,
          opacity: digestMode ? Math.max(0.18, 1 - digestT * 0.72) : 1,
        }}
      >
        <defs>
          <filter id="lysis-blur" x="-25%" y="-25%" width="150%" height="150%">
            <feGaussianBlur stdDeviation="2.4" />
          </filter>
          <mask id="lysis-mask" maskUnits="userSpaceOnUse" x="0" y="0" width={IMAGES.bacterium.width} height={IMAGES.bacterium.height}>
            <rect x="0" y="0" width={IMAGES.bacterium.width} height={IMAGES.bacterium.height} fill="white" />
            {digestMode && digestT > 0.05 ? (
              <g filter="url(#lysis-blur)" opacity={digestT}>
                <ellipse cx={18} cy={22} rx={16 * digestT} ry={13 * digestT} fill="black" />
                <ellipse cx={45} cy={30} rx={18 * digestT} ry={14 * digestT} fill="black" />
                <circle cx={33} cy={14} r={11 * digestT} fill="black" />
              </g>
            ) : null}
          </mask>
        </defs>
        <image
          href={staticFile(`${ASSET_DIR}/${IMAGES.bacterium.file}`)}
          width={IMAGES.bacterium.width}
          height={IMAGES.bacterium.height}
          mask={digestMode && digestT > 0.05 ? 'url(#lysis-mask)' : undefined}
        />
      </svg>

      {/* Docking lysosomes */}
      {lysoDots.map(({i, x, y}) => (
        <AssetImage
          key={`lyso-${i}`}
          assetDir={ASSET_DIR}
          asset={IMAGES.lysosome}
          id={`lysosome-${i}`}
          box={{left: x, top: y, width: 76, height: 76}}
        />
      ))}

      {/* Acidification & ROS markers inside intact vesicle */}
      <svg width={MEDANIM_W} height={MEDANIM_H} style={{position: 'absolute', left: 0, top: 0, pointerEvents: 'none'}}>
        {rosActive
          ? rosParticles.map((p) => (
              <circle
                key={`ros-${p.i}`}
                cx={p.x}
                cy={p.y}
                r={9}
                fill={p.i % 2 ? pyhColors.alert : pyhColors.accent}
                stroke={pyhColors.ink}
                strokeWidth={2}
                opacity={digestMode ? 0.9 : fuseT * 0.85}
              />
            ))
          : null}
      </svg>

      {!digestMode && frame >= 560 ? (
        <LegendCard
          box={{left: 1295, top: 445}}
          items={[
            {label: 'Bơm V-ATPase', color: pyhColors.accent, startFrame: 565},
            {label: 'Enzym thủy phân', color: pyhColors.alert, startFrame: 585},
          ]}
          opacity={fadeIn(frame, 565)}
        />
      ) : null}
    </AbsoluteFill>
  );
};

const DigestionAndIntactScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill data-medanim-scene="phagocytosis-resolution" style={{opacity: fadeIn(frame, 720, 12)}}>
      <div
        data-medanim-panel="b4-resolution"
        style={{
          position: 'absolute',
          ...B4_STAGE_BOX,
          borderRadius: pyhStroke.radius,
          border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      />
      <PhagolysosomeFusionScene digestMode />
      <div
        style={{
          position: 'absolute',
          left: CYCLE_INSET_BOX.left - 16,
          top: 190,
          width: CYCLE_INSET_BOX.width + 32,
          padding: '16px',
          borderRadius: pyhStroke.radius,
          border: `3px solid ${pyhColors.ink}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            fontFamily: pyhType.fontFamily,
            fontSize: pyhType.landscape.label,
            fontWeight: pyhType.labelWeight,
            color: pyhColors.ink,
            marginBottom: 12,
          }}
        >
          Chu trình thực bào hoàn chỉnh
        </div>
        <Img
          src={staticFile(`${ASSET_DIR}/${IMAGES.cycle.file}`)}
          data-medanim-image="cycle"
          style={{width: CYCLE_INSET_BOX.width, height: CYCLE_INSET_BOX.height, objectFit: 'contain', display: 'block'}}
        />
      </div>
    </AbsoluteFill>
  );
};

export const MedAnimMacrophagePhagocytosisBody: React.FC = () => {
  const frame = useCurrentFrame();
  const level = frame < PRR_ZOOM.end ? 0 : frame < FUSION_ZOOM.end ? 1 : 2;
  const b1ShellOpacity = frame >= 240 ? 1 - smoothstep((frame - 240) / 14) : 1;
  const b3ShellOpacity = frame >= 586 ? 1 - smoothstep((frame - 586) / 14) : 1;

  return (
    <AbsoluteFill style={{backgroundColor: pyhColors.background}}>
      {frame >= 240 && frame < 596 ? <EngulfmentScene /> : null}
      {frame >= 546 && frame < 720 ? <PhagolysosomeFusionScene /> : null}

      {frame < 254 ? (
        <AbsoluteFill style={{opacity: b1ShellOpacity}}>
          <MacrophagePatrolScene />
          <MagnifierZoom
            sourceRegion={PRR_SOURCE_REGION}
            detailBox={PRR_DETAIL_BOX}
            locatorStart={PRR_LOCATOR_START}
            open={PRR_ZOOM}
          >
            <ReceptorBindingDetail />
          </MagnifierZoom>
        </AbsoluteFill>
      ) : null}

      {frame >= FUSION_LOCATOR_START && frame < 600 ? (
        <AbsoluteFill style={{opacity: b3ShellOpacity}}>
          <MagnifierZoom
            sourceRegion={FUSION_SOURCE_REGION}
            detailBox={FUSION_DETAIL_BOX}
            locatorStart={FUSION_LOCATOR_START}
            open={FUSION_ZOOM}
          >
            <PhagolysosomeFusionScene inMagnifier />
          </MagnifierZoom>
        </AbsoluteFill>
      ) : null}

      {frame >= 720 && frame < CREDITS_START ? <DigestionAndIntactScene /> : null}

      <MiniMapPillBar assetDir={ASSET_DIR} levels={MINI_MAP_LEVELS} activeIndex={level} hideAfterFrame={CREDITS_START} />

      <MedAnimChrome
        steps={STEPS}
        glossary={GLOSSARY}
        labels={LABELS}
        openingPoses={OPENING_POSES}
        closingPoses={CLOSING_POSES}
        creditsStart={CREDITS_START}
        totalFrames={TOTAL_FRAMES}
        attribution={ATTRIBUTION}
        literature={LITERATURE}
      />
    </AbsoluteFill>
  );
};

export const MedAnimMacrophagePhagocytosis: React.FC = () => (
  <LayoutContext.Provider value={LAYOUTS.youtube_long}>
    <MedAnimMacrophagePhagocytosisBody />
  </LayoutContext.Provider>
);
