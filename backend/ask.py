"""묻기 API. 확정 지식은 부른 사람의 JWT 로만 읽고(RLS), 답과 숫자는 core/ask·core/engine 이 만든다."""
import asyncio
import json
import os
import threading
import time
from datetime import date

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=500)
    model: str | None = Field(default=None, max_length=100)


KEPT, KEPT_MAX, KEPT_LOCK = {}, 16, threading.Lock()  # 워크스페이스 번호 → (바뀐 횟수, engine.load 가 읽어 둔 표)
MEMO_MAX = 12  # 워크스페이스마다 다시 쓸 화면 계산 결과 수(기간 네 개 × 화면 몇 개)


def kept_tables(http, g, tid):
    """워크스페이스의 확정 지식이 마지막으로 읽은 뒤 그대로면 읽어 둔 표를, 바뀌었으면 빈 자리를 준다.
    바뀐 횟수(021 tenant_versions)는 부른 사람의 권한으로 읽어서, 구성원이 아니거나 읽지 못하면 나누지 않는다."""
    r = http.get(g.url + '/rest/v1/tenant_versions', params={'tenant_id': f'eq.{tid}', 'select': 'v'})
    rows = r.json() if r.is_success else []
    if not rows:
        return None
    v = rows[0]['v']
    with KEPT_LOCK:
        hit = KEPT.pop(tid, None)
        kept = hit[1] if hit and hit[0] == v else {}
        KEPT[tid] = (v, kept)  # 가장 최근에 쓴 것이 뒤로 간다
        while len(KEPT) > KEPT_MAX:
            KEPT.pop(next(iter(KEPT)))
    return kept


def remembered(t, name, key, make):
    """확정 지식이 그대로이고 같은 날 · 같은 입력(key)이면 앞 요청이 센 결과를 다시 준다. make 는 그 결과를 새로 센다.
    지식이 바뀌면 kept_tables 가 빈 자리를 주므로 함께 비워진다. 이번 주 · 기한처럼 날에 따라 달라지는 숫자가 있어 오늘 날짜를 열쇠에 넣는다.
    결과는 여러 요청이 함께 쓰므로 고치지 않고 그대로 돌려줄 것만 넣는다(부른 사람에 따라 다른 값은 밖에서 붙인다)."""
    kept = getattr(t, 'cache', None)
    if kept is None:
        return make()
    k = json.dumps([name, date.today().isoformat(), key], ensure_ascii=False, sort_keys=True, default=str)
    with KEPT_LOCK:
        memo = kept.setdefault('_memo', {})
        if k in memo:
            memo[k] = memo.pop(k)  # 가장 최근에 쓴 것이 뒤로 간다
            return memo[k]
    out = make()
    with KEPT_LOCK:
        memo[k] = out
        while len(memo) > MEMO_MAX:
            memo.pop(next(iter(memo)))
    return out


def open_reader(g, token, tid):
    """engine 이 읽는 표를 부른 사람의 권한으로 읽는 창구. 1,000줄이 넘는 표는 이어서 읽는다.
    워크스페이스가 바뀌지 않았으면 앞 요청이 읽어 둔 표를 다시 쓴다(kept_tables)."""
    from backend.structure import Reader
    http = httpx.Client(timeout=30, trust_env=False, headers={'apikey': g.key, 'Authorization': 'Bearer ' + token})

    def fetch(table, params):
        params = dict(params)
        if 'limit' in params:
            r = http.get(g.url + '/rest/v1/' + table, params=params)
            if not r.is_success:
                raise RuntimeError(f'read_failed:{table}:{r.status_code}')
            return r.json()
        params.setdefault('order', 'id')
        out = []
        while True:
            r = http.get(g.url + '/rest/v1/' + table, params={**params, 'limit': 1000, 'offset': len(out)})
            if not r.is_success:
                raise RuntimeError(f'read_failed:{table}:{r.status_code}')
            batch = r.json()
            out += batch
            if len(batch) < 1000:
                return out
    return Reader(fetch, tid, kept_tables(http, g, tid)), http


def install_routes(app, session, gateway):
    def knowledge(g, token, tid):
        from core import engine
        t, http = open_reader(g, token, tid)
        try:
            return engine.load(t)
        finally:
            http.close()

    @app.get('/v1/workspaces/{tid}/ask')
    async def ask_options(tid: int, token=Depends(session), g=Depends(gateway)):
        await g.authorize(token, tid)
        from core import llm
        from core.ask import examples
        K = await asyncio.to_thread(knowledge, g, token, tid)
        return {'models': llm.MODELS, 'default_model': llm.DEFAULT, 'examples': examples(K), 'has_records': bool(K['types'])}

    @app.post('/v1/workspaces/{tid}/ask')
    async def ask_question(tid: int, body: Question, token=Depends(session), g=Depends(gateway)):
        await g.authorize(token, tid)
        import anthropic
        from core import engine, llm
        from core.ask import ask
        question, model = body.question.strip(), body.model or llm.DEFAULT
        if not question or model not in llm.MODELS:
            raise HTTPException(422, '질문과 모델을 확인해 주세요.')
        usage, started = {}, time.monotonic()

        def work():
            t, http = open_reader(g, token, tid)
            try:
                K = engine.load(t)
                if not K['types']:
                    return None
                with anthropic.Anthropic(**llm.connect(os.environ)) as client:
                    return ask(t, K, model, question, api_client=client, votes=False,  # 맞다고 고른 답은 새 웹에 아직 없다
                              
                               log_sink=lambda t, m, prompt, answer, used_in, used_out, started=None: usage.update(
                                   model=m, prompt=prompt, answer=answer, input_tokens=used_in, output_tokens=used_out))
            finally:
                http.close()
        try:
            result = await asyncio.to_thread(work)
        except (anthropic.APIError, RuntimeError, httpx.HTTPError) as exc:
            # 질문·답·키는 로그에 남기지 않는다. 어떤 종류의 실패인지만 남긴다.
            print(json.dumps({'ask': 'failed', 'error_type': type(exc).__name__, 'status': getattr(exc, 'status_code', None),
                              'read': str(exc) if str(exc).startswith('read_failed:') else None}), flush=True)
            raise HTTPException(503, 'AI가 답하지 못했어요. 잠시 뒤 다시 눌러 주세요.' if isinstance(exc, anthropic.APIError)
                                else '기록을 읽지 못했어요. 잠시 뒤 다시 눌러 주세요.') from None
        if result is None:
            raise HTTPException(409, '아직 확정한 기록이 없어요.')
        if usage:
            price = llm.PRICE[usage['model']]
            cost = (usage['input_tokens'] * price[0] + usage['output_tokens'] * price[1]) / 1_000_000
            try:  # 사용 기록을 남기지 못해도 이미 받은 답은 돌려준다
                await g.rpc(token, 'passo_log_ai', {'tid': tid, 'model': usage['model'], 'prompt': usage['prompt'],
                    'answer': usage['answer'], 'input_tokens': usage['input_tokens'], 'output_tokens': usage['output_tokens'],
                    'cost_usd': round(cost, 6), 'duration_ms': round((time.monotonic() - started) * 1000)})
            except (HTTPException, ValueError):
                print('{"ask":"usage_log_failed"}', flush=True)
        return result
