import React from 'react';
import {Composition} from 'remotion';
import {HealthVideo} from './HealthVideo';
import {parseRenderInput} from './types';
import type {RenderInput, Scene} from './types';

export const MIN_DURATION_IN_FRAMES = 1350;

const defaultProps: RenderInput = {
  schema_version: '1.0',
  title: 'Protect Your Health',
  audio_file: 'audio/silence.wav',
  scenes: [
    {
      schema_version: '1.0',
      id: 'S01',
      start_frame: 0,
      duration_frames: MIN_DURATION_IN_FRAMES,
      narration: 'Bản xem trước video y tế dự phòng.',
      visual: 'whiteboard',
    },
  ],
  width: 1080,
  height: 1920,
  fps: 30,
};

export const durationFromScenes = (scenes: Scene[]): number =>
  Math.max(
    MIN_DURATION_IN_FRAMES,
    ...scenes.map((scene) => scene.start_frame + scene.duration_frames),
  );

export const RemotionRoot: React.FC = () => (
  <Composition
    id="HealthVideo"
    component={HealthVideo}
    defaultProps={defaultProps}
    durationInFrames={MIN_DURATION_IN_FRAMES}
    fps={30}
    width={1080}
    height={1920}
    calculateMetadata={({props}) => ({
      durationInFrames: durationFromScenes(parseRenderInput(props).scenes),
    })}
  />
);
