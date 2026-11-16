"""묻기: 질문 하나에 답과 근거를 만든다. 화면과 떨어져 있어 어느 화면에서 불러도 같은 답을 낸다.
숫자는 engine 의 조회 도구가 기록에서 세고, Claude 는 도구를 고르고 답 문장을 쓴다."""
import json
import math

from . import engine, llm

FN_KO = {"count": "줄 수", "sum": "합계", "avg": "평균", "min": "가장 작은 값", "max": "가장 큰 값", "latest": "가장 최근 값"}


def cond_text(c):
    """조건 하나를 쉬운 말로."""
    v = c.get("value_prop") or c.get("value")
    if c["op"] == "within_days":
        return f"{c['prop']}이(가) {v}일 안"
    if c["op"] == "is_today":
        return f"{c['prop']}이(가) 오늘"
    if c["op"] == "last_days":
        return f"{c['prop']}이(가) 지난 {v}일 안"
    if c["op"] == "older_than_days":
        return f"{'마지막 기록이' if c['prop'] == '날짜' else c['prop'] + '이(가)'} {v}일 넘게 지남"
    if c["op"] == "contains":
        return f"{c['prop']}에 '{v}' 포함"
    return f"{c['prop']} {c['op']} {v}"


def understood(calls):
    """AI가 부른 조회 도구의 입력을 쉬운 말로: '기록 종류 설비 점검 · 진동 > 7 · 진동 가장 큰 값 · 설비별'."""
    out = []
    for name, inp, *results in calls:
        if name == "saved":
            if inp.get("name"):
                out.append(f"켜 둔 자동화·올린 지표: {inp['name']}")
            continue
        if name == "schema" or not inp.get("type"):
            continue
        parts = [inp["type"]]
        parts += [cond_text(c) for c in inp.get("where") or []]
        if name == "aggregate":
            parts.append(f"{inp.get('prop') or ''} {FN_KO.get(inp.get('fn'), '')}".strip())
            result = results[0] if results and isinstance(results[0], dict) else {}
            if "미확정 칸" in result:
                parts.append(f"확인된 수량 {result['확인된 수량 칸']}칸 · 미확정 {result['미확정 칸']}칸")
            if inp.get("group_by"):
                parts.append(f"{inp['group_by']}별")
        if (line := " · ".join(parts)) not in out:
            out.append(line)
    return out


def examples(K):
    """질문 칸 아래 예시: 확정한 기록 종류·칸 이름으로만 만든다."""
    out = []
    for T in K["types"][:2]:
        out.append(f"이번 주 {T} 몇 건?")
        nums, ent = engine.prop_names(K, T, "number"), engine.entity(K, T)
        if nums and ent:
            out.append(f"{ent}별 {nums[0]} 가장 큰 값은?")
    return out[:3]


def verified(t, q):
    """[이 답이 맞아요]로 고른 적이 있는 같은 질문의 답."""
    v = t.get("eval_votes", select="pick,answer_before,answer_after", question=f"eq.{q}", order="id.desc", limit=1)
    return (v[0]["answer_after"] if v[0]["pick"] == "확정 후" else v[0]["answer_before"]) if v else None


def plain(rows):
    """화면으로 보낼 수 있는 값으로: 숫자 꼴(numpy)·날짜는 글이나 수로, 값이 없는 수(NaN)는 빈 값으로."""
    def fix(v):
        if isinstance(v, float) and math.isnan(v):
            return None
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        return v
    return fix(json.loads(json.dumps(rows, ensure_ascii=False, default=llm._plain)))


def ask(t, K, model, question, api_client=None, log_sink=None, votes=True):
    """질문 → 답, 어떻게 찾았는지, 근거 기록. t 는 읽기만 한다. votes: 전에 맞다고 고른 답(eval_votes)도 찾아 붙일지."""
    q = question.strip()
    calls = []

    def run(name, inp):
        out = engine.run_tool(KK, name, inp)
        calls.append((name, inp, out[0]))
        return out
    saved = {"automations": [a["spec"] for a in t.get("automations", select="spec", status="eq.켜짐")],
             "widgets": [w["spec"] for w in t.get("widgets", select="spec", status="eq.올림")]}
    KK = {**K, "_saved": saved}
    text, ids = llm.answer(t, model, q, run, api_client=api_client, log_sink=log_sink)
    rows = engine.records_by_id(K, set(ids))
    return {"question": q, "text": text, "how": understood(calls), "checked": verified(t, q) if votes else None,
            "left": sum(out.get("분류 안 된 줄", 0) for _, _, out in calls if isinstance(out, dict)),
            "evidence": plain([{k: v for k, v in r.items() if k != "_photo"} for r in rows])}
