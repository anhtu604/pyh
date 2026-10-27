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
  staticFile: (path: string) => path,
  useCurrentFrame: () => 0,
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
});
