// Shared PYH Style A building blocks for reusable medical mechanism animations.
import React from 'react';
import {AbsoluteFill, Img, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {MascotHost} from '../components/MascotHost';
import {StyleCaptions} from '../components/StyleCaptions';
import {evenWordTiming} from '../components/captionPaging';
import {clamp01, hexToRgba, pyhColors, pyhStroke, pyhTiming, pyhType, smoothstep} from '../style/pyhStyle';

export type Box = {left: number; top: number; width: number; height: number};
export type Point = {x: number; y: number};
export type AssetSpec = {file: string; width: number; height: number};

export type MedAnimStep = {
  id: 'B1' | 'B2' | 'B3' | 'B4';
  start: number;
  end: number;
  narration: string;
};

export type LabelSpec = {
  id: string;
  vi: string;
  viLines?: readonly [string, string];
  latin: string;
  start: number;
  end: number;
  at: Point;
  target: Point;
  ring?: {center: Point; rx: number; ry: number};
};

export type PoseBeat = {frame: number; pose: 'welcome' | 'explain' | 'caution' | 'point_up' | 'thumbs_up' | 'myth_bust'};

export const MEDANIM_W = 1920;
export const MEDANIM_H = 1080;
export const MEDANIM_FPS = 30;
export const MEDANIM_DURATION_FRAMES = 1050;
export const MEDANIM_CREDITS_START = 960;
export const MEDANIM_MASCOT_BOX: Box = {left: 20, top: 783, width: 340, height: 297};

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
export const fadeIn = (frame: number, start: number, frames: number = pyhTiming.labelFadeFrames): number =>
  smoothstep((frame - start) / frames);
export const center = (b: Box): Point => ({x: b.left + b.width / 2, y: b.top + b.height / 2});
export const toSvgPath = (pts: readonly Point[]): string => `M${pts.map((p) => `${p.x} ${p.y}`).join(' L')}`;

export const squareAround = (c: Point, size: number): Box => ({
  left: Math.round(c.x - size / 2),
  top: Math.round(c.y - size / 2),
  width: size,
  height: size,
});

export const imageToScreen = (box: Box, asset: AssetSpec, p: Point): Point => ({
  x: box.left + (p.x / asset.width) * box.width,
  y: box.top + (p.y / asset.height) * box.height,
});

export const pathPoint = (path: readonly Point[], t: number): Point => {
  const lengths = path.slice(1).map((p, i) => Math.hypot(p.x - path[i].x, p.y - path[i].y));
  const total = lengths.reduce((a, b) => a + b, 0);
  if (t >= 1) return path[path.length - 1];
  let d = clamp01(t) * total;
  for (let i = 0; i < lengths.length; i++) {
    if (d <= lengths[i] || i === lengths.length - 1) {
      const k = lengths[i] === 0 ? 0 : Math.min(1, d / lengths[i]);
      return {x: lerp(path[i].x, path[i + 1].x, k), y: lerp(path[i].y, path[i + 1].y, k)};
    }
    d -= lengths[i];
  }
  return path[path.length - 1];
};

export const stepCaptionTiming = (step: {start: number; end: number; narration: string}): {firstFrame: number; framesPerWord: number} => {
  const words = step.narration.trim().split(/\s+/).length;
  const firstFrame = 4;
  return {firstFrame, framesPerWord: Math.max(4, Math.floor((step.end - step.start - firstFrame - 8) / words))};
};

export const AssetImage: React.FC<{
  assetDir: string;
  asset: AssetSpec;
  id: string;
  box: Box;
  opacity?: number;
  style?: React.CSSProperties;
}> = ({assetDir, asset, id, box, opacity = 1, style}) => (
  <Img
    src={staticFile(`${assetDir}/${asset.file}`)}
    data-medanim-image={id}
    style={{
      position: 'absolute',
      left: box.left,
      top: box.top,
      width: box.width,
      height: box.height,
      objectFit: 'contain',
      opacity,
      ...style,
    }}
  />
);

export const labelCardSize = (l: {vi: string; viLines?: readonly [string, string]; latin: string}) => {
  const maxViChars = l.viLines
    ? Math.max(...l.viLines.map((line) => Array.from(line).length))
    : Array.from(l.vi).length;
  const linesCount = l.viLines?.length ?? 1;
  return {
    width: Math.ceil(Math.max(maxViChars * pyhType.landscape.label * 0.6, Array.from(l.latin).length * 24 * 0.56) + 52),
    height: Math.round(pyhType.landscape.label * (linesCount > 1 ? 1.18 : 1.25) * linesCount + 24 * 1.3 + 26),
  };
};

export const attachPoint = (card: Box, target: Point): Point => {
  if (target.x > card.left + card.width) return {x: card.left + card.width, y: card.top + card.height / 2};
  if (target.x < card.left) return {x: card.left, y: card.top + card.height / 2};
  return target.y < card.top ? {x: card.left + card.width / 2, y: card.top} : {x: card.left + card.width / 2, y: card.top + card.height};
};

export const LabelCard: React.FC<{
  vi: string;
  viLines?: readonly [string, string];
  latin: string;
  at: Point;
  opacity: number;
  rise?: number;
}> = ({vi, viLines, latin, at, opacity, rise = 0}) => {
  const size = labelCardSize({vi, viLines, latin});
  return (
    <div
      data-medanim-label={vi}
      style={{
        position: 'absolute',
        left: at.x,
        top: at.y,
        ...size,
        boxSizing: 'border-box',
        opacity,
        transform: `translateY(${rise}px) scale(${pyhTiming.labelStartScale + (1 - pyhTiming.labelStartScale) * opacity})`,
        backgroundColor: pyhColors.background,
        border: `${pyhStroke.width}px solid ${pyhColors.ink}`,
        borderRadius: pyhStroke.radius,
        color: pyhColors.ink,
        fontFamily: pyhType.fontFamily,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        whiteSpace: 'nowrap',
      }}
    >
      {(viLines ?? [vi]).map((line, i) => (
        <div key={i} style={{fontWeight: pyhType.labelWeight, fontSize: pyhType.landscape.label, lineHeight: viLines ? 1.18 : 1.2}}>
          {line}
        </div>
      ))}
      <div style={{fontWeight: pyhType.bodyWeight, fontSize: 24, lineHeight: 1.25, fontStyle: 'italic'}}>{latin}</div>
    </div>
  );
};

export const ActiveLabelsOverlay: React.FC<{labels: readonly LabelSpec[]}> = ({labels}) => {
  const frame = useCurrentFrame();
  const label = labels.find((l) => frame >= l.start && frame < l.end);
  if (!label) return null;
  const opacity = fadeIn(frame, label.start) * (1 - clamp01((frame - (label.end - 6)) / 6));
  const size = labelCardSize(label);
  const card = {left: label.at.x, top: label.at.y, ...size};
  const from = attachPoint(card, label.target);
  const draw = clamp01((frame - label.start - 4) / 12);
  return (
    <>
      <svg width={MEDANIM_W} height={MEDANIM_H} style={{position: 'absolute', left: 0, top: 0, pointerEvents: 'none'}} data-medanim-leader={label.id}>
        <path
          d={`M${from.x} ${from.y} L${label.target.x} ${label.target.y}`}
          stroke={pyhColors.ink}
          strokeWidth={4}
          strokeLinecap="round"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - draw}
          opacity={opacity}
        />
        <circle cx={label.target.x} cy={label.target.y} r={10 * draw} fill={pyhColors.alert} stroke={pyhColors.ink} strokeWidth={3} opacity={opacity} />
        {label.ring ? (
          <ellipse
            data-medanim-emphasis={label.id}
            cx={label.ring.center.x}
            cy={label.ring.center.y}
            rx={label.ring.rx}
            ry={label.ring.ry}
            fill="none"
            stroke={pyhColors.accent}
            strokeWidth={pyhStroke.ringWidth}
            pathLength={1}
            strokeDasharray={1}
            strokeDashoffset={1 - draw}
            opacity={opacity}
          />
        ) : null}
      </svg>
      <LabelCard vi={label.vi} viLines={label.viLines} latin={label.latin} at={label.at} opacity={opacity} rise={(1 - opacity) * 8} />
    </>
  );
};

