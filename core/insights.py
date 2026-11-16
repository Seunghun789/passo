"""홈·대시보드·자동화에 보이는 글과 숫자. 숫자는 engine 이 기록에서 세고, 여기서는 화면에 보일 모양으로만 바꾼다.
웹 API 가 쓰고, 화면 종류(웹·모바일)와 상관없이 같은 글이 나온다."""
from datetime import date

import pandas as pd

from . import engine
from .ask import cond_text, plain

HOME_MAX = 2     # 홈 "오늘 먼저 볼 것"에 띄우는 걸린 자동화 카드 수
WHY_MAX = 2      # 카드에서 왜 · 안 보면을 보이는 걸린 대상 수
FOLLOW_MAX = 2   # 카드마다 이어서 볼 것 수
ROWS_MAX = 50    # 근거 표로 보내는 줄 수
TREND_MAX = 60   # 추이 그림으로 보내는 점 수(최근부터)


def fmt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    v = float(v)
    return f"{int(v):,}" if v == int(v) else f"{v:,.2f}".rstrip("0").rstrip(".")


def fmtv(v):
    if not engine.filled(v):
        return "없음"
    try:
        return fmt(v)
    except (TypeError, ValueError):  # '74℃ 이하'처럼 숫자와 글이 섞인 값은 적힌 그대로
        return str(v)


def fmt_day(d):
    return f"{int(str(d)[5:7])}월 {int(str(d)[8:10])}일" if d and len(str(d)) >= 10 else str(d)


def josa(word, pair):
    """받침에 맞춘 조사: josa('측정 온도', '이가') → '측정 온도가'."""
    w = str(word)
    last = w.rstrip(")")[-1:] if w else ""
    has = (ord(last) - 0xAC00) % 28 != 0 if "가" <= last <= "힣" else last in "013678LMNRlmnr"
    return w + (pair[0] if has else pair[1])


def until(K, T):
    """'N월 N일 기록까지': 그 기록 종류의 마지막 기록 날짜."""
    d = engine.last_date(K, T)
    return f"{fmt_day(d)} 기록까지" if d else "아직 기록 없음"


def alert_kind(spec):
    """걸린 자동화의 이름표와 띠: 기준 넘음 · 기준 아래 · 빠진 기록 · 예정일 · 걸린 것."""
    ops = [c["op"] for c in spec["conditions"]]
    if {"missed_weekday", "missed_monthday"} & set(ops):
        return "예정일", "due"
    if "older_than_days" in ops:
        return "빠진 기록", "gap"
    if any(o in (">", ">=") for o in ops):
        return "기준 넘음", "over"
    if any(o in ("<", "<=") for o in ops):
        return "기준 아래", "under"
    return "걸린 것", "hit"


def value_cond(spec):
    return next((c for c in spec["conditions"] if c["op"] in (">", ">=", "<", "<=") and c["prop"] != "날짜"), None)


def why_line(spec, row, today=None):
    """걸린 대상 한 줄의 '왜': 규칙의 칸과 그 값, 기준. 값은 기록에서 그대로 꺼낸다."""
    parts = []
    for c in spec["conditions"]:
        if c["op"] in ("missed_weekday", "missed_monthday"):
            due = engine.last_due(c["op"], int(c["value"]), today or date.today())
            parts.append(f"예정일 {due.month}월 {due.day}일 · 마지막 기록 {fmt_day(row['날짜'])}")
        elif c["op"] == "older_than_days":
            parts.append(f"마지막 기록 {fmt_day(row['날짜'])} · 기준 {c['value']}일")
        elif c.get("value_prop"):
            parts.append(f"{c['prop']} {fmtv(row.get(c['prop']))} · {c['value_prop']} {fmtv(row.get(c['value_prop']))}")
        else:
            parts.append(f"{c['prop']} {fmtv(row.get(c['prop']))} · 기준 {c['op']} {c.get('value')}")
    return " / ".join(parts)


def headline(K, spec, hits, period="이번 주", today=None):
    """카드 맨 위 한 문장. 이름과 수는 걸린 기록에서 코드가 꺼내고 센다."""
    today = today or date.today()
    ent = engine.entity(K, spec["type"])
    names = list(dict.fromkeys(hits[ent].dropna().astype(str))) if ent else []
    who = " · ".join(names[:2]) + (f" 외 {len(names) - 2}개" if len(names) > 2 else "") if names else f"기록 {len(hits)}줄"
    _, kind = alert_kind(spec)
    if kind == "due":
        return f"{who}의 예정일 기록이 없어요"
    if kind == "gap":
        last = max(str(d) for d in hits["날짜"])
        days = (today - date.fromisoformat(last[:10])).days if len(names) == 1 else None
        n = next(c["value"] for c in spec["conditions"] if c["op"] == "older_than_days")
        return f"{who} 기록이 {days}일째 없어요" if days else f"{who} 기록이 {n}일 넘게 없어요"
    c = value_cond(spec)
    if c and kind in ("over", "under"):
        verb, verb_past = ("기준을 넘었어요",) * 2 if kind == "over" else ("기준보다 낮아요", "기준보다 낮았어요")
        if len(names) == 1:  # 보는 기간 안에 그 대상이 몇 번 걸렸나
            a, b, _, _ = engine.period_range(period, today)
            df = engine.frame(K, spec["type"])
            df = df[(df[ent].astype(str) == names[0]) & (df["날짜"] >= a.isoformat()) & (df["날짜"] <= b.isoformat())]
            n = len(engine.match(df, spec["conditions"], today))
            if n > 1:
                return f"{who}의 {josa(c['prop'], '이가')} {period} {n}번 {verb_past}"
        return f"{who}의 {josa(c['prop'], '이가')} {verb}"
    return f"'{spec['title']}'에 {josa(who, '이가')} 걸렸어요"


