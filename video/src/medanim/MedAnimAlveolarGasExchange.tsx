import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {MagnifierZoom, magnifierOverviewOpacity} from '../components/MagnifierZoom';
import {LayoutContext, LAYOUTS} from '../layout';
import {clamp01, hexToRgba, pyhColors, pyhStroke, pyhType, smoothstep} from '../style/pyhStyle';
import {
  ALVEOLI_DETAIL_BOX,
  ALVEOLI_IMAGE_BOX,
  ALVEOLI_LOCATOR_START,
  ALVEOLI_SOURCE_REGION,
  ALVEOLI_ZOOM,
  ASSET_DIR,
  ATTRIBUTION,
  B1_CAP_INSET,
  B1_PANEL,
  B2_ALVEOLI_BOX,
  B2_CAPILLARY_BOX,
  B2_PANEL,
  B4_STAGE_BOX,
  CLOSING_POSES,
  CREDITS_START,
  EDEMA_IMAGE_BOX,
  GLOSSARY,
  IMAGES,
  LABELS,
  LITERATURE,
  LUNG_BOX,
  LUNG_LOCATOR_START,
  LUNG_SOURCE_REGION,
  LUNG_ZOOM,
  MEMBRANE_DETAIL_BOX,
  MINI_MAP_LEVELS,
  OPENING_POSES,
  STEPS,
  TOTAL_FRAMES,
} from './alveolarGasExchange';
import {
  AssetImage,
  LegendCard,
  MEDANIM_W,
  MEDANIM_H,
  MedAnimChrome,
  MiniMapPillBar,
  fadeIn,
  lerp,
  type Box,
} from './medAnimShared';

const LungOverviewScene: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = fadeIn(frame, 0, 10) * magnifierOverviewOpacity(frame, LUNG_ZOOM);
  return (
    <AbsoluteFill data-medanim-scene="lung-overview" style={{opacity}}>
      <div
        data-medanim-panel="b1-overview"
        style={{
          position: 'absolute',
          ...B1_PANEL,
          borderRadius: pyhStroke.radius,
          border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      />
      <AssetImage assetDir={ASSET_DIR} asset={IMAGES.lung} id="lung" box={LUNG_BOX} />
      <div
        style={{
          position: 'absolute',
          left: B1_CAP_INSET.left - 18,
          top: B1_CAP_INSET.top - 58,
          width: B1_CAP_INSET.width + 36,
          padding: '14px 18px 18px',
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
            marginBottom: 10,
          }}
        >
          Mạng mao mạch phổi
        </div>
        <Img
          src={staticFile(`${ASSET_DIR}/${IMAGES.capillary.file}`)}
          data-medanim-image="capillary-preview"
          style={{width: B1_CAP_INSET.width, height: B1_CAP_INSET.height, objectFit: 'contain', display: 'block'}}
        />
      </div>
      <div
        style={{
          position: 'absolute',
          left: B1_CAP_INSET.left - 18,
          top: 590,
          width: B1_CAP_INSET.width + 36,
          fontFamily: pyhType.fontFamily,
          color: pyhColors.ink,
        }}
      >
        <div style={{fontSize: pyhType.landscape.label, fontWeight: pyhType.labelWeight}}>Phổi (Pulmones)</div>
        <div style={{fontSize: 28, fontWeight: pyhType.bodyWeight, marginTop: 6}}>
          Cây phế quản dẫn khí tới tận phế nang
        </div>
      </div>
    </AbsoluteFill>
  );
};

const AlveoliDetailScene: React.FC = () => {
  const frame = useCurrentFrame();
  const pulse = Math.sin((frame / 30) * Math.PI * 1.4) * 0.015;
  return (
    <AbsoluteFill data-medanim-scene="alveoli-detail">
      <div
        data-medanim-panel="alveoli-detail"
        style={{
          position: 'absolute',
          ...ALVEOLI_DETAIL_BOX,
          borderRadius: pyhStroke.radius,
          backgroundColor: pyhColors.background,
        }}
      />
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.alveoli}
        id="alveoli"
        box={{
          left: ALVEOLI_IMAGE_BOX.left - ALVEOLI_IMAGE_BOX.width * pulse * 0.5,
          top: ALVEOLI_IMAGE_BOX.top - ALVEOLI_IMAGE_BOX.height * pulse * 0.5,
          width: ALVEOLI_IMAGE_BOX.width * (1 + pulse),
          height: ALVEOLI_IMAGE_BOX.height * (1 + pulse),
        }}
      />
      <AssetImage
        assetDir={ASSET_DIR}
        asset={IMAGES.capillary}
        id="capillary"
        box={{left: 1290, top: 470, width: 510, height: 292}}
      />
    </AbsoluteFill>
  );
};

