import json

from healthvideo.workflows.review_html import render_video_packet
from tests.helpers import create_v2_project_fixture


def test_video_packet_lists_pronunciation_flags(tmp_path):
    revision = create_v2_project_fixture(tmp_path) / 'revisions/001'
    path = revision/'reviews/pronunciation-qa.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'status': 'aligned', 'lines': [{'line': 'LN01', 'match_ratio': .8}],
                                   'flags': [{'line': 'LN01', 'script_word': 'URAT <script>', 'heard': 'u rát',
                                               'start': 2.1, 'end': 2.5, 'priority': 'term',
                                               'suggestion': 'Thêm vào pronunciation.vi.yaml'}]}, ensure_ascii=False), encoding='utf-8')
    html = render_video_packet(revision)
    assert 'Có thể đọc sai' in html
    assert 'URAT &lt;script&gt;' in html
    assert 'u rát' in html and '80.0%' in html
    assert 'LN01.wav#t=1.900,2.900' in html
    assert 'video.mp4#t=2.100' in html