def table(K, df, limit=ROWS_MAX):
    """근거 표: 보이는 칸과 줄. 줄마다 기록 id 와 원본 종이 id 를 붙여 원본을 열 수 있게 한다."""
    if df is None or not len(df):
        return {"columns": [], "rows": [], "total": 0}
    source = {r["id"]: r.get("source_input_id") for r in K["records"]}
    cols = [c for c in df.columns if not str(c).startswith("_")]
    rows = [{"id": int(r["_id"]), "source_id": source.get(int(r["_id"])), "values": {c: r[c] for c in cols}}
            for r in df.head(limit).to_dict("records")]
    return plain({"columns": cols, "rows": rows, "total": int(len(df))})


def series(df, limit=TREND_MAX):
    """추이 표(날짜 × 선) → [{날짜, 선 이름: 값}] 최근 limit 점."""
    if df is None or not len(df):
        return {"lines": [], "points": []}
    df = df.tail(limit)
    return plain({"lines": [str(c) for c in df.columns],
                  "points": [{"date": str(i), **{str(c): v for c, v in row.items()}} for i, row in df.iterrows()]})


def rule_text(spec):
    return f"{spec['type']}: {' 그리고 '.join(cond_text(c) for c in spec['conditions'])}"


def suggestions(K, taken=()):
    """확정한 관계·기록 간격·요일에서 규칙으로 바로 만드는 지표·자동화 후보(Claude 를 부르지 않는다).
    이미 켠(올린) 것과 같은 제목은 뺀다."""
    widgets, autos = engine.from_links(K)
    autos += engine.from_gaps(K) + engine.from_schedules(K)
    keep = lambda specs: [s for s in specs if s["title"] not in taken and engine.valid_spec(K, s)]
    return keep(widgets), keep(autos)


def automation_card(K, spec, period="이번 주", today=None, detail=True):
    """자동화 한 장: 지금 걸린 것, 한 문장, 걸린 대상마다 왜 · 안 보면, 근거 표."""
    hits = engine.run_automation(K, spec, today)
    chip, kind = alert_kind(spec)
    out = {"title": spec["title"], "type": spec["type"], "rule": rule_text(spec), "chip": chip, "kind": kind,
           "count": int(len(hits)), "until": until(K, spec["type"])}
    if not detail:
        return out
    ent = engine.entity(K, spec["type"])
    follow = [{"name": n, "why": w} for n, w in engine.follow(K, spec, hits)[:FOLLOW_MAX]]
    out.update(headline=headline(K, spec, hits, period, today) if len(hits) else None,
               targets=[{"name": str(r[ent]) if ent else fmt_day(r["날짜"]), "why": why_line(spec, r, today),
                         "record_id": int(r["_id"])} for _, r in hits.head(WHY_MAX).iterrows()],
               follow=follow, evidence=table(K, hits))
    return plain(out)


def suggestion_card(K, spec, today=None):
    """[켜기] 카드: 지금 걸린 것과 '지난 30일이었다면 N번 걸렸어요 (근거 N줄)'."""
    hits = engine.run_automation(K, spec, today)
    past = engine.backtest(K, spec)
    return plain({"title": spec["title"], "type": spec["type"], "rule": rule_text(spec), "reason": spec.get("reason"),
                  "count": int(len(hits)), "backtest": len(past), "schedule": spec.get("schedule"),
                  "chip": alert_kind(spec)[0], "evidence": table(K, hits)})


def widget_card(K, spec, period="이번 주"):
    """지표 한 장: 숫자 하나면 이 기간 값 · 앞 기간 값 · 근거 줄, 추이면 기간 안의 선."""
    a, b, _, _ = engine.period_range(period)
    if spec.get("kind") in ("kpi", "count_where"):
        v, pv, ev = engine.period_values(K, spec, period)
        return plain({"title": spec["title"], "kind": "number", "value": fmt(v), "previous": fmt(pv),
                      "previous_label": engine.PERIODS[period][0], "until": until(K, spec["type"]),
                      "reason": spec.get("reason"), "evidence": table(K, ev)})
    if spec.get("kind") == "trend" and engine.valid_spec(K, spec):
        df = engine.match(engine.frame(K, spec["type"]), spec.get("conditions"))
        seen = df[(df["날짜"] >= a.isoformat()) & (df["날짜"] <= b.isoformat())]
        return plain({"title": spec["title"], "kind": "trend", "until": until(K, spec["type"]), "reason": spec.get("reason"),
                      "series": series(engine.trend(K, spec["type"], seen, spec["props"], engine.PERIODS[period][1])),
                      "evidence": table(K, seen)})
    return None  # 대화로 만든 보기·달력은 다음 단계에서 웹에 옮긴다


def glance(K, widgets, period="이번 주"):
    """보는 기간 한눈에: 올린 지표(값이 하나인 것)부터, 모자라면 기록 종류마다 기록 수. 세 장까지."""
    specs = [w for w in widgets if w.get("kind") in ("kpi", "count_where")]
    specs += [{"title": f"{T} 기록 수", "kind": "kpi", "type": T, "fn": "count", "props": [], "conditions": []} for T in K["types"]]
    out = []
    for s in specs[:3]:
        v, pv, ev = engine.period_values(K, s, period)
        out.append({"title": s["title"], "value": fmt(v), "previous": fmt(pv), "previous_label": engine.PERIODS[period][0],
                    "evidence": int(len(ev))})
    return out
