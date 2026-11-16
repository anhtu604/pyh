import * as AltAstTissueDistributionModule from './AltAstTissueDistribution';
import * as HepaticFibrosisSectionModule from './HepaticFibrosisSection';
import * as HepaticToxicInjuryModule from './HepaticToxicInjury';
import * as HepaticSynthesisAndBileModule from './HepaticSynthesisAndBile';
import * as HepatocyteSinusoidUnitModule from './HepatocyteSinusoidUnit';
import * as IntestinalVitaminCAbsorptionModule from './IntestinalVitaminCAbsorption';
import * as CalciumOxalateCrystalModule from './CalciumOxalateCrystal';
import * as VitaminCOxalatePathwayModule from './VitaminCOxalatePathway';
import * as VitaminCTransportModule from './VitaminCTransport';
import * as RenalTubuleOxalateModule from './RenalTubuleOxalate';
import * as MuscleWastingSectionModule from './MuscleWastingSection';
import * as TumorProteinUptakeModule from './TumorProteinUptake';
import * as MuscleProteinTurnoverModule from './MuscleProteinTurnover';
import * as MuscleTumorAminoAcidBalanceModule from './MuscleTumorAminoAcidBalance';
import * as EsophagusTransverseImpactionModule from './EsophagusTransverseImpaction';
import * as EsophagusWallPenetrationModule from './EsophagusWallPenetration';
import * as EsophagusFoodBolusModule from './EsophagusFoodBolus';
import * as EsophagusAorticArchModule from './EsophagusAorticArch';
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
  alt_ast_tissue_distribution: AltAstTissueDistributionModule.CUE_ACTIONS,
  hepatic_fibrosis_section: HepaticFibrosisSectionModule.CUE_ACTIONS,
  hepatic_toxic_injury: HepaticToxicInjuryModule.CUE_ACTIONS,
  hepatic_synthesis_and_bile: HepaticSynthesisAndBileModule.CUE_ACTIONS,
  hepatocyte_sinusoid_unit: HepatocyteSinusoidUnitModule.CUE_ACTIONS,
  intestinal_vitamin_c_absorption: IntestinalVitaminCAbsorptionModule.CUE_ACTIONS,
  calcium_oxalate_crystal: CalciumOxalateCrystalModule.CUE_ACTIONS,
  vitamin_c_oxalate_pathway: VitaminCOxalatePathwayModule.CUE_ACTIONS,
  vitamin_c_transport: VitaminCTransportModule.CUE_ACTIONS,
  renal_tubule_oxalate: RenalTubuleOxalateModule.CUE_ACTIONS,
  muscle_wasting_section: MuscleWastingSectionModule.CUE_ACTIONS,
  tumor_protein_uptake: TumorProteinUptakeModule.CUE_ACTIONS,
  muscle_protein_turnover: MuscleProteinTurnoverModule.CUE_ACTIONS,
  muscle_tumor_amino_acid_balance: MuscleTumorAminoAcidBalanceModule.CUE_ACTIONS,
  esophagus_transverse_impaction: EsophagusTransverseImpactionModule.CUE_ACTIONS,
  esophagus_wall_penetration: EsophagusWallPenetrationModule.CUE_ACTIONS,
  esophagus_food_bolus: EsophagusFoodBolusModule.CUE_ACTIONS,
  esophagus_aortic_arch_impaction: EsophagusAorticArchModule.CUE_ACTIONS,
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
  alt_ast_tissue_distribution: AltAstTissueDistributionModule.CONTENT_BOX,
  hepatic_fibrosis_section: HepaticFibrosisSectionModule.CONTENT_BOX,
  hepatic_toxic_injury: HepaticToxicInjuryModule.CONTENT_BOX,
  hepatic_synthesis_and_bile: HepaticSynthesisAndBileModule.CONTENT_BOX,
  hepatocyte_sinusoid_unit: HepatocyteSinusoidUnitModule.CONTENT_BOX,
  intestinal_vitamin_c_absorption: IntestinalVitaminCAbsorptionModule.CONTENT_BOX,
  calcium_oxalate_crystal: CalciumOxalateCrystalModule.CONTENT_BOX,
  vitamin_c_oxalate_pathway: VitaminCOxalatePathwayModule.CONTENT_BOX,
  vitamin_c_transport: VitaminCTransportModule.CONTENT_BOX,
  renal_tubule_oxalate: RenalTubuleOxalateModule.CONTENT_BOX,
  muscle_wasting_section: MuscleWastingSectionModule.CONTENT_BOX,
  tumor_protein_uptake: TumorProteinUptakeModule.CONTENT_BOX,
  muscle_protein_turnover: MuscleProteinTurnoverModule.CONTENT_BOX,
  muscle_tumor_amino_acid_balance: MuscleTumorAminoAcidBalanceModule.CONTENT_BOX,
  esophagus_transverse_impaction: EsophagusTransverseImpactionModule.CONTENT_BOX,
  esophagus_wall_penetration: EsophagusWallPenetrationModule.CONTENT_BOX,
  esophagus_food_bolus: EsophagusFoodBolusModule.CONTENT_BOX,
  esophagus_aortic_arch_impaction: EsophagusAorticArchModule.CONTENT_BOX,
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
  alt_ast_tissue_distribution: AltAstTissueDistributionModule.FOCUS_REGIONS,
  hepatic_fibrosis_section: HepaticFibrosisSectionModule.FOCUS_REGIONS,
  hepatic_toxic_injury: HepaticToxicInjuryModule.FOCUS_REGIONS,
  hepatic_synthesis_and_bile: HepaticSynthesisAndBileModule.FOCUS_REGIONS,
  hepatocyte_sinusoid_unit: HepatocyteSinusoidUnitModule.FOCUS_REGIONS,
  intestinal_vitamin_c_absorption: IntestinalVitaminCAbsorptionModule.FOCUS_REGIONS,
  calcium_oxalate_crystal: CalciumOxalateCrystalModule.FOCUS_REGIONS,
  vitamin_c_oxalate_pathway: VitaminCOxalatePathwayModule.FOCUS_REGIONS,
  vitamin_c_transport: VitaminCTransportModule.FOCUS_REGIONS,
  renal_tubule_oxalate: RenalTubuleOxalateModule.FOCUS_REGIONS,
  muscle_wasting_section: MuscleWastingSectionModule.FOCUS_REGIONS,
  tumor_protein_uptake: TumorProteinUptakeModule.FOCUS_REGIONS,
  muscle_protein_turnover: MuscleProteinTurnoverModule.FOCUS_REGIONS,
  muscle_tumor_amino_acid_balance: MuscleTumorAminoAcidBalanceModule.FOCUS_REGIONS,
  esophagus_transverse_impaction: EsophagusTransverseImpactionModule.FOCUS_REGIONS,
  esophagus_wall_penetration: EsophagusWallPenetrationModule.FOCUS_REGIONS,
  esophagus_food_bolus: EsophagusFoodBolusModule.FOCUS_REGIONS,
  esophagus_aortic_arch_impaction: EsophagusAorticArchModule.FOCUS_REGIONS,
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
  alt_ast_tissue_distribution: AltAstTissueDistributionModule.LABELS,
  hepatic_fibrosis_section: HepaticFibrosisSectionModule.LABELS,
  hepatic_toxic_injury: HepaticToxicInjuryModule.LABELS,
  hepatic_synthesis_and_bile: HepaticSynthesisAndBileModule.LABELS,
  hepatocyte_sinusoid_unit: HepatocyteSinusoidUnitModule.LABELS,
  intestinal_vitamin_c_absorption: IntestinalVitaminCAbsorptionModule.LABELS,
  calcium_oxalate_crystal: CalciumOxalateCrystalModule.LABELS,
  vitamin_c_oxalate_pathway: VitaminCOxalatePathwayModule.LABELS,
  vitamin_c_transport: VitaminCTransportModule.LABELS,
  renal_tubule_oxalate: RenalTubuleOxalateModule.LABELS,
  muscle_wasting_section: MuscleWastingSectionModule.LABELS,
  tumor_protein_uptake: TumorProteinUptakeModule.LABELS,
  muscle_protein_turnover: MuscleProteinTurnoverModule.LABELS,
  muscle_tumor_amino_acid_balance: MuscleTumorAminoAcidBalanceModule.LABELS,
  esophagus_transverse_impaction: EsophagusTransverseImpactionModule.LABELS,
  esophagus_wall_penetration: EsophagusWallPenetrationModule.LABELS,
  esophagus_food_bolus: EsophagusFoodBolusModule.LABELS,
  esophagus_aortic_arch_impaction: EsophagusAorticArchModule.LABELS,
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
  alt_ast_tissue_distribution: AltAstTissueDistributionModule.AltAstTissueDistribution,
  hepatic_fibrosis_section: HepaticFibrosisSectionModule.HepaticFibrosisSection,
  hepatic_toxic_injury: HepaticToxicInjuryModule.HepaticToxicInjury,
  hepatic_synthesis_and_bile: HepaticSynthesisAndBileModule.HepaticSynthesisAndBile,
  hepatocyte_sinusoid_unit: HepatocyteSinusoidUnitModule.HepatocyteSinusoidUnit,
  intestinal_vitamin_c_absorption: IntestinalVitaminCAbsorptionModule.IntestinalVitaminCAbsorption,
  calcium_oxalate_crystal: CalciumOxalateCrystalModule.CalciumOxalateCrystal,
  vitamin_c_oxalate_pathway: VitaminCOxalatePathwayModule.VitaminCOxalatePathway,
  vitamin_c_transport: VitaminCTransportModule.VitaminCTransport,
  renal_tubule_oxalate: RenalTubuleOxalateModule.RenalTubuleOxalate,
  muscle_wasting_section: MuscleWastingSectionModule.MuscleWastingSection,
  tumor_protein_uptake: TumorProteinUptakeModule.TumorProteinUptake,
  muscle_protein_turnover: MuscleProteinTurnoverModule.MuscleProteinTurnover,
  muscle_tumor_amino_acid_balance: MuscleTumorAminoAcidBalanceModule.MuscleTumorAminoAcidBalance,
  esophagus_transverse_impaction: EsophagusTransverseImpactionModule.EsophagusTransverseImpaction,
  esophagus_wall_penetration: EsophagusWallPenetrationModule.EsophagusWallPenetration,
  esophagus_food_bolus: EsophagusFoodBolusModule.EsophagusFoodBolus,
  esophagus_aortic_arch_impaction: EsophagusAorticArchModule.EsophagusAorticArch,
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
  alt_ast_tissue_distribution: {left:0,top:0,width:560,height:560},
  hepatocyte_sinusoid_unit: {left:0,top:0,width:560,height:560},
  hepatic_synthesis_and_bile: {left:0,top:0,width:560,height:560},
  hepatic_toxic_injury: {left:0,top:0,width:560,height:560},
  hepatic_fibrosis_section: {left:0,top:0,width:560,height:560},
  intestinal_vitamin_c_absorption: {left:0,top:0,width:560,height:560},
  calcium_oxalate_crystal: {left:0,top:0,width:560,height:560},
  vitamin_c_oxalate_pathway: {left:0,top:0,width:560,height:560},
  vitamin_c_transport: {left:0,top:0,width:560,height:560},
  renal_tubule_oxalate: {left:0,top:0,width:560,height:560},
  muscle_wasting_section: {left:0,top:0,width:560,height:560},
  tumor_protein_uptake: {left:0,top:0,width:560,height:560},
  muscle_protein_turnover: {left:0,top:0,width:560,height:560},
  muscle_tumor_amino_acid_balance: {left:0,top:0,width:560,height:560},
  esophagus_transverse_impaction: {left:0,top:0,width:560,height:560},
  esophagus_wall_penetration: {left:0,top:0,width:560,height:560},
  esophagus_food_bolus: {left:0,top:0,width:560,height:560},
  esophagus_aortic_arch_impaction: {left:0,top:0,width:560,height:560},
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
