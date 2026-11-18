"""Pure extraction + provenance adapter; never imports legacy DB or writes records."""
import io
import os
import time
from datetime import date


def page_image(content, mime, page):
    from PIL import Image, ImageOps
    if mime == 'application/pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(content) as pdf:
            if not 1 <= page <= len(pdf):
                raise ValueError('page')
            p = pdf[page-1]
            scale = min(2, 2000/max(p.get_size()))
            bitmap = p.render(scale=scale)
            im = bitmap.to_pil().copy()
            bitmap.close(); p.close()
    else:
        if page != 1:
            raise ValueError('page')
        with Image.open(io.BytesIO(content)) as source:
            im = ImageOps.exif_transpose(source).convert('RGB')
            im.thumbnail((2000,2000))
    out = io.BytesIO(); im.save(out,format='PNG'); im.close()
    return out.getvalue()


def run_ocr(content, mime):
    from core import ocr
    pages = 1
    if mime == 'application/pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(content) as pdf:
            pages = len(pdf)
    return {str(n):ocr.lines(page_image(content,mime,n)) for n in range(1,pages+1)}


def selected_model(model=None):
    from core.llm import DEFAULT, MODELS
    selected = model or os.environ.get('PASSO_MODEL', DEFAULT)
    if selected not in MODELS:
        raise ValueError('unsupported_model')
    return selected


def ai_client():
    import anthropic
    import httpx2
    from core.llm import connect
    # Explicit transport: use authorized provider key, no implicit retries or proxy.
    return anthropic.Anthropic(**{'base_url':'https://api.anthropic.com',**connect(os.environ),'max_retries':0,'timeout':180},
        http_client=httpx2.Client(trust_env=False,timeout=180))


def run_structure(fetch, tid, sheet, records, model=None):
    from backend.structure import Reader, plan_structure
    with ai_client() as client:
        return plan_structure(Reader(fetch,tid),selected_model(model),sheet['title'],records,client)


def run_entities(fetch, tid, structure, records):
    from backend.structure import Reader, plan_entities
    with ai_client() as client:
        return plan_entities(Reader(fetch,tid),structure,records,client)


def run_model(content, mime, model=None):
    from core.llm import extract
    selected = selected_model(model)
    usage = {}
    def sink(t, model, prompt, answer, usage_in, usage_out, started):
        usage.update(model=model,input_tokens=usage_in,output_tokens=usage_out,seconds=round(time.monotonic()-started,3))
    with ai_client() as client:
        sheet = extract(None,selected,'original.pdf' if mime=='application/pdf' else 'original.png',
                        content,api_client=client,log_sink=sink)
    return {'sheet':sheet,'usage':usage}


def run_tables(content, mime):
    """쪽마다 인쇄된 표 선을 찾는다(core/grid.py, OpenCV, 한 장 0.3~0.4초). 표 선이 없거나 찾지 못한 쪽은 뺀다."""
    from core import grid
    pages = 1
    if mime == 'application/pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(content) as pdf:
            pages = len(pdf)
    out = {}
    for n in range(1, pages+1):
        try:
            if g := grid.lines(page_image(content,mime,n)):
                out[str(n)] = g
        except Exception as exc:  # 표 선을 못 찾으면 OCR 격자로 자리를 잡는다
            print(f"표 선 찾기 실패: {type(exc).__name__}", flush=True)
    return out


