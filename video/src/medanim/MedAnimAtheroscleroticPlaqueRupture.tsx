import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {MagnifierZoom, magnifierOverviewOpacity} from '../components/MagnifierZoom';
import {LayoutContext, LAYOUTS} from '../layout';
import {clamp01, hexToRgba, pyhColors, pyhStroke, pyhType, smoothstep} from '../style/pyhStyle';
import {
  ARTERY_STAGE_BOX,
  ARTERY_TUNIC_BOX,
  ASSET_DIR,
  ATTRIBUTION,
  B1_PANEL,
  CLOSING_POSES,
  CORONARY_LOCATOR_START,
  CORONARY_SOURCE_REGION,
  CORONARY_ZOOM,
  CREDITS_START,
  GLOSSARY,
  HEART_BOX,
  IMAGES,
  INTIMA_DETAIL_BOX,
  LABELS,
  LITERATURE,
  MINI_MAP_LEVELS,
  OPENING_POSES,
  STEPS,
  TOTAL_FRAMES,
} from './atheroscleroticPlaqueRupture';
import {
  AssetImage,
  LegendCard,
  MEDANIM_H,
  MEDANIM_W,
  MedAnimChrome,
  MiniMapPillBar,
  fadeIn,
  lerp,
  type Box,
} from './medAnimShared';