const AlveoliMacroOverview: React.FC = () => {
  const frame = useCurrentFrame();
  const overviewOpacity = magnifierOverviewOpacity(frame, ALVEOLI_ZOOM);
  const enterOpacity = fadeIn(frame, 240, 12);
  return (
    <AbsoluteFill data-medanim-scene="alveoli-macro" style={{opacity: overviewOpacity * enterOpacity}}>
      <div
        data-medanim-panel="b2-overview"
        style={{
          position: 'absolute',
          ...B2_PANEL,
          borderRadius: pyhStroke.radius,
          border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      />
      <AssetImage assetDir={ASSET_DIR} asset={IMAGES.alveoli} id="alveoli-macro" box={B2_ALVEOLI_BOX} />
      <AssetImage assetDir={ASSET_DIR} asset={IMAGES.capillary} id="capillary-macro" box={B2_CAPILLARY_BOX} />
      <div
        style={{
          position: 'absolute',
          left: 200,
          top: 645,
          fontFamily: pyhType.fontFamily,
          fontSize: pyhType.landscape.label,
          fontWeight: pyhType.labelWeight,
          color: pyhColors.ink,
        }}
      >
        Phế nang &amp; mao mạch phổi
      </div>
    </AbsoluteFill>
  );
};

const GasBarrierDiagram: React.FC<{
  box: Box;
  interstitialThickness: number;
  edemaMode?: boolean;
}> = ({box, interstitialThickness, edemaMode = false}) => {
  const frame = useCurrentFrame();
  const epiY = box.top + 255;
  const epiTiles = 6;
  const epiW = (box.width - 120) / epiTiles;
  const endoY = epiY + 72 + interstitialThickness;
  const lumenH = 148;
  const rbcSize = 74;

  const rbcOffsets = [0, 1, 2, 3, 4].map((i) => {
    const prog = ((frame * (edemaMode ? 1.8 : 2.6) + i * 240) % (box.width - 120)) / (box.width - 120);
    const x = box.left + 60 + prog * (box.width - 140);
    const oxygenated = !edemaMode && prog > 0.38 && frame >= 480;
    return {i, x, prog, oxygenated};
  });

  // Gas particles: O2 flows downward into capillary; CO2 flows upward into alveolar space.
  const o2Particles = Array.from({length: 6}, (_, i) => {
    const cycle = ((frame - 360 + i * 16) % 72) / 72;
    const clamped = cycle < 0 ? 0 : cycle;
    const baseX = box.left + 150 + i * ((box.width - 320) / 5);
    const targetY = edemaMode ? epiY + 80 + interstitialThickness * 0.45 : endoY + 58;
    const y = frame < 360 ? epiY - 90 : lerp(epiY - 85, targetY, smoothstep(clamped));
    const opacity = frame < 360 ? 0 : Math.sin(clamped * Math.PI);
    return {i, x: baseX, y, opacity};
  });

  const co2Particles = Array.from({length: 5}, (_, i) => {
    const cycle = ((frame - 375 + i * 19) % 76) / 76;
    const clamped = cycle < 0 ? 0 : cycle;
    const baseX = box.left + 210 + i * ((box.width - 420) / 4);
    const y = frame < 375 ? endoY + 52 : lerp(endoY + 55, epiY - 120, smoothstep(clamped));
    const opacity = frame < 375 ? 0 : Math.sin(clamped * Math.PI);
    return {i, x: baseX, y, opacity};
  });

  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: box.left + 28,
          top: box.top + 38,
          width: box.width - 56,
          height: epiY - (box.top + 28),
          borderRadius: 18,
          backgroundColor: hexToRgba(pyhColors.accent, 0.08),
          border: `2px dashed ${hexToRgba(pyhColors.accent, 0.4)}`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: box.left + 56,
          top: box.top + 54,
          fontFamily: pyhType.fontFamily,
          fontSize: pyhType.landscape.label,
          fontWeight: pyhType.labelWeight,
          color: pyhColors.ink,
        }}
      >
        Lòng phế nang (không khí hít vào)
      </div>

      {/* Interstitium / basement membrane — widens cleanly during pulmonary edema (B4) */}
      <div
        data-medanim-interstitium={edemaMode ? 'edema-thickened' : 'normal-thin'}
        style={{
          position: 'absolute',
          left: box.left + 40,
          top: epiY + 46,
          width: box.width - 80,
          height: interstitialThickness + 34,
          borderRadius: 10,
          backgroundColor: edemaMode ? hexToRgba(pyhColors.accent, 0.28) : hexToRgba(pyhColors.ink, 0.08),
          borderTop: `2px solid ${hexToRgba(pyhColors.ink, 0.28)}`,
          borderBottom: `2px solid ${hexToRgba(pyhColors.ink, 0.28)}`,
        }}
      />

      {/* Alveolar epithelial lining tiled cleanly with licensed Reactome SVGs */}
      {Array.from({length: epiTiles}, (_, i) => (
        <Img
          key={`epi-${i}`}
          src={staticFile(`${ASSET_DIR}/${IMAGES.alveolusCell.file}`)}
          data-medanim-image="alveolusCell"
          style={{
            position: 'absolute',
            left: box.left + 60 + i * epiW,
            top: epiY - 22,
            width: epiW - 10,
            height: 78,
            objectFit: 'contain',
          }}
        />
      ))}

      {/* Capillary blood lumen + endothelial wall */}
      <div
        style={{
          position: 'absolute',
          left: box.left + 40,
          top: endoY + 26,
          width: box.width - 80,
          height: lumenH,
          borderRadius: 18,
          backgroundColor: hexToRgba(pyhColors.alert, 0.13),
          borderTop: `4px solid ${pyhColors.ink}`,
          borderBottom: `4px solid ${pyhColors.ink}`,
        }}
      />
      {Array.from({length: 5}, (_, i) => (
        <Img
          key={`endo-${i}`}
          src={staticFile(`${ASSET_DIR}/${IMAGES.endothelial.file}`)}
          data-medanim-image="endothelial"
          style={{
            position: 'absolute',
            left: box.left + 58 + i * ((box.width - 116) / 5),
            top: endoY + 2,
            width: (box.width - 140) / 5,
            height: 36,
            objectFit: 'contain',
          }}
        />
      ))}

      {/* Flowing erythrocytes with hemoglobin O2 saturation glow in B3 */}
      {rbcOffsets.map(({i, x, oxygenated}) => (
        <div
          key={`rbc-${i}`}
          style={{
            position: 'absolute',
            left: x,
            top: endoY + 60 + (i % 2) * 10,
            width: rbcSize,
            height: rbcSize,
          }}
        >
          {oxygenated ? (
            <div
              data-medanim-hbo2="true"
              style={{
                position: 'absolute',
                inset: -6,
                borderRadius: 999,
                border: `4px solid ${pyhColors.accent}`,
                backgroundColor: hexToRgba(pyhColors.accent, 0.2),
              }}
            />
          ) : null}
          <Img
            src={staticFile(`${ASSET_DIR}/${IMAGES.rbc.file}`)}
            data-medanim-image="rbc"
            style={{position: 'relative', width: rbcSize, height: rbcSize, objectFit: 'contain'}}
          />
        </div>
      ))}

      <div
        style={{
          position: 'absolute',
          left: box.left + 56,
          top: endoY + lumenH + 38,
          fontFamily: pyhType.fontFamily,
          fontSize: pyhType.landscape.label,
          fontWeight: pyhType.labelWeight,
          color: pyhColors.ink,
        }}
      >
        Lòng mao mạch phổi
      </div>

      {/* Diffusion trajectories & particles */}
      <svg width={MEDANIM_W} height={MEDANIM_H} style={{position: 'absolute', left: 0, top: 0, pointerEvents: 'none'}}>
        <defs>
          <marker id="gas-o2-arrow" markerWidth="7" markerHeight="7" refX="4" refY="3.5" orient="auto">
            <path d="M0 0 L7 3.5 L0 7 z" fill={pyhColors.accent} />
          </marker>
          <marker id="gas-co2-arrow" markerWidth="7" markerHeight="7" refX="4" refY="3.5" orient="auto">
            <path d="M0 0 L7 3.5 L0 7 z" fill={pyhColors.alert} />
          </marker>
        </defs>
        {frame >= 360 ? (
          <>
            <path
              data-medanim-flow="o2-diffusion"
              d={`M ${box.left + 150} ${epiY - 56} L ${box.left + 150} ${edemaMode ? epiY + 75 : endoY + 48}`}
              stroke={pyhColors.accent}
              strokeWidth={5}
              strokeDasharray="10 8"
              markerEnd="url(#gas-o2-arrow)"
            />
            {!edemaMode ? (
              <path
                data-medanim-flow="co2-diffusion"
                d={`M ${box.left + 210} ${endoY + 46} L ${box.left + 210} ${epiY - 68}`}
                stroke={pyhColors.alert}
                strokeWidth={5}
                strokeDasharray="10 8"
                markerEnd="url(#gas-co2-arrow)"
              />
            ) : null}
          </>
        ) : null}
        {o2Particles.map((p) => (
          <circle
            key={`o2-${p.i}`}
            cx={p.x}
            cy={p.y}
            r={12}
            fill={pyhColors.accent}
            stroke={pyhColors.ink}
            strokeWidth={2.5}
            opacity={p.opacity}
          />
        ))}
        {co2Particles.map((p) => (
          <circle
            key={`co2-${p.i}`}
            cx={p.x}
            cy={p.y}
            r={11}
            fill={pyhColors.alert}
            stroke={pyhColors.ink}
            strokeWidth={2.5}
            opacity={p.opacity}
          />
        ))}
      </svg>
    </>
  );
};

