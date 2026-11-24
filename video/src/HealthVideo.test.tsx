import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {HealthVideo} from './HealthVideo';
import {VisualAsset} from './components/VisualAsset';
import {SceneMotionOverlay} from './motion/SceneMotionOverlay';
import {ChartScene} from './scenes/ChartScene';
import {KineticTermScene} from './scenes/KineticTermScene';
import {OutroScene} from './scenes/OutroScene';
import {StatGaugeScene} from './scenes/StatGaugeScene';
import {WhiteboardScene} from './scenes/WhiteboardScene';
import {SourceCardScene} from './scenes/SourceCardScene';
import {parseRenderInput} from './types';

vi.mock('remotion', () => ({
  AbsoluteFill: 'div',
  Audio: 'audio',
  Img: 'img',
  OffthreadVideo: 'video',
  Sequence: 'section',
  interpolate: () => 1,
  spring: () => 1,
  staticFile: (path: string) => path,
  useCurrentFrame: () => 0,
  useVideoConfig: () => ({fps: 30, width: 1080, height: 1920}),
}));

const input = (visual: 'whiteboard' | 'evidence_highlight') => ({
  schema_version: '1.0',
  title: 'PYH',
  audio_file: 'audio/silence.wav',
  scenes: [{
    schema_version: '1.0',
    id: 'S01', start_frame: 0, duration_frames: 90, narration: 'Nội dung', visual,
    source_marker: visual === 'evidence_highlight' ? '[1]' : undefined,
    evidence_highlight: visual === 'evidence_highlight' ? {
      schema_version: '1.0',
      image: 'assets/evidence.svg', quote: 'Trích dẫn', x: 0, y: 0,
      width: 0.5, height: 0.5,
    } : undefined,
    visual_assets: [{path: 'assets/guide.svg', role: 'mascot' as const, pose: 'welcome' as const}],
  }],
  visual_budget_profile: 'explain_first_v1' as const,
  format_profile: 'vertical_clip' as const,
  width: 1080 as const, height: 1920 as const, fps: 30 as const,
});

// HealthVideo wraps the frame in LayoutContext.Provider; unwrap to the AbsoluteFill.
const renderVideo = (props: ReturnType<typeof parseRenderInput>) =>
  (HealthVideo(props) as React.ReactElement<{children: React.ReactElement}>).props.children as
    React.ReactElement<{children: React.ReactNode}>;

