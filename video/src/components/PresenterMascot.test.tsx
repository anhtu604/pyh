import {expect, it} from 'vitest';
import {LAYOUTS} from '../layout';
import {presenterGeometry} from './PresenterMascot';

it('shows the top 65% and keeps the lower body below the fixed cut through entrance and bob', () => {
  for (const layout of Object.values(LAYOUTS)) {
    const box = layout.mechanism.mascot;
    for (const entrance of [0, 0.2, 0.8, 1, 1.03]) {
      for (let frame = 0; frame < 180; frame++) {
        const {fullHeight, offsetY} = presenterGeometry(box, entrance, frame, 30);
        expect(box.height / fullHeight).toBeCloseTo(0.65);
        expect(fullHeight + offsetY).toBeGreaterThan(box.height);
        if (entrance >= 1) expect((box.height - offsetY) / fullHeight).toBeCloseTo(0.65, 1);
      }
    }
  }
});
