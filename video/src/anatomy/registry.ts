import type React from 'react';
import type {Anatomy} from '../types';
import {ArterySection, CONTENT_BOX as ARTERY_CONTENT_BOX, type OrganProps} from './ArterySection';
import {Heart, CONTENT_BOX as HEART_CONTENT_BOX} from './Heart';
import {HepaticCell, CONTENT_BOX as HEPATIC_CONTENT_BOX} from './HepaticCell';
import library from './library.json';

export type AnatomySubject = Anatomy['subject'];

export const ANATOMY_COMPONENTS: Record<AnatomySubject, React.FC<OrganProps>> = {
  artery_cross_section: ArterySection,
  heart: Heart,
  hepatic_cell_and_tissue_lipid_balance: HepaticCell,
};

export const ANATOMY_SUBJECTS = Object.keys(library.components);

export const ANATOMY_CONTENT_BOXES: Record<AnatomySubject, {left: number; top: number; width: number; height: number}> = {
  artery_cross_section: ARTERY_CONTENT_BOX,
  heart: HEART_CONTENT_BOX,
  hepatic_cell_and_tissue_lipid_balance: HEPATIC_CONTENT_BOX,
};
