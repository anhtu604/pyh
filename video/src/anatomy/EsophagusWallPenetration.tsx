import React from 'react';
import type {OrganProps} from './ArterySection';
import {EsophagusDiagram} from './EsophagusDiagram';
import type {DiagramLabels} from './annotations';
export const CONTENT_BOX = {left: 30, top: 30, width: 500, height: 500};
export const CUE_ACTIONS: readonly string[] = ['swallow', 'press', 'penetrate', 'swell'];
export const FOCUS_REGIONS = {"overview": {"left": 0, "top": 0, "width": 560, "height": 560}, "detail": {"left": 115, "top": 150, "width": 330, "height": 330}};
export const LABELS: DiagramLabels = {"tip": {"text": "Mũi xương", "region": "detail", "x": 28, "y": 12, "width": 226, "height": 36, "anchor": [280, 295]}, "mucosa": {"text": "Niêm mạc", "region": "detail", "x": 306, "y": 12, "width": 226, "height": 36, "anchor": [430, 300]}, "muscle": {"text": "Lớp cơ", "region": "detail", "x": 28, "y": 512, "width": 226, "height": 36, "anchor": [430, 450]}};
// penetration-and-tissue: original flat diagram; process timing is illustrative, never a clinical scale.
export const EsophagusWallPenetration: React.FC<OrganProps> = (props) => <EsophagusDiagram {...props} view="wall" labels={LABELS}/>;
