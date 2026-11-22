import React from 'react';
import type {Scene, VisualStyle} from '../types';
import {MechanismScene} from './MechanismScene';
export const AnatomyScene: React.FC<{scene: Scene; visualStyle?: VisualStyle}> = ({scene, visualStyle}) => (
  <MechanismScene scene={scene} kind="anatomy" visualStyle={visualStyle} />
);
