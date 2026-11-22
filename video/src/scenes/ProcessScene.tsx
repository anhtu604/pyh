import React from 'react';
import type {Scene, VisualStyle} from '../types';
import {MechanismScene} from './MechanismScene';
export const ProcessScene: React.FC<{scene: Scene; visualStyle?: VisualStyle}> = ({scene, visualStyle}) => (
  <MechanismScene scene={scene} kind="process" visualStyle={visualStyle} />
);
