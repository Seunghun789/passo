"""사람이 대상 화면 · 지식그래프에서 직접 고친 것("직접 고친 것" 카드). 화면이 보낸 값을 확정 지식으로 검사하고
카드에 넣을 모양으로 맞춘다. 반영은 DB 함수(passo_user_card_answer)가 [적용]을 누를 때 한다.
칸 이름과 값의 종류는 바꾸지 않는다(지난 기록 · 관계 · 지표 · 자동화가 칸 이름으로 이어져 있다)."""
from . import engine

KINDS = ("속성 값", "대상", "대상 속성", "같은 대상", "상위 분류", "관계 속성", "칸 설정")
OPS = ("단위·설명", "다른 이름", "칸 더하기", "대상 칸")


def _name(v, what, limit=100):
    v = str(v or "").strip()
    if not v or len(v) > limit:
        raise ValueError(f"{what}을(를) {limit}자 안으로 적어 주세요.")
    return v


def _dtype(v):
    if v not in engine.DTYPE_KO:
        raise ValueError("값의 종류를 고르세요.")
    return v


def card(K, kind, P):
    """화면이 보낸 고친 것 → 카드 payload. 틀리면 ValueError(사람이 읽을 까닭)."""
    if kind == "속성 값":
        e = K["entities"].get(int(P.get("entity_id") or 0))
        if not e:
            raise ValueError("대상을 찾지 못했어요.")
        attr = P.get("attr")
        if attr not in [a["name"] for a in engine.class_attrs(K, e["class_name"])]:
            raise ValueError("그 분류에 없는 정보예요. 먼저 [정보 더하기]를 해 주세요.")
        new = P.get("new")
        if new is not None and len(str(new)) > 500:
            raise ValueError("값은 500자 안으로 적어 주세요.")
        if engine.same_value(e["attrs"].get(attr), new):
            raise ValueError("바뀐 값이 없어요.")
        return {"entity_id": e["id"], "entity": e["name"], "class": e["class_name"], "attr": attr, "old": e["attrs"].get(attr), "new": new}
    if kind in ("대상", "대상 속성", "같은 대상", "상위 분류") and kind != "상위 분류":
        C = P.get("class")
        if C not in K["classes"]:
            raise ValueError("대상 분류를 고르세요.")
    if kind == "대상":
        names = list(dict.fromkeys(_name(v, "대상 이름", 200) for v in P.get("values") or []))[:100]
        fresh = [n for n in names if not engine.find_entity(K, C, n)]
        if not fresh:
            raise ValueError("이미 있는 대상이에요.")
        return {"class": C, "values": fresh, "attrs": {}}
    if kind == "대상 속성":
        attr = _name(P.get("attr"), "정보 이름")
        if attr in [a["name"] for a in engine.class_attrs(K, C)]:
            raise ValueError("이미 있는 정보예요.")
        return {"class": C, "attr": attr, "dtype": _dtype(P.get("dtype") or "text"), "unit": None, "values": {}}
    if kind == "같은 대상":
        same = P.get("same_as")
        if same not in {e["name"] for e in engine.members(K, C)}:
            raise ValueError("대상을 고르세요.")
        value = _name(P.get("value"), "별칭", 200)
        if engine.find_entity(K, C, value):
            raise ValueError("이미 쓰고 있는 이름이에요.")
        return {"class": C, "value": value, "same_as": same, "reason": "직접 더한 별칭이에요."}
    if kind == "상위 분류":
        C, parent = _name(P.get("class"), "분류 이름"), _name(P.get("parent"), "상위 분류 이름")
        if C == parent or (C in K["classes"] and parent in engine.descendants(K, C)):
            raise ValueError("분류가 돌고 돌게 되어 묶을 수 없어요.")
        members = [m for m in dict.fromkeys(str(m) for m in P.get("members") or []) if parent in K["classes"] and engine.find_entity(K, parent, m)]
        if C not in K["classes"] and not members:
            raise ValueError("하위 분류로 묶을 대상을 고르세요.")
        return {"class": C, "parent": parent, "members": members, "reason": "직접 정한 분류예요."}
    if kind == "관계 속성":
        L = next((l for l in K["links"] if l["id"] == int(P.get("link_id") or 0)), None)
        if not L or "." in L["from_ref"] or "." in L["to_ref"]:
            raise ValueError("대상 분류 사이의 관계를 고르세요.")
        values = {str(k): v for k, v in (P.get("values") or {}).items() if engine.filled(v)}
        if not values:
            raise ValueError("쌍마다 값을 하나 이상 적어 주세요.")
        return {"link_id": L["id"], "link": f"{L['from_ref']}—{L['to_ref']}", "attr": _name(P.get("attr"), "관계 정보 이름"),
                "dtype": _dtype(P.get("dtype") or "text"), "values": values}
    if kind == "칸 설정":
        T, op = P.get("type"), P.get("op")
        if T not in K["types"] or op not in OPS:
            raise ValueError("기록 종류와 할 일을 고르세요.")
        props = {p["name"]: p for p in K["props"][T]}
        if op == "칸 더하기":
            name = _name(P.get("name"), "칸 이름")
            if name in props or name == "날짜":
                raise ValueError("이미 있는 칸이에요.")
            return {"type": T, "op": op, "name": name, "dtype": _dtype(P.get("dtype") or "text"), "unit": (P.get("unit") or "").strip() or None}
        prop = P.get("prop")
        if prop not in props:
            raise ValueError("칸을 고르세요.")
        if op == "대상 칸":  # 이 칸은 무엇을 가리키나요? · 칸을 골라 대상으로 만들기
            if props[prop].get("ref_class"):
                raise ValueError(f"이미 '{props[prop]['ref_class']}'을(를) 가리키는 칸이에요.")
            if props[prop].get("dtype") not in ("text", "choice"):
                raise ValueError("글 칸만 대상 칸으로 정할 수 있어요.")
            C = _name(P.get("class"), "분류 이름")
            if C in K["types"]:
                raise ValueError("기록 종류와 같은 이름은 분류 이름으로 쓸 수 없어요.")
            df = engine.frame(K, T)
            seen = list(dict.fromkeys(str(v).strip() for v in (df[prop].dropna() if prop in df else []) if str(v).strip()))
            fresh = [v for v in seen if not (C in K["classes"] and engine.find_entity(K, C, v))][:300]
            return {"type": T, "op": op, "prop": prop, "class": C, "values": fresh,
                    "rows": int(df[prop].notna().sum()) if prop in df else 0}
        if op == "다른 이름":
            alias = _name(P.get("alias"), "다른 이름", 200)
            if (T, alias) in K["alias"]:
                raise ValueError("이미 쓰고 있는 이름이에요.")
            return {"type": T, "op": op, "prop": prop, "alias": alias}
        return {"type": T, "op": op, "prop": prop, "unit": (P.get("unit") or "").strip()[:30],
                "description": (P.get("description") or "").strip()[:300],
                "old_unit": props[prop].get("unit"), "old_description": props[prop].get("description")}
    raise ValueError("고칠 것을 고르세요.")


