import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext, type FrameLayout} from '../layout';
import {
  R5_COMPONENT_IDS,
  ResolvedR5ShotSchema,
  type ResolvedR5Shot,
  type Scene,
} from '../types';
import {
  R5_COMPONENT_REGISTRY,
  R5ShotScene,
  resolveActiveR5Shot,
  type R5ComponentId,
} from './R5ShotScene';

vi.mock('remotion', () => ({
  AbsoluteFill: 'div',
  Img: 'img',
  staticFile: (path: string) => `static://${path}`,
  useCurrentFrame: () => 15,
}));

const WORDS = [
  {text: 'Men', start_frame: 0, end_frame: 15},
  {text: 'gan', start_frame: 15, end_frame: 30},
  {text: 'trong', start_frame: 30, end_frame: 45},
  {text: 'máu', start_frame: 45, end_frame: 60},
];

const makeShotForComponent = (
  component: R5ComponentId,
  overrides: Partial<ResolvedR5Shot> = {},
): ResolvedR5Shot => {
  const base = {
    id: `SH-${component}`,
    kind: (component === 'CreditCard'
      ? 'credit'
      : component === 'TakeawayCard'
        ? 'recap'
        : component === 'VnLabSheet' || component === 'StoryShot'
          ? 'story'
          : 'mechanism') as ResolvedR5Shot['kind'],
    tier: component === 'CreditCard' || component === 'StoryShot' ? null : 'organ',
    component,
    asset_paths:
      component === 'TakeawayCard'
        ? ['assets/brand/mascot/explain.png']
        : component === 'R5LiverLeakSignature'
          ? [
              'assets/medanim/hepatocyte.svg',
              'assets/medanim/blood-vessel.svg',
              'assets/medanim/blood-vial.svg',
            ]
          : ['assets/medanim/sample-organ.svg'],
    question_ids: ['Q1'],
    start_frame: 0,
    end_frame: 180,
    actions:
      component === 'R5LiverLeakSignature'
        ? [
            {
              actor: 'enzyme',
              compartment: 'intracellular',
              change: 'normal retention',
              outcome: 'stays inside cell',
              start_frame: 0,
              end_frame: 60,
            },
            {
              actor: 'membrane',
              compartment: 'membrane',
              change: 'permeability increase',
              outcome: 'barrier opens',
              start_frame: 60,
              end_frame: 120,
            },
            {
              actor: 'enzyme',
              compartment: 'bloodstream',
              change: 'release into blood',
              outcome: 'detected in lab sample',
              start_frame: 120,
              end_frame: 180,
            },
          ]
        : [
            {
              actor: 'marker',
              compartment: 'Vùng định vị A',
              change: 'highlight',
              outcome: 'localized',
              start_frame: 0,
              end_frame: 180,
            },
          ],
    text_windows:
      component === 'ScaleChain'
        ? [
            {
              kind: 'scale_bar' as const,
              text: 'Cơ thể → Cơ quan → Tế bào',
              claim_ids: ['C01'],
              start_frame: 0,
              end_frame: 180,
            },
          ]
        : component === 'ZoomChain'
          ? [
              {
                kind: 'label' as const,
                text: 'Vùng định vị A',
                claim_ids: ['C01'],
                start_frame: 0,
                end_frame: 180,
              },
            ]
          : component === 'TakeawayCard'
            ? [
                {
                  kind: 'takeaway' as const,
                  text: 'Men gan phản ánh tổn thương tế bào',
                  claim_ids: ['C01'],
                  start_frame: 0,
                  end_frame: 180,
                },
              ]
            : component === 'VnLabSheet'
              ? [
                  {
                    kind: 'lab_sheet' as const,
                    text: 'ALT | 240 | U/L | < 40 | H',
                    claim_ids: ['C01'],
                    start_frame: 0,
                    end_frame: 180,
                  },
                ]
              : component === 'ReferenceDistribution'
                ? [
                    {
                      kind: 'label' as const,
                      text: 'Khoảng tham chiếu',
                      claim_ids: ['C01'],
                      start_frame: 0,
                      end_frame: 180,
                    },
                  ]
                : component === 'CreditCard'
                  ? [
                      {
                        kind: 'credit' as const,
                        text: 'Kho A · CC BY 4.0',
                        claim_ids: [],
                        start_frame: 0,
                        end_frame: 180,
                      },
                    ]
                  : component === 'StoryShot'
                    ? []
                    : [
                        {
                          kind: 'label' as const,
                          text: 'Tế bào gan',
                          claim_ids: ['C01'],
                          start_frame: 0,
                          end_frame: 90,
                        },
                      ],
  };

  return ResolvedR5ShotSchema.parse({...base, ...overrides});
};

