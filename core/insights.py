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


DAY_KO = "월화수목금토일"


def hm(at):
    """'오후 3시', '오전 10시 30분'."""
    h, m = at.hour, at.minute
    return f"{'오전' if h < 12 else '오후'} {h % 12 or 12}시" + (f" {m}분" if m else "")


def day_ko(d):
    return f"{d.month}/{d.day}({DAY_KO[d.weekday()]})"


def line_vega(df, height=None):
    """날짜별 추이 선(Vega-Lite). 대화로 만든 보기와 같은 꾸밈(VIEW_STYLE)."""
    d = df.copy()
    d.index = pd.to_datetime(d.index, errors="coerce")
    d.index.name = "날짜"
    long = d.reset_index().melt(id_vars="날짜", var_name="계열", value_name="값").dropna(subset=["값", "날짜"])
    long["날짜"] = long["날짜"].dt.strftime("%Y-%m-%d")
    return {"data": {"values": long.to_dict("records")}, "mark": {"type": "line", "point": len(long) < 30},
            "encoding": {"x": {"field": "날짜", "type": "temporal", "title": None, "axis": {"format": "%-m/%-d", "labelAngle": 0}},
                         "y": {"field": "값", "type": "quantitative", "title": None},
                         "color": {"field": "계열", "type": "nominal", "title": None}},
            "height": height or engine.VIEW_HEIGHT, "config": engine.VIEW_STYLE}


def bar_vega(out):
    """나눈 값마다 가로 막대와 값."""
    d = [{"묶음": str(a), "값": v} for a, v in zip(out.iloc[:, 0], out["값"])]
    return {"data": {"values": d}, "layer": [{"mark": {"type": "bar"}},
            {"mark": {"type": "text", "align": "left", "dx": 4}, "encoding": {"text": {"field": "값", "type": "quantitative", "format": ",.4~f"}}}],
            "encoding": {"y": {"field": "묶음", "type": "nominal", "sort": None, "title": None, "axis": {"labelOverlap": False}},
                         "x": {"field": "값", "type": "quantitative", "title": None, "axis": None, "scale": {"nice": False}}},
            "padding": {"right": 48}, "height": max(80, 28 * len(d)), "config": engine.VIEW_STYLE}


def calendar_view(K, spec, mode, offset, today=None):
    """일정 달력: 날마다 그날 일정(시각 · 이름 · 곁 글 · 색). 일정을 누르면 그 기록을 연다."""
    today = today or date.today()
    days, ev, tones, label = engine.calendar(K, spec, mode, offset, today)
    return {"kind": "calendar", "mode": mode, "offset": offset, "label": label, "heads": list("일월화수목금토"),
            "days": [{"iso": d["day"].isoformat(), "n": d["day"].day, "wd": (d["day"].weekday() + 1) % 7, "wdk": DAY_KO[d["day"].weekday()],
                      "today": d["day"] == today, "past": d["day"] < today, "out": d["out"],
                      "events": [{"id": int(r["_id"]), "time": hm(r["at"]).replace(" ", "") if r["timed"] else "", "name": r["name"],
                                  "side": r["side"], "color": tones.get(r["tone"], "#A1A1AA")} for r in d["events"]]} for d in days],
            "legend": [{"name": k, "color": c} for k, c in tones.items()]}, ev


