import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {LAYOUTS, LayoutContext} from '../layout';
import {KineticTermScene} from '../scenes/KineticTermScene';
import {StatGaugeScene} from '../scenes/StatGaugeScene';
import {MOTION_EMPHASIS_KINDS, MOTION_TRANSITION_KINDS} from '../types';
import {BeforeAfterSliderScrub} from './BeforeAfterSliderScrub';
import {ChartLiveMoves} from './ChartLiveMoves';
import {CircleMatchIris} from './CircleMatchIris';
import {CrashZoomPunch} from './CrashZoomPunch';
import {GaugeReadoutMoves} from './GaugeReadoutMoves';
import {LeadWordZoomAssemble} from './LeadWordZoomAssemble';
import {MarkerUnderlineTitle} from './MarkerUnderlineTitle';
import {OutlineWordFill} from './OutlineWordFill';
import {ScanBracketSweep} from './ScanBracketSweep';
import {ScanlineAnnotateFocus, type AnnotateTarget} from './ScanlineAnnotateFocus';
import {SceneMotionOverlay} from './SceneMotionOverlay';
import {SpotlightSweepMoves} from './SpotlightSweepMoves';
import {TimelineTravel, type TimelineMilestone} from './TimelineTravel';
import {TitleDemoteToLabel} from './TitleDemoteToLabel';
import {WipeTransitions} from './WipeTransitions';

const env = vi.hoisted(() => ({frame: 0, width: 1080, height: 1920}));
vi.mock('remotion', () => ({
  AbsoluteFill: ({
    children,
    style,
    ...rest
  }: {
    children?: React.ReactNode;
    style?: React.CSSProperties;
    [k: string]: unknown;
  }) => (
    <div style={style} {...rest}>
      {children}
    </div>
  ),
  useCurrentFrame: () => env.frame,
  useVideoConfig: () => ({fps: 30, width: env.width, height: env.height}),
}));

const extractFontSizesPx = (html: string): number[] => {
  const sizes: number[] = [];
  const regex = /font-size:(\d+(?:\.\d+)?)px/g;
  let match = regex.exec(html);
  while (match !== null) {
    sizes.push(Number.parseFloat(match[1]));
    match = regex.exec(html);
  }
  return sizes;
};

const stripTags = (html: string): string => html.replace(/<[^>]+>/g, ' ');

const SAMPLE_SCAN_ROWS: readonly [string, string, string][] = [
  ['Chỉ tiêu', 'Giá trị tham chiếu', 'Nhận định lâm sàng'],
  ['Urat huyết thanh', '≥ 6,8 mg/dL', 'Bắt đầu kết tủa tinh thể hình kim'],
  ['Dịch khớp MTP1', 'Phân cực âm tính', 'Tiêu chuẩn vàng chẩn đoán gút'],
  ['Phức hợp NLRP3', 'Giải phóng IL-1β', 'Khởi phát cơn viêm cấp tính'],
];

const SAMPLE_ANNOTATE_TARGETS: readonly AnnotateTarget[] = [
  {key: 'source', x: 64, y: 76, w: 740, h: 164, head: 'NGUỒN Y VĂN', detail: 'Đối chiếu PMID / DOI'},
  {key: 'metric', x: 64, y: 312, w: 740, h: 184, head: 'NGƯỠNG BÃO HÒA', detail: '6,8 mg/dL tại 37°C'},
  {key: 'crystal', x: 864, y: 180, w: 740, h: 316, head: 'TINH THỂ URAT', detail: 'Lắng đọng bề mặt sụn'},
  {key: 'nlrp3', x: 64, y: 568, w: 740, h: 196, head: 'PHỨC HỢP NLRP3', detail: 'Hoạt hóa đại thực bào'},
];

