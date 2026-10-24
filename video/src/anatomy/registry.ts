import type React from 'react';
import type {Anatomy} from '../types';
import type {OrganProps} from './ArterySection';
import type {FocusRegion,DiagramLabels} from './annotations';
import library from './library.json';
import * as UrateFluidModule from './UrateFluid';
import * as InflammationSignalModule from './InflammationSignal';
import * as ArterySectionModule from './ArterySection';
import * as HepaticCellModule from './HepaticCell';
import * as LiverLobuleModule from './LiverLobule';
import * as LiverOrganModule from './LiverOrgan';
import * as HeartModule from './Heart';
import * as GoutFootOverviewModule from './GoutFootOverview';
import * as UrateCrystalCloseUpModule from './UrateCrystalCloseUp';
import * as UrateDepositionModule from './UrateDeposition';

export type AnatomySubject = Anatomy['subject'];
export const ANATOMY_SUBJECTS = Object.keys(library.components);
export const ANATOMY_CUE_ACTIONS: Record<AnatomySubject, readonly string[]> = {
  joint_fluid_urate_to_inflammation: UrateFluidModule.CUE_ACTIONS,
  immune_cell_alarm: InflammationSignalModule.CUE_ACTIONS,
  artery_cross_section: ArterySectionModule.CUE_ACTIONS,
  hepatic_cell_and_tissue_lipid_balance: HepaticCellModule.CUE_ACTIONS,
  liver_lobule: LiverLobuleModule.CUE_ACTIONS,
  liver_organ: LiverOrganModule.CUE_ACTIONS,
  heart: HeartModule.CUE_ACTIONS,
  gout_foot_overview: GoutFootOverviewModule.CUE_ACTIONS,
  urate_crystal_close_up: UrateCrystalCloseUpModule.CUE_ACTIONS,
  urate_deposition: UrateDepositionModule.CUE_ACTIONS,
};
export const ANATOMY_CONTENT_BOXES: Record<AnatomySubject, FocusRegion> = {
  joint_fluid_urate_to_inflammation: UrateFluidModule.CONTENT_BOX,
  immune_cell_alarm: InflammationSignalModule.CONTENT_BOX,
  artery_cross_section: ArterySectionModule.CONTENT_BOX,
  hepatic_cell_and_tissue_lipid_balance: HepaticCellModule.CONTENT_BOX,
  liver_lobule: LiverLobuleModule.CONTENT_BOX,
  liver_organ: LiverOrganModule.CONTENT_BOX,
  heart: HeartModule.CONTENT_BOX,
  gout_foot_overview: GoutFootOverviewModule.CONTENT_BOX,
  urate_crystal_close_up: UrateCrystalCloseUpModule.CONTENT_BOX,
  urate_deposition: UrateDepositionModule.CONTENT_BOX,
};
export const ANATOMY_FOCUS_REGIONS: Record<AnatomySubject, Record<string, FocusRegion>> = {
  joint_fluid_urate_to_inflammation: UrateFluidModule.FOCUS_REGIONS,
  immune_cell_alarm: InflammationSignalModule.FOCUS_REGIONS,
  artery_cross_section: ArterySectionModule.FOCUS_REGIONS,
  hepatic_cell_and_tissue_lipid_balance: HepaticCellModule.FOCUS_REGIONS,
  liver_lobule: LiverLobuleModule.FOCUS_REGIONS,
  liver_organ: LiverOrganModule.FOCUS_REGIONS,
  heart: HeartModule.FOCUS_REGIONS,
  gout_foot_overview: GoutFootOverviewModule.FOCUS_REGIONS,
  urate_crystal_close_up: UrateCrystalCloseUpModule.FOCUS_REGIONS,
  urate_deposition: UrateDepositionModule.FOCUS_REGIONS,
};
export const ANATOMY_LABELS: Record<AnatomySubject, DiagramLabels> = {
  joint_fluid_urate_to_inflammation: UrateFluidModule.LABELS,
  immune_cell_alarm: InflammationSignalModule.LABELS,
  artery_cross_section: ArterySectionModule.LABELS,
  hepatic_cell_and_tissue_lipid_balance: HepaticCellModule.LABELS,
  liver_lobule: LiverLobuleModule.LABELS,
  liver_organ: LiverOrganModule.LABELS,
  heart: HeartModule.LABELS,
  gout_foot_overview: GoutFootOverviewModule.LABELS,
  urate_crystal_close_up: UrateCrystalCloseUpModule.LABELS,
  urate_deposition: UrateDepositionModule.LABELS,
};
export const ANATOMY_COMPONENTS: Record<AnatomySubject, React.FC<OrganProps>> = {
  joint_fluid_urate_to_inflammation: UrateFluidModule.UrateFluid,
  immune_cell_alarm: InflammationSignalModule.InflammationSignal,
  artery_cross_section: ArterySectionModule.ArterySection,
  hepatic_cell_and_tissue_lipid_balance: HepaticCellModule.HepaticCell,
  liver_lobule: LiverLobuleModule.LiverLobule,
  liver_organ: LiverOrganModule.LiverOrgan,
  heart: HeartModule.Heart,
  gout_foot_overview: GoutFootOverviewModule.GoutFootOverview,
  urate_crystal_close_up: UrateCrystalCloseUpModule.UrateCrystalCloseUp,
  urate_deposition: UrateDepositionModule.UrateDeposition,
};
export const ANATOMY_VIEW_BOXES: Record<AnatomySubject, FocusRegion> = {
  joint_fluid_urate_to_inflammation: {left:0,top:0,width:560,height:560},
  immune_cell_alarm: {left:0,top:0,width:560,height:560},
  artery_cross_section: {left:0,top:0,width:560,height:560},
  hepatic_cell_and_tissue_lipid_balance: {left:0,top:0,width:560,height:560},
  liver_lobule: {left:0,top:0,width:560,height:560},
  liver_organ: {left:0,top:0,width:560,height:560},
  heart: {left:80,top:10,width:520,height:520},
  gout_foot_overview: {left:0,top:0,width:560,height:560},
  urate_crystal_close_up: {left:0,top:0,width:560,height:560},
  urate_deposition: {left:0,top:0,width:560,height:560},
};
