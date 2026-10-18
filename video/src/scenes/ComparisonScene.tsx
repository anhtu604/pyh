import React from 'react';
import type {Scene} from '../types';
import {MechanismScene} from './MechanismScene';
export const ComparisonScene: React.FC<{scene: Scene}> = ({scene}) => <MechanismScene scene={scene} kind="comparison" />;
