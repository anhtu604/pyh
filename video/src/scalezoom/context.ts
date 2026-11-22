import {createContext, useContext} from 'react';
import type {VisualStyle} from '../types';

export const VisualStyleContext = createContext<VisualStyle | undefined>(undefined);

export const useVisualStyle = (): VisualStyle | undefined => {
  try {
    return useContext(VisualStyleContext);
  } catch {
    return undefined;
  }
};
