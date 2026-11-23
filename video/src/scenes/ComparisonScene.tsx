import React from 'react';
import type {SceneTransitionProps} from '../motion/sceneEnvelope';
import type {Scene} from '../types';
import {MechanismScene} from './MechanismScene';
export const ComparisonScene: React.FC<{
  scene: Scene;
  transition?: SceneTransitionProps;
  forceLightCanvas?: boolean;
}> = ({scene, transition, forceLightCanvas}) => (
  <MechanismScene scene={scene} kind="comparison" transition={transition} forceLightCanvas={forceLightCanvas} />
);
