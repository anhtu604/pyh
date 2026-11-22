import type {AnatomySubject} from '../anatomy/registry';
import type {ScaleSurface} from '../anatomy/entityColors';
import type {Box} from '../layout';
import type {Scene} from '../types';

export type ScaleLevel = 'organ' | 'tissue' | 'cell' | 'molecule';

export type ScaleLevelMeta = {
  readonly id: ScaleLevel;
  readonly order: number;
  readonly labelVi: string;
  readonly scaleText: string;
  readonly defaultSurface: ScaleSurface;
  /** Baseline log-zoom multiplier relative to organ = 1.0. */
  readonly baseZoom: number;
};

export const SCALE_LEVELS: readonly ScaleLevelMeta[] = [
  {id: 'organ', order: 0, labelVi: 'Cơ quan', scaleText: '~10 cm', defaultSurface: 'off_white', baseZoom: 1.0},
  {id: 'tissue', order: 1, labelVi: 'Mô / Đơn vị', scaleText: '~1 mm', defaultSurface: 'off_white', baseZoom: 1.16},
  {id: 'cell', order: 2, labelVi: 'Tế bào', scaleText: '~20 µm', defaultSurface: 'night', baseZoom: 1.32},
  {id: 'molecule', order: 3, labelVi: 'Phân tử', scaleText: '~10 nm', defaultSurface: 'night', baseZoom: 1.48},
] as const;

export const SCALE_LEVEL_MAP: Readonly<Record<ScaleLevel, ScaleLevelMeta>> = {
  organ: SCALE_LEVELS[0],
  tissue: SCALE_LEVELS[1],
  cell: SCALE_LEVELS[2],
  molecule: SCALE_LEVELS[3],
};

/**
 * Editable mapping from each registered anatomy subject to its primary Scale Zoom tier.
 */
export const SUBJECT_SCALE_LEVEL: Readonly<Record<AnatomySubject, ScaleLevel>> = {
  // Organ level (~10 cm)
  liver_organ: 'organ',
  heart: 'organ',
  gout_foot_overview: 'organ',
  alt_ast_tissue_distribution: 'organ',
  esophagus_aortic_arch_impaction: 'organ',
  esophagus_food_bolus: 'organ',
  esophagus_transverse_impaction: 'organ',

  // Tissue / structural unit level (~1 mm)
  liver_lobule: 'tissue',
  artery_cross_section: 'tissue',
  hepatic_fibrosis_section: 'tissue',
  muscle_wasting_section: 'tissue',
  esophagus_wall_penetration: 'tissue',
  intestinal_vitamin_c_absorption: 'tissue',
  renal_tubule_oxalate: 'tissue',

  // Cellular level (~20 µm)
  hepatocyte_sinusoid_unit: 'cell',
  hepatic_toxic_injury: 'cell',
  hepatic_synthesis_and_bile: 'cell',
  hepatic_cell_and_tissue_lipid_balance: 'cell',
  immune_cell_alarm: 'cell',
  tumor_protein_uptake: 'cell',
  muscle_protein_turnover: 'cell',
  muscle_tumor_amino_acid_balance: 'cell',
  vitamin_c_transport: 'cell',
  joint_fluid_urate_to_inflammation: 'cell',

  // Molecular / crystal / enzyme level (~10 nm)
  calcium_oxalate_crystal: 'molecule',
  vitamin_c_oxalate_pathway: 'molecule',
  urate_crystal_close_up: 'molecule',
  urate_deposition: 'molecule',
};

/** Focus region hints that refine the active tier within a scene. */
export const FOCUS_LEVEL_OVERRIDES: Readonly<Record<string, ScaleLevel>> = {
  right_lobe: 'organ',
  left_lobe: 'organ',
  central_vein: 'tissue',
  portal_triad: 'tissue',
  lobule: 'tissue',
  scar: 'tissue',
  cell: 'cell',
  mitochondria: 'cell',
  membrane: 'cell',
  sinusoid: 'cell',
  blood: 'cell',
  bile: 'molecule',
  enzyme: 'molecule',
  alt: 'molecule',
  ast: 'molecule',
  crystal: 'molecule',
  molecule: 'molecule',
};

/** Action hints that refine the active tier when a beat triggers a molecular event. */
export const ACTION_LEVEL_OVERRIDES: Readonly<Record<string, ScaleLevel>> = {
  leak: 'molecule',
  toxic: 'molecule',
  export: 'molecule',
  seed: 'molecule',
  grow: 'molecule',
  deposit: 'molecule',
  cell: 'cell',
  scar: 'tissue',
  block: 'tissue',
};

