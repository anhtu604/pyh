import React from 'react';
import type {SceneTransitionProps} from '../motion/sceneEnvelope';
import type {Scene} from '../types';
import {MechanismScene} from './MechanismScene';
export const TimelapseScene: React.FC<{
  scene: Scene;
  transition?: SceneTransitionProps;
  forceLightCanvas?: boolean;
}> = ({scene, transition, forceLightCanvas}) => (
  <MechanismScene scene={scene} kind="timelapse" transition={transition} forceLightCanvas={forceLightCanvas} />
);