def view(K, spec, period="이번 주", cal=None, today=None):
    """지표 한 장을 화면이 그릴 모양으로: 숫자 · 그림(Vega-Lite, 기록 줄을 넣은 것) · 표 · 상태별 · 목록 · 달력.
    숫자와 줄은 engine 이 기록에서 센다. cal=(mode, offset)은 달력을 넘길 때."""
    kind, base = spec.get("kind"), {"title": spec["title"], "until": until(K, spec["type"]), "reason": spec.get("reason")}
    if not engine.valid_spec(K, spec):
        return {**base, "kind": "empty", "message": "기록에 없는 칸이 들어 있어 그리지 못했어요.", "evidence": table(K, None)}
    if kind in ("kpi", "count_where"):
        v, pv, ev = engine.period_values(K, spec, period)
        return plain({**base, "kind": "number", "value": fmt(v), "previous": fmt(pv), "previous_label": engine.PERIODS[period][0],
                      "rule": " 그리고 ".join(cond_text(c) for c in spec.get("conditions") or []), "evidence": table(K, ev)})
    if kind == "trend":
        a, b, _, _ = engine.period_range(period, today)
        df = engine.match(engine.frame(K, spec["type"]), spec.get("conditions"))
        seen = df[(df["날짜"] >= a.isoformat()) & (df["날짜"] <= b.isoformat())]
        if not len(seen):
            return {**base, "kind": "empty", "message": f"{period}에는 그릴 기록이 없어요.", "evidence": table(K, seen)}
        return plain({**base, "kind": "vega", "vega": line_vega(engine.trend(K, spec["type"], seen, spec["props"], engine.PERIODS[period][1])),
                      "evidence": table(K, seen)})
    if kind == "view":
        rows = engine.view_rows(K, spec)
        v = engine.vega_of(spec, engine.view_cols(K, spec["type"]))
        data = plain(rows.drop(columns=["_id", "_photo"]).to_dict("records"))
        return plain({**base, "kind": "vega", "vega": {**v, "data": {"values": data}}, "evidence": table(K, rows)})
    shape = spec.get("shape")
    if shape == "달력":
        mode, off = cal or (("week", 0) if period in ("오늘", "이번 주") else ("month", engine.first_month(K, spec, today)))
        out, ev = calendar_view(K, spec, mode, off, today)
        return plain({**base, **out, "evidence": table(K, ev)})
    if shape == "목록":
        _, _, rows = engine.coming(K, spec, today)
        _, ev, tones = engine.schedule(K, spec, today)
        items = [{"id": int(r["_id"]), "at": day_ko(r["at"]) + (" " + hm(r["at"]) if r["timed"] else ""), "name": r["name"], "side": r["side"],
                  "color": tones.get(r["tone"], "#A1A1AA")} for r in rows[:engine.LIST_MAX]]
        return plain({**base, "kind": "list", "items": items, "more": max(0, len(rows) - engine.LIST_MAX), "prop": spec["prop"],
                      "evidence": table(K, ev[ev["_id"].isin({r["_id"] for r in rows})])})
    out, ev = engine.pick_values(K, spec, period, today)
    if not len(out):
        return {**base, "kind": "empty", "message": f"{period}에는 셀 기록이 없어요.", "evidence": table(K, ev)}
    if shape == "막대":
        return plain({**base, "kind": "vega", "vega": bar_vega(out), "evidence": table(K, ev)})
    if shape == "선":
        return plain({**base, "kind": "vega", "vega": line_vega(out.set_index(spec["by"])[["값"]].rename(columns={"값": spec["title"]})),
                      "evidence": table(K, ev)})
    if shape == "표":
        fn = engine.FNS[spec.get("fn") or "count"]
        shown = out.assign(값=out["값"].round(1)).rename(columns={"값": fn, "줄": "근거 줄"})
        return plain({**base, "kind": "table", "columns": [str(c) for c in shown.columns], "rows": shown.to_dict("records"),
                      "evidence": table(K, ev)})
    ent = engine.entity(K, spec["type"])  # 상태별: 값마다 건수와 최근 대상 두 개
    items = [{"label": str(r[0]), "value": fmt(r[1]),
              "names": list(ev[ev[spec["by"]].astype(str) == str(r[0])][ent].dropna().astype(str).head(2)) if ent else []}
             for r in out.head(4).itertuples(index=False)]
    return plain({**base, "kind": "status", "items": items, "evidence": table(K, ev)})


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
