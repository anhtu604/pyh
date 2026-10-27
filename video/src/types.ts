import {z} from 'zod';
import {FORMAT_SIZES} from './format';
import anatomyLibrary from './anatomy/library.json';

const unitCoordinate = z.number().min(0).max(1);

const safeRelativePath = z.string().regex(/^(?!\.?\/?$)(?![A-Za-z]:)(?!\/)(?!.*\\)(?!.*(?:^|\/)\.\.(?:\/|$))\S+$/);

export const VisualAssetRefSchema = z
  .object({
    path: safeRelativePath,
    role: z.enum(['whiteboard', 'mascot', 'brand', 'chart']),
    pose: z.enum(['welcome', 'explain', 'caution', 'point_up', 'thinking', 'surprised', 'thumbs_up', 'blank_board', 'myth_bust']).nullable().optional(),
  })
  .superRefine((asset, context) => {
    if (asset.role === 'mascot' && !asset.pose) {
      context.addIssue({code: 'custom', path: ['pose'], message: 'mascot requires pose'});
    }
    if (asset.role !== 'mascot' && asset.pose) {
      context.addIssue({code: 'custom', path: ['pose'], message: `${asset.role} cannot have pose`});
    }
  });

export const EvidenceHighlightSchema = z
  .object({
    schema_version: z.string().default('1.0'),
    image: z.string().regex(/\S/),
    quote: z.string().regex(/\S/),
    x: unitCoordinate,
    y: unitCoordinate,
    width: unitCoordinate,
    height: unitCoordinate,
    source_id: z.string().nullable().optional(),
    page: z.number().int().positive().nullable().optional(),
    crop_x: unitCoordinate.nullable().optional(),
    crop_y: unitCoordinate.nullable().optional(),
    crop_width: unitCoordinate.nullable().optional(),
    crop_height: unitCoordinate.nullable().optional(),
    crop_pixel_width: z.number().int().positive().nullable().optional(),
    crop_pixel_height: z.number().int().positive().nullable().optional(),
  })
  .superRefine((highlight, context) => {
    if (highlight.x + highlight.width > 1) {
      context.addIssue({
        code: 'custom',
        path: ['width'],
        message: 'Evidence highlight x + width must be at most 1',
      });
    }
    if (highlight.y + highlight.height > 1) {
      context.addIssue({
        code: 'custom',
        path: ['height'],
        message: 'Evidence highlight y + height must be at most 1',
      });
    }
    if ((highlight.source_id == null) !== (highlight.page == null)) {
      context.addIssue({code: 'custom', path: ['page'], message: 'source_id and page must be paired'});
    }
    const crop = [highlight.crop_x, highlight.crop_y, highlight.crop_width, highlight.crop_height,
      highlight.crop_pixel_width, highlight.crop_pixel_height];
    if (crop.some((value) => value !== null && value !== undefined)) {
      if (crop.some((value) => value === null || value === undefined) ||
          !highlight.crop_width || !highlight.crop_height ||
          highlight.crop_x === null || highlight.crop_x === undefined ||
          highlight.crop_y === null || highlight.crop_y === undefined ||
          highlight.crop_x + highlight.crop_width > 1 ||
          highlight.crop_y + highlight.crop_height > 1 ||
          highlight.x < highlight.crop_x || highlight.y < highlight.crop_y ||
          highlight.x + highlight.width > highlight.crop_x + highlight.crop_width + 1e-9 ||
          highlight.y + highlight.height > highlight.crop_y + highlight.crop_height + 1e-9) {
        context.addIssue({code: 'custom', path: ['crop_width'], message: 'highlight must be contained within complete crop'});
      }
    }
  });

type LibrarySubject = keyof typeof anatomyLibrary.components;
const anatomySubjects = Object.keys(anatomyLibrary.components) as [LibrarySubject, ...LibrarySubject[]];
if (anatomySubjects.length === 0) throw new Error('Anatomy library must contain at least one subject');