const BloodGasBarrierScene: React.FC<{inMagnifier?: boolean}> = ({inMagnifier = false}) => {
  const frame = useCurrentFrame();
  const exitFade = !inMagnifier && frame >= 712 ? 1 - smoothstep((frame - 712) / 8) : 1;
  return (
    <AbsoluteFill data-medanim-scene="blood-gas-barrier" style={{opacity: exitFade}}>
      <div
        data-medanim-panel="membrane-detail"
        style={{
          position: 'absolute',
          ...MEMBRANE_DETAIL_BOX,
          borderRadius: pyhStroke.radius,
          border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      />
      <GasBarrierDiagram box={MEMBRANE_DETAIL_BOX} interstitialThickness={12} />
      {frame >= 480 && frame < 720 ? (
        <LegendCard
          box={{left: 48, top: 430}}
          items={[
            {label: 'Oxy vào máu', color: pyhColors.accent, startFrame: 486},
            {label: 'Cacbonic thải ra', color: pyhColors.alert, startFrame: 506},
          ]}
          opacity={fadeIn(frame, 486)}
        />
      ) : null}
    </AbsoluteFill>
  );
};

const PulmonaryEdemaScene: React.FC = () => {
  const frame = useCurrentFrame();
  const enter = fadeIn(frame, 720, 12);
  const swell = lerp(18, 92, smoothstep((frame - 726) / 28));
  const barrierBox: Box = {
    left: 960,
    top: B4_STAGE_BOX.top + 20,
    width: 876,
    height: B4_STAGE_BOX.height - 40,
  };
  return (
    <AbsoluteFill data-medanim-scene="pulmonary-edema" style={{opacity: enter}}>
      <div
        data-medanim-panel="b4-edema"
        style={{
          position: 'absolute',
          ...B4_STAGE_BOX,
          borderRadius: pyhStroke.radius,
          border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: EDEMA_IMAGE_BOX.left,
          top: 122,
          width: 490,
          fontFamily: pyhType.fontFamily,
          fontSize: pyhType.landscape.label,
          fontWeight: pyhType.labelWeight,
          color: pyhColors.ink,
        }}
      >
        Phù nề khoảng kẽ
      </div>
      <AssetImage assetDir={ASSET_DIR} asset={IMAGES.edema} id="edema" box={EDEMA_IMAGE_BOX} />
      <div
        style={{
          position: 'absolute',
          left: EDEMA_IMAGE_BOX.left,
          top: 545,
          width: EDEMA_IMAGE_BOX.width,
          padding: '14px 18px',
          borderRadius: pyhStroke.radius,
          border: `3px solid ${pyhColors.alert}`,
          backgroundColor: hexToRgba(pyhColors.alert, 0.1),
          fontFamily: pyhType.fontFamily,
          fontSize: 28,
          fontWeight: 700,
          color: pyhColors.ink,
          boxSizing: 'border-box',
        }}
      >
        Khoảng kẽ dày làm chậm khuếch tán khí oxy
      </div>
      <GasBarrierDiagram box={barrierBox} interstitialThickness={swell} edemaMode />
    </AbsoluteFill>
  );
};

export const MedAnimAlveolarGasExchangeBody: React.FC = () => {
  const frame = useCurrentFrame();
  const level = frame < LUNG_ZOOM.end ? 0 : frame < ALVEOLI_ZOOM.end ? 1 : 2;
  const b1ShellOpacity = frame >= 240 ? 1 - smoothstep((frame - 240) / 14) : 1;
  const b2ShellOpacity = frame >= 360 ? 1 - smoothstep((frame - 360) / 12) : 1;

  return (
    <AbsoluteFill style={{backgroundColor: pyhColors.background}}>
      {frame >= 240 && frame < 372 ? <AlveoliMacroOverview /> : null}
      {frame >= 318 && frame < 720 ? <BloodGasBarrierScene /> : null}

      {frame < 254 ? (
        <AbsoluteFill style={{opacity: b1ShellOpacity}}>
          <LungOverviewScene />
          <MagnifierZoom
            sourceRegion={LUNG_SOURCE_REGION}
            detailBox={ALVEOLI_DETAIL_BOX}
            locatorStart={LUNG_LOCATOR_START}
            open={LUNG_ZOOM}
          >
            <AlveoliDetailScene />
          </MagnifierZoom>
        </AbsoluteFill>
      ) : null}

      {frame >= ALVEOLI_LOCATOR_START && frame < 372 ? (
        <AbsoluteFill style={{opacity: b2ShellOpacity}}>
          <MagnifierZoom
            sourceRegion={ALVEOLI_SOURCE_REGION}
            detailBox={MEMBRANE_DETAIL_BOX}
            locatorStart={ALVEOLI_LOCATOR_START}
            open={ALVEOLI_ZOOM}
          >
            <BloodGasBarrierScene inMagnifier />
          </MagnifierZoom>
        </AbsoluteFill>
      ) : null}

      {frame >= 720 && frame < CREDITS_START ? <PulmonaryEdemaScene /> : null}

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

export const MedAnimAlveolarGasExchange: React.FC = () => (
  <LayoutContext.Provider value={LAYOUTS.youtube_long}>
    <MedAnimAlveolarGasExchangeBody />
  </LayoutContext.Provider>
);
