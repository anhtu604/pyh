import {z} from 'zod';

const unitCoordinate = z.number().min(0).max(1);

const safeRelativePath = z.string().regex(/^(?!\.?\/?$)(?![A-Za-z]:)(?!\/)(?!.*\\)(?!.*(?:^|\/)\.\.(?:\/|$))\S+$/);

export const VisualAssetRefSchema = z
  .object({
    path: safeRelativePath,
    role: z.enum(['whiteboard', 'mascot', 'brand', 'chart']),
    pose: z.enum(['welcome', 'explain', 'caution']).nullable().optional(),
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

export const SceneSchema = z
  .object({
    schema_version: z.string().default('1.0'),
    id: z.string(),
    start_frame: z.number().int().min(0),
    duration_frames: z.number().int().positive(),
    narration: z.string(),
    script_line_id: z.string().nullable().optional(),
    claim_id: z.string().nullable().optional(),
    source_marker: z.string().regex(/\S/).nullable().optional(),
    visual: z.enum(['whiteboard', 'chart', 'evidence_highlight', 'ai_clip', 'brand_outro']),
    evidence_highlight: EvidenceHighlightSchema.nullable().optional(),
    visual_assets: z.array(VisualAssetRefSchema).default([]),
  })
  .superRefine((scene, context) => {
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
      if (scene.claim_id || scene.source_marker || scene.evidence_highlight) {
        context.addIssue({code: 'custom', path: ['visual'], message: 'outro cannot contain evidence'});
      }
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
  scenes: z.array(SceneSchema).default([]),
  visual_budget_profile: z.enum(['legacy', 'm6_5_v1']).default('legacy'),
  width: z.literal(1080).default(1080),
  height: z.literal(1920).default(1920),
  fps: z.literal(30).default(30),
}).superRefine((input, context) => {
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
export type VisualAssetRef = z.input<typeof VisualAssetRefSchema>;
export type Scene = z.input<typeof SceneSchema>;
export type SceneTiming = Pick<Scene, 'id' | 'start_frame' | 'duration_frames'>;
export type RenderInput = z.output<typeof RenderInputSchema>;

export const parseRenderInput = (value: unknown): RenderInput =>
  RenderInputSchema.parse(value);
