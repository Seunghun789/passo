"""지식그래프의 점과 선. 기록 종류(청록 원) · 칸(작은 청록 점) · 대상 분류(주황 상자) · 분류 정보 · 상위 분류 · 관계.
확정한 관계는 실선, 확인할 관계는 점선. 점마다 코드가 센 숫자와 다른 점과의 관계를 붙인다(점을 누르면 보이는 카드)."""
from . import engine

COLOR = {"type_fill": "#0F766E", "prop_dot": "#5EEAD4", "class_fill": "#C2410C", "attr_dot": "#FDBA74",
         "entity_dot": "#D4D4D8", "entity_link": "#C2410C", "line_weak": "#E4E4E7", "line": "#71717A", "line_strong": "#52525B"}
NODE_KO = {"T": "기록 종류", "P": "칸", "C": "대상 분류", "A": "대상 정보", "E": "대상"}
ENTITY_MAX = 60  # [대상까지]에 그리는 대상 수


def ref_text(ref):
    T, p = engine.split(ref)
    return f"{p}({T})" if p else T


def link_sentence(P):
    a, b = ref_text(P["from"]), ref_text(P["to"])
    if "." not in P["from"] and "." not in P["to"]:
        return {"의존": f"'{a}'은(는) '{b}'에 의존하나요?", "영향": f"'{a}'이(가) '{b}'에 영향을 주나요?",
                "대체": f"'{a}'이(가) '{b}'을(를) 대신할 수 있나요?"}.get(
            P["kind"], f"'{a}'와 '{b}'는 이어져 있나요?{' (관계 이름: ' + P['name'] + ')' if P.get('name') else ''}")
    return {"최소 기준": f"'{a}'이(가) '{b}'의 최소 기준인가요?", "최대 기준": f"'{a}'이(가) '{b}'의 최대 기준인가요?",
            "연결": f"'{a}'와 '{b}'는 같은 대상을 가리키나요?", "함께 움직임": f"'{a}'와 '{b}'는 함께 움직이나요?",
            "의존": f"'{a}'은(는) '{b}'에 의존하나요?", "영향": f"'{a}'이(가) '{b}'에 영향을 주나요?",
            "대체": f"'{a}'이(가) '{b}'을(를) 대신할 수 있나요?"}[P["kind"]]


def stated(question):
    """관계 질문을 확정한 관계의 문장으로: '영향을 주나요?' → '영향을 줘요.'"""
    for ask, say in (("의존하나요?", "의존해요."), ("주나요?", "줘요."), ("있나요?", "있어요."), ("기준인가요?", "기준이에요."),
                     ("가리키나요?", "가리켜요."), ("움직이나요?", "움직여요.")):
        question = question.replace(ask, say)
    return question


def node_id(K, ref):
    """관계가 가리키는 곳(칸·분류·분류 정보)을 그림의 점 이름으로."""
    T, p = engine.split(ref)
    if not p:
        return ("T:" if T in K["types"] else "C:") + T
    return ("P:" if T in K["types"] else "A:") + ref


def graph_data(K, pend, with_entities=False):
    """기록 종류(청록 원)·칸(작은 청록 점)·대상 분류(주황 상자)·분류 정보·상위 분류·관계. 확정은 실선, 제안은 점선."""
    nodes, edges = [], []

    def dot(id_, label, color, big=False, box=False):
        c = {"background": color, "border": color, "highlight": {"background": color, "border": color},
             "hover": {"background": color, "border": color}}  # 누른 점은 테두리 대신 빛으로 보인다
        nodes.append({"id": id_, "label": label, "color": c, **(
            {"shape": "box", "font": {"color": "#FFFFFF"}, "margin": 10, "shapeProperties": {"borderRadius": 8}} if box else
            {"shape": "circle", "font": {"color": "#FFFFFF"}, "widthConstraint": {"minimum": 60}} if big else
            {"shape": "dot", "size": 6})})

    def line(a, b, **kw):
        edges.append({"from": a, "to": b, **kw})

    for T in K["types"]:
        dot(f"T:{T}", T, COLOR["type_fill"], big=True)
        for p in K["props"][T]:
            dot(f"P:{T}.{p['name']}", p["name"], COLOR["prop_dot"])
            line(f"T:{T}", f"P:{T}.{p['name']}", color=COLOR["line_weak"], rel=["칸", "기록 종류"])
            if p.get("ref_class") in K["classes"]:
                line(f"P:{T}.{p['name']}", f"C:{p['ref_class']}", label="가리킴", dashes=[2, 4], arrows="to", rel=["가리키는 대상 분류", "가리키는 칸"])
    for C, parent in K["classes"].items():
        n = sum(1 for e in K["entities"].values() if e["class_name"] == C)
        dot(f"C:{C}", f"{C}\n대상 {n}개", COLOR["class_fill"], box=True)
        if parent:
            line(f"C:{C}", f"C:{parent}", label="종류의 하나", arrows="to", color=COLOR["line"], rel=["상위 분류", "하위 분류"])
        for a in K["props"].get(C, []):
            dot(f"A:{C}.{a['name']}", a["name"], COLOR["attr_dot"])
            line(f"C:{C}", f"A:{C}.{a['name']}", color=COLOR["line_weak"], rel=["정보 칸", "대상 분류"])
    for l in K["links"]:
        label = (l.get("name") or l["kind"]) + (" (" + ", ".join(d["name"] for d in l["attr_defs"]) + ")" if l.get("attr_defs") else "")
        line(node_id(K, l["from_ref"]), node_id(K, l["to_ref"]), label=label, arrows="to", width=1.6, color=COLOR["line_strong"],
             say=stated(link_sentence({"from": l["from_ref"], "to": l["to_ref"], "kind": l["kind"], "name": l.get("name")})))
    for q in pend:
        P = q["payload"]
        line(node_id(K, P["from"]), node_id(K, P["to"]), label=f"{P.get('name') or P['kind']}?", arrows="to", dashes=True,
             say=link_sentence(P) + " (확인할 관계)")
    if with_entities:
        for e in list(K["entities"].values())[:ENTITY_MAX]:
            dot(f"E:{e['id']}", e["name"], COLOR["entity_dot"])
            line(f"E:{e['id']}", f"C:{e['class_name']}", color=COLOR["line_weak"], rel=["분류", "대상"])
        for l in K["links"]:
            if "." in l["from_ref"] or "." in l["to_ref"]:
                continue
            for a, b in engine.link_pairs(K, l)[[l["from_ref"], l["to_ref"]]].itertuples(index=False):
                x, y = engine.find_entity(K, l["from_ref"], a), engine.find_entity(K, l["to_ref"], b)
                if x and y:
                    line(f"E:{x}", f"E:{y}", arrows="to", color=COLOR["entity_link"],
                         say=f"{K['entities'][x]['name']} → {l.get('name') or l['kind']} → {K['entities'][y]['name']}")
    ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from"] in ids and e["to"] in ids]
    for n in nodes:
        n["info"] = node_info(K, n, nodes, edges)
    return nodes, edges