export const AnatomySchema = z.object({
  subject: z.enum(anatomySubjects, {error: 'Unsupported anatomy subject'}),
  state: z.enum(['normal', 'diseased']),
  severity: z.number().min(0).max(1),
  motion: z.string(),
  cues: z.array(z.object({word: z.string().trim().min(1), action: z.string().trim().min(1),
    start_frame: z.number().int().min(0).optional()})).optional(),
});
export type Anatomy = z.input<typeof AnatomySchema>;
export const MECHANISM_VISUALS = ['anatomy_animation', 'process_animation', 'comparison', 'timelapse'] as const;
export const isMechanismVisual = (visual: string): boolean =>
  (MECHANISM_VISUALS as readonly string[]).includes(visual);

export const SourceCardSchema = z.object({
  source_id: z.string().trim().min(1),
  title: z.string().trim().min(1),
  journal: z.string().trim().min(1),
  year: z.number().int().positive().nullable(),
  pmid: z.string().trim().min(1).nullable(),
  doi: z.string().trim().min(1).nullable(),
  interpretation: z.string().trim().min(1),
});

export const BeatSchema = z.object({
  at: z.union([z.string().trim().min(1), z.number().finite().nonnegative()]),
  focus: z.string().trim().min(1).nullable().optional(),
  labels: z.array(z.string().trim().min(1)).max(6).default([]),
  action: z.string().trim().min(1).nullable().optional(),
  start_frame: z.number().int().nonnegative().optional(),
});
export type SceneBeat = z.input<typeof BeatSchema>;

