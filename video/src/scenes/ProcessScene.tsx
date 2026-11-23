import React from 'react';
import type {SceneTransitionProps} from '../motion/sceneEnvelope';
import type {Scene, VisualStyle} from '../types';
import {MechanismScene} from './MechanismScene';
export const ProcessScene: React.FC<{
  scene: Scene;
  visualStyle?: VisualStyle;
  transition?: SceneTransitionProps;
  forceLightCanvas?: boolean;
}> = ({scene, visualStyle, transition, forceLightCanvas}) => (
  <MechanismScene
    scene={scene}
    kind="process"
    visualStyle={visualStyle}
    transition={transition}
    forceLightCanvas={forceLightCanvas}
  />
);
