"""뜻 풀이: 손으로 적은 짧은 표기(예: '현수 \\700', '현 \\700')를 사람이 확인한 규칙으로 칸 값으로 푼다.
규칙은 AI가 짓고(llm.meaning_rule), 적용과 숫자 읽기는 코드가 한다. 숫자는 적힌 글에 있는 것만 넣는다.
규칙: {"heads": [{"written": "현수", "means": "현수막"}], "head_col": "품목", "number_col": "폭"}"""
import re
from collections import defaultdict

HEAD = re.compile(r"[가-힣]+")          # 표기 앞의 글(머리말). 한글만 본다(T1 · MR 같은 기호는 뜻 풀이로 다루지 않는다)
NUM = re.compile(r"\d+(?:\.\d+)?")      # 동그라미 숫자(①)는 \d 가 아니라 잡히지 않는다


def head_of(value):
    m = HEAD.search(str(value or ""))
    return m.group(0) if m else ""


def number_after(value, head):
    v = str(value or "")
    m = NUM.search(v[v.index(head) + len(head):]) if head and head in v else None
    if not m:
        return None
    return float(m.group(0)) if "." in m.group(0) else int(m.group(0))


def clean(rule, label=""):
    """AI가 지은 규칙을 코드가 쓰는 모양으로 다듬는다. 쓸 수 없으면 None."""
    if not isinstance(rule, dict):
        return None
    heads = [{"written": str(h.get("written") or "").strip(), "means": str(h.get("means") or "").strip()}
             for h in rule.get("heads") or [] if isinstance(h, dict)]
    heads = [h for h in heads if HEAD.fullmatch(h["written"]) and 0 < len(h["means"]) <= 40][:20]
    col = lambda k: (str(rule.get(k) or "").strip()[:30] or None)
    head_col, number_col = col("head_col"), col("number_col")
    if head_col == label or number_col == label or (head_col and head_col == number_col):
        return None
    if not heads or not (head_col or number_col):
        return None
    return {"heads": heads, "head_col": head_col, "number_col": number_col, "meaning": str(rule.get("meaning") or "")[:80]}


def apply(rule, value):
    """규칙으로 적힌 표기 하나를 푼다: {칸 이름: 값}. 머리말이 규칙에 없으면 {}."""
    h = head_of(value)
    means = {x["written"]: x["means"] for x in rule.get("heads") or []}
    if not h or h not in means:
        return {}
    out = {}
    if rule.get("head_col"):
        out[rule["head_col"]] = means[h]
    if rule.get("number_col") and (n := number_after(value, h)) is not None:
        out[rule["number_col"]] = n
    return out


def shapes(values, known_heads=(), names=(), least=2, most=2):
    """되풀이되는 짧은 표기(한글 머리말 + 숫자)의 묶음. '현'과 '현수'처럼 앞이 같은 머리말은 한 묶음으로 본다.
    이미 뜻을 아는 머리말과 확정한 이름은 뺀다. [{"heads", "examples", "rows"}] 많은 순으로 most 개."""
    skip = set(known_heads) | {str(n).strip() for n in names}
    groups = defaultdict(list)
    for v in values:
        s = str(v or "").strip()
        h = head_of(s)
        if not s or len(s) > 20 or not h or len(h) > 4 or h in skip or number_after(s, h) is None:
            continue
        groups[h].append(s)
    out, used = [], set()
    for h in sorted(groups, key=lambda x: -len(groups[x])):
        if h in used:
            continue
        family = [x for x in groups if x not in used and (x.startswith(h) or h.startswith(x))]
        examples = [v for x in family for v in groups[x]]
        if len(examples) >= least:
            out.append({"heads": family, "examples": list(dict.fromkeys(examples))[:8], "rows": len(examples)})
            used.update(family)
    return out[:most]
