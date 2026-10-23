import type React from 'react';
import type {Anatomy} from '../types';
import {ArterySection, CONTENT_BOX as ARTERY_CONTENT_BOX, type OrganProps} from './ArterySection';
import {Heart, CONTENT_BOX as HEART_CONTENT_BOX} from './Heart';
import {HepaticCell, CONTENT_BOX as HEPATIC_CONTENT_BOX} from './HepaticCell';
import library from './library.json';
import {LiverLobule, CONTENT_BOX as LOBULE_CONTENT_BOX} from './LiverLobule';
import {LiverOrgan, CONTENT_BOX as LIVER_CONTENT_BOX} from './LiverOrgan';

export type AnatomySubject = Anatomy['subject'];

export const ANATOMY_COMPONENTS: Record<AnatomySubject, React.FC<OrganProps>> = {
  artery_cross_section: ArterySection,
  heart: Heart,
  hepatic_cell_and_tissue_lipid_balance: HepaticCell,
  liver_lobule: LiverLobule,
  liver_organ: LiverOrgan,
};

export const ANATOMY_SUBJECTS = Object.keys(library.components);

export const ANATOMY_CONTENT_BOXES: Record<AnatomySubject, {left: number; top: number; width: number; height: number}> = {
  artery_cross_section: ARTERY_CONTENT_BOX,
  heart: HEART_CONTENT_BOX,
  hepatic_cell_and_tissue_lipid_balance: HEPATIC_CONTENT_BOX,
  liver_lobule: LOBULE_CONTENT_BOX,
  liver_organ: LIVER_CONTENT_BOX,
};

// SVG coordinates used when mapping content bounds through preserveAspectRatio="xMidYMid meet".
export const ANATOMY_VIEW_BOXES: Record<AnatomySubject, {left: number; top: number; width: number; height: number}> = {
  artery_cross_section: {left: 0, top: 0, width: 560, height: 560},
  heart: {left: 80, top: 10, width: 520, height: 520},
  hepatic_cell_and_tissue_lipid_balance: {left: 0, top: 0, width: 560, height: 560},
  liver_lobule: {left: 0, top: 0, width: 560, height: 560},
  liver_organ: {left: 0, top: 0, width: 560, height: 560},
};
