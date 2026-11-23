import React from 'react';
import {Captions} from '../components/Captions';
import {ChartLiveMoves} from '../motion/ChartLiveMoves';
import {GaugeReadoutMoves} from '../motion/GaugeReadoutMoves';
import {TimelineTravel} from '../motion/TimelineTravel';
import {SceneEnvelopeWrapper, type SceneTransitionProps} from '../motion/sceneEnvelope';
import type {Scene} from '../types';

export const StatGaugeScene: React.FC<{scene: Scene; transition?: SceneTransitionProps}> = ({scene, transition}) => {
  const gauge = scene.stat_gauge;
  if (!gauge) {
    throw new Error('stat_gauge scene requires stat_gauge metadata');
  }
  const variant = gauge.variant ?? 'gauge-readout-moves';
  const content = (
    <>
      {variant === 'chart-live-moves' ? (
        <ChartLiveMoves
          value={gauge.value}
          unit={gauge.unit}
          label={gauge.label}
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
        />
      )}
      <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} />
    </>
  );
  return transition ? <SceneEnvelopeWrapper transition={transition}>{content}</SceneEnvelopeWrapper> : content;
};
