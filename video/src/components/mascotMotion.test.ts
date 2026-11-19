import {describe, expect, it} from 'vitest';
import {bobOffset, entranceOffset, entranceProgress, facesDiagram, normalizePoseTrack, poseAt, type MascotBeat} from './mascotMotion';
import {CLOSING_POSES, OPENING_POSES, STEPS, TOTAL_FRAMES} from '../medanim/liverEnzymeLeak';

const track: MascotBeat[] = [{frame: 0, pose: 'surprised'}, {frame: 132, pose: 'explain'}, {frame: 294, pose: 'thumbs_up'}];

describe('mascot pose track', () => {
  it('returns the right pose for each frame', () => {
    expect(poseAt(track, 0).pose).toBe('surprised');
    expect(poseAt(track, 131).pose).toBe('surprised');
    expect(poseAt(track, 132).pose).toBe('explain');
    expect(poseAt(track, 293).pose).toBe('explain');
    expect(poseAt(track, 359).pose).toBe('thumbs_up');
  });

  it('cross-fades over 6 frames then settles', () => {
    expect(poseAt(track, 132)).toEqual({pose: 'explain', from: 'surprised', mix: 0});
    expect(poseAt(track, 135).mix).toBeCloseTo(0.5);
    expect(poseAt(track, 138)).toEqual({pose: 'explain', from: null, mix: 1});
  });

  it('drops pose changes that would hold a pose under 2 s', () => {
    const quick: MascotBeat[] = [{frame: 0, pose: 'welcome'}, {frame: 40, pose: 'point_up'}, {frame: 60, pose: 'explain'}];
    expect(normalizePoseTrack(quick, 30).map((b) => b.pose)).toEqual(['welcome', 'explain']);
  });

  it('the medanim tracks already hold every pose at least 2 s', () => {
    const windows = [[OPENING_POSES, STEPS[0].end], [CLOSING_POSES, TOTAL_FRAMES - STEPS[5].start]] as const;
    windows.forEach(([poses, length]) => {
      const normalized = normalizePoseTrack(poses, 30);
      expect(normalized).toEqual(poses);
      normalized.forEach((beat, i) => {
        const end = normalized[i + 1]?.frame ?? length;
        expect(end - beat.frame).toBeGreaterThanOrEqual(60);
      });
    });
  });
});

describe('mascot motion', () => {
  it('slides in over 12 frames with a small bounce', () => {
    expect(entranceProgress(0)).toBeCloseTo(0);
    expect(entranceProgress(12)).toBeCloseTo(1);
    expect(Math.max(...Array.from({length: 13}, (_, f) => entranceProgress(f)))).toBeGreaterThan(1);
    expect(entranceOffset(0, 200)).toBeCloseTo(200);
    expect(entranceOffset(30, 200)).toBeCloseTo(0);
  });

  it('bobs 2 px with a 2 s period only while speaking', () => {
    expect(bobOffset(15, 30)).toBeCloseTo(2);
    expect(bobOffset(45, 30)).toBeCloseTo(-2);
    expect(bobOffset(60, 30)).toBeCloseTo(0);
    expect(bobOffset(15, 30, false)).toBe(0);
    for (let f = 0; f < 200; f++) expect(Math.abs(bobOffset(f, 30))).toBeLessThanOrEqual(2);
  });

  it('is deterministic per frame', () => {
    expect(poseAt(track, 100)).toEqual(poseAt(track, 100));
    expect(bobOffset(77, 30)).toBe(bobOffset(77, 30));
  });

  it('flips only when the diagram sits to the mascot left', () => {
    expect(facesDiagram(200, 900)).toBe(false);
    expect(facesDiagram(1500, 700)).toBe(true);
  });
});

