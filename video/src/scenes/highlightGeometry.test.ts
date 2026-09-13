import {describe, expect, it} from 'vitest';
import {
  cropImageLayout,
  highlightImageLayout,
  highlightObjectFit,
  localHighlightRect,
} from './highlightGeometry';

describe('paper highlight coordinates', () => {
  it('preserves legacy page-image coordinates', () => {
    const legacy = {schema_version: '1.0', image: 'assets/old.svg', quote: 'q', x: 0.4, y: 0.4, width: 0.1, height: 0.1};
    expect(localHighlightRect(legacy)).toEqual({x: 0.4, y: 0.4, width: 0.1, height: 0.1});
    expect(highlightObjectFit(legacy)).toBe('cover');
    expect(highlightImageLayout(legacy)).toEqual({left: 0, top: 0, width: 1080, height: 1920});
  });
  it('positions page rectangle within its crop', () => {
    const rect = localHighlightRect({schema_version: '1.0', image: 'assets/crop.png', quote: 'q', x: 0.4, y: 0.4, width: 0.1, height: 0.1, source_id: 'R01', page: 2, crop_x: 0.35, crop_y: 0.35, crop_width: 0.2, crop_height: 0.2, crop_pixel_width: 200, crop_pixel_height: 200});
    expect(rect.x).toBeCloseTo(0.25);
    expect(rect.y).toBeCloseTo(0.25);
    expect(rect.width).toBeCloseTo(0.5);
    expect(rect.height).toBeCloseTo(0.5);
  });
  it('keeps a square crop square in the portrait frame', () => {
    expect(cropImageLayout(200, 200)).toEqual({left: 0, top: 420, width: 1080, height: 1080});
    const cropped = {schema_version: '1.0', image: 'assets/crop.png', quote: 'q', x: 0.4, y: 0.4, width: 0.1, height: 0.1, source_id: 'R01', page: 2, crop_x: 0.35, crop_y: 0.35, crop_width: 0.2, crop_height: 0.2, crop_pixel_width: 200, crop_pixel_height: 200};
    expect(highlightObjectFit(cropped)).toBe('contain');
    const layout = highlightImageLayout(cropped);
    const local = localHighlightRect(cropped);
    expect(layout.left + local.x * layout.width).toBeCloseTo(270);
    expect(layout.top + local.y * layout.height).toBeCloseTo(690);
  });
});
