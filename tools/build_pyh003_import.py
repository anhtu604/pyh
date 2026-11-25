"""One-off offline adapter for the supplied PYH-003 prototype bundle (read-only input)."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.script import Script
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.external_revision import validate_import


def build(source: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError(f'{destination}: thư mục đích đã tồn tại, không ghi đè')
    destination = destination.resolve()
    if destination.is_relative_to(source.resolve()):
        raise ValueError('Đích phải nằm ngoài thư mục dữ liệu nguồn')
    lines = json.loads((source / 'script-full-lines.json').read_text(encoding='utf-8'))
    script_md = (source / 'script-full.md').read_text(encoding='utf-8')
    topic = re.search(r'^Chủ đề:\s*(.+)$', script_md, re.MULTILINE)
    if topic is None:
        raise ValueError('script-full.md: thiếu Chủ đề')
    title = topic[1]
    sources_md = (source / 'sources-full.md').read_text(encoding='utf-8')
    # These original data files are read for provenance, never used to invent links.
    research = json.loads((source / 'research-ledger.json').read_text(encoding='utf-8'))
    old = read_yaml(source / 'evidence-rev001/ledger.yaml')
    known = {str(r.get('pmid')): r for r in old['records'] if r.get('pmid')}
    for record in research['data']['resultList']['result']:
        pmid = str(record.get('pmid') or record.get('id'))
        known.setdefault(pmid, {'pmid': pmid, 'title': record['title'], 'doi': record.get('doi'),
                                'pmcid': record.get('pmcid'), 'authors': record.get('authorString', '').split(', ')})
    records, claim_rows, line_claims = {}, {}, {}
    for row in sources_md.splitlines():
        if not row.startswith('|'):
            continue
        cells = [c.strip() for c in row.strip('|').split('|')]
        if len(cells) >= 5 and re.fullmatch(r'\[[A-ZĐ0-9]+\]', cells[0]):
            marker = cells[0][1:-1]
            pmid = re.search(r'PMID\s+(\d+)', cells[3])
            doi = re.search(r'https://doi\.org/([^\s)]+)', cells[3])
            data = dict(known.get(pmid[1], {})) if pmid else {}
            year = re.search(r';\s*(\d{4})\s*;', cells[1])
            data.update({'id': marker, 'title': cells[2],
                         'authors': [a.strip() for a in cells[1].split(';')[0].split(',')],
                         'year': int(year[1]) if year else None,
                         'key_findings': cells[4], 'retraction_status': 'unverified'})
            if pmid:
                data['pmid'] = pmid[1]
                data['url'] = f'https://europepmc.org/article/MED/{pmid[1]}'
            if doi:
                data['doi'] = doi[1]
            records[marker] = SourceRecord.model_validate(data).model_dump(mode='json')
        elif len(cells) == 4 and re.fullmatch(r'[FN]\d{2}', cells[0]):
            claim_rows[cells[0]] = {'text': cells[1], 'locator': cells[2], 'limits': cells[3],
                                    'sources': re.findall(r'\[([A-ZĐ0-9]+)\]', cells[2])}
        elif len(cells) == 3 and re.fullmatch(r'C\d-L\d{2}', cells[0]):
            line_claims[cells[0]] = re.findall(r'[FN]\d{2}', cells[2])
    if not records or not claim_rows:
        raise ValueError('sources-full.md: thiếu bảng nguồn hoặc bảng claim có cấu trúc')
    # The voiced v4 text lives in the aligned words; script-full-lines.json predates the
    # revision cuts (e.g. 25 removed "Nói gọn"), so the gate must review what is spoken.
    spoken = {line['id']: ' '.join(w['word'] for w in line['words'])
              for line in json.loads((source / 'timeline-full-v5.json').read_text(encoding='utf-8'))['lines']}
    missing, claims, script_lines = [], [], []
    for item in lines:
        line_id = item['id']
        if line_id not in spoken:
            raise ValueError(f'timeline-full-v5.json: thiếu dòng {line_id}')
        text = spoken[line_id].replace('**', '')
        groups = line_claims.get(line_id, [])
        ids = set()
        details = []
        for group in groups:
            claim = claim_rows.get(group)
            if claim is None:
                missing.append({'line': line_id, 'claim': group, 'reason': 'Không có hàng claim'})
                continue
            unknown = set(claim['sources']) - records.keys()
            if unknown or not claim['sources']:
                missing.append({'line': line_id, 'claim': group, 'reason': f'Thiếu nguồn: {sorted(unknown)}'})
                continue
            ids.update(claim['sources'])
            details.append(f"{group}: {claim['text']} Locator: {claim['locator']} Giới hạn: {claim['limits']}")
        # A composite line claim retains ALL explicitly mapped claims and their limits.
        is_outro = line_id == 'C5-L03' and not item.get('sources')
        if not groups and not is_outro:
            missing.append({'line': line_id, 'reason': 'Không có ánh xạ claim → dòng trong sources-full.md'})
        claim_id = f'LINE-{line_id}' if ids else None
        if claim_id:
            claims.append(EvidenceClaim(id=claim_id, text_public=text, text_technical='\n'.join(details),
                                         type='evidence', sources=sorted(ids), certainty='unrated',
                                         doctor_notes='Ánh xạ nguyên từ sources-full.md; chưa được critic/bác sĩ duyệt.'
                                         ).model_dump(mode='json'))
        script_lines.append({'id': line_id, 'text': text, 'delivery': text, 'claim_id': claim_id,
                             'purpose': 'outro' if is_outro else 'content'})
    # Dedicated clip hook/outro lines (approved at the medical gate, never in the 16:9 video).
    clip_file = source / 'clip-lines.json'
    if clip_file.is_file():
        for item in json.loads(clip_file.read_text(encoding='utf-8'))['lines']:
            script_lines.append({'id': item['id'], 'text': item['text'], 'delivery': item['text'],
                                 'claim_id': None, 'purpose': item['purpose'], 'clip_id': item['clip_id']})
    report = {'lines': len(script_lines), 'claims': len(claims), 'source_claims': len(claim_rows),
              'sources': len(records), 'missing_support': missing,
              'critic_required': ['Trạm 07: critic lời nhập trước PIN y khoa',
                                  'Trạm 12: critic video/clip/posts sau QA, trước submit_video/PIN'],
              'posts_status': 'Bản nháp cho bác sĩ xem ở cổng video'}
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.pyh003-import-', dir=destination.parent))
    try:
        write_yaml_atomic(staging / 'script/script.yaml', Script(title=title, lines=script_lines).model_dump(mode='json'))
        write_yaml_atomic(staging / 'evidence/ledger.yaml', {'schema_version': '1.0',
                                                          'claims': claims, 'records': list(records.values())})
        shutil.copy2(source / 'sources-full.md', staging / 'evidence/sources-full.md')
        shutil.copy2(source / 'research-ledger.json', staging / 'evidence/research-ledger.json')
        (staging / 'renders/clips').mkdir(parents=True)
        for src, dst in [('pyh003-full.mp4', 'renders/video.mp4'),
                         ('short-bo-gan.mp4', 'renders/clips/CL01.mp4'),
                         ('short-di-kham.mp4', 'renders/clips/CL02.mp4')]:
            shutil.copy2(source / src, staging / dst)
        draft = 'Bản nháp để bác sĩ xem ở cổng video. '
        # Retain exact source titles; claim references satisfy the existing numeric-copy check.
        references = []
        for marker, record in records.items():
            claim_id = next((c['id'] for c in claims if marker in c['sources']), None)
            if claim_id is None:
                references.append(record['title'])
            else:
                references.append(f"[claim:{claim_id}] {record['title']}")
        brief_title = title[:90].rsplit(' ', 1)[0]
        posts = {'youtube_titles': [brief_title, 'Tìm hiểu: ' + brief_title],
                 'youtube_description': draft + '\nNguồn:\n' + '\n'.join(references),
                 'youtube_tags': [], 'facebook_post': draft + title, 'youtube_community': draft + title,
                 'clip_captions': {cid: dict.fromkeys(('tiktok', 'shorts', 'reels'), draft + title)
                                   for cid in ('CL01', 'CL02')}}
        write_yaml_atomic(staging / 'posts/posts.yaml', posts)
        shutil.copy2(source / 'thumb-a.png', staging / 'posts/thumbnail.png')
        if missing:
            report['schema_valid'] = False
        else:
            validate_import(staging)
            report['schema_valid'] = True
        (staging / 'import-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if missing:
            # Retain a reviewable report outside Git, but make the bundle fail closed on import.
            write_yaml_atomic(staging / 'evidence/unresolved-claims.yaml', {'missing_support': missing})
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, nargs='?', default=Path('cache/pyh003-import'))
    parser.add_argument('--source', type=Path, default=Path('E:/pyh-003/cache/pyh003'))
    args = parser.parse_args()
    report = build(args.source, args.destination)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['schema_valid']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
