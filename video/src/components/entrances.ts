import type {Scene} from '../types';

// Match Python's NFC/casefold/alphanumeric policy without discarding Vietnamese tones.
const normalize = (word: string) => word.normalize('NFC').toLocaleLowerCase('vi').replace(/ß/g, 'ss').replace(/ς/g, 'σ').replace(/[^\p{L}\p{N}]/gu, '');

/** Scene-local frames; fallback entrances occupy the first 70% of narration. */
export const textEntrances = (scene: Scene): {text: string; start_frame: number}[] => {
  if (scene.entrances?.length) return scene.entrances;
  const pieces = scene.on_screen_text?.match(/[^;\n•]+[;\n•]?/gu) ?? [];
  return pieces.map((text, index) => {
    const token = normalize(text.trim().split(/\s+/)[0] ?? '');
    const word = scene.words?.find(candidate => normalize(candidate.text) === token);
    const fallback = pieces.length === 1 ? (scene.duration_frames > 120 ? .35 : 0)
      : .7 * index / Math.max(1, pieces.length - 1);
    return {text, start_frame: word?.start_frame ?? Math.round(scene.duration_frames * fallback)};
  });
};