export const MiniMapPillBar: React.FC<{
  assetDir: string;
  levels: readonly {label: string; asset: AssetSpec}[];
  activeIndex: number;
  hideAfterFrame: number;
}> = ({assetDir, levels, activeIndex, hideAfterFrame}) => {
  const frame = useCurrentFrame();
  if (frame >= hideAfterFrame) return null;
  return (
    <div
      data-mini-map="true"
      style={{
        position: 'absolute',
        right: 38,
        top: 16,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 16px',
        border: `2px solid ${pyhColors.accent}`,
        borderRadius: 12,
        backgroundColor: pyhColors.background,
        fontFamily: pyhType.fontFamily,
        fontSize: 28,
        color: pyhColors.ink,
      }}
    >
      {levels.map((item, i) => {
        const active = i === activeIndex;
        return (
          <React.Fragment key={item.label}>
            {i > 0 ? <span aria-hidden="true" style={{opacity: 0.55}}>→</span> : null}
            <span
              data-mini-map-step={item.label}
              data-active-step={active ? 'true' : undefined}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: active ? '4px 14px' : '4px 8px',
                borderRadius: 999,
                backgroundColor: active ? hexToRgba(pyhColors.accent, 0.24) : 'transparent',
                border: active ? `2px solid ${pyhColors.accent}` : '2px solid transparent',
                fontWeight: active ? 800 : 600,
                opacity: active ? 1 : 0.72,
              }}
            >
              <Img src={staticFile(`${assetDir}/${item.asset.file}`)} style={{width: 32, height: 32, objectFit: 'contain'}} />
              {item.label}
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
};

export const LegendCard: React.FC<{
  box: {left: number; top: number};
  items: readonly {label: string; color: string; startFrame: number}[];
  opacity?: number;
}> = ({box, items, opacity = 1}) => {
  const frame = useCurrentFrame();
  return (
    <div
      data-medanim-legend="true"
      style={{
        position: 'absolute',
        left: box.left,
        top: box.top,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        padding: '10px 18px',
        border: `${pyhStroke.width}px solid ${pyhColors.ink}`,
        borderRadius: pyhStroke.radius,
        backgroundColor: pyhColors.background,
        fontFamily: pyhType.fontFamily,
        fontWeight: pyhType.labelWeight,
        fontSize: pyhType.landscape.label,
        color: pyhColors.ink,
        opacity,
      }}
    >
      {items.map((it) => (
        <div key={it.label} style={{display: 'flex', alignItems: 'center', gap: 14, opacity: fadeIn(frame, it.startFrame)}}>
          <span
            style={{
              width: 28,
              height: 28,
              borderRadius: 14,
              backgroundColor: it.color,
              border: `3px solid ${pyhColors.ink}`,
              flexShrink: 0,
            }}
          />
          {it.label}
        </div>
      ))}
    </div>
  );
};

export const MechanismCreditsScene: React.FC<{
  attribution: readonly string[];
  literature: readonly string[];
}> = ({attribution, literature}) => {
  const frame = useCurrentFrame();
  const text = {fontFamily: pyhType.fontFamily, color: pyhColors.ink} as const;
  return (
    <AbsoluteFill data-medanim-scene="credits" style={{backgroundColor: pyhColors.background, opacity: fadeIn(frame, 0)}}>
      <div style={{position: 'absolute', left: 410, top: 72, width: 1430}}>
        <div data-medanim-title="true" style={{...text, fontWeight: pyhType.titleWeight, fontSize: pyhType.landscape.title}}>
          Nguồn hình và y văn
        </div>
        <div style={{...text, fontWeight: pyhType.bodyWeight, fontSize: 28, lineHeight: 1.42, marginTop: 22}}>
          {attribution.map((l) => <div key={l}>{l}</div>)}
        </div>
        <div style={{...text, fontWeight: pyhType.bodyWeight, fontSize: 26, lineHeight: 1.42, marginTop: 24}}>
          {literature.map((l) => <div key={l}>{l}</div>)}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const MedAnimChrome: React.FC<{
  steps: readonly MedAnimStep[];
  glossary: readonly string[];
  labels: readonly LabelSpec[];
  openingPoses: readonly PoseBeat[];
  closingPoses: readonly PoseBeat[];
  creditsStart: number;
  totalFrames: number;
  attribution: readonly string[];
  literature: readonly string[];
}> = ({steps, glossary, labels, openingPoses, closingPoses, creditsStart, totalFrames, attribution, literature}) => {
  const frame = useCurrentFrame();
  const lastStep = steps[steps.length - 1];
  return (
    <>
      <ActiveLabelsOverlay labels={labels} />
      {frame >= creditsStart ? (
        <Sequence from={creditsStart}>
          <MechanismCreditsScene attribution={attribution} literature={literature} />
        </Sequence>
      ) : null}
      <Sequence from={0} durationInFrames={steps[0].end} name="Mascot mở">
        <MascotHost box={MEDANIM_MASCOT_BOX} track={openingPoses} speakingUntil={steps[0].end} />
      </Sequence>
      <Sequence from={lastStep.start} durationInFrames={totalFrames - lastStep.start} name="Mascot kết">
        <MascotHost box={MEDANIM_MASCOT_BOX} track={closingPoses} speakingUntil={lastStep.end - lastStep.start} />
      </Sequence>
      {steps.map((step) => {
        const {firstFrame, framesPerWord} = stepCaptionTiming(step);
        const words = evenWordTiming(step.narration, firstFrame, framesPerWord);
        return (
          <Sequence key={step.id} from={step.start} durationInFrames={step.end - step.start} name={`Phụ đề ${step.id}`}>
            <StyleCaptions
              text={step.narration}
              durationInFrames={step.end - step.start}
              words={words}
              glossary={glossary}
              previousText={steps.filter((s) => s.start < step.start).map((s) => s.narration).join(' ')}
              labelWindows={labels.map((l) => ({term: l.vi, start: l.start - step.start, end: l.end - step.start}))}
            />
          </Sequence>
        );
      })}
    </>
  );
};