def make_payload(sheet, found, uploaded=None, tables=None):
    """uploaded: 올린 날(YYYY-MM-DD). 종이에서 날짜를 읽지 못하면 이 날을 기록 날짜로 넣고 date_assumed 로 알려
    "기록 날짜" 카드로 묻게 한다. 올린 날도 모르면 날짜를 지어내지 않고 실패한다.
    tables: run_tables 결과(쪽 → 표 선 격자). 표 칸의 상자는 표 선 격자 칸을 먼저 쓰고, 못 찾은 칸만 OCR 격자 · 짝짓기 상자를 쓴다."""
    from core import engine, ocr
    from core.record_cells import extracted_data, encode_record
    raw_date = sheet.get('occurred_at')
    assumed = None
    try:
        occurred = date.fromisoformat(raw_date).isoformat()
    except (TypeError, ValueError):
        if uploaded is None:
            raise
        occurred = date.fromisoformat(uploaded).isoformat()
        assumed = {'value': occurred, 'written': raw_date if isinstance(raw_date, str) else ''}
    if not sheet.get('title') or not 1 <= len(sheet.get('rows',[])) <= 1000:
        raise ValueError('empty or oversized extraction')
    def box(c):
        b = c.get('box')
        return b if isinstance(b,list) and len(b)==4 and all(isinstance(v,(int,float)) and 0<=v<=1000 for v in b) and b[0]<b[2] and b[1]<b[3] else None
    every_cell = [*sheet.get('doc_fields',[]), *(c for r in sheet['rows'] for c in r['cells'])]
    # 쪽마다 AI 의 세로 좌표가 실제보다 늘거나 밀린 정도를 한 번 재어 모든 대략의 상자를 바로잡는다
    fits = {p: ocr.calibrate([(str(c.get('source_raw') or ''),box(c),c['label']) for c in every_cell if str(c.get('page',1))==p], lines)
            for p,lines in found.items()}
    # 표의 칸 상자는 OCR 격자(가로줄 · 열)로 잡는다. 격자를 못 잡은 쪽만 AI 좌표를 보정해 쓴다
    gridded = {}
    for p, lines in found.items():
        rows_p = [cs for cs in ([c for c in r['cells'] if str(c.get('page',1))==p] for r in sheet['rows']) if cs]
        boxes = ocr.grid([[(str(c.get('source_raw') or ''),box(c),c['label']) for c in cs] for cs in rows_p], lines)
        for cs, bs in zip(rows_p, boxes or []):
            gridded.update({id(c): b for c, b in zip(cs, bs) if b})
    # 표 선 격자(core/grid.py): 기록 줄 순서와 열 이름으로 표의 칸을 찾는다. 찾은 칸은 그 칸 상자를 쓴다
    ruled = {}
    for p, g in (tables or {}).items():
        rows_p = [cs for cs in ([c for c in r['cells'] if str(c.get('page',1))==p] for r in sheet['rows']) if cs]
        sub = {'columns': sheet.get('columns', []),
               'rows': [{'cells': [{'value': c.get('value'), 'label': c['label'], 'box': None} for c in cs]} for cs in rows_p]}
        try:
            engine.place_grid(sub, found.get(p, []), g)
        except Exception as exc:
            print(f"표 선 격자 맞추기 실패: {type(exc).__name__}", flush=True)
            continue
        for cs, r in zip(rows_p, sub['rows']):
            ruled.update({id(c): x['box'] for c, x in zip(cs, r['cells']) if x['box']})
    records, spans, used = [], {}, {}
    for index, row in enumerate(sheet['rows']):
        cells = [*sheet.get('doc_fields',[]), *row['cells']]
        normalized = [{**c,'value':c.get('normal') or c.get('source_raw',c.get('value')),
                       'written':c.get('source_raw',c.get('value'))} for c in cells]
        data = encode_record({'data':extracted_data(normalized,sheet.get('columns',[]))})['data']
        records.append({'type_name':sheet['title'],'occurred_at':occurred,'data':data,
                        'uncertain':[c['label'] for c in cells if c.get('uncertain') or c.get('unreadable')]})
        for page in {c.get('page',1) for c in cells}:
            group = [c for c in cells if c.get('page',1)==page]
            # A column header is not evidence for a short cell (e.g. row number 1).
            # Legacy OCR matching gives label text a bonus; exclude exact header-only lines here.
            labels = {ocr._norm(c['label']) for c in cells}
            every = found.get(str(page),[])
            keep = [n for n,line in enumerate(every) if ocr._norm(line['text']) not in labels]  # '상 호'도 칸 이름 '상호'다
            took = set()
            fit = fits.get(str(page))
            placed = ocr.place_all([(str(c.get('source_raw') or ''),gridded.get(id(c)) or ocr.stretch(box(c),fit),c['label']) for c in group],[every[n] for n in keep],took)
            used.setdefault(str(page),set()).update(keep[n] for n in took)
            for n,c in enumerate(group):
                spans.setdefault(c['label'],[]).append({'rec':index,'page':page,'quote':c.get('source_raw'),
                    'box':ruled.get(id(c)) or (placed[n] if n < len(placed) else box(c)),'model_box':box(c),'location':'estimated',
                    'unsure':c.get('uncertain',False),'unreadable':c.get('unreadable',False)})
    names = [*sheet.get('columns',[]), *(c['label'] for c in sheet.get('doc_fields',[])), sheet['title']]
    pages = {p: ocr.unread(lines, used.get(p,set()), names) for p,lines in found.items()}
    result = {'records':records,'spans':spans,
              'coverage':{'unread':sum(len(v['unread']) for v in pages.values()),'pages':pages}}
    if assumed:
        result['date_assumed'] = assumed
    return result


