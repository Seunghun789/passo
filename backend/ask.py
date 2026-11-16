"""묻기 API. 확정 지식은 부른 사람의 JWT 로만 읽고(RLS), 답과 숫자는 core/ask·core/engine 이 만든다."""
import asyncio
import json
import os
import time

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=500)
    model: str | None = Field(default=None, max_length=100)


def open_reader(g, token, tid):
    """engine 이 읽는 표를 부른 사람의 권한으로 읽는 창구. 1,000줄이 넘는 표는 이어서 읽는다."""
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
    return Reader(fetch, tid), http


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
        except (anthropic.APIError, RuntimeError) as exc:
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