/** Transition duration between Scale Zoom tiers/beats (18-30 frames at 30 fps). */
export const SCALE_TRANSITION_FRAMES = 24;
/** Maximum hold before an automatic sub-beat ensures meaningful visual change (< 5s at 30fps). */
export const MAX_STATIC_HOLD_FRAMES = 140;

export const resolveScaleLevel = (
  subject: AnatomySubject,
  focus?: string | null,
  action?: string | null,
): ScaleLevel => {
  if (action && ACTION_LEVEL_OVERRIDES[action]) {
    return ACTION_LEVEL_OVERRIDES[action];
  }
  if (focus && focus !== 'overview' && FOCUS_LEVEL_OVERRIDES[focus]) {
    return FOCUS_LEVEL_OVERRIDES[focus];
  }
  return SUBJECT_SCALE_LEVEL[subject] ?? 'organ';
};

/** Pure surface selector: organ/tissue scenes use off_white; cell/molecule scenes use night. */
export const resolveScaleSurface = (level: ScaleLevel): ScaleSurface =>
  SCALE_LEVEL_MAP[level].defaultSurface;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));

export const easeInOutCubic = (t: number): number => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};

/** Logarithmic zoom interpolation (perceptually constant zoom speed, zero rotation). */
export const logZoomInterpolate = (fromZoom: number, toZoom: number, t: number): number => {
  const safeFrom = Math.max(0.25, fromZoom);
  const safeTo = Math.max(0.25, toZoom);
  const e = easeInOutCubic(t);
  return Math.exp(Math.log(safeFrom) + (Math.log(safeTo) - Math.log(safeFrom)) * e);
};

/** Normalized handoff point where outgoing layer finishes fading out and incoming layer begins entering. */
export const LAYER_HANDOFF_T = 0.44;

export type LayerTransitionMetrics = {
  readonly t: number;
  readonly handedOff: boolean;
  readonly outgoingOpacity: number;
  readonly incomingOpacity: number;
  readonly outgoingZoom: number;
  readonly outgoingPanProgress: number;
  readonly incomingScale: number;
};

const smoothstep01 = (v: number): number => {
  const x = clamp01(v);
  return x * x * (3 - 2 * x);
};

/**
 * Sequential log-zoom layer transition:
 * - Outgoing layer zooms logarithmically into the target region and fades out completely
 *   BEFORE handoff (t = LAYER_HANDOFF_T).
 * - Incoming layer enters ONLY after handoff, scaling logarithmically from small -> 1.0
 *   at the same screen center.
 * Guarantees outgoing and incoming layers are never simultaneously opaque (zero ghost overlap).
 */
export const computeLayerTransition = (rawT: number): LayerTransitionMetrics => {
  const t = clamp01(rawT);
  const handedOff = t >= LAYER_HANDOFF_T;

  const exitU = clamp01(t / LAYER_HANDOFF_T);
  const outgoingPanProgress = easeInOutCubic(exitU);
  const outgoingZoom = Math.exp(Math.log(3.8) * Math.pow(exitU, 1.55));
  const outgoingOpacity =
    t <= 0.2
      ? 1
      : t >= LAYER_HANDOFF_T
        ? 0
        : 1 - smoothstep01((t - 0.2) / (LAYER_HANDOFF_T - 0.2));

  const enterU = clamp01((t - LAYER_HANDOFF_T) / (1 - LAYER_HANDOFF_T));
  const enterEase = 1 - Math.pow(1 - enterU, 3);
  const incomingScale = Math.exp(Math.log(0.46) * (1 - enterEase));
  const incomingOpacity =
    t <= LAYER_HANDOFF_T
      ? 0
      : t >= 0.6
        ? 1
        : 1 - Math.pow(1 - (t - LAYER_HANDOFF_T) / (0.6 - LAYER_HANDOFF_T), 2.2);

  return {
    t,
    handedOff,
    outgoingOpacity,
    incomingOpacity,
    outgoingZoom,
    outgoingPanProgress,
    incomingScale,
  };
};

export type ScaleZoomBeat = {
  readonly startFrame: number;
  readonly focus: string | null;
  readonly action: string | null;
  readonly level: ScaleLevel;
  readonly primaryLabelId: string | null;
  readonly labelIds: readonly string[];
  readonly zoomBoost: number;
};

/**
 * Build a deterministic beat timeline where every segment <= MAX_STATIC_HOLD_FRAMES (~4.67s)
 * has a meaningful visual change (level/zoom/label/highlight).
 */
