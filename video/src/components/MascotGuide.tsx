import React from 'react';
import {useLayout, type Box} from '../layout';
import type {SceneTransitionProps} from '../motion/sceneEnvelope';
import type {Scene} from '../types';
import {VisualAsset} from './VisualAsset';

export const MascotGuide: React.FC<{
  scene: Pick<Scene, 'visual_assets'>;
  box?: Box;
  continuation?: boolean;
  transition?: SceneTransitionProps;
}> = ({scene, box, continuation, transition}) => {
  const layout = useLayout();
  const asset = scene.visual_assets?.find((item) => item.role === 'mascot');
  return asset ? (
    <VisualAsset
      asset={asset}
      box={box ?? layout.mechanism.mascot}
      continuation={continuation}
      transition={transition}
    />
  ) : null;
};