const normalizeWord = (text: string): string =>
  text.normalize('NFC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

export const phraseInNarration = (phrase: string, narration: string): boolean => {
  const nTokens = narration.split(/\s+/).map(normalizeWord).filter(Boolean);
  const pTokens = phrase.split(/\s+/).map(normalizeWord).filter(Boolean);
  if (pTokens.length === 0 || pTokens.length > nTokens.length) return false;
  for (let i = 0; i <= nTokens.length - pTokens.length; i++) {
    if (pTokens.every((tok, j) => nTokens[i + j] === tok)) return true;
  }
  return false;
};

export const MOTION_EMPHASIS_KINDS = [
  'marker-underline-title',
  'lead-word-zoom-assemble',
  'outline-word-fill',
  'title-demote-to-label',
  'scan-bracket-sweep',
  'scanline-annotate-focus',
  'spotlight-sweep-moves',
] as const;

export const MOTION_TRANSITION_KINDS = [
  'circle-match-iris',
  'wipe-transitions',
  'crash-zoom-punch',
] as const;

export const SceneMotionSchema = z
  .object({
    emphasis: z.enum(MOTION_EMPHASIS_KINDS).nullable().optional(),
    emphasis_text: z.string().trim().min(1).nullable().optional(),
    transition_in: z.enum(MOTION_TRANSITION_KINDS).nullable().optional(),
  })
  .superRefine((motion, context) => {
    if (!motion.emphasis && !motion.transition_in) {
      context.addIssue({
        code: 'custom',
        path: ['emphasis'],
        message: 'motion requires emphasis or transition_in',
      });
    }
    if (motion.emphasis_text && !motion.emphasis) {
      context.addIssue({
        code: 'custom',
        path: ['emphasis_text'],
        message: 'emphasis_text requires emphasis',
      });
    }
  });
export type SceneMotion = z.input<typeof SceneMotionSchema>;

export const StatGaugeSchema = z.object({
  value: z.union([
    z.number().finite(),
    z.string().trim().min(1).refine((v) => /\d/.test(v), 'stat_gauge string value must contain a digit'),
  ]),
  unit: z.string().trim().min(1),
  label: z.string().trim().min(1),
  max_value: z.number().positive().nullable().optional(),
  variant: z
    .enum(['gauge-readout-moves', 'chart-live-moves', 'timeline-travel'])
    .default('gauge-readout-moves'),
});
export type StatGauge = z.input<typeof StatGaugeSchema>;

export const KineticTermSchema = z.object({
  term: z.string().trim().min(1),
  definition: z.string().trim().min(1),
  variant: z
    .enum(['lead-word-zoom-assemble', 'outline-word-fill', 'marker-underline-title', 'title-demote-to-label'])
    .default('lead-word-zoom-assemble'),
});
export type KineticTerm = z.input<typeof KineticTermSchema>;

export const SceneSchema = z
  .object({
    schema_version: z.string().default('1.0'),
    id: z.string(),
    start_frame: z.number().int().min(0),
    duration_frames: z.number().int().positive(),
    narration: z.string(),
    words: z.array(z.object({text: z.string(), start_frame: z.number().int().min(0),
      end_frame: z.number().int().min(0)}).refine(word => word.end_frame >= word.start_frame,
      'word end must follow start')).optional(),
    beats: z.array(BeatSchema).optional(),
    entrances: z.array(z.object({text: z.string(), start_frame: z.number().int().min(0)})).optional(),
    on_screen_text: z.string().refine((text) => Array.from(text).length <= 90,
      'on_screen_text must be at most 90 Unicode characters').nullable().optional(),
    script_line_id: z.string().nullable().optional(),
    claim_id: z.string().nullable().optional(),
    chapter_id: z.string().regex(/^CH\d{2}$/).nullable().optional(),
    source_marker: z.string().regex(/\S/).nullable().optional(),
    visual: z.enum(['whiteboard', 'chart', 'evidence_highlight', 'source_card', 'brand_outro', 'stat_gauge', 'kinetic_term', ...MECHANISM_VISUALS]),
    anatomy: AnatomySchema.optional(),
    explainer_layer_id: z.string().optional(),
    evidence_highlight: EvidenceHighlightSchema.nullable().optional(),
    source_card: SourceCardSchema.nullable().optional(),
    stat_gauge: StatGaugeSchema.nullable().optional(),
    kinetic_term: KineticTermSchema.nullable().optional(),
    motion: SceneMotionSchema.nullable().optional(),
    visual_assets: z.array(VisualAssetRefSchema).default([]),
  })
  .superRefine((scene, context) => {
    if (isMechanismVisual(scene.visual) && !scene.anatomy) {
      context.addIssue({code: 'custom', path: ['anatomy'], message: `${scene.visual} requires anatomy`});
    }
    if (scene.beats?.length) {
      const metadata = scene.anatomy ? anatomyLibrary.components[scene.anatomy.subject] : undefined;
      const info = metadata as unknown as {focus_regions?: Record<string, unknown>; labels?: Record<string, unknown>};
      scene.beats.forEach((beat, index) => {
        if (!scene.anatomy || (beat.focus && !info?.focus_regions?.[beat.focus])) {
          context.addIssue({code: 'custom', path: ['beats', index, 'focus'], message: 'beat focus must exist in component'});
        }
        if (new Set(beat.labels).size !== beat.labels.length || beat.labels.some(label => !info?.labels?.[label])) {
          context.addIssue({code: 'custom', path: ['beats', index, 'labels'], message: 'beat labels must exist and be unique'});
        }
        if (beat.start_frame !== undefined && beat.start_frame >= scene.duration_frames) {
          context.addIssue({code: 'custom', path: ['beats', index, 'start_frame'], message: 'beat exceeds scene'});
        }
      });
    }
    const paths = scene.visual_assets.map((asset) => asset.path);
    if (new Set(paths).size !== paths.length) {
      context.addIssue({
        code: 'custom',
        path: ['visual_assets'],
        message: 'scene visual asset paths must be unique',
      });
    }
    if (scene.visual === 'brand_outro') {
      if (scene.visual_assets.filter((asset) => asset.role === 'brand').length !== 1 ||
          scene.visual_assets.some((asset) => asset.role === 'whiteboard')) {
        context.addIssue({code: 'custom', path: ['visual_assets'], message: 'outro requires one brand asset'});
      }
      if (scene.claim_id || scene.source_marker || scene.evidence_highlight || scene.source_card) {
        context.addIssue({code: 'custom', path: ['visual'], message: 'outro cannot contain evidence'});
      }
    }
    if (scene.visual === 'source_card') {
      if (!scene.claim_id?.trim()) {
        context.addIssue({code: 'custom', path: ['claim_id'], message: 'source_card requires claim_id'});
      }
      if (!scene.source_marker?.trim()) {
        context.addIssue({code: 'custom', path: ['source_marker'], message: 'source_card requires source_marker'});
      }
      if (!scene.source_card) {
        context.addIssue({code: 'custom', path: ['source_card'], message: 'source_card requires source metadata'});
      }
    } else if (scene.source_card) {
      context.addIssue({code: 'custom', path: ['source_card'], message: 'source_card payload requires source_card visual'});
    }
    if (scene.visual === 'stat_gauge') {
      if (!scene.claim_id?.trim()) {
        context.addIssue({code: 'custom', path: ['claim_id'], message: 'stat_gauge requires claim_id'});
      }
      if (!scene.stat_gauge) {
        context.addIssue({code: 'custom', path: ['stat_gauge'], message: 'stat_gauge requires stat_gauge metadata'});
      }
    } else if (scene.stat_gauge) {
      context.addIssue({code: 'custom', path: ['stat_gauge'], message: 'stat_gauge payload requires stat_gauge visual'});
    }
    if (scene.visual === 'kinetic_term') {
      if (!scene.kinetic_term) {
        context.addIssue({code: 'custom', path: ['kinetic_term'], message: 'kinetic_term requires kinetic_term metadata'});
      }
    } else if (scene.kinetic_term) {
      context.addIssue({code: 'custom', path: ['kinetic_term'], message: 'kinetic_term payload requires kinetic_term visual'});
    }
    if (scene.motion?.emphasis_text && !phraseInNarration(scene.motion.emphasis_text, scene.narration)) {
      context.addIssue({
        code: 'custom',
        path: ['motion', 'emphasis_text'],
        message: 'motion.emphasis_text must be in narration',
      });
    }
    if (scene.visual !== 'evidence_highlight') {
      return;
    }
    if (!scene.source_marker?.trim()) {
      context.addIssue({
        code: 'custom',
        path: ['source_marker'],
        message: 'evidence_highlight requires a source_marker',
      });
    }
    if (scene.evidence_highlight === null || scene.evidence_highlight === undefined) {
      context.addIssue({
        code: 'custom',
        path: ['evidence_highlight'],
        message: 'evidence_highlight requires image and quote',
      });
    }
  });

export const RenderInputSchema = z.object({
  schema_version: z.string().default('1.0'),
  title: z.string(),
  audio_file: z.string(),
  youtube_cta: z.object({
    text: z.string().regex(/\S/),
    mascot_path: safeRelativePath,
    logo_path: safeRelativePath.default('clips/cta/logo.svg'),
    duration_frames: z.literal(90).default(90),
  }).nullable().optional(),
  scenes: z.array(SceneSchema).default([]),
  visual_budget_profile: z.enum(['m6_5_v1', 'explain_first_v1']).default('explain_first_v1'),
  format_profile: z.enum(['vertical_clip', 'youtube_long']).default('vertical_clip'),
  width: z.union([z.literal(1080), z.literal(1920)]).default(1080),
  height: z.union([z.literal(1920), z.literal(1080)]).default(1920),
  fps: z.literal(30).default(30),
}).superRefine((input, context) => {
  if (input.youtube_cta) {
    const frames = Math.max(0, ...input.scenes.map((s) => s.start_frame + s.duration_frames)) + 90;
    if (input.format_profile !== 'vertical_clip' || frames < 1800 || frames > 5400) {
      context.addIssue({code: 'custom', path: ['youtube_cta'], message: 'CTA clip duration must be 60-180 s'});
    }
  }
  const size = FORMAT_SIZES[input.format_profile];
  if (input.width !== size.width || input.height !== size.height) {
    context.addIssue({
      code: 'custom',
      path: ['width'],
      message: `${input.format_profile} requires ${size.width}x${size.height}`,
    });
  }
  if (input.visual_budget_profile !== 'm6_5_v1') {
    return;
  }
  input.scenes.forEach((scene, index) => {
    if (scene.visual !== 'chart') {
      return;
    }
    const charts = scene.visual_assets.filter((asset) => asset.role === 'chart');
    if (charts.length !== 1) {
      context.addIssue({
        code: 'custom',
        path: ['scenes', index, 'visual_assets'],
        message: 'M6.5 chart scene requires exactly one chart asset',
      });
    }
  });
});

export type EvidenceHighlight = z.input<typeof EvidenceHighlightSchema>;
export type SourceCard = z.input<typeof SourceCardSchema>;
export type VisualAssetRef = z.input<typeof VisualAssetRefSchema>;
export type Scene = z.input<typeof SceneSchema>;
export type SceneTiming = Pick<Scene, 'id' | 'start_frame' | 'duration_frames'>;
export type RenderInput = z.output<typeof RenderInputSchema>;

export const parseRenderInput = (value: unknown): RenderInput =>
  RenderInputSchema.parse(value);