def node_info(K, n, nodes, edges):
    """점을 누르면 그 옆에 뜨는 정보 카드: 이름·종류, 코드가 센 숫자 세 개, 다른 점과 어떤 관계인지."""
    kind, _, ref = n["id"].partition(":")
    name = n["label"].split("\n")[0]
    def short(i):  # 칸·정보는 다른 종류·분류의 것일 때만 어디 것인지 붙인다
        if i[0] in "PA":
            owner, p = engine.split(i[2:])
            return p if owner == ref else ref_text(i[2:])
        return next(x["label"].split("\n")[0] for x in nodes if x["id"] == i)
    mine = [e for e in edges if n["id"] in (e["from"], e["to"])]
    groups, rels = {}, []
    for e in mine:  # 칸·정보·분류 같은 짜임은 "칸: 담당자, 설비"로 묶고, 관계는 지식그래프 목록과 같은 문장으로
        out = e["from"] == n["id"]
        if e.get("rel"):
            groups.setdefault(e["rel"][0 if out else 1], []).append(short(e["to"] if out else e["from"]))
        elif e.get("say"):
            rels.append(e["say"])
    rels = [f"{k}: {', '.join(v[:6])}" + (f" 외 {len(v) - 6}개" if len(v) > 6 else "") for k, v in groups.items()] + rels
    near = len({e["to"] if e["from"] == n["id"] else e["from"] for e in mine})
    desc, stats = "", []
    if kind == "T":
        df = engine.frame(K, ref)
        desc = f"날짜 {df['날짜'].min()} ~ {df['날짜'].max()}" if len(df) else "아직 확정한 기록이 없어요"
        stats = [("기록", f"{len(df)}줄"), ("칸", f"{len(K['props'][ref])}개"), ("이어진 점", f"{near}개")]
    elif kind == "P":
        T, prop = engine.split(ref)
        p = next(x for x in K["props"][T] if x["name"] == prop)
        df = engine.frame(K, T)
        filled = int(df[prop].notna().sum()) if prop in df else 0
        desc = " · ".join(x for x in (f"{T}의 칸", p.get("unit") and f"단위 {p['unit']}", p.get("description")) if x)
        stats = [("값의 종류", engine.DTYPE_KO[p["dtype"]]), ("값이 적힌 기록", f"{filled}줄"), ("이어진 점", f"{near}개")]
    elif kind == "C":
        names = [e["name"] for e in engine.members(K, ref)]
        direct = sum(1 for e in K["entities"].values() if e["class_name"] == ref)  # 그림의 상자에 적힌 수
        desc = (f"상위 분류 {K['classes'][ref]} · " if K["classes"][ref] else "") + (f"대상 예: {', '.join(names[:3])}" if names else "아직 대상이 없어요")
        stats = [("하위 분류까지 대상" if direct != len(names) else "대상", f"{len(names)}개"),("정보 칸", f"{len(K['props'].get(ref, []))}개"), ("이어진 점", f"{near}개")]
    elif kind == "A":
        C, attr = engine.split(ref)
        has = sum(1 for e in engine.members(K, C) if engine.filled(e["attrs"].get(attr)))
        desc = f"{C}의 정보 칸"
        stats = [("값이 있는 대상", f"{has}개"), ("대상", f"{len(engine.members(K, C))}개"), ("이어진 점", f"{near}개")]
    elif kind == "E" and int(ref) in K["entities"]:
        e = K["entities"][int(ref)]
        attrs = {k: v for k, v in e["attrs"].items() if engine.filled(v)}
        desc = " · ".join(f"{k} {v}" for k, v in list(attrs.items())[:3]) or f"{e['class_name']} 대상"
        stats = [("분류", e["class_name"]), ("별칭", f"{len(engine.aliases_of(K, e['id']))}개"), ("이어진 점", f"{near}개")]
    return {"name": name, "kind": NODE_KO[kind], "desc": desc, "stats": [list(x) for x in stats], "rels": rels, "count": len(mine)}