def card_text(q):
    """카드 한 줄."""
    P, k = q["payload"], q["kind"]
    if k == "속성 값":
        return f"'{P['entity']}'의 {P['attr']}: {P.get('old') if engine.filled(P.get('old')) else '없음'} → {P['new'] if engine.filled(P.get('new')) else '없음'}"
    if k == "대상":
        return f"{P['class']}에 대상 {', '.join(P['values'])} 더하기"
    if k == "대상 속성":
        return f"{P['class']}에 정보 '{P['attr']}'({engine.DTYPE_KO.get(P['dtype'], P['dtype'])}) 더하기"
    if k == "같은 대상":
        return f"'{P['value']}'를 '{P['same_as']}'의 다른 이름으로"
    if k == "상위 분류":
        return (f"{', '.join(P['members'])}를 '{P['class']}'로 묶어 '{P['parent']}' 아래에 두기" if P.get("members")
                else f"'{P['class']}'의 상위 분류를 '{P['parent']}'로 정하기")
    if k == "관계 속성":
        return f"관계 '{P['link']}'에 정보 '{P['attr']}' 더하기 · 쌍 {len(P['values'])}개"
    if P.get("op") == "칸 더하기":
        return f"'{P['type']}'에 칸 '{P['name']}'({engine.DTYPE_KO.get(P['dtype'], P['dtype'])}) 더하기"
    if P.get("op") == "다른 이름":
        return f"'{P['alias']}'라고 적힌 칸을 '{P['type']}.{P['prop']}' 칸으로 읽기"
    if P.get("op") == "대상 칸":
        return f"'{P['type']}.{P['prop']}' 칸을 대상 분류 '{P['class']}'로 · 새 대상 {len(P['values'])}개 · 기록 {P.get('rows', 0)}줄"
    return f"'{P['type']}.{P['prop']}' 단위 {P.get('unit') or '없음'} · 설명 {P.get('description') or '없음'}"
