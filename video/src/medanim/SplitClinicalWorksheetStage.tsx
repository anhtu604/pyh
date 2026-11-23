import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {ANATOMY_COMPONENTS} from '../anatomy/registry';
import {activePanelIndex, panelRows} from '../components/AuthoredPanels';
import {Captions, CAPTION_BACKGROUND_COLOR, shouldRenderCaptions} from '../components/Captions';
import {MascotGuide} from '../components/MascotGuide';
import {FONT_FAMILY} from '../fonts';
import {useLayout, type Box} from '../layout';
import {ChapterBridgeBar, computeSceneEnvelope, type SceneTransitionProps} from '../motion/sceneEnvelope';
import {hexToRgba} from '../style/pyhStyle';
import type {Scene} from '../types';
import {isScientificHepaticSubject, ScientificHepaticArtwork} from './ScientificHepaticArtwork';

export type SplitClinicalWorksheetStageProps = {
  scene: Scene;
  transition?: SceneTransitionProps;
};

export const SplitClinicalWorksheetStage: React.FC<SplitClinicalWorksheetStageProps> = ({
  scene,
  transition,
}) => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const rows = panelRows(scene, 3);
  const active = activePanelIndex(rows, frame);
  const isVertical = layout.frame.height > layout.frame.width;
  const hasMascot = Boolean(scene.visual_assets?.some((asset) => asset.role === 'mascot'));
  const whiteboardAsset = scene.visual_assets?.find((asset) => asset.role === 'whiteboard');

  const env = computeSceneEnvelope(frame, transition);
  const envelopeStyle = transition && transition.durationFrames >= 45
    ? {opacity: env.opacity, transform: env.transform}
    : {};

  const headerTitle = scene.on_screen_text ?? scene.visualTakeaway ?? 'Phiếu minh họa';
  const takeawayNote = scene.visualTakeaway && scene.visualTakeaway !== headerTitle ? scene.visualTakeaway : null;

  const mascotBox: Box = isVertical
    ? {left: 32, top: 1350, width: 220, height: 192}
    : {left: 28, top: 842, width: 230, height: 200};

  const visualBox: Box = isVertical
    ? {left: 48, top: 148, width: layout.frame.width - 96, height: 460}
    : {
        left: 52,
        top: 132,
        width: 960,
        height: hasMascot ? 690 : 840,
      };

  const sheetBox: Box = isVertical
    ? {left: 48, top: 626, width: layout.frame.width - 96, height: 700}
    : {left: 1044, top: 132, width: 824, height: 840};

  const innerWidth = sheetBox.width - 56;
  const headerReserve = 96;
  const rowHeight = Math.max(78, (sheetBox.height - headerReserve - 36) / Math.max(1, rows.length));
  const colWidths = [innerWidth * 0.25, innerWidth * 0.34, innerWidth * 0.37];

  const Organ = scene.anatomy && !isScientificHepaticSubject(scene.anatomy.subject)
    ? ANATOMY_COMPONENTS[scene.anatomy.subject]
    : null;

  return (
    <AbsoluteFill
      data-split-clinical-stage="true"
      style={{backgroundColor: brand.off_white, color: brand.navy, overflow: 'hidden', ...envelopeStyle}}
    >
      {/* Top takeaway / title pill */}
      <div
        style={{
          position: 'absolute',
          left: isVertical ? 48 : 52,
          top: 28,
          right: isVertical ? 48 : 52,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 18,
          padding: '12px 22px',
          borderRadius: 14,
          backgroundColor: brand.off_white,
          border: `2px solid ${brand.teal}`,
          fontFamily: FONT_FAMILY,
          boxSizing: 'border-box',
        }}
      >
        <div style={{fontSize: isVertical ? 26 : 28, fontWeight: 800, color: brand.navy}}>
          {headerTitle}
        </div>
        {takeawayNote && !isVertical ? (
          <div style={{fontSize: 18, fontWeight: 600, color: hexToRgba(brand.navy, 0.78), textAlign: 'right', maxWidth: 760}}>
            {takeawayNote}
          </div>
        ) : null}
      </div>

      {/* Left (or Top in 9:16): FLUX illustration OR Scientific Hepatic Artwork */}
      <div
        data-split-visual={whiteboardAsset ? 'flux' : 'anatomy'}
        style={{
          position: 'absolute',
          left: visualBox.left,
          top: visualBox.top,
          width: visualBox.width,
          height: visualBox.height,
          borderRadius: 22,
          backgroundColor: hexToRgba(brand.teal, 0.06),
          border: `2px solid ${hexToRgba(brand.navy, 0.16)}`,
          padding: 16,
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
        }}
      >
        {whiteboardAsset ? (
          <Img
            aria-label={`PYH whiteboard ${scene.id}`}
            src={staticFile(whiteboardAsset.path)}
            style={{width: '100%', height: '100%', objectFit: 'contain', borderRadius: 14}}
          />
        ) : scene.anatomy && isScientificHepaticSubject(scene.anatomy.subject) ? (
          <ScientificHepaticArtwork
            subject={scene.anatomy.subject}
            state={scene.anatomy.state}
            severity={scene.anatomy.severity}
            compact
            lightBackground
            durationFrames={scene.duration_frames}
          />
        ) : Organ && scene.anatomy ? (
          <Organ
            state={scene.anatomy.state}
            severity={scene.anatomy.severity}
            lightBackground
            visibleLabels={[]}
          />
        ) : null}
      </div>

      {/* Right (or Bottom in 9:16): Progressive 3-column clinical worksheet */}
      <section
        aria-label={headerTitle}
        data-worksheet="true"
        data-active-row={active}
        style={{
          position: 'absolute',
          left: sheetBox.left,
          top: sheetBox.top,
          width: sheetBox.width,
          height: sheetBox.height,
          boxSizing: 'border-box',
          padding: '24px 28px',
          border: `3px solid ${brand.teal}`,
          borderRadius: 22,
          backgroundColor: brand.off_white,
          color: brand.navy,
          fontFamily: FONT_FAMILY,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            fontSize: isVertical ? 26 : 28,
            fontWeight: 800,
            marginBottom: 14,
            paddingBottom: 10,
            borderBottom: `2px solid ${hexToRgba(brand.teal, 0.35)}`,
          }}
        >
          {scene.on_screen_text ?? 'Đối chiếu từng bước'}
        </div>
        <div style={{position: 'relative'}}>
          <svg
            aria-hidden="true"
            width={innerWidth}
            height={rows.length * rowHeight}
            style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}
          >
            <path
              d={`M12 ${rowHeight / 2} V${Math.max(rowHeight / 2, (rows.length - 0.5) * rowHeight)}`}
              stroke={brand.teal}
              strokeWidth="3"
              fill="none"
            />
            {rows.map((row, index) =>
              frame >= row.start_frame ? (
                <g key={index}>
                  <path
                    data-leader={index}
                    d={`M12 ${(index + 0.5) * rowHeight} H30`}
                    stroke={brand.navy}
                    strokeWidth="2"
                  />
                  <circle
                    cx="12"
                    cy={(index + 0.5) * rowHeight}
                    r="7"
                    fill={index === active ? brand.yellow : brand.teal}
                  />
                </g>
              ) : null,
            )}
          </svg>
          {rows.map((row, index) => (
            <div
              key={index}
              style={{
                height: rowHeight,
                paddingLeft: 36,
                boxSizing: 'border-box',
                display: 'flex',
                alignItems: 'center',
                visibility: frame >= row.start_frame ? 'visible' : 'hidden',
                backgroundColor: index === active ? hexToRgba(brand.teal, 0.12) : 'transparent',
                borderRadius: 12,
              }}
            >
              {frame >= row.start_frame
                ? row.text.split('\t').map((cell, column) => {
                    let size = isVertical ? 22 : 24;
                    while (
                      size > 12 &&
                      Math.ceil(Array.from(cell).length / Math.max(1, Math.floor((colWidths[column] - 12) / (size * 0.62)))) *
                        size *
                        1.32 >
                        rowHeight - 14
                    ) {
                      size -= 1;
                    }
                    return (
                      <div
                        key={column}
                        style={{
                          width: colWidths[column],
                          padding: '4px 6px',
                          boxSizing: 'border-box',
                          fontSize: size,
                          fontWeight: column === 0 ? 800 : 600,
                          lineHeight: 1.28,
                          overflowWrap: 'anywhere',
                          whiteSpace: 'pre-line',
                        }}
                      >
                        {cell}
                      </div>
                    );
                  })
                : null}
            </div>
          ))}
        </div>
      </section>

      <MascotGuide scene={scene} box={mascotBox} continuation={transition?.mascotContinuation} transition={transition} />

      {shouldRenderCaptions(layout) && !scene.words?.length ? (
        <div
          data-mechanism-caption-band="true"
          style={{
            position: 'absolute',
            left: layout.captions.left,
            bottom: layout.captions.bottom,
            width: layout.captions.width,
            height: layout.captions.height,
            backgroundColor: CAPTION_BACKGROUND_COLOR,
            borderRadius: 16,
            zIndex: 7,
          }}
        />
      ) : null}
      <Captions
        variant={scene.words?.length ? 'shorts' : undefined}
        hasMascot={hasMascot}
        text={scene.narration}
        words={scene.words}
        durationInFrames={scene.duration_frames}
      />
      <ChapterBridgeBar bridge={env.bridge} />
    </AbsoluteFill>
  );
};