export const planScaleZoomBeats = (
  scene: Scene,
  availableFocusKeys: readonly string[],
  availableLabelKeys: readonly string[],
): readonly ScaleZoomBeat[] => {
  if (!scene.anatomy) return [];
  const subject = scene.anatomy.subject;
  const duration = Math.max(1, scene.duration_frames);
  const baseLevel = SUBJECT_SCALE_LEVEL[subject];

  const authored = (scene.beats ?? [])
    .filter((b) => b.start_frame !== undefined && b.start_frame < duration)
    .sort((a, b) => (a.start_frame ?? 0) - (b.start_frame ?? 0));

  const focusPool = availableFocusKeys.filter((k) => k !== 'overview');
  const rawBeats: ScaleZoomBeat[] = [];

  if (authored.length > 0) {
    if ((authored[0].start_frame ?? 0) > 0) {
      rawBeats.push({
        startFrame: 0,
        focus: 'overview',
        action: null,
        level: baseLevel,
        primaryLabelId: availableLabelKeys[0] ?? null,
        labelIds: availableLabelKeys.slice(0, 1),
        zoomBoost: 1.0,
      });
    }
    authored.forEach((beat, idx) => {
      const labels = (beat.labels ?? []).slice(0, 6);
      const level = resolveScaleLevel(subject, beat.focus, beat.action);
      rawBeats.push({
        startFrame: beat.start_frame ?? 0,
        focus: beat.focus ?? null,
        action: beat.action ?? null,
        level,
        primaryLabelId: labels[0] ?? availableLabelKeys[idx % Math.max(1, availableLabelKeys.length)] ?? null,
        labelIds: labels.length ? labels : availableLabelKeys.slice(0, 1),
        zoomBoost: 1 + (idx % 3) * 0.14,
      });
    });
  } else {
    // Synthesize beats so even un-beated scenes step meaningfully across focus/labels/zoom.
    const stepCount = Math.max(2, Math.ceil(duration / MAX_STATIC_HOLD_FRAMES));
    const stepFrames = Math.max(30, Math.floor(duration / stepCount));
    const zoomSteps = [1.0, 1.24, 1.48, 1.18];
    for (let i = 0; i < stepCount; i++) {
      const startFrame = i * stepFrames;
      if (startFrame >= duration) break;
      const focus = i === 0 ? 'overview' : focusPool.length ? focusPool[(i - 1) % focusPool.length] : 'overview';
      const primaryLabelId = availableLabelKeys.length ? availableLabelKeys[i % availableLabelKeys.length] : null;
      const level = resolveScaleLevel(subject, focus, null);
      rawBeats.push({
        startFrame,
        focus,
        action: null,
        level,
        primaryLabelId,
        labelIds: primaryLabelId ? [primaryLabelId] : [],
        zoomBoost: zoomSteps[i % zoomSteps.length],
      });
    }
  }

  // Subdivide any gap exceeding MAX_STATIC_HOLD_FRAMES so no 5-second window is ever static.
  const subdivided: ScaleZoomBeat[] = [];
  for (let i = 0; i < rawBeats.length; i++) {
    const current = rawBeats[i];
    subdivided.push(current);
    const nextStart = i + 1 < rawBeats.length ? rawBeats[i + 1].startFrame : duration;
    let cursor = current.startFrame + MAX_STATIC_HOLD_FRAMES;
    let subIdx = 1;
    while (cursor < nextStart - 24) {
      const nextFocus = focusPool.length
        ? focusPool[(i + subIdx) % focusPool.length]
        : current.focus;
      const nextLabel = availableLabelKeys.length
        ? availableLabelKeys[(i + subIdx) % availableLabelKeys.length]
        : current.primaryLabelId;
      const nextLevel = resolveScaleLevel(subject, nextFocus, current.action);
      subdivided.push({
        startFrame: cursor,
        focus: nextFocus,
        action: current.action,
        level: nextLevel,
        primaryLabelId: nextLabel,
        labelIds: nextLabel ? [nextLabel] : current.labelIds,
        zoomBoost: current.zoomBoost * (subIdx % 2 === 1 ? 1.22 : 0.92),
      });
      cursor += MAX_STATIC_HOLD_FRAMES;
      subIdx += 1;
    }
  }

  return subdivided;
};

export type ScaleZoomCamera = {
  readonly zoom: number;
  readonly x: number;
  readonly y: number;
  readonly origin: '0% 0%';
};

export type ScaleZoomState = {
  readonly level: ScaleLevel;
  readonly previousLevel: ScaleLevel;
  readonly transitionProgress: number;
  readonly surface: ScaleSurface;
  readonly camera: ScaleZoomCamera;
  readonly fromCamera: ScaleZoomCamera;
  readonly activeBeatIndex: number;
  readonly activeBeat: ScaleZoomBeat | null;
  readonly beats: readonly ScaleZoomBeat[];
};

