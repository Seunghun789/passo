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


class Ruled:
    """표 선 격자 대역: 줄 높이 28, 열 너비 100인 표."""
    def straddles(self, box):
        return False

    def where(self, box):
        return (box[1] - 44) // 28, box[0] // 100, ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)

    def cell_at(self, y, C):
        r = round((y - 44 - 12.5) / 28)
        return [C * 100, 44 + r * 28, C * 100 + 100, 72 + r * 28]


def test_ruled_grid_cell_wins_over_ocr_placement():
    found = [{'text': f'값{n:03d}', 'conf': 0.9, 'box': [110, 44 + n * 28, 190, 69 + n * 28]} for n in range(4)]
    s = sheet([f'값{n:03d}' for n in range(4)])
    p = make_payload(s, {'1': found}, tables={'1': Ruled()})
    assert [x['box'] for x in p['spans']['품명']] == [[100, 44 + n * 28, 200, 72 + n * 28] for n in range(4)]


def test_without_tables_ocr_placement_is_used():
    found = [{'text': f'값{n:03d}', 'conf': 0.9, 'box': [110, 44 + n * 28, 190, 69 + n * 28]} for n in range(4)]
    p = make_payload(sheet([f'값{n:03d}' for n in range(4)]), {'1': found})
    assert [x['box'][1] for x in p['spans']['품명']] == [44 + n * 28 for n in range(4)]


def test_box_outside_its_column_is_pulled_back():
    from backend.extraction import keep_in_columns
    spans = {'수량': [{'box': [270, 44 + n * 28, 330, 72 + n * 28]} for n in range(5)] + [{'box': [517, 958, 637, 985]}]}
    keep_in_columns(spans, ['수량'])
    assert spans['수량'][-1]['box'] == [270, 958, 330, 985] and spans['수량'][0]['box'] == [270, 44, 330, 72]


def test_reading_notes_build_hint_from_this_workspace_only():
    from backend.extraction import reading_notes
    seen = []
    def fetch(table, params):
        seen.append((table, params['tenant_id']))
        if table == 'reading_notes':
            return [{'kind': '고친 글씨', 'label': '품명', 'written': '컨(F)710', 'value': '컨(고)40'},
                    {'kind': '뜻 풀이', 'label': '품명', 'written': '현수', 'value': '현수막'}]
        return [{'name': '파트라인'}, {'name': '일안'}]
    n = reading_notes(fetch, 7)
    assert n['answers'] == 2 and n['names'] == 2 and all(t == 'eq.7' for _, t in seen)
    assert '컨(F)710 → 컨(고)40' in n['hint'] and '현수 = 현수막' in n['hint'] and '파트라인' in n['hint']


def test_reading_notes_missing_table_reads_without_notes():
    from backend.extraction import reading_notes
    def fetch(table, params):
        raise RuntimeError('worker_gateway_404')
    assert reading_notes(fetch, 7) == {'hint': '', 'answers': 0, 'names': 0, 'names_list': []}


def test_close_name_becomes_candidate():
    from backend.extraction import known_name
    assert known_name('파트라인1', ['파트라인', '한샘']) == '파트라인'
    assert known_name('파트라인', ['파트라인']) is None and known_name('130', ['130']) is None and known_name('나이스', ['파트라인']) is None
    s = sheet(['파트라인1'])
    p = make_payload(s, {'1': []}, names=['파트라인'])
    assert p['spans']['품명'][0]['known'] == '파트라인' and p['spans']['품명'][0]['cand'][0] == '파트라인'
