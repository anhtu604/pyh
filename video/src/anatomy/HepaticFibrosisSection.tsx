import React from 'react';
import type {OrganProps} from './ArterySection';
import type {DiagramLabels} from './annotations';
import {HepatocyteDiagram} from './HepatocyteDiagram';
export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 484};
export const CUE_ACTIONS: readonly string[] = ['export', 'leak', 'toxic', 'block', 'scar'];
// Retain the full cell, nucleus and blood destination at every locked beat.
export const FOCUS_REGIONS = {
  overview: {left: 0, top: 0, width: 560, height: 560},
  cell: CONTENT_BOX, blood: CONTENT_BOX, bile: CONTENT_BOX,
};
export const LABELS: DiagramLabels = {"cell": {"text": "Tế bào gan", "region": "cell", "x": 28, "y": 350, "width": 160, "height": 34, "anchor": [58, 332]}, "blood": {"text": "Dòng máu", "region": "blood", "x": 350, "y": 516, "width": 182, "height": 34, "anchor": [490, 470]}, "bile": {"text": "Đường mật", "region": "bile", "x": 342, "y": 8, "width": 190, "height": 34, "anchor": [430, 55]}, "scar": {"text": "Dải xơ", "region": "cell", "x": 422, "y": 338, "width": 110, "height": 34, "anchor": [453, 320]}};
export const HepaticFibrosisSection: React.FC<OrganProps> = (props) => <HepatocyteDiagram {...props} view="scar" labels={LABELS}/>;

// Delegated SVG layers: sinusoid, hepatocyte-membrane, bile-canaliculus, fibrous-septa
