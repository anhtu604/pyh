import React from 'react';
import type {OrganProps} from './ArterySection';
import {EsophagusDiagram} from './EsophagusDiagram';
import type {DiagramLabels} from './annotations';
export const CONTENT_BOX = {left: 30, top: 30, width: 500, height: 500};
export const CUE_ACTIONS: readonly string[] = ['swallow', 'press', 'penetrate', 'swell'];
export const FOCUS_REGIONS = {"overview": {"left": 0, "top": 0, "width": 560, "height": 560}, "detail": {"left": 115, "top": 150, "width": 330, "height": 330}};
export const LABELS: DiagramLabels = {"bone": {"text": "Xương cá", "region": "detail", "x": 28, "y": 12, "width": 226, "height": 36, "anchor": [340, 274]}, "lumen": {"text": "Lòng thực quản", "region": "detail", "x": 306, "y": 12, "width": 226, "height": 36, "anchor": [220, 210]}, "wall": {"text": "Thành thực quản", "region": "detail", "x": 28, "y": 512, "width": 226, "height": 36, "anchor": [430, 430]}};
// transverse-impaction: original flat diagram; process timing is illustrative, never a clinical scale.
export const EsophagusTransverseImpaction: React.FC<OrganProps> = (props) => <EsophagusDiagram {...props} view="section" labels={LABELS}/>;