def tails(coverage, least=3):
    """쪽마다 마지막으로 읽은 가로줄 아래에 읽지 않은 가로줄이 least 곳 넘게 남으면 그 세로 범위 [위, 아래](0~1000)."""
    out = {}
    for page, v in coverage['pages'].items():
        below = [b for b in v['unread'] if v['read_to'] is not None and b[1] >= v['read_to'] - 5]
        if len(below) >= least:
            # 이미 읽은 마지막 줄은 다시 자르지 않는다(같은 줄을 두 번 읽지 않게). 그 아래 줄은 위 끝까지 넣는다
            out[page] = [max(0, min(b[1] for b in below) - 10, v['read_to'] - 3), min(1000, max(b[3] for b in below) + 10)]
    return out


def crop_rows(png, top, bottom):
    """쪽 그림에서 세로 범위 [top, bottom](0~1000)를 가로 전체로 잘라 PNG 로."""
    from PIL import Image
    with Image.open(io.BytesIO(png)) as im:
        W, H = im.size
        part = im.crop((0, round(top*H/1000), W, round(bottom*H/1000)))
        out = io.BytesIO(); part.save(out, format='PNG')
    return out.getvalue()


def merge_rows(sheet, more, page, top, bottom):
    """잘라 읽은 표(more)의 줄을 쪽 좌표로 옮겨 그 쪽의 마지막 줄 뒤에 넣는다. 처음 보는 doc_fields 칸도 더한다. 넣은 줄 수."""
    def move(box):
        if not (isinstance(box, list) and len(box) == 4):
            return None
        return [box[0], round(top + box[1]*(bottom-top)/1000), box[2], round(top + box[3]*(bottom-top)/1000)]
    rows = [{'cells':[{**c,'page':int(page),'box':move(c.get('box'))} for c in r['cells']]} for r in more.get('rows',[]) if r.get('cells')]
    last = max((n for n, r in enumerate(sheet['rows']) if any(c.get('page',1) == int(page) for c in r['cells'])), default=len(sheet['rows'])-1)
    sheet['rows'][last+1:last+1] = rows
    known = {c['label'] for c in sheet.get('doc_fields',[])}
    sheet.setdefault('doc_fields',[]).extend({**c,'page':int(page),'box':move(c.get('box'))} for c in more.get('doc_fields',[]) if c['label'] not in known)
    return len(rows)


def run_fill(content, mime, sheet, found, uploaded=None, model=None, rounds=3):
    """하네스: 원본 아래쪽에 읽지 않은 가로줄이 남으면 그 부분만 잘라 AI 에게 이어서 읽힌다(최대 rounds 번).
    더 읽히지 않거나 남은 곳이 줄지 않으면 멈춘다. {'sheet': 이어 붙인 표, 'usage': [AI 사용량]}"""
    import copy
    from core.llm import extract
    sheet, usage, last = copy.deepcopy(sheet), [], None
    selected = selected_model(model)
    for _ in range(rounds):
        gaps = tails(make_payload(sheet, found, uploaded)['coverage'])
        if not gaps or gaps == last:
            break
        last, added = gaps, 0
        hint = ("\n- 이 사진은 앞서 읽은 표의 아래쪽 부분만 잘라 낸 것이에요. 머리글이 보이지 않아도 같은 표예요. "
                f"columns 의 label 은 {', '.join(sheet.get('columns',[]))} 를 같은 순서로 쓰고, 이 부분에 적힌 줄을 처음부터 끝까지 빠짐없이 모두 읽어 주세요.")
        with ai_client() as client:
            for page, (top, bottom) in gaps.items():
                one = {}
                def sink(t, model, prompt, answer, usage_in, usage_out, started):
                    one.update(model=model,input_tokens=usage_in,output_tokens=usage_out,seconds=round(time.monotonic()-started,3))
                more = extract(None, selected, 'part.png', crop_rows(page_image(content, mime, int(page)), top, bottom),
                               api_client=client, log_sink=sink, hint=hint)
                usage.append(one)
                added += merge_rows(sheet, more, page, top, bottom)
        if not added:
            break
    return {'sheet': sheet, 'usage': usage}
