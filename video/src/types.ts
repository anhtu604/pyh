import {z} from 'zod';

const unitCoordinate = z.number().min(0).max(1);

export const EvidenceHighlightSchema = z
  .object({
    schema_version: z.string().default('1.0'),
    image: z.string().regex(/\S/),
    quote: z.string().regex(/\S/),
    x: unitCoordinate,
    y: unitCoordinate,
    width: unitCoordinate,
    height: unitCoordinate,
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
  });

export const SceneSchema = z
  .object({
    schema_version: z.string().default('1.0'),
    id: z.string(),
    start_frame: z.number().int().min(0),
    duration_frames: z.number().int().positive(),
    narration: z.string(),
    claim_id: z.string().nullable().optional(),
    source_marker: z.string().regex(/\S/).nullable().optional(),
    visual: z.enum(['whiteboard', 'chart', 'evidence_highlight', 'ai_clip']),
    evidence_highlight: EvidenceHighlightSchema.nullable().optional(),
  })
  .superRefine((scene, context) => {
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
  width: z.literal(1080).default(1080),
  height: z.literal(1920).default(1920),
  fps: z.literal(30).default(30),
});

export type EvidenceHighlight = z.output<typeof EvidenceHighlightSchema>;
export type Scene = z.output<typeof SceneSchema>;
export type SceneTiming = Pick<Scene, 'id' | 'start_frame' | 'duration_frames'>;
export type RenderInput = z.output<typeof RenderInputSchema>;

export const parseRenderInput = (value: unknown): RenderInput =>
  RenderInputSchema.parse(value);