describe('HealthVideo visual asset layer', () => {
  it('labels current visual assets with the PYH identity', () => {
    const rendered = VisualAsset({asset: {path: 'assets/pyh.svg', role: 'brand'}}) as
      React.ReactElement<{['aria-label']: string}>;
    expect(rendered.props['aria-label']).toBe('PYH brand');
  });
  it('opens with authored content and dispatches one declared logo in the final outro', () => {
    const initial = input('whiteboard');
    const props = parseRenderInput({...initial, scenes: [...initial.scenes, {
      schema_version: '1.0', id: 'OUTRO', start_frame: 90, duration_frames: 60,
      narration: 'Cảm ơn', visual: 'brand_outro',
      source_marker: undefined, evidence_highlight: undefined,
      visual_assets: [{path: 'assets/pyh.svg', role: 'brand'}],
    }]});
    const root = renderVideo(props);
    const sequences = React.Children.toArray(root.props.children).slice(1) as React.ReactElement<{
      children: React.ReactNode; from: number;
    }>[];
    expect(sequences[0].props.from).toBe(0);
    const children = React.Children.toArray(sequences[1].props.children);
    expect(children.some((child) => React.isValidElement(child) && child.type === OutroScene)).toBe(true);
    expect(children.filter((child) => React.isValidElement(child) && child.type === VisualAsset)).toHaveLength(1);
  });
  it.each(['whiteboard', 'evidence_highlight'] as const)(
    'renders one declared asset for a %s scene',
    (visual) => {
      const root = renderVideo(input(visual));
      const sequence = React.Children.toArray(root.props.children)[1] as React.ReactElement<{
        children: React.ReactNode;
      }>;
      const assets = React.Children.toArray(sequence.props.children).filter(
        (child) => React.isValidElement(child) && child.type === VisualAsset,
      );
      expect(assets).toHaveLength(1);
    },
  );
  it('keeps illustrations behind authored whiteboard text and the presenter in front', () => {
    const props = parseRenderInput({...input('whiteboard'), scenes: [{...input('whiteboard').scenes[0],
      on_screen_text: 'Ý chính', visual_assets: [
        {path: 'assets/drawing.svg', role: 'whiteboard'},
        {path: 'assets/guide.svg', role: 'mascot', pose: 'welcome'},
      ]}]});
    const sequence = React.Children.toArray(renderVideo(props).props.children)[1] as React.ReactElement<{children: React.ReactNode}>;
    const elements = React.Children.toArray(sequence.props.children) as React.ReactElement<{asset?: {role: string}}>[];
    expect(elements.map(element => element.type)).toEqual([VisualAsset, WhiteboardScene, VisualAsset]);
    expect(elements[0].props.asset?.role).toBe('whiteboard');
    expect(elements[2].props.asset?.role).toBe('mascot');
  });
  it('dispatches source cards to their dedicated renderer', () => {
    const props = parseRenderInput({...input('whiteboard'), scenes: [{...input('whiteboard').scenes[0],
      visual: 'source_card', claim_id: 'C01', source_marker: '[1]', source_card: {
        source_id: 'R01', title: 'Study title', journal: 'Journal', year: null, pmid: null, doi: null,
        interpretation: 'Diễn giải được duyệt.',
      }}]});
    const sequence = React.Children.toArray(renderVideo(props).props.children)[1] as React.ReactElement<{children: React.ReactNode}>;
    expect(React.Children.toArray(sequence.props.children).some(child => React.isValidElement(child) && child.type === SourceCardScene)).toBe(true);
  });
  it('dispatches an enabled declared chart once outside the overlay layer', () => {
    const props = parseRenderInput({
      ...input('whiteboard'),
      visual_budget_profile: 'm6_5_v1',
      scenes: [{
        ...input('whiteboard').scenes[0],
        visual: 'chart',
        visual_assets: [{path: 'assets/chart.svg', role: 'chart'}],
      }],
    });
    const root = renderVideo(props);
    const sequence = React.Children.toArray(root.props.children)[1] as React.ReactElement<{
      children: React.ReactNode;
    }>;
    const children = React.Children.toArray(sequence.props.children);
    expect(children.filter((child) => React.isValidElement(child) && child.type === ChartScene))
      .toHaveLength(1);
    expect(children.filter((child) => React.isValidElement(child) && child.type === VisualAsset))
      .toHaveLength(0);
  });
  it('renders scenes with motion overlay, stat_gauge, and kinetic_term through HealthVideo', () => {
    const props = parseRenderInput({
      ...input('whiteboard'),
      scenes: [
        {
          schema_version: '1.0',
          id: 'S01',
          start_frame: 0,
          duration_frames: 90,
          narration: 'Tăng acid uric máu kéo dài dễ dẫn tới lắng đọng urat.',
          on_screen_text: 'Tăng acid uric máu',
          visual: 'whiteboard',
          motion: {
            emphasis: 'marker-underline-title',
            emphasis_text: 'tăng acid uric máu',
            transition_in: 'circle-match-iris',
          },
          visual_assets: [],
        },
        {
          schema_version: '1.0',
          id: 'S02',
          start_frame: 90,
          duration_frames: 90,
          narration: 'Ngưỡng bão hòa urat huyết thanh là 6,8 mg/dL.',
          claim_id: 'C01',
          source_marker: '[1]',
          visual: 'stat_gauge',
          stat_gauge: {
            value: 6.8,
            unit: 'mg/dL',
            label: 'Ngưỡng bão hòa urat',
            max_value: 12,
            variant: 'gauge-readout-moves',
          },
          visual_assets: [],
        },
        {
          schema_version: '1.0',
          id: 'S03',
          start_frame: 180,
          duration_frames: 90,
          narration: 'Gút cấp là cơn viêm khớp khởi phát đột ngột.',
          visual: 'kinetic_term',
          kinetic_term: {
            term: 'GÚT CẤP',
            definition: 'Cơn viêm khớp khởi phát đột ngột do tinh thể urat.',
            variant: 'lead-word-zoom-assemble',
          },
          visual_assets: [],
        },
      ],
    });
    const root = renderVideo(props);
    const sequences = React.Children.toArray(root.props.children).slice(1) as React.ReactElement<{
      children: React.ReactNode;
    }>[];
    expect(sequences).toHaveLength(3);
    const seq1Children = React.Children.toArray(sequences[0].props.children);
    expect(seq1Children.some((c) => React.isValidElement(c) && c.type === SceneMotionOverlay)).toBe(true);
    const seq2Children = React.Children.toArray(sequences[1].props.children);
    expect(seq2Children.some((c) => React.isValidElement(c) && c.type === StatGaugeScene)).toBe(true);
    const seq3Children = React.Children.toArray(sequences[2].props.children);
    expect(seq3Children.some((c) => React.isValidElement(c) && c.type === KineticTermScene)).toBe(true);

    const html = renderToStaticMarkup(<HealthVideo {...props} />);
    expect(html).toContain('tăng acid uric máu');
    expect(html).toContain('Ngưỡng bão hòa urat');
    expect(html).toContain('Cơn viêm khớp khởi phát đột ngột do tinh thể urat.');
  });

  it('omits burned-in captions and outro narration text on 16:9 youtube_long while preserving them on 9:16 vertical_clip', () => {
    const words = [
      {text: 'Lời', start_frame: 0, end_frame: 15},
      {text: 'đọc', start_frame: 15, end_frame: 30},
      {text: 'riêng', start_frame: 30, end_frame: 45},
    ];
    const baseScenes = [
      {
        schema_version: '1.0',
        id: 'S01',
        start_frame: 0,
        duration_frames: 90,
        narration: 'Lời đọc riêng',
        words,
        on_screen_text: 'Ý chính ngắn',
        visual: 'whiteboard' as const,
        visual_assets: [{path: 'assets/guide.svg', role: 'mascot' as const, pose: 'welcome' as const}],
      },
      {
        schema_version: '1.0',
        id: 'OUTRO',
        start_frame: 90,
        duration_frames: 60,
        narration: 'Để lại 1 lượt like và subscribe nhé.',
        words: [{text: 'Để', start_frame: 0, end_frame: 10}],
        visual: 'brand_outro' as const,
        visual_assets: [
          {path: 'assets/pyh.svg', role: 'brand' as const},
          {path: 'assets/guide.svg', role: 'mascot' as const, pose: 'welcome' as const},
        ],
      },
    ];

    const longProps = parseRenderInput({
      ...input('whiteboard'),
      format_profile: 'youtube_long',
      width: 1920,
      height: 1080,
      scenes: baseScenes,
    });
    expect(longProps.scenes[0].words).toEqual(words);
    const longHtml = renderToStaticMarkup(<HealthVideo {...longProps} />);
    expect(longHtml).not.toContain('aria-label="Phụ đề đang đọc"');
    expect(longHtml).not.toContain('data-outro-text="true"');
    expect(longHtml).not.toContain('Để lại 1 lượt like và subscribe');
    expect(longHtml).toContain('Ý chính ngắn');
    expect(longHtml).toContain('data-brand-badge="true"');
    expect(longHtml).toContain('data-outro-landscape="true"');

    const shortProps = parseRenderInput({
      ...input('whiteboard'),
      format_profile: 'vertical_clip',
      width: 1080,
      height: 1920,
      scenes: baseScenes,
    });
    const shortHtml = renderToStaticMarkup(<HealthVideo {...shortProps} />);
    expect(shortHtml).toContain('aria-label="Phụ đề đang đọc"');
    expect(shortHtml).toContain('data-outro-text="true"');
    expect(shortHtml).toContain('Để lại 1 lượt like và subscribe');
  });

  it('drops marker-underline-title on ScaleZoomStage scenes while keeping wipe-transitions and whiteboard emphasis', () => {
    const props = parseRenderInput({
      ...input('whiteboard'),
      visualStyle: 'scale_zoom',
      format_profile: 'youtube_long',
      width: 1920,
      height: 1080,
      scenes: [
        {
          schema_version: '1.0',
          id: 'S01',
          start_frame: 0,
          duration_frames: 120,
          narration: 'Men gan tăng cần tìm nguyên nhân.',
          visual: 'anatomy_animation',
          anatomy: {subject: 'hepatocyte_sinusoid_unit', state: 'diseased', severity: 0.4, motion: 'leak'},
          motion: {emphasis: 'marker-underline-title', emphasis_text: 'tìm nguyên nhân', transition_in: 'wipe-transitions'},
          visual_assets: [],
        },
        {
          schema_version: '1.0',
          id: 'S02',
          start_frame: 120,
          duration_frames: 120,
          narration: 'Nhắc lại điểm chính.',
          visual: 'whiteboard',
          motion: {emphasis: 'marker-underline-title', emphasis_text: 'điểm chính'},
          visual_assets: [],
        },
      ],
    });
    const html = renderToStaticMarkup(<HealthVideo {...props} />);
    expect(html).not.toContain('tìm nguyên nhân');
    expect(html).toContain('data-motion="wipe-transitions"');
    expect(html).toContain('điểm chính');
  });

  it('normalizes snake_case visual_style and visual_takeaway into ScaleZoomStage, scientific comparison, and split clinical worksheet', () => {
    const props = parseRenderInput({
      title: 'Snake case PYH-003',
      audio_file: 'audio/silence.wav',
      visual_style: 'scale_zoom',
      format_profile: 'youtube_long',
      width: 1920,
      height: 1080,
      scenes: [
        {
          schema_version: '1.0',
          id: 'S01',
          start_frame: 0,
          duration_frames: 120,
          narration: 'Men nằm trong tế bào gan có thể thoát sang máu.',
          visual_takeaway: 'Men nằm trong tế bào gan thoát sang dòng máu khi tổn thương.',
          visual: 'anatomy_animation',
          anatomy: {subject: 'hepatocyte_sinusoid_unit', state: 'diseased', severity: 0.5, motion: 'leak'},
          motion: {emphasis: 'marker-underline-title', emphasis_text: 'tế bào gan'},
          visual_assets: [],
        },
        {
          schema_version: '1.0',
          id: 'S02',
          start_frame: 120,
          duration_frames: 120,
          narration: 'Đừng tự ngưng thuốc kê đơn.',
          on_screen_text: 'Thuốc kê đơn: không tự ngưng',
          visual_takeaway: 'Giữ nguyên thuốc kê đơn tới khi bác sĩ rà soát.',
          visual: 'process_animation',
          anatomy: {subject: 'liver_organ', state: 'normal', severity: 0, motion: 'overview'},
          entrances: [
            {text: 'Thuốc kê đơn\tMỡ máu / huyết áp\tKhông tự bỏ ngang', start_frame: 0},
          ],
          motion: {emphasis: 'marker-underline-title', emphasis_text: 'đừng'},
          visual_assets: [{path: 'assets/illustrations/prescription-review.png', role: 'whiteboard'}],
        },
        {
          schema_version: '1.0',
          id: 'S11',
          start_frame: 240,
          duration_frames: 120,
          narration: 'So sánh tế bào lành và tế bào tổn thương.',
          visual_takeaway: 'So sánh trực quan tế bào bình thường và tổn thương.',
          visual: 'comparison',
          anatomy: {subject: 'hepatocyte_sinusoid_unit', state: 'diseased', severity: 0.7, motion: 'compare'},
          visual_assets: [],
        },
      ],
    });
    expect(props.visualStyle).toBe('scale_zoom');
    expect(props.scenes[0].visualTakeaway).toBe('Men nằm trong tế bào gan thoát sang dòng máu khi tổn thương.');

    const html = renderToStaticMarkup(<HealthVideo {...props} />);
    expect(html).toContain('data-scalezoom-stage="true"');
    expect(html).toContain('data-scalezoom-takeaway="true"');
    expect(html).toContain('data-split-clinical-stage="true"');
    expect(html).toContain('data-split-visual="flux"');
    expect(html).toContain('data-scientific-stage="comparison"');
    expect(html).toContain('data-scientific-artwork="hepatocyte_sinusoid_unit"');
    expect(html).not.toContain('data-motion="marker-underline-title"');
  });

  it('routes quality_profile=r5_v1 through R5ShotScene without legacy FLUX/caption leakage, and fails closed when missing resolved_shots', () => {
    const r5Contract = {
      questions: [
        {id: 'Q1', text: 'Men gan tăng là gì?', hook_line_id: 'L01', answer_line_ids: ['L02']},
        {id: 'Q2', text: 'Khi nào cần đi khám?', hook_line_id: 'L01', answer_line_ids: ['L03']},
      ],
      blocks: [
        {
          id: 'B1',
          line_ids: ['L01', 'L02', 'L03'],
          question_ids: ['Q1', 'Q2'],
          takeaway_line_id: 'L02',
          professional_update: true,
        },
      ],
    };
    const words = [
      {text: 'Men', start_frame: 0, end_frame: 20},
      {text: 'gan', start_frame: 20, end_frame: 40},
    ];
    const r5Scene = {
      schema_version: '1.0',
      id: 'S01',
      start_frame: 0,
      duration_frames: 120,
      narration: 'Men gan tăng.',
      words,
      visual: 'whiteboard' as const,
      visual_assets: [
        {path: 'assets/legacy-flux.png', role: 'whiteboard' as const},
        {path: 'assets/brand/mascot/explain.png', role: 'mascot' as const, pose: 'explain' as const},
      ],
      resolved_shots: [
        {
          id: 'SH01',
          kind: 'recap' as const,
          tier: 'organ',
          component: 'TakeawayCard' as const,
          asset_paths: ['assets/brand/mascot/explain.png'],
          question_ids: ['Q1'],
          long_shot_reason: null,
          start_frame: 0,
          end_frame: 120,
          actions: [],
          text_windows: [
            {
              kind: 'takeaway' as const,
              text: 'Men gan phản ánh tổn thương tế bào',
              claim_ids: ['C01'],
              exception_reason: null,
              start_frame: 0,
              end_frame: 120,
            },
          ],
        },
      ],
    };

    const longProps = parseRenderInput({
      title: 'R5 16:9',
      audio_file: 'audio/silence.wav',
      quality_profile: 'r5_v1',
      r5_contract: r5Contract,
      r5_assets: [{id: 'mascot', path: 'assets/brand/mascot/explain.png', title: 'Fixture mascot',
        author: 'Fixture author', repository: 'servier', license: 'CC BY 4.0',
        license_url: 'https://creativecommons.org/licenses/by/4.0/',
        source_page: 'https://smart.servier.com/smart_image/cell/', sha256: 'a'.repeat(64)}],
      format_profile: 'youtube_long',
      width: 1920,
      height: 1080,
      scenes: [r5Scene],
    });
    const longHtml = renderToStaticMarkup(<HealthVideo {...longProps} />);
    expect(longHtml).toContain('data-r5-scene="S01"');
    expect(longHtml).toContain('data-r5-component="TakeawayCard"');
    expect(longHtml).toContain('data-layout="16:9"');
    expect(longHtml).not.toContain('assets/legacy-flux.png');
    expect(longHtml).not.toContain('aria-label="Phụ đề đang đọc"');
    expect(longHtml).not.toContain('data-mechanism-caption-band');
    expect(longProps.scenes[0].words).toEqual(words);

    const shortProps = parseRenderInput({
      title: 'R5 9:16',
      audio_file: 'audio/silence.wav',
      quality_profile: 'r5_v1',
      r5_contract: r5Contract,
      r5_assets: [{id: 'mascot', path: 'assets/brand/mascot/explain.png', title: 'Fixture mascot',
        author: 'Fixture author', repository: 'servier', license: 'CC BY 4.0',
        license_url: 'https://creativecommons.org/licenses/by/4.0/',
        source_page: 'https://smart.servier.com/smart_image/cell/', sha256: 'a'.repeat(64)}],
      format_profile: 'vertical_clip',
      width: 1080,
      height: 1920,
      scenes: [r5Scene],
    });
    const shortHtml = renderToStaticMarkup(<HealthVideo {...shortProps} />);
    expect(shortHtml).toContain('data-r5-scene="S01"');
    expect(shortHtml).toContain('data-layout="9:16"');
    expect(shortHtml).toContain('aria-label="Phụ đề đang đọc"');
    expect(shortHtml).not.toContain('assets/legacy-flux.png');
    expect(longHtml).not.toBe(shortHtml);

    // Missing resolved_shots under quality_profile=r5_v1 must fail closed, never fall back to legacy.
    const missingResolved = parseRenderInput({
      title: 'R5 missing resolved',
      audio_file: 'audio/silence.wav',
      quality_profile: 'r5_v1',
      r5_contract: r5Contract,
      r5_assets: [{id: 'mascot', path: 'assets/brand/mascot/explain.png', title: 'Fixture mascot',
        author: 'Fixture author', repository: 'servier', license: 'CC BY 4.0',
        license_url: 'https://creativecommons.org/licenses/by/4.0/',
        source_page: 'https://smart.servier.com/smart_image/cell/', sha256: 'a'.repeat(64)}],
      format_profile: 'youtube_long',
      width: 1920,
      height: 1080,
      scenes: [{...r5Scene, resolved_shots: undefined}],
    });
    expect(() => renderToStaticMarkup(<HealthVideo {...missingResolved} />)).toThrow(
      /S01.*resolved_shots/i,
    );
  });
});