const SAMPLE_MILESTONES: readonly TimelineMilestone[] = [
  {
    stage: 'Giai đoạn 1',
    timeLabel: '12–24 giờ',
    title: 'Diễn tiến cơn gút cấp',
    desc: 'Nồng độ urat máu vượt 6,8 mg/dL nhưng chưa khởi phát cơn đau.',
  },
  {
    stage: 'Giai đoạn 2',
    timeLabel: 'Lắng đọng',
    title: 'Tinh thể hình kim bám mặt sụn',
    desc: 'Vi tinh thể monosodium urate tích tụ âm thầm trong ổ khớp.',
  },
  {
    stage: 'Giai đoạn 3',
    timeLabel: 'Bùng phát',
    title: 'Cơn gút cấp tính',
    desc: 'Đại thực bào kích hoạt NLRP3 gây sưng, nóng, đỏ, đau dữ dội.',
  },
  {
    stage: 'Giai đoạn 4',
    timeLabel: 'Mạn tính',
    title: 'Hạt tophi và tổn thương khớp',
    desc: 'Tinh thể lắng đọng lâu ngày gây bào mòn xương dưới sụn.',
  },
];

describe('shotcraft motion components', () => {
  const cases = [
    {
      name: 'typography/marker-underline-title',
      expectedText: 'tăng acid uric máu',
      element: (
        <MarkerUnderlineTitle
          prefix="Biến chứng"
          emphasisText="tăng acid uric máu"
          subline="Cần theo dõi định kỳ"
        />
      ),
    },
    {
      name: 'typography/lead-word-zoom-assemble',
      expectedText: 'Viêm khớp cấp do tinh thể muối urat.',
      element: (
        <LeadWordZoomAssemble
          term="GÚT CẤP"
          definition="Viêm khớp cấp do tinh thể muối urat."
        />
      ),
    },
    {
      name: 'typography/outline-word-fill',
      expectedText: 'ĐỀ KHÁNG INSULIN',
      element: (
        <OutlineWordFill
          term="ĐỀ KHÁNG INSULIN"
          definition="Tế bào giảm đáp ứng với nồng độ hormone"
          leftReadout="BÌNH THƯỜNG < 6,0 mg/dL"
          rightReadout="KẾT TỦA ≥ 6,8 mg/dL"
        />
      ),
    },
    {
      name: 'typography/title-demote-to-label',
      expectedText: 'HỘI CHỨNG CHUYỂN HÓA',
      element: (
        <TitleDemoteToLabel
          title="HỘI CHỨNG CHUYỂN HÓA"
          chapterCode="01"
          summary="Tăng huyết áp và rối loạn mỡ máu"
          points={[
            'Nồng độ urat vượt ngưỡng hòa tan 6,8 mg/dL',
            'Tinh thể hình kim lắng đọng trên bề mặt sụn khớp',
            'Đại thực bào hoạt hóa phức hợp viêm NLRP3',
          ]}
        />
      ),
    },
    {
      name: 'data/chart-live-moves',
      expectedText: 'Nồng độ urat huyết thanh',
      element: <ChartLiveMoves label="Nồng độ urat huyết thanh" value={6.8} unit="mg/dL" />,
    },
    {
      name: 'data/gauge-readout-moves',
      expectedText: 'Ngưỡng bão hòa urat',
      element: (
        <GaugeReadoutMoves
          value={6.8}
          maxValue={12}
          unit="mg/dL"
          label="Ngưỡng bão hòa urat"
        />
      ),
    },
    {
      name: 'data/timeline-travel',
      expectedText: 'Diễn tiến cơn gút cấp',
      element: <TimelineTravel milestones={SAMPLE_MILESTONES} />,
    },
    {
      name: 'data/before-after-slider-scrub',
      expectedText: 'Điều chỉnh lối sống',
      element: (
        <BeforeAfterSliderScrub
          beforeLabel="TRƯỚC KHI KẾT TỦA"
          afterLabel="SAU KHI KẾT TỦA"
          beforeTitle="Dịch khớp trong suốt, urat hòa tan"
          afterTitle="Điều chỉnh lối sống"
          beforeValue="8,6 mg/dL"
          afterValue="5,4 mg/dL"
        />
      ),
    },
    {
      name: 'effects/scan-bracket-sweep',
      expectedText: 'Đối chiếu bằng chứng lâm sàng',
      element: (
        <ScanBracketSweep
          title="Đối chiếu bằng chứng y văn"
          emphasisText="Đối chiếu bằng chứng lâm sàng"
          rows={SAMPLE_SCAN_ROWS}
        />
      ),
    },
    {
      name: 'effects/scanline-annotate-focus',
      expectedText: 'Kết quả phân tích dịch khớp',
      element: (
        <ScanlineAnnotateFocus
          emphasisText="Kết quả phân tích dịch khớp"
          targets={SAMPLE_ANNOTATE_TARGETS}
        />
      ),
    },
    {
      name: 'effects/spotlight-sweep-moves',
      expectedText: 'Vị trí khớp bàn ngón chân cái',
      element: (
        <SpotlightSweepMoves
          title="Soi vùng lắng đọng tinh thể"
          emphasisText="Vị trí khớp bàn ngón chân cái"
          detail="Ánh sáng quét đều mở dần toàn bộ cấu trúc giải phẫu cần đối chiếu."
        />
      ),
    },
    {
      name: 'transition/circle-match-iris',
      expectedText: 'Chuyển mạch giải phẫu',
      element: (
        <CircleMatchIris
          anchorLabel="Chuyển mạch giải phẫu"
          targetTitle="Tỷ lệ khởi phát tại khớp ngón chân cái"
          targetPercent={87}
        />
      ),
    },
    {
      name: 'transition/wipe-transitions',
      expectedText: 'Sang chương điều trị dự phòng',
      expectedEndText: 'Phác đồ hạ acid uric',
      element: (
        <WipeTransitions
          fromTitle="Sang chương điều trị dự phòng"
          toTitle="Phác đồ hạ acid uric"
          fromSubtitle="Màng hoạt dịch mỏng, dịch khớp trong suốt"
          toSubtitle="Tinh thể hình kim kích hoạt phản ứng viêm cấp"
        />
      ),
    },
    {
      name: 'camera/crash-zoom-punch',
      expectedText: 'Điểm bùng phát đại thực bào',
      element: (
        <CrashZoomPunch
          targetLabel="Điểm bùng phát đại thực bào"
          targetValue="6,8 mg/dL"
          targetDetail="Phóng đại cận cảnh vị trí lắng đọng tinh thể urat gây đau cấp"
        />
      ),
    },
  ];

  for (const [width, height, profileLabel] of [
    [1080, 1920, '1080x1920'],
    [1920, 1080, '1920x1080'],
  ] as const) {
    for (const {name, expectedText, expectedEndText, element} of cases) {
      it(`renders ${name} at ${profileLabel} with fontSize >= 30px and Vietnamese diacritics`, () => {
        env.width = width;
        env.height = height;

        env.frame = 0;
        const startHtml = renderToStaticMarkup(element);
        env.frame = 42;
        const midHtml = renderToStaticMarkup(element);
        env.frame = 70;
        const qaHtml = renderToStaticMarkup(element);
        env.frame = 120;
        const endHtml = renderToStaticMarkup(element);

        expect(startHtml).toContain(expectedText);
        expect(midHtml).toContain(expectedText);
        expect(endHtml).toContain(expectedEndText ?? expectedText);
        expect(startHtml).toContain('Be Vietnam Pro');
        expect(new Set([startHtml, midHtml, endHtml]).size).toBeGreaterThanOrEqual(2);

        for (const html of [startHtml, midHtml, qaHtml, endHtml]) {
          const sizes = extractFontSizesPx(html);
          expect(sizes.length).toBeGreaterThan(0);
          expect(Math.min(...sizes)).toBeGreaterThanOrEqual(30);
        }
      });
    }
  }

  it('clips wipe-transitions layers with complementary non-overlapping clipPaths at mid frames', () => {
    for (const [width, height] of [
      [1080, 1920],
      [1920, 1080],
    ] as const) {
      env.width = width;
      env.height = height;
      for (const midFrame of [42, 70]) {
        env.frame = midFrame;
        const html = renderToStaticMarkup(
          <WipeTransitions
            fromTitle="Sang chương điều trị dự phòng"
            toTitle="Phác đồ hạ acid uric"
          />,
        );

        const fromTag = html.match(/<div[^>]*data-wipe-layer="from"[^>]*>/);
        const toTag = html.match(/<div[^>]*data-wipe-layer="to"[^>]*>/);
        expect(fromTag).not.toBeNull();
        expect(toTag).not.toBeNull();

        const fromMatch = fromTag![0].match(/clip-path:inset\(0 0 0 (\d+(?:\.\d+)?)%\)/);
        const toMatch = toTag![0].match(/clip-path:inset\(0 (\d+(?:\.\d+)?)% 0 0\)/);

        expect(fromMatch).not.toBeNull();
        expect(toMatch).not.toBeNull();

        const fromLeftInset = Number.parseFloat(fromMatch![1]);
        const toRightInset = Number.parseFloat(toMatch![1]);

        expect(fromLeftInset).toBeGreaterThan(0);
        expect(fromLeftInset).toBeLessThan(100);
        expect(toRightInset).toBeGreaterThan(0);
        expect(toRightInset).toBeLessThan(100);
        expect(fromLeftInset + toRightInset).toBeCloseTo(100, 2);
      }
    }
  });

  it('switches vertical vs horizontal layout orientations for slider, demote cards, and iris label', () => {
    env.frame = 70;

    env.width = 1080;
    env.height = 1920;
    const sliderVert = renderToStaticMarkup(<BeforeAfterSliderScrub afterTitle="ZZTERM" />);
    const demoteVert = renderToStaticMarkup(
      <TitleDemoteToLabel title="ZZTERM" points={['ZZA', 'ZZB']} />,
    );
    const irisVert = renderToStaticMarkup(
      <CircleMatchIris anchorLabel="ZZTERM" targetTitle="ZZTARGET" />,
    );
    expect(sliderVert).toContain('data-slider-orientation="horizontal"');
    expect(demoteVert).toContain('data-cards-axis="column"');
    expect(irisVert).toContain('data-iris-label-position="below"');

    env.width = 1920;
    env.height = 1080;
    const sliderHoriz = renderToStaticMarkup(<BeforeAfterSliderScrub afterTitle="ZZTERM" />);
    const demoteHoriz = renderToStaticMarkup(
      <TitleDemoteToLabel title="ZZTERM" points={['ZZA', 'ZZB']} />,
    );
    const irisHoriz = renderToStaticMarkup(
      <CircleMatchIris anchorLabel="ZZTERM" targetTitle="ZZTARGET" />,
    );
    expect(sliderHoriz).toContain('data-slider-orientation="vertical"');
    expect(demoteHoriz).toContain('data-cards-axis="row"');
    expect(irisHoriz).toContain('data-iris-label-position="right"');
  });

  const FORBIDDEN_MEDICAL_TOKENS = ['mg/dL', 'NLRP3', 'PMID', 'IL-1', 'urat', '%'] as const;

  const minimalMarkerCases = [
    {name: 'MarkerUnderlineTitle', element: <MarkerUnderlineTitle emphasisText="ZZTERM" />, allowedDigits: []},
    {name: 'LeadWordZoomAssemble', element: <LeadWordZoomAssemble term="ZZTERM" />, allowedDigits: []},
    {name: 'OutlineWordFill', element: <OutlineWordFill term="ZZTERM" />, allowedDigits: []},
    {name: 'TitleDemoteToLabel', element: <TitleDemoteToLabel title="ZZTERM" />, allowedDigits: []},
    {name: 'ScanBracketSweep', element: <ScanBracketSweep emphasisText="ZZTERM" />, allowedDigits: []},
    {name: 'ScanlineAnnotateFocus', element: <ScanlineAnnotateFocus emphasisText="ZZTERM" />, allowedDigits: []},
    {name: 'SpotlightSweepMoves', element: <SpotlightSweepMoves emphasisText="ZZTERM" />, allowedDigits: []},
    {name: 'CircleMatchIris', element: <CircleMatchIris anchorLabel="ZZTERM" />, allowedDigits: []},
    {name: 'WipeTransitions', element: <WipeTransitions fromTitle="ZZTERM" />, allowedDigits: []},
    {name: 'CrashZoomPunch', element: <CrashZoomPunch targetValue="ZZTERM" />, allowedDigits: []},
    {name: 'ChartLiveMoves (label only)', element: <ChartLiveMoves label="ZZTERM" />, allowedDigits: []},
    {name: 'ChartLiveMoves (with value)', element: <ChartLiveMoves label="ZZTERM" value={42} unit="ZZUNIT" />, allowedDigits: ['4', '2']},
    {name: 'GaugeReadoutMoves (label only)', element: <GaugeReadoutMoves label="ZZTERM" />, allowedDigits: []},
    {name: 'GaugeReadoutMoves (with value)', element: <GaugeReadoutMoves label="ZZTERM" value={42} unit="ZZUNIT" />, allowedDigits: ['4', '2']},
    {name: 'TimelineTravel', element: <TimelineTravel milestones={[{title: 'ZZTERM'}]} />, allowedDigits: []},
    {name: 'BeforeAfterSliderScrub', element: <BeforeAfterSliderScrub afterTitle="ZZTERM" />, allowedDigits: []},
  ] as const;

  for (const {name, element, allowedDigits} of minimalMarkerCases) {
    it(`renders ${name} with minimal props + ZZTERM without default medical text or unpassed digits`, () => {
      for (const [width, height] of [
        [1080, 1920],
        [1920, 1080],
      ] as const) {
        env.width = width;
        env.height = height;
        for (const frame of [0, 42, 70, 120]) {
          env.frame = frame;
          const html = renderToStaticMarkup(element);
          const visibleText = stripTags(html);

          expect(visibleText).toContain('ZZTERM');

          const digitsInText = visibleText.match(/\d/g) ?? [];
          for (const d of digitsInText) {
            expect(allowedDigits).toContain(d);
          }

          for (const token of FORBIDDEN_MEDICAL_TOKENS) {
            expect(visibleText.toLowerCase()).not.toContain(token.toLowerCase());
            if (token !== '%') {
              expect(html.toLowerCase()).not.toContain(token.toLowerCase());
            }
          }
        }
      }
    });
  }

  for (const emphasis of MOTION_EMPHASIS_KINDS) {
    it(`renders SceneMotionOverlay emphasis=${emphasis} with only emphasis_text and no extra numbers or medical defaults`, () => {
      env.width = 1080;
      env.height = 1920;
      for (const frame of [0, 42, 70, 120]) {
        env.frame = frame;
        const html = renderToStaticMarkup(
          <SceneMotionOverlay
            motion={{emphasis, emphasis_text: 'ZZTERM'}}
            narration="Câu thuyết minh có số 6,8 mg/dL urat NLRP3 PMID IL-1β 87%"
          />,
        );
        const visibleText = stripTags(html);
        expect(visibleText).toContain('ZZTERM');
        expect(visibleText).not.toMatch(/\d/);
        for (const token of FORBIDDEN_MEDICAL_TOKENS) {
          expect(visibleText.toLowerCase()).not.toContain(token.toLowerCase());
          if (token !== '%') {
            expect(html.toLowerCase()).not.toContain(token.toLowerCase());
          }
        }
      }
    });
  }

  for (const transition_in of MOTION_TRANSITION_KINDS) {
    it(`renders SceneMotionOverlay transition_in=${transition_in} as pure geometry without text or numbers`, () => {
      env.width = 1080;
      env.height = 1920;
      for (const frame of [0, 10, 25, 42, 70]) {
        env.frame = frame;
        const html = renderToStaticMarkup(
          <SceneMotionOverlay
            motion={{transition_in}}
            narration="Câu thuyết minh có số 6,8 mg/dL urat NLRP3 PMID IL-1β 87%"
          />,
        );
        const visibleText = stripTags(html).trim();
        expect(visibleText).toBe('');
        expect(visibleText).not.toMatch(/\d/);
        for (const token of FORBIDDEN_MEDICAL_TOKENS) {
          if (token !== '%') {
            expect(html.toLowerCase()).not.toContain(token.toLowerCase());
          }
        }
      }
    });
  }

  for (const variant of ['gauge-readout-moves', 'chart-live-moves', 'timeline-travel'] as const) {
    it(`renders StatGaugeScene variant=${variant} with only value, unit, label and no extra numbers or defaults`, () => {
      env.width = 1080;
      env.height = 1920;
      for (const frame of [0, 42, 70, 120]) {
        env.frame = frame;
        const html = renderToStaticMarkup(
          <LayoutContext.Provider value={LAYOUTS.vertical_clip}>
            <StatGaugeScene
              scene={{
                id: 'S01',
                start_frame: 0,
                duration_frames: 90,
                narration: 'Lời thuyết minh',
                claim_id: 'C01',
                visual: 'stat_gauge',
                stat_gauge: {
                  value: 42,
                  unit: 'ZZUNIT',
                  label: 'ZZTERM',
                  variant,
                },
                visual_assets: [],
              }}
            />
          </LayoutContext.Provider>,
        );
        const visibleText = stripTags(html);
        expect(visibleText).toContain('42');
        expect(visibleText).toContain('ZZUNIT');
        expect(visibleText).toContain('ZZTERM');
        const digitsInText = visibleText.match(/\d/g) ?? [];
        for (const d of digitsInText) {
          expect(['4', '2']).toContain(d);
        }
        for (const token of FORBIDDEN_MEDICAL_TOKENS) {
          expect(visibleText.toLowerCase()).not.toContain(token.toLowerCase());
          if (token !== '%') {
            expect(html.toLowerCase()).not.toContain(token.toLowerCase());
          }
        }
      }
    });
  }

  for (const variant of [
    'lead-word-zoom-assemble',
    'outline-word-fill',
    'marker-underline-title',
    'title-demote-to-label',
  ] as const) {
    it(`renders KineticTermScene variant=${variant} with only term and definition and no digits or medical defaults`, () => {
      env.width = 1080;
      env.height = 1920;
      for (const frame of [0, 42, 70, 120]) {
        env.frame = frame;
        const html = renderToStaticMarkup(
          <LayoutContext.Provider value={LAYOUTS.vertical_clip}>
            <KineticTermScene
              scene={{
                id: 'S01',
                start_frame: 0,
                duration_frames: 90,
                narration: 'Lời thuyết minh',
                visual: 'kinetic_term',
                kinetic_term: {
                  term: 'ZZTERM',
                  definition: 'ZZDEF',
                  variant,
                },
                visual_assets: [],
              }}
            />
          </LayoutContext.Provider>,
        );
        const visibleText = stripTags(html);
        expect(visibleText).toContain('ZZTERM');
        expect(visibleText).toContain('ZZDEF');
        expect(visibleText).not.toMatch(/\d/);
        for (const token of FORBIDDEN_MEDICAL_TOKENS) {
          expect(visibleText.toLowerCase()).not.toContain(token.toLowerCase());
          if (token !== '%') {
            expect(html.toLowerCase()).not.toContain(token.toLowerCase());
          }
        }
      }
    });
  }
});
