import React from 'react';
import {Captions} from '../components/Captions';
import {ChartLiveMoves} from '../motion/ChartLiveMoves';
import {GaugeReadoutMoves} from '../motion/GaugeReadoutMoves';
import {TimelineTravel} from '../motion/TimelineTravel';
import type {Scene} from '../types';
import {SourceMarker} from './WhiteboardScene';

export const StatGaugeScene: React.FC<{scene: Scene}> = ({scene}) => {
  const gauge = scene.stat_gauge;
  if (!gauge) {
    throw new Error('stat_gauge scene requires stat_gauge metadata');
  }
  const variant = gauge.variant ?? 'gauge-readout-moves';
  return (
    <>
      {variant === 'chart-live-moves' ? (
        <ChartLiveMoves
          value={gauge.value}
          unit={gauge.unit}
          label={gauge.label}
          sourceMarker={scene.source_marker}
        />
      ) : variant === 'timeline-travel' ? (
        <TimelineTravel
          milestones={[
            {
              timeLabel: `${gauge.value} ${gauge.unit}`,
              title: gauge.label,
            },
          ]}
        />
      ) : (
        <GaugeReadoutMoves
          value={gauge.value}
          maxValue={gauge.max_value ?? undefined}
          unit={gauge.unit}
          label={gauge.label}
          sourceMarker={scene.source_marker}
        />
      )}
      {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
      <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} />
    </>
  );
};
