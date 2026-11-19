// Progressive diagram build: each beat adds exactly one element; the speaking element is emphasised,
// everything else drops 40% in strength.
import {clamp01, pyhTiming, smoothstep} from './pyhStyle';

export type BuildKind = 'organ' | 'arrow' | 'label' | 'flow';
/** Frames the flow step takes to carry every enzyme dot from cell to vessel. */
export const FLOW_FRAMES = 54;
export type Emphasis = {type: 'ring'; cx: number; cy: number; rx: number; ry: number} | {type: 'underline'};
export type BuildStep = {id: string; kind: BuildKind; start: number; emphasis?: Emphasis};

/** Steps sorted by start; throws if two elements share a beat (one element per beat). */
export const validateBuild = (steps: readonly BuildStep[]): BuildStep[] => {
  const sorted = [...steps].sort((a, b) => a.start - b.start);
  sorted.forEach((step, i) => {
    if (i > 0 && sorted[i - 1].start === step.start) throw new Error(`Build beat ${step.start} adds more than one element`);
  });
  return sorted;
};

export const stepDuration = (kind: BuildKind): number =>
  kind === 'arrow' ? pyhTiming.arrowDrawFrames : kind === 'flow' ? FLOW_FRAMES : pyhTiming.labelFadeFrames;

/** 0..1 progress of a step's entrance (arrow: stroke draw, others: fade-up). */
export const stepProgress = (step: BuildStep, frame: number): number =>
  clamp01((frame - step.start) / stepDuration(step.kind));

export const startedSteps = (steps: readonly BuildStep[], frame: number): BuildStep[] =>
  steps.filter((step) => frame >= step.start);

/** The element being spoken about: the latest step that has started. */
export const activeStep = (steps: readonly BuildStep[], frame: number): BuildStep | undefined => {
  const started = startedSteps(steps, frame);
  return started[started.length - 1];
};

/** Opacity of an element: hidden before its beat, full while active, 60% afterwards. */
export const stepOpacity = (steps: readonly BuildStep[], id: string, frame: number): number => {
  const step = steps.find((s) => s.id === id);
  if (!step || frame < step.start) return 0;
  const entrance = step.kind === 'arrow' ? 1 : smoothstep(stepProgress(step, frame));
  const active = activeStep(steps, frame)?.id === id;
  return entrance * (active ? 1 : pyhTiming.dimOpacity);
};

/** Label fade-up: scale 0.95 → 1.0 and a short rise over the same 12 frames. */
export const labelTransform = (step: BuildStep, frame: number): {scale: number; rise: number} => {
  const t = smoothstep(stepProgress(step, frame));
  return {scale: pyhTiming.labelStartScale + (1 - pyhTiming.labelStartScale) * t, rise: (1 - t) * 8};
};

/** Stroke-dashoffset fraction (1 = undrawn, 0 = fully drawn) of an arrow. */
export const arrowDashOffset = (step: BuildStep, frame: number): number => 1 - stepProgress(step, frame);

/** Only one label is lit at a time: a label fades out over 12 frames once the next label starts. */
export const exclusiveLabelOpacity = (steps: readonly BuildStep[], id: string, frame: number): number => {
  const labels = steps.filter((s) => s.kind === 'label');
  const index = labels.findIndex((s) => s.id === id);
  if (index < 0 || frame < labels[index].start) return 0;
  const enter = smoothstep(stepProgress(labels[index], frame));
  const next = labels[index + 1];
  return next ? enter * (1 - smoothstep((frame - next.start) / pyhTiming.labelFadeFrames)) : enter;
};

/** 0..1 progress of the enzyme flow (drives the `leak` cue of the hepatocyte diagram). */
export const flowProgress = (step: BuildStep, frame: number): number => clamp01((frame - step.start) / FLOW_FRAMES);

/** Straight leader from a label edge to its target point, drawn over 12 frames (1 = undrawn). */
export const leaderDashOffset = (step: BuildStep, frame: number): number => 1 - smoothstep(stepProgress(step, frame));