const makeScene = (shots: ResolvedR5Shot[], extra: Partial<Scene> = {}): Scene => ({
  id: 'S01',
  start_frame: 0,
  duration_frames: 180,
  narration: 'Men gan trong máu.',
  words: WORDS,
  visual: 'whiteboard',
  visual_assets: [{path: 'assets/brand/mascot/explain.png', role: 'mascot', pose: 'explain'}],
  resolved_shots: shots,
  ...extra,
});

const renderScene = (scene: Scene, layout: FrameLayout, frame = 15): string =>
  renderToStaticMarkup(
    <LayoutContext.Provider value={layout}>
      <R5ShotScene scene={scene} frame={frame} assets={scene.resolved_shots?.flatMap(s => s.asset_paths).filter((p, i, all) => all.indexOf(p) === i).map((path, i) => ({
        id: `fixture-${i}`, path, title: 'Synthetic organ', author: 'Fixture author', repository: 'servier',
        license: 'CC BY 4.0', license_url: 'https://creativecommons.org/licenses/by/4.0/',
        source_page: 'https://smart.servier.com/smart_image/cell/', sha256: 'a'.repeat(64),
      }))} />
    </LayoutContext.Provider>,
  );

describe('R5ShotScene registry routing and caption policy', () => {
  it('fails closed on absent asset provenance and missing license', () => {
    const scene = makeScene([makeShotForComponent('ZoomChain')]);
    expect(() => renderToStaticMarkup(<R5ShotScene scene={scene} frame={15} />))
      .toThrow(/SH-ZoomChain.*sample-organ.svg.*metadata/i);
    expect(() => renderToStaticMarkup(<R5ShotScene scene={scene} frame={15}
      assets={[{path: 'assets/medanim/sample-organ.svg', author: 'Fixture author', license: ''}]} />))
      .toThrow(/SH-ZoomChain.*sample-organ.svg.*license/i);
  });
  it('registers every R5_COMPONENT_IDS member with no extras', () => {
    expect(Object.keys(R5_COMPONENT_REGISTRY).sort()).toEqual([...R5_COMPONENT_IDS].sort());
  });

  it.each(R5_COMPONENT_IDS)(
    'routes %s with no captions in 16:9, captions in 9:16 (even with mascot), and distinct format markup',
    (component) => {
      const scene = makeScene([makeShotForComponent(component)]);
      const landscape = renderScene(scene, LAYOUTS.youtube_long, 20);
      const portrait = renderScene(scene, LAYOUTS.vertical_clip, 20);

      expect(landscape).toContain(`data-r5-component="${component}"`);
      expect(landscape).toContain('data-layout="16:9"');
      expect(landscape).not.toContain('aria-label="Phụ đề đang đọc"');
      expect(landscape).not.toContain('data-mechanism-caption-band');

      expect(portrait).toContain(`data-r5-component="${component}"`);
      expect(portrait).toContain('data-layout="9:16"');
      expect(portrait).toContain('aria-label="Phụ đề đang đọc"');

      // Format markup must differ between 16:9 and 9:16.
      expect(landscape).not.toBe(portrait);
      // Word timings must remain intact on the scene.
      expect(scene.words).toEqual(WORDS);
    },
  );

  it.each(['story', 'mechanism', 'recap', 'credit'] as const)(
    'enforces 16:9 no-caption and 9:16 caption policy for shot kind=%s',
    (kind) => {
      const shot = makeShotForComponent('TakeawayCard', {kind});
      const scene = makeScene([shot]);
      const landscape = renderScene(scene, LAYOUTS.youtube_long, 20);
      const portrait = renderScene(scene, LAYOUTS.vertical_clip, 20);

      expect(landscape).toContain(`data-shot-kind="${kind}"`);
      expect(landscape).not.toContain('aria-label="Phụ đề đang đọc"');
      expect(portrait).toContain(`data-shot-kind="${kind}"`);
      expect(portrait).toContain('aria-label="Phụ đề đang đọc"');
    },
  );

  it('renders a single primary viewpoint per shot and connects transitions via anchors', () => {
    const shot1 = makeShotForComponent('ZoomChain', {
      id: 'SH01',
      tier: 'body',
      start_frame: 0,
      end_frame: 90,
      actions: [
        {
          actor: 'organ',
          compartment: 'Vùng gan',
          change: 'locate',
          outcome: 'oriented',
          start_frame: 0,
          end_frame: 90,
        },
      ],
      text_windows: [
        {kind: 'label', text: 'Vùng gan', claim_ids: ['C01'], exception_reason: null, start_frame: 0, end_frame: 90},
      ],
    });
    const shot2 = makeShotForComponent('TakeawayCard', {
      id: 'SH02',
      tier: 'organ',
      start_frame: 90,
      end_frame: 180,
      actions: [],
      text_windows: [
        {kind: 'takeaway', text: 'Điểm chốt rõ ràng', claim_ids: ['C01'], exception_reason: null, start_frame: 90, end_frame: 180},
      ],
    });
    const scene = makeScene([shot1, shot2]);

    const early = renderScene(scene, LAYOUTS.youtube_long, 30);
    expect(early).toContain('data-active-shot="SH01"');
    expect(early).toContain('data-r5-component="ZoomChain"');
    expect(early).toContain('data-from-tier="body"');
    expect(early).toContain('data-to-tier="organ"');
    expect(early).not.toContain('data-r5-component="TakeawayCard"');

    const late = renderScene(scene, LAYOUTS.youtube_long, 120);
    expect(late).toContain('data-active-shot="SH02"');
    expect(late).toContain('data-r5-component="TakeawayCard"');
    expect(late).toContain('data-transition-anchor="body-&gt;organ"');
    expect(late).not.toContain('data-r5-component="ZoomChain"');
  });

  it('fails closed with scene and shot IDs on unknown component, missing data, or implicit tabs', () => {
    const badComponentShot = {
      ...makeShotForComponent('ScaleChain'),
      id: 'SH-BAD',
      component: 'FluxLegacyScene' as unknown as R5ComponentId,
    };
    expect(() =>
      renderScene(makeScene([badComponentShot], {id: 'S99'}), LAYOUTS.youtube_long),
    ).toThrow(/S99\/SH-BAD.*unknown R5 component/i);

    expect(() =>
      resolveActiveR5Shot(makeScene([], {id: 'S98'}), 0),
    ).toThrow(/S98.*missing resolved_shots/i);

    const missingLabRows = makeShotForComponent('VnLabSheet', {
      id: 'SH-EMPTY-LAB',
      text_windows: [],
    });
    expect(() =>
      renderScene(makeScene([missingLabRows], {id: 'S97'}), LAYOUTS.youtube_long),
    ).toThrow(/S97\/SH-EMPTY-LAB.*VnLabSheet/i);

    const actionOnlyDistribution = makeShotForComponent('ReferenceDistribution', {
      id: 'SH-ID-LABELS',
      text_windows: [],
    });
    expect(() =>
      renderScene(makeScene([actionOnlyDistribution], {id: 'S93'}), LAYOUTS.youtube_long),
    ).toThrow(/S93\/SH-ID-LABELS.*ReferenceDistribution requires text_windows/i);

    const missingLeakStages = makeShotForComponent('R5LiverLeakSignature', {
      id: 'SH-SHORT-LEAK',
      actions: [
        {
          actor: 'enzyme',
          compartment: 'cell',
          change: 'only one step',
          outcome: 'incomplete',
          start_frame: 0,
          end_frame: 180,
        },
      ],
    });
    expect(() =>
      renderScene(makeScene([missingLeakStages], {id: 'S96'}), LAYOUTS.youtube_long),
    ).toThrow(/S96\/SH-SHORT-LEAK.*at least 3 resolved actions/i);

    const tabScene = makeScene([makeShotForComponent('TakeawayCard')], {
      id: 'S95',
      entrances: [{text: 'ALT\t240 U/L\t< 40', start_frame: 0}],
    });
    expect(() => renderScene(tabScene, LAYOUTS.youtube_long)).toThrow(/S95.*tab layout/i);
  });

  it('routes StoryShot with asset, with mascot-only fallback, and fails closed when neither exists', () => {
    expect(R5_COMPONENT_REGISTRY.StoryShot).toBeTypeOf('function');

    const assetShot = makeShotForComponent('StoryShot', {
      id: 'SH-STORY-A',
      asset_paths: ['assets/medanim/sample-organ.svg'],
      actions: [],
      text_windows: [],
    });
    const assetHtml = renderScene(makeScene([assetShot], {visual_assets: []}), LAYOUTS.youtube_long, 30);
    expect(assetHtml).toContain('data-r5-component="StoryShot"');
    expect(assetHtml).toContain('data-story-mode="asset"');

    const mascotOnlyShot = makeShotForComponent('StoryShot', {
      id: 'SH-STORY-M',
      asset_paths: [],
      actions: [],
      text_windows: [],
    });
    const mascotHtml = renderScene(makeScene([mascotOnlyShot]), LAYOUTS.vertical_clip, 30);
    expect(mascotHtml).toContain('data-r5-component="StoryShot"');
    expect(mascotHtml).toContain('data-story-mode="mascot"');
    expect(mascotHtml).toContain('aria-label="Phụ đề đang đọc"');

    expect(() =>
      renderScene(makeScene([mascotOnlyShot], {id: 'S94', visual_assets: []}), LAYOUTS.youtube_long, 30),
    ).toThrow(/S94\/SH-STORY-M.*StoryShot requires/i);
  });
});
