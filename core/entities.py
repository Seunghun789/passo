"""읽은 기록에서 대상(품목 · 설비 · 거래처 등)을 등록할 계획을 세운다. DB에는 쓰지 않고, 계획을 DB 함수
(passo_private.apply_entities)가 반영한다. 워커(새 종이)와 API(대상 화면의 [새로 추천받기])가 같은 함수를 쓴다.

- 대상을 가리키는 칸(AI가 주 대상으로 본 칸, 또는 대상 분류를 단 칸)이 아직 분류에 이어지지 않았으면 분류로 잇는다.
- 처음 보는 값 중 띄어쓰기 · 대소문자만 다른 것은 코드가 같은 대상으로 보고, 나머지는 등록된 대상이 있을 때만
  AI(llm.match_entities)에게 같은 대상인지 묻는다. 같다고 하지 않은 값은 새 대상으로 등록한다."""
import re

from . import engine, llm

MAX_VALUES = 300  # 한 칸에서 한 번에 등록하는 대상 수


def spell_key(v):
    return re.sub(r"\s+", "", str(v)).lower()


def plan(K, T, props, rows, match=None):
    """props: [{name, label, dtype, is_entity, ref_class}] (label 은 rows 의 열 이름). rows: [{열: 값}].
    match(C, values, known_text) → [{value, same_as, reason}] (AI). 없으면 띄어쓰기 · 대소문자만 맞춘다.
    (계획 {classes, entities, same}, 근거)."""
    out, seen = {"classes": [], "entities": [], "same": []}, set()
    defs = {p["name"]: p for p in K["props"].get(T, [])}
    for p in props:
        name, label = p["name"], p.get("label") or p["name"]
        old = defs.get(name, {})
        C = old.get("ref_class") if old.get("ref_class") in K["classes"] else None
        if not C:
            if (p.get("dtype") or old.get("dtype")) not in ("text", "choice"):
                continue
            if not (p.get("is_entity") or p.get("ref_class") or old.get("is_entity")):
                continue
            C = engine.class_name_for(K, (p.get("ref_class") or name).strip())[:100]
            reason = "AI가 이 칸을 기록의 주 대상으로 봤어요." if p.get("is_entity") or old.get("is_entity") else f"AI가 이 칸을 '{C}' 대상으로 봤어요."
            out["classes"].append({"type": T, "prop": name, "class": C, "reason": reason})
        values = list(dict.fromkeys(str(r[label]).strip() for r in rows if engine.filled(r.get(label))))[:MAX_VALUES]
        known = engine.members(K, C) if C in K["classes"] else []
        unseen = [v for v in values if not (C in K["classes"] and engine.find_entity(K, C, v)) and (C, v) not in seen]
        if not unseen:
            continue
        names = {e["id"]: e["name"] for e in known}
        spell = {}
        for alias, ids in [*K["ealias"].items(), *((n, [i]) for i, n in names.items())]:
            for i in ids:
                if i in names:
                    spell.setdefault(spell_key(alias), set()).add(names[i])
        same = {v: (next(iter(spell[spell_key(v)])), "띄어쓰기 · 대소문자만 달라요.") for v in unseen if len(spell.get(spell_key(v), ())) == 1}
        ask = [v for v in unseen if v not in same] if names and match else []
        if ask:
            text = "\n".join(f"- {e['name']}{' (별칭: ' + ', '.join(engine.aliases_of(K, e['id'])) + ')' if engine.aliases_of(K, e['id']) else ''}"
                             for e in known)
            for m in match(C, ask, text):
                if m.get("value") in ask and m.get("same_as") in names.values():
                    same[m["value"]] = (m["same_as"], m.get("reason") or "AI가 같은 대상으로 봤어요.")
        # 같은 종이 안에서 띄어쓰기만 다른 새 값은 처음 나온 것으로 묶는다
        first = {}
        for v in unseen:
            if v in same:
                continue
            k = spell_key(v)
            if k in first:
                same[v] = (first[k], "띄어쓰기 · 대소문자만 달라요.")
            else:
                first[k] = v
        out["entities"] += [{"class": C, "name": v} for v in first.values()]
        out["same"] += [{"class": C, "value": v, "same_as": s, "reason": why} for v, (s, why) in same.items()]
        seen |= {(C, v) for v in unseen}
    return out


def matcher(t, client=None, sink=None):
    """AI 로 같은 대상을 찾는 함수(작은 모델). client · sink 를 주면 그 연결 · 사용 기록 창구로 부른다."""
    ai = {k: v for k, v in (("api_client", client), ("log_sink", sink)) if v}
    return lambda C, values, known: llm.match_entities(t, C, values, known, **ai)


def confirmed_plan(K, match=None):
    """확정한 기록 전체로 세운 계획(대상 화면의 [새로 추천받기]). 기록 종류마다 대상 칸을 본다."""
    out = {"classes": [], "entities": [], "same": []}
    for T in K["types"]:
        props = [{**p, "label": p["name"]} for p in K["props"].get(T, [])]
        df = engine.frame(K, T)
        rows = [{c: (None if v is None or (isinstance(v, float) and v != v) else v) for c, v in r.items()}
                for r in df.drop(columns=["_photo"]).to_dict("records")]
        part = plan(K, T, props, rows, match)
        for k in out:
            out[k] += part[k]
    return out
