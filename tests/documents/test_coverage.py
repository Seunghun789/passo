from core import ocr
from backend import extraction
from backend.extraction import make_payload, tails, merge_rows


def line(text, y, x0=100, x1=300, conf=0.9):
    return {'text': text, 'conf': conf, 'box': [x0, y, x1, y + 25]}


def sheet(values, step=60, start=70):
    """AI 가 줄 위치를 실제(28 간격, 44부터)보다 두 배쯤 늘려 적은 표."""
    rows = [{'cells': [{'label': '품명', 'source_raw': v, 'value': v, 'page': 1,
                        'box': [100, start + n * step, 300, start + (n + 1) * step]}]} for n, v in enumerate(values)]
    return {'title': '장부', 'occurred_at': '2026-11-18', 'columns': ['품명'], 'doc_fields': [], 'rows': rows}


def test_wide_line_in_other_column_is_not_a_pair():
    found = [{'text': '137.5', 'conf': 0.9, 'box': [408, 293, 514, 322]}]
    box = ocr.place_all([('7', [285, 290, 345, 325], '수량')], found)[0]
    assert box == [285, 290, 345, 325]  # 다른 열의 글줄과 짝짓지 않고 뒤집힌 상자도 만들지 않는다


def test_calibrate_fixes_stretched_rows():
    found = [line(f'값{n:03d}', 44 + n * 28) for n in range(6)]
    cells = [(f'값{n:03d}', [100, 70 + n * 60, 300, 130 + n * 60], '품명') for n in range(6)]
    a, b = ocr.calibrate(cells, found)
    assert abs(a - 28 / 60) < 0.01 and ocr.stretch([100, 70, 300, 130], (a, b))[1] < 60


def test_unread_counts_rows_below_last_read_row():
    found = [line('품명', 10)] + [line(f'값{n:03d}', 44 + n * 28) for n in range(10)]
    p = make_payload(sheet([f'값{n:03d}' for n in range(4)]), {'1': found})
    page = p['coverage']['pages']['1']
    assert p['coverage']['unread'] == 6 and page['bands'] == 10 and page['read_to'] == 44 + 3 * 28 + 25
    assert tails(p['coverage']) == {'1': [page['read_to'] - 3, 44 + 9 * 28 + 25 + 10]}


def test_all_read_has_no_unread():
    found = [line(f'값{n:03d}', 44 + n * 28) for n in range(4)]
    p = make_payload(sheet([f'값{n:03d}' for n in range(4)]), {'1': found})
    assert p['coverage']['unread'] == 0 and tails(p['coverage']) == {}


def test_merge_rows_maps_crop_to_page_and_keeps_order():
    s = sheet(['a', 'b'])
    more = {'rows': [{'cells': [{'label': '품명', 'value': 'c', 'page': 1, 'box': [100, 0, 300, 500]}]}], 'doc_fields': []}
    assert merge_rows(s, more, '1', 400, 600) == 1
    assert [r['cells'][0]['value'] for r in s['rows']] == ['a', 'b', 'c'] and s['rows'][2]['cells'][0]['box'] == [100, 400, 300, 500]


def test_fill_reads_tail_and_stops(monkeypatch):
    found = [line(f'값{n:03d}', 44 + n * 28) for n in range(8)]
    calls = []

    def fake_extract(t, model, name, photo, *a, hint='', **k):
        calls.append(hint)
        return {'rows': [{'cells': [{'label': '품명', 'value': f'값{n:03d}', 'source_raw': f'값{n:03d}', 'page': 1,
                                     'box': [100, 0, 300, 100]}]} for n in range(4, 8)], 'doc_fields': []}
    monkeypatch.setattr('core.llm.extract', fake_extract)
    monkeypatch.setattr(extraction, 'page_image', lambda *a: b'png')
    monkeypatch.setattr(extraction, 'crop_rows', lambda *a: b'part')
    monkeypatch.setattr(extraction, 'ai_client', lambda: __import__('contextlib').nullcontext())
    out = extraction.run_fill(b'', 'image/png', sheet([f'값{n:03d}' for n in range(4)]), {'1': found}, model='claude-sonnet-5-5')
    assert len(out['sheet']['rows']) == 8 and len(calls) == 1 and '아래쪽 부분' in calls[0]


def test_grid_places_rows_on_ocr_rows_not_ai_coordinates():
    found = [line(f'값{n:03d}', 44 + n * 28) for n in range(6)]
    rows = [[(f'값{n:03d}', [100, 70 + n * 60, 300, 130 + n * 60], '품명')] for n in range(6)]
    out = ocr.grid(rows, found)
    assert [b[0][1] for b in out] == [44 + n * 28 for n in range(6)]


def test_grid_keeps_order_for_rows_without_matching_text():
    found = [line(f'값{n:03d}', 44 + n * 28) for n in (0, 5)] + [line('흐림', 44 + n * 28, conf=0.3) for n in range(1, 5)]
    rows = [[('값000', None, '품명')]] + [[('??', None, '품명')] for _ in range(4)] + [[('값005', None, '품명')]]
    out = ocr.grid(rows, found)
    assert [b[0][1] for b in out] == [44 + n * 28 for n in range(6)]  # 글이 닮지 않은 줄도 차례대로 그 가로줄에


def test_grid_measures_columns_from_confident_values():
    found = [{'text': f'1{n}6,500', 'conf': 0.9, 'box': [408, 44 + n * 28, 504, 69 + n * 28]} for n in range(3)]
    rows = [[(f'1{n}6,500', [640, 70 + n * 60, 1000, 130 + n * 60], '금액')] for n in range(3)]
    assert all(b[0][0] == 408 and b[0][2] == 504 for b in ocr.grid(rows, found))  # AI가 오른쪽 칸으로 적은 열을 실제 자리로
