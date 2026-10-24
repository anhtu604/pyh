import type {Box} from '../layout';
import type {Scene} from '../types';

export const activeSceneBeat = (scene: Scene, frame: number) =>
  [...(scene.beats ?? [])].reverse().find(beat => beat.start_frame !== undefined && beat.start_frame <= frame);

/** Smoothstep is deterministic at render time; each authored focus settles in 0.8 seconds. */
export const beatCamera = (scene: Scene, frame: number, regions: Record<string, Box>,
  view: Box, boxes: readonly Box[], viewport: Box) => {
  const pose = (focus?: string | null) => {
    if (!focus || !regions[focus]) return {zoom: 1, x: 0, y: 0};
    const region = regions[focus];
    const mapped = boxes.map(box => {
      const s = Math.min(box.width / view.width, box.height / view.height);
      return {left: box.left - viewport.left + (box.width - view.width*s)/2 + (region.left-view.left)*s,
        top: box.top - viewport.top + (box.height-view.height*s)/2 + (region.top-view.top)*s,
        width: region.width*s, height: region.height*s};
    });
    const left = Math.min(...mapped.map(b => b.left)), top = Math.min(...mapped.map(b => b.top));
    const width = Math.max(...mapped.map(b => b.left+b.width))-left;
    const height = Math.max(...mapped.map(b => b.top+b.height))-top;
    const zoom = Math.max(1, Math.min(1.65, viewport.width*.82/width, viewport.height*.82/height));
    return {zoom, x: (viewport.width/2-(left+width/2)*zoom)/viewport.width*100,
      y: (viewport.height/2-(top+height/2)*zoom)/viewport.height*100};
  };
  const beats = (scene.beats ?? []).filter(beat => beat.start_frame !== undefined && beat.start_frame <= frame);
  // Recompute interrupted transitions from their actual pose, preventing jumps at closely spaced beats.
  let from = pose(), target = from, start = 0;
  const mix = (at: number) => {
    const t = Math.max(0, Math.min(1, (at-start)/24));
    const e = t*t*(3-2*t);
    return {zoom: from.zoom+(target.zoom-from.zoom)*e, x: from.x+(target.x-from.x)*e,
      y: from.y+(target.y-from.y)*e};
  };
  beats.forEach(beat => {from = mix(beat.start_frame!); target = pose(beat.focus); start = beat.start_frame!;});
  return {...mix(frame), origin: '0% 0%', framing: activeSceneBeat(scene, frame)?.focus ?? 'wide'};
};