const computePoseForBeat = (
  beat: ScaleZoomBeat,
  regions: Record<string, Box>,
  view: Box,
  subjectBox: Box,
  viewport: Box,
): {zoom: number; x: number; y: number} => {
  const s = Math.min(subjectBox.width / view.width, subjectBox.height / view.height);
  const offsetX = subjectBox.left - viewport.left + (subjectBox.width - view.width * s) / 2;
  const offsetY = subjectBox.top - viewport.top + (subjectBox.height - view.height * s) / 2;

  const region = beat.focus && regions[beat.focus] ? regions[beat.focus] : view;
  const left = offsetX + (region.left - view.left) * s;
  const top = offsetY + (region.top - view.top) * s;
  const width = Math.max(1, region.width * s);
  const height = Math.max(1, region.height * s);

  const fitZoom = Math.min((viewport.width * 0.84) / width, (viewport.height * 0.84) / height);
  const targetZoom = Math.max(1.0, Math.min(1.95, Math.min(fitZoom, 1.0) * beat.zoomBoost + Math.max(0, fitZoom - 1) * 0.55));
  const cx = left + width / 2;
  const cy = top + height / 2;
  const x = ((viewport.width / 2 - cx * targetZoom) / viewport.width) * 100;
  const y = ((viewport.height / 2 - cy * targetZoom) / viewport.height) * 100;
  return {zoom: targetZoom, x, y};
};

export const computeScaleZoomState = (
  scene: Scene,
  frame: number,
  regions: Record<string, Box>,
  view: Box,
  subjectBox: Box,
  viewport: Box,
  availableLabelKeys: readonly string[],
): ScaleZoomState => {
  const beats = planScaleZoomBeats(scene, Object.keys(regions), availableLabelKeys);
  const baseLevel: ScaleLevel = scene.anatomy ? SUBJECT_SCALE_LEVEL[scene.anatomy.subject] : 'organ';
  const sceneSurface = resolveScaleSurface(baseLevel);

  if (!beats.length) {
    return {
      level: baseLevel,
      previousLevel: baseLevel,
      transitionProgress: 1,
      surface: sceneSurface,
      camera: {zoom: 1, x: 0, y: 0, origin: '0% 0%'},
      fromCamera: {zoom: 1, x: 0, y: 0, origin: '0% 0%'},
      activeBeatIndex: 0,
      activeBeat: null,
      beats: [],
    };
  }

  let activeIdx = 0;
  for (let i = 0; i < beats.length; i++) {
    if (beats[i].startFrame <= frame) activeIdx = i;
  }
  const activeBeat = beats[activeIdx];
  const prevBeat = activeIdx > 0 ? beats[activeIdx - 1] : activeBeat;

  // Compute interrupted-safe log-zoom camera trajectory across all beats up to frame.
  let fromPose = computePoseForBeat(beats[0], regions, view, subjectBox, viewport);
  let targetPose = fromPose;
  let start = beats[0].startFrame;

  const mixAt = (at: number): {zoom: number; x: number; y: number} => {
    const t = clamp01((at - start) / SCALE_TRANSITION_FRAMES);
    const e = easeInOutCubic(t);
    return {
      zoom: logZoomInterpolate(fromPose.zoom, targetPose.zoom, t),
      x: fromPose.x + (targetPose.x - fromPose.x) * e,
      y: fromPose.y + (targetPose.y - fromPose.y) * e,
    };
  };

  for (let i = 1; i <= activeIdx; i++) {
    fromPose = mixAt(beats[i].startFrame);
    targetPose = computePoseForBeat(beats[i], regions, view, subjectBox, viewport);
    start = beats[i].startFrame;
  }

  const baseCamera = mixAt(frame);
  const transitionProgress = activeIdx === 0 ? 1 : clamp01((frame - activeBeat.startFrame) / SCALE_TRANSITION_FRAMES);

  // Subtle living push during settled holds so camera stays smoothly alive without jumping.
  const holdFrames = Math.max(0, frame - activeBeat.startFrame);
  const subtlePush = Math.exp(Math.min(1, holdFrames / 120) * Math.log(1.035));
  const finalZoom = baseCamera.zoom * subtlePush;
  const cxOffset = (finalZoom / baseCamera.zoom - 1) * 50;

  return {
    level: activeBeat.level,
    previousLevel: prevBeat.level,
    transitionProgress,
    surface: resolveScaleSurface(activeBeat.level),
    camera: {
      zoom: finalZoom,
      x: baseCamera.x - cxOffset,
      y: baseCamera.y - cxOffset,
      origin: '0% 0%',
    },
    fromCamera: {
      zoom: fromPose.zoom,
      x: fromPose.x,
      y: fromPose.y,
      origin: '0% 0%',
    },
    activeBeatIndex: activeIdx,
    activeBeat,
    beats,
  };
};
