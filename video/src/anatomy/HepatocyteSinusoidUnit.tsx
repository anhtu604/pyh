import React from 'react';
import type {OrganProps} from './ArterySection';
import type {DiagramLabels} from './annotations';
import {HepatocyteDiagram} from './HepatocyteDiagram';
export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 484};
export const CUE_ACTIONS: readonly string[] = ['export', 'leak', 'toxic', 'block', 'scar'];
// Keep the complete mechanism and its callouts visible at every locked beat.
export const FOCUS_REGIONS = {
  overview: {left: 0, top: 0, width: 560, height: 560},
  cell: CONTENT_BOX, blood: CONTENT_BOX, bile: CONTENT_BOX,
};
export const LABELS: DiagramLabels = {"cell": {"text": "Tế bào gan", "region": "cell", "x": 28, "y": 350, "width": 160, "height": 34, "anchor": [58, 332]}, "enzyme": {"text": "ALT / AST", "region": "cell", "x": 352, "y": 348, "width": 176, "height": 34, "anchor": [434, 314]}, "blood": {"text": "Dòng máu", "region": "blood", "x": 350, "y": 516, "width": 182, "height": 34, "anchor": [490, 470]}, "bile": {"text": "Đường mật", "region": "bile", "x": 342, "y": 8, "width": 190, "height": 34, "anchor": [430, 55]}};
export const HepatocyteSinusoidUnit: React.FC<OrganProps> = (props) => <HepatocyteDiagram {...props} view="unit" labels={LABELS}/>;

// Delegated SVG layers: sinusoid, hepatocyte-membrane, bile-canaliculus
