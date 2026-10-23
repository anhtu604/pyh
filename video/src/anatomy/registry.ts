import type React from 'react';
import type {Anatomy} from '../types';
import {ArterySection, type OrganProps} from './ArterySection';
import {Heart} from './Heart';
import {HepaticCell} from './HepaticCell';
import library from './library.json';

export type AnatomySubject = Anatomy['subject'];

export const ANATOMY_COMPONENTS: Record<AnatomySubject, React.FC<OrganProps>> = {
  artery_cross_section: ArterySection,
  heart: Heart,
  hepatic_cell_and_tissue_lipid_balance: HepaticCell,
};

export const ANATOMY_SUBJECTS = Object.keys(library.components);
