"""Copy existing line WAVs to scratch, benchmark local ASR, print a JSON report."""
import argparse
import json
import shutil
import time
from collections import Counter
from pathlib import Path

from healthvideo.audio.align import align_lines, alignment_identity, pronunciation_qa
from healthvideo.storage.files import read_yaml, sha256_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lines', type=Path, required=True)
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sources = sorted(args.lines.glob('*.wav'))
    if not sources:
        raise ValueError('No source line WAVs')
    hashes = {p.name: sha256_file(p) for p in sources}
    scripts = {line['id']: line['text'] for line in read_yaml(args.script)['lines']}
    copied = {}
    for source in sources:
        target = args.out/'audio/lines'/source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[source.stem] = target
    start = time.perf_counter()
    aligned = align_lines(copied, scripts, out_dir=args.out/'audio/alignment',
                          cache_dir=args.out/'asr-cache')
    elapsed = time.perf_counter()-start
    qa = pronunciation_qa(aligned)
    (args.out/'pronunciation-qa.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = Counter(flag['script_word'].casefold().strip('.,;:!?') for flag in qa['flags'])
    top = []
    for word, count in counts.most_common(10):
        flags = [f for f in qa['flags'] if f['script_word'].casefold().strip('.,;:!?') == word]
        top.append({'word': word, 'count': count, 'heard': list(dict.fromkeys(f['heard'] for f in flags)),
                    'examples': [{'line': f['line'], 'seconds': round(f['start'], 2)} for f in flags[:3]]})
    report = {'identity': alignment_identity(), 'source': str(args.lines),
              'copied_to': str(args.out), 'elapsed_seconds': round(elapsed, 3),
              'line_count': len(sources), 'aligned_count': len(aligned),
              'mean_match_ratio': sum(row['match_ratio'] for row in qa['lines'])/len(qa['lines']) if qa['lines'] else None,
              'weighted_match_ratio': sum(sum(w['matched'] for w in words) for words in aligned.values()) /
                                      max(1, sum(len(words) for words in aligned.values())),
              'flags': len(qa['flags']), 'top10': top,
              'source_unchanged': hashes == {p.name: sha256_file(p) for p in sources}}
    (args.out/'benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if len(aligned) != len(sources):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