const HeartOverviewScene: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = fadeIn(frame, 0, 10) * magnifierOverviewOpacity(frame, CORONARY_ZOOM);
  return (
    <AbsoluteFill data-medanim-scene="heart-overview" style={{opacity}}>
      <div
        data-medanim-panel="b1-heart"
        style={{
          position: 'absolute',
          ...B1_PANEL,
          borderRadius: pyhStroke.radius,
          border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      />
      <AssetImage assetDir={ASSET_DIR} asset={IMAGES.heart} id="heart" box={HEART_BOX} />
      <AssetImage assetDir={ASSET_DIR} asset={IMAGES.artery} id="artery-tunic" box={ARTERY_TUNIC_BOX} />
      <div
        style={{
          position: 'absolute',
          left: 1005,
          top: 735,
          width: 470,
          textAlign: 'center',
          fontFamily: pyhType.fontFamily,
          color: pyhColors.ink,
        }}
      >
        <div style={{fontSize: pyhType.landscape.label, fontWeight: pyhType.labelWeight}}>Thành động mạch</div>
        <div style={{fontSize: 28, fontWeight: pyhType.bodyWeight, marginTop: 4}}>
          Lớp nội mô, áo giữa cơ trơn &amp; áo ngoài
        </div>
      </div>
    </AbsoluteFill>
  );
};

const ArterialWallScene: React.FC<{box: Box; inMagnifier?: boolean}> = ({box, inMagnifier = false}) => {
  const frame = useCurrentFrame();
  const baseLumenY = box.top + 275;
  const cx = box.left + box.width * 0.52;

  // Plaque growth bulge curves endothelial roof upward in B3/B4
  const b2Grow = smoothstep((frame - 240) / 140);
  const b3Grow = smoothstep((frame - 480) / 110);
  const domeLift = inMagnifier ? 0 : b2Grow * 24 + b3Grow * 64;
  const ruptureT = !inMagnifier && frame >= 746 ? smoothstep((frame - 746) / 28) : 0;
  const thrombusT = !inMagnifier && frame >= 770 ? smoothstep((frame - 770) / 65) : 0;

  // LDL infiltration in B1/B2
  const ldlCross = smoothstep((frame - 92) / 76);
  const oxAppear = smoothstep((frame - 122) / 56);
  const monocyteT = inMagnifier ? 0 : smoothstep((frame - 252) / 86);
  const foamT = inMagnifier ? 0 : smoothstep((frame - 348) / 86);
  const capT = inMagnifier ? 0 : smoothstep((frame - 560) / 76);

  const rbcOffsets = Array.from({length: 6}, (_, i) => {
    const span = box.width - 130;
    const x = box.left + 40 + ((frame * (1 - thrombusT * 0.45) * 3.1 + i * (span / 6)) % span);
    const distCenter = Math.abs(x - cx);
    const localRoof = distCenter < 260 ? domeLift * Math.cos((distCenter / 260) * (Math.PI / 2)) : 0;
    return {i, x, y: box.top + 86 + (i % 2) * 52 - localRoof * 0.25};
  });

  return (
    <AbsoluteFill data-medanim-scene={inMagnifier ? 'intima-detail' : 'arterial-wall'}>
      <div
        data-medanim-panel={inMagnifier ? 'b1-intima-lens' : 'artery-stage'}
        style={{
          position: 'absolute',
          ...box,
          borderRadius: pyhStroke.radius,
          border: `2px solid ${hexToRgba(pyhColors.ink, 0.14)}`,
          backgroundColor: pyhColors.background,
          boxSizing: 'border-box',
        }}
      />

      {/* Preload SVGs used inside SVG <image> mask elements */}
      {(['collagen', 'endothelial'] as const).map((k) => (
        <Img
          key={k}
          src={staticFile(`${ASSET_DIR}/${IMAGES[k].file}`)}
          aria-hidden="true"
          style={{position: 'absolute', left: 0, top: 0, width: 1, height: 1, opacity: 0, pointerEvents: 'none'}}
        />
      ))}

      {/* Arterial lumen */}
      <div
        style={{
          position: 'absolute',
          left: box.left + 24,
          top: box.top + 28,
          width: box.width - 48,
          height: baseLumenY - box.top - 10,
          borderRadius: 16,
          backgroundColor: hexToRgba(pyhColors.alert, 0.1),
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: box.left + 48,
          top: box.top + 42,
          fontFamily: pyhType.fontFamily,
          fontSize: pyhType.landscape.label,
          fontWeight: pyhType.labelWeight,
          color: pyhColors.ink,
        }}
      >
        Lòng động mạch vành
      </div>

      {/* Tunica media / smooth muscle base */}
      <div
        style={{
          position: 'absolute',
          left: box.left + 24,
          top: baseLumenY + 340,
          width: box.width - 48,
          height: 145,
          borderRadius: 14,
          backgroundColor: hexToRgba(pyhColors.ink, 0.06),
          borderTop: `4px solid ${hexToRgba(pyhColors.ink, 0.35)}`,
        }}
      />
      {Array.from({length: 3}, (_, i) => (
        <AssetImage
          key={`smc-${i}`}
          assetDir={ASSET_DIR}
          asset={IMAGES.smc}
          id={`smc-${i}`}
          box={{
            left: box.left + 44 + i * ((box.width - 120) / 3),
            top: baseLumenY + 365 + (i % 2) * 20,
            width: (box.width - 140) / 3,
            height: 62,
          }}
        />
      ))}
      {/* Migrating VSMCs contributing to cap synthesis in B3 */}
      {capT > 0 ? (
        <AssetImage
          assetDir={ASSET_DIR}
          asset={IMAGES.smc}
          id="smc-cap"
          box={{left: cx - 190, top: baseLumenY - domeLift + 26, width: 380, height: 62}}
          opacity={capT * 0.85}
        />
      ) : null}

      {/* Flowing erythrocytes in arterial lumen */}
      {rbcOffsets.map(({i, x, y}) => (
        <AssetImage
          key={`rbc-${i}`}
          assetDir={ASSET_DIR}
          asset={IMAGES.rbc}
          id={`rbc-${i}`}
          box={{left: x, top: y, width: 64, height: 64}}
        />
      ))}

      {/* Subendothelial intimal necrotic / lipid core dome in B2-B4 */}
      {!inMagnifier ? (
        <div
          data-medanim-core="necrotic"
          style={{
            position: 'absolute',
            left: cx - 280,
            top: baseLumenY - domeLift + 42,
            width: 560,
            height: 295 + domeLift * 0.65,
            borderRadius: '240px 240px 36px 36px',
            backgroundColor: hexToRgba(pyhColors.alert, 0.22 + b3Grow * 0.25),
            border: `3px dashed ${pyhColors.alert}`,
            opacity: b2Grow,
          }}
        />
      ) : null}

      {/* Native LDL in lumen & oxidized oxLDL accumulating in subendothelial intima */}
      {[
        {x: cx - 180, ox: true},
        {x: cx - 40, ox: true},
        {x: cx + 95, ox: true},
        {x: cx + 210, ox: false},
      ].map((item, idx) => (
        <React.Fragment key={`ldl-${idx}`}>
          <AssetImage
            assetDir={ASSET_DIR}
            asset={IMAGES.ldl}
            id={`ldl-${idx}`}
            box={{
              left: item.x,
              top: lerp(baseLumenY - 82, baseLumenY + 95, clamp01(ldlCross * 1.2 - idx * 0.1)),
              width: 72,
              height: 63,
            }}
            opacity={1 - oxAppear * (item.ox ? 0.85 : 0.2)}
          />
          {item.ox && oxAppear > 0 ? (
            <AssetImage
              assetDir={ASSET_DIR}
              asset={IMAGES.oxldl}
              id={`oxldl-${idx}`}
              box={{
                left: item.x - 10,
                top: baseLumenY + 115 + (idx % 2) * 58,
                width: 78,
                height: 82,
              }}
              opacity={oxAppear}
            />
          ) : null}
        </React.Fragment>
      ))}

      {/* B2: Monocyte transmigration & differentiation into lipid-laden foam cells */}
      {monocyteT > 0 ? (
        <AssetImage
          assetDir={ASSET_DIR}
          asset={IMAGES.monocyte}
          id="monocyte"
          box={{
            left: lerp(cx - 320, cx - 285, monocyteT),
            top: lerp(baseLumenY - 85, baseLumenY + 88, monocyteT),
            width: 98,
            height: 114,
          }}
          opacity={1 - foamT}
        />
      ) : null}
      {foamT > 0
        ? [
            {x: cx - 180, y: baseLumenY + 140},
            {x: cx - 45, y: baseLumenY + 175},
            {x: cx + 85, y: baseLumenY + 135},
          ].map((pos, idx) => (
            <AssetImage
              key={`foam-${idx}`}
              assetDir={ASSET_DIR}
              asset={IMAGES.foam}
              id={`foam-${idx}`}
              box={{left: pos.x, top: pos.y - domeLift * 0.22, width: 112, height: 125}}
              opacity={foamT}
            />
          ))
        : null}

      {/* Fibrous cap collagen layer + soft SVG <mask> fissure on cap rupture in B4 */}
      {capT > 0 ? (
        <svg
          width={box.width}
          height={240}
          viewBox={`0 0 ${box.width} 240`}
          data-medanim-cap="collagen-cap"
          data-rupture-mask={ruptureT > 0 ? 'svg-mask' : 'intact'}
          style={{
            position: 'absolute',
            left: box.left,
            top: baseLumenY - domeLift - 44,
            opacity: capT,
            pointerEvents: 'none',
          }}
        >
          <defs>
            <filter id="cap-rupture-blur" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="5" />
            </filter>
            <mask id="cap-rupture-mask" maskUnits="userSpaceOnUse" x="0" y="0" width={box.width} height={240}>
              <rect x="0" y="0" width={box.width} height={240} fill="white" />
              {ruptureT > 0 ? (
                <g filter="url(#cap-rupture-blur)" opacity={ruptureT}>
                  <path
                    d={`M ${box.width * 0.52 - 58} 10 C ${box.width * 0.52 - 36} 55, ${box.width * 0.52 - 42} 95, ${box.width * 0.52} 135 C ${box.width * 0.52 + 44} 92, ${box.width * 0.52 + 38} 50, ${box.width * 0.52 + 60} 10 Z`}
                    fill="black"
                  />
                  <ellipse cx={box.width * 0.52} cy={72} rx={68 * ruptureT} ry={58 * ruptureT} fill="black" />
                </g>
              ) : null}
            </mask>
          </defs>
          <g mask={ruptureT > 0 ? 'url(#cap-rupture-mask)' : undefined}>
            <image
              href={staticFile(`${ASSET_DIR}/${IMAGES.collagen.file}`)}
              x={box.width * 0.52 - 285}
              y={42}
              width={570}
              height={68}
            />
          </g>
        </svg>
      ) : null}

      {/* Endothelial cell lining along the arterial wall, opening softly at focal plaque fissure in B4 */}
      {Array.from({length: 6}, (_, i) => {
        const segW = (box.width - 96) / 6;
        const x = box.left + 48 + i * segW;
        const distCenter = Math.abs(x + segW / 2 - cx);
        const lift = distCenter < 290 ? domeLift * Math.cos((distCenter / 290) * (Math.PI / 2)) : 0;
        const rupturedSegment = ruptureT > 0 && (i === 2 || i === 3);
        const shiftX = rupturedSegment ? (i === 2 ? -42 : 42) * ruptureT : 0;
        return (
          <Img
            key={`endo-${i}`}
            src={staticFile(`${ASSET_DIR}/${IMAGES.endothelial.file}`)}
            data-medanim-image="endothelial"
            style={{
              position: 'absolute',
              left: x + shiftX,
              top: baseLumenY - lift - 26,
              width: segW - 8,
              height: 44,
              objectFit: 'contain',
              opacity: rupturedSegment ? 1 - ruptureT * 0.55 : 1,
            }}
          />
        );
      })}

      {/* B4: Exposed core triggers platelet aggregation + fibrin mesh forming occlusive thrombus */}
      {thrombusT > 0 ? (
        <div data-medanim-thrombus="active" style={{opacity: thrombusT}}>
          <AssetImage
            assetDir={ASSET_DIR}
            asset={IMAGES.plateletBioart}
            id="platelet-core"
            box={{left: cx - 72, top: baseLumenY - domeLift - 86, width: 144, height: 144}}
          />
          {[
            {dx: -135, dy: -62},
            {dx: 48, dy: -70},
            {dx: -48, dy: -98},
            {dx: 105, dy: -38},
          ].map((p, idx) => (
            <AssetImage
              key={`plt-${idx}`}
              assetDir={ASSET_DIR}
              asset={IMAGES.platelet}
              id={`platelet-active-${idx}`}
              box={{left: cx + p.dx, top: baseLumenY - domeLift + p.dy, width: 88, height: 84}}
            />
          ))}
          <AssetImage
            assetDir={ASSET_DIR}
            asset={IMAGES.fibrin}
            id="fibrin-mesh"
            box={{left: cx - 210, top: baseLumenY - domeLift - 48, width: 420, height: 64}}
          />
        </div>
      ) : null}

      {!inMagnifier && frame >= 480 && frame < 720 ? (
        <LegendCard
          box={{left: 36, top: 650}}
          items={[
            {label: 'Lõi hoại tử', color: pyhColors.alert, startFrame: 486},
            {label: 'Bao xơ sợi', color: pyhColors.accent, startFrame: 560},
          ]}
          opacity={fadeIn(frame, 486)}
        />
      ) : null}
    </AbsoluteFill>
  );
};

export const MedAnimAtheroscleroticPlaqueRuptureBody: React.FC = () => {
  const frame = useCurrentFrame();
  const level = frame < CORONARY_ZOOM.end ? 0 : frame < 480 ? 1 : 2;
  const b1ShellOpacity = frame >= 240 ? 1 - smoothstep((frame - 240) / 14) : 1;

  return (
    <AbsoluteFill style={{backgroundColor: pyhColors.background}}>
      {frame >= 240 && frame < CREDITS_START ? <ArterialWallScene box={ARTERY_STAGE_BOX} /> : null}

      {frame < 254 ? (
        <AbsoluteFill style={{opacity: b1ShellOpacity}}>
          <HeartOverviewScene />
          <MagnifierZoom
            sourceRegion={CORONARY_SOURCE_REGION}
            detailBox={INTIMA_DETAIL_BOX}
            locatorStart={CORONARY_LOCATOR_START}
            open={CORONARY_ZOOM}
          >
            <ArterialWallScene box={INTIMA_DETAIL_BOX} inMagnifier />
          </MagnifierZoom>
        </AbsoluteFill>
      ) : null}

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

export const MedAnimAtheroscleroticPlaqueRupture: React.FC = () => (
  <LayoutContext.Provider value={LAYOUTS.youtube_long}>
    <MedAnimAtheroscleroticPlaqueRuptureBody />
  </LayoutContext.Provider>
);
