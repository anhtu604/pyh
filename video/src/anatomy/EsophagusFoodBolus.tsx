import React from 'react';
import type {OrganProps} from './ArterySection';
import {EsophagusDiagram} from './EsophagusDiagram';
import type {DiagramLabels} from './annotations';
export const CONTENT_BOX = {left: 30, top: 30, width: 500, height: 500};
export const CUE_ACTIONS: readonly string[] = ['swallow', 'press', 'penetrate', 'swell'];
export const FOCUS_REGIONS = {"overview": {"left": 0, "top": 0, "width": 560, "height": 560}, "detail": {"left": 115, "top": 150, "width": 330, "height": 330}};
export const LABELS: DiagramLabels = {"tube": {"text": "Thành thực quản", "region": "detail", "x": 28, "y": 12, "width": 226, "height": 36, "anchor": [145, 330]}, "bolus": {"text": "Khối thức ăn mềm", "region": "detail", "x": 306, "y": 12, "width": 226, "height": 36, "anchor": [280, 145]}, "muscle": {"text": "Cơ thực quản", "region": "detail", "x": 28, "y": 512, "width": 226, "height": 36, "anchor": [90, 260]}};
// bolus-and-contraction: original flat diagram; process timing is illustrative, never a clinical scale.
export const EsophagusFoodBolus: React.FC<OrganProps> = (props) => <EsophagusDiagram {...props} view="bolus" labels={LABELS}/>;
