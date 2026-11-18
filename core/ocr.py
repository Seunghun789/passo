"""사진 속 글줄의 정확한 위치(OCR). PP-OCRv5 검출 + 한국어 인식 ONNX 모델을 onnxruntime 으로 CPU에서 돌린다.
값은 Claude 가 읽고, 여기서는 글줄마다 상자와 대략 읽은 글을 돌려준다. 모델 파일은 models/ocr/ 에 둔다(git 제외)."""
import io
import shutil
import threading
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np

DIR = Path(__file__).resolve().parent.parent / "models" / "ocr"
DET, REC, DICT = DIR / "detection_v5_det.onnx", DIR / "languages_korean_rec.onnx", DIR / "languages_korean_dict.txt"


SOURCE = "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/"
FILES = {DET: "detection/v5/det.onnx", REC: "languages/korean/rec.onnx", DICT: "languages/korean/dict.txt"}
FETCHING = threading.Lock()  # 여러 사람이 동시에 읽어도 한 번만 받는다


def ready():
    return all(path.exists() for path in FILES)


def fetch():
    """없는 모델 파일을 Hugging Face(monkt/paddleocr-onnx, Apache-2.0)에서 받아 models/ocr/ 에 둔다.
    git 에 넣지 않아서 Streamlit Cloud 처럼 새로 켠 서버에는 없다. 다 받은 뒤에 이름을 바꿔, 받다 끊겨도 깨진 파일이 남지 않는다."""
    with FETCHING:
        DIR.mkdir(parents=True, exist_ok=True)
        for path, rel in FILES.items():
            if path.exists():
                continue
            part = path.with_suffix(path.suffix + ".part")
            try:
                with urllib.request.urlopen(SOURCE + rel, timeout=60) as res, open(part, "wb") as out:
                    shutil.copyfileobj(res, out)
                part.replace(path)
            finally:
                part.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def _models():
    import onnxruntime as ort
    opt = ort.SessionOptions()
    opt.log_severity_level = 3
    det = ort.InferenceSession(str(DET), opt, providers=["CPUExecutionProvider"])
    rec = ort.InferenceSession(str(REC), opt, providers=["CPUExecutionProvider"])
    chars = [""] + DICT.read_text(encoding="utf-8").split("\n")[:-1] + [" "]
    return det, rec, chars


def _components(mask):
    """이진 그림의 이어진 덩어리마다 (y0, x0, y1, x1, 넓이). 4방향 이웃."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys, xs):
        if seen[sy, sx]:
            continue
        stack, seen[sy, sx] = [(sy, sx)], True
        y0 = y1 = sy; x0 = x1 = sx; n = 0
        while stack:
            y, x = stack.pop(); n += 1
            y0, y1, x0, x1 = min(y0, y), max(y1, y), min(x0, x), max(x1, x)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True; stack.append((ny, nx))
        out.append((y0, x0, y1, x1, n))
    return out


def _detect(img, side=1280):
    """글줄 상자(원본 픽셀). DB 검출: 글자일 확률 그림을 0.3 으로 자르고 덩어리마다 상자를 조금 넓힌다."""
    det, _, _ = _models()
    W, H = img.size
    s = min(1.0, side / max(W, H))
    w, h = max(32, round(W * s / 32) * 32), max(32, round(H * s / 32) * 32)
    x = np.asarray(img.resize((w, h)), dtype=np.float32) / 255.0
    x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    prob = det.run(None, {"x": x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0, 0]
    boxes = []
    for y0, x0, y1, x1, n in _components(prob > 0.3):
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if n < 12 or bh < 4 or prob[y0:y1 + 1, x0:x1 + 1].mean() < 0.5 * (n / (bw * bh)):
            continue
        d = n * 1.5 / (2 * (bw + bh))  # 검출은 글줄 안쪽을 좁게 잡아서 둘레만큼 넓힌다(unclip 1.5)
        boxes.append([max(0, (x0 - d) * W / w), max(0, (y0 - d) * H / h),
                      min(W, (x1 + 1 + d) * W / w), min(H, (y1 + 1 + d) * H / h)])
    return boxes


def _recognize(img, boxes):
    _, rec, chars = _models()
    out = []
    for b in boxes:
        crop = img.crop(tuple(int(v) for v in b))
        cw, ch = crop.size
        tw = max(16, min(1600, round(48 * cw / max(1, ch))))
        x = np.asarray(crop.resize((tw, 48)), dtype=np.float32) / 255.0
        x = (x - 0.5) / 0.5
        p = rec.run(None, {"x": x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
        idx, conf = p.argmax(axis=1), p.max(axis=1)
        text, last, cs = [], 0, []
        for i, c in zip(idx, conf):
            if i != last and i != 0 and i < len(chars):
                text.append(chars[i]); cs.append(c)
            last = i
        out.append(("".join(text).strip(), float(np.mean(cs)) if cs else 0.0))
    return out


def lines(photo):
    """사진(바이트) → [{"text", "conf", "box": [x0, y0, x1, y1] 0~1000}]. 사진은 휴대폰 방향대로 돌려서 본다."""
    from PIL import Image, ImageOps
    fetch()
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(photo))).convert("RGB")
    W, H = img.size
    boxes = _detect(img)
    return [{"text": t, "conf": round(c, 3), "box": [round(b[0] / W * 1000), round(b[1] / H * 1000), round(b[2] / W * 1000), round(b[3] / H * 1000)]}
            for b, (t, c) in zip(boxes, _recognize(img, boxes))]


def _norm(s):
    return "".join(ch for ch in str(s) if ch.isalnum())


def _jamo(s):
    """한글 음절을 자모로 푼다('경욱' → ㄱㅕㅇㅇㅜㄱ). 흘려 쓴 글씨를 OCR 이 한두 자모 틀리게 읽어도 닮음을 잡는다."""
    out = []
    for ch in s:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out += [chr(0x1100 + c // 588), chr(0x1161 + c % 588 // 28)] + ([chr(0x11A7 + c % 28)] if c % 28 else [])
        else:
            out.append(ch)
    return "".join(out)


def _digits(s):
    return "".join(ch for ch in str(s) if ch.isdigit())


def _sim(value, text):
    """값과 OCR 글이 얼마나 닮았나(0~1). 긴 값은 여러 글줄에 걸쳐 적히므로 OCR 글이 값 안에 얼마나 들어 있는지로 본다.
    둘 다 숫자가 있는데 숫자가 서로 다르면(106동과 109동) 거의 닮지 않은 것으로 본다."""
    from difflib import SequenceMatcher
    a, b = _norm(value), _norm(text)
    if not a or not b:
        return 0.0
    if len(a) <= 2:  # '7' · '0' 처럼 짧은 값은 글줄에 그대로 들어 있는지만 본다
        return 0.6 if a in b else 0.0
    da, db = _digits(a), _digits(b)
    a, b = _jamo(a), _jamo(b)
    m = SequenceMatcher(None, a, b, autojunk=False)
    inside = sum(blk.size for blk in m.get_matching_blocks()) / len(b)  # OCR 글이 값 안에 든 정도(글줄이 나뉘어 잡혔을 때)
    sim = inside if len(a) > 15 * 3 and len(b) < len(a) else max(m.ratio(), 0.8 * inside if len(b) < len(a) else 0)
    if da and (not db or (da not in db and db not in da)):  # 106동 ↔ 109동, 106동 ↔ '대 표'
        sim *= 0.3 if db else 0.5
    return sim


def _center(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _dist(a, b):
    """두 상자 가운데의 거리(0~1000). 위아래로 어긋난 것을 두 배로 친다. 줄을 잘못 짚는 것이 더 나쁘다."""
    (ax, ay), (bx, by) = _center(a), _center(b)
    return ((ax - bx) ** 2 + (2 * (ay - by)) ** 2) ** 0.5


def _overlap_x(a, b):
    """좌우로 겹친 정도: 겹친 폭 / 둘 중 넓은 폭."""
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) / max(1, a[2] - a[0], b[2] - b[0])


def place_all(cells, found, used=None):
    """두 번 짝짓는다. 첫 번째에서 글이 확실히 닮은 짝으로 Claude 의 대략의 상자가 위아래로 얼마나 쏠렸는지 재고,
    각 값의 대략의 상자를 가까운 확실한 짝들의 쏠림만큼 옮겨 다시 짝짓는다(사진 아래로 갈수록 커지는 쏠림을 바로잡는다).
    used: 집합을 넘기면 값과 짝지어진 글줄 번호(found 안의 순서)를 더한다. 읽지 않은 곳을 셀 때 쓴다."""
    first, sure, took = _place(cells, found)
    shifts = [(cells[ci][1][1], (first[ci][1] + first[ci][3] - cells[ci][1][1] - cells[ci][1][3]) / 2) for ci in sure]
    if len(shifts) < 3:
        if used is not None:
            used.update(took)
        return first
    moved = []
    for value, rough, label in cells:
        if not rough:
            moved.append((value, rough, label)); continue
        near = sorted(shifts, key=lambda s: abs(s[0] - rough[1]))[:3]
        dy = sorted(s[1] for s in near)[1]
        moved.append((value, [rough[0], rough[1] + dy, rough[2], rough[3] + dy], label))
    out, _, took = _place(moved, found)
    if used is not None:
        used.update(took)
    return out


def _place(cells, found):
    """Claude 가 읽은 값마다 정확한 상자. cells: [(값, 대략의 상자 또는 None, 칸 이름)], found: lines() 결과.
    값과 글줄의 모든 짝을 점수로 줄 세워 좋은 짝부터 정한다(한 글줄은 한 값만). 점수는 글이 닮은 정도에서 대략의 상자와의 거리를 뺀 것.
    글이 닮지 않아도 대략의 상자와 같은 열에서 가까우면 짝이 된다(흘려 쓴 손글씨). 짝이 없으면 대략의 상자를 그대로 쓴다."""
    pairs, sims = [], {}
    for ci, (value, rough, label) in enumerate(cells):
        if not _norm(value):  # 빈 칸은 짝지을 글이 없다(칸 이름이 적힌 머리글과 짝짓지 않는다)
            continue
        short = len(_norm(value)) <= 2
        for li, l in enumerate(found):
            b, sim = l["box"], _sim(value, l["text"])
            if short and label and _norm(label) and _norm(label) in _norm(l["text"]):  # '찬성 : 7' 처럼 칸 이름과 함께 적힌 짧은 값
                sim = max(sim, 0.7)
            d = _dist(rough, b) if rough else 0.0
            if sim >= 0.5 and d <= 300:
                pairs.append((sim - d / 150, ci, li))
                sims[ci, li] = sim
            elif rough and not short and _overlap_x(rough, b) >= 0.2 \
                    and abs(_center(rough)[1] - _center(b)[1]) <= 60:
                pairs.append((-1 - d / 150, ci, li))
    score = {(ci, li): sc for sc, ci, li in pairs}
    wide = lambda ci, li: cells[ci][1] and found[li]["box"][2] - found[li]["box"][0] > 1.5 * (cells[ci][1][2] - cells[ci][1][0])
    pick = {}
    for sc, ci, li in sorted(pairs, reverse=True):  # 좋은 짝부터. 여러 값이 든 넓은 글줄은 칸 이름이 다른 값끼리 함께 쓴다
        if ci in pick:
            continue
        others = [cj for cj, lj in pick.items() if lj == li]
        if others and not (wide(ci, li) and all(cells[cj][2] != cells[ci][2] and wide(cj, li) for cj in others)):
            continue
        pick[ci] = li
    better = True
    while better:  # 두 값의 글줄을 맞바꾸면 점수 합이 커지면 바꾼다(대략의 상자가 옆 칸으로 쏠렸을 때)
        better = False
        for ci in list(pick):
            for cj in list(pick):
                li, lj = pick[ci], pick[cj]
                if ci < cj and li != lj and (ci, lj) in score and (cj, li) in score \
                        and score[ci, lj] + score[cj, li] > score[ci, li] + score[cj, lj] + 1e-9:
                    pick[ci], pick[cj], better = lj, li, True
    out = [c[1] for c in cells]
    for ci, li in list(pick.items()):
        box, rough = list(found[li]["box"]), cells[ci][1]
        if wide(ci, li):  # 한 글줄에 여러 값('찬성 7 반대 0'): 위아래는 글줄, 좌우는 대략의 상자
            box = [max(box[0], rough[0]), box[1], min(box[2], rough[2]), box[3]]
            if box[0] >= box[2]:  # 대략의 상자가 그 글줄과 가로로 겹치지 않으면 다른 열의 글이다. 짝을 버린다
                del pick[ci]
                continue
        out[ci] = box
    used, done = set(pick.values()), set(pick)
    for ci, (value, rough, _) in enumerate(cells):  # 긴 값: 바로 위아래로 이어지고 값에 든 글줄을 함께 감싼다
        box = out[ci]
        if ci in done and len(_norm(value)) > 15:
            for li, l in enumerate(found):
                b = l["box"]
                if li not in used and _sim(value, l["text"]) >= 0.6 and _overlap_x(box, b) >= 0.3 and b[1] < box[3] + 25 and b[3] > box[1] - 25:
                    box = [min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3])]; used.add(li)
            out[ci] = box
    sure = [ci for ci, li in pick.items() if cells[ci][1] and sims.get((ci, li), 0) >= 0.8 and len(_norm(cells[ci][0])) > 2]
    return out, sure, used


def calibrate(cells, found):
    """쪽 전체에서 글이 확실히 같은 짝(값과 0.8 넘게 닮은 글줄이 그 쪽에 하나뿐)으로 Claude 의 세로 좌표가 실제보다
    얼마나 늘거나 밀렸는지 잰다: 실제 y = a·y + b. 짝이 3개 안 되거나 비율이 터무니없으면 None(바로잡지 않는다).
    cells: [(값, 대략의 상자 또는 None, 칸 이름)]"""
    from itertools import combinations
    pts = []
    for value, rough, _ in cells:
        if not rough or len(_norm(value)) <= 2:
            continue
        hits = [l for l in found if len(_norm(l["text"])) > 2 and _sim(value, l["text"]) >= 0.8]  # 한두 글자 글줄은 어디에나 들어맞는다
        if len(hits) == 1:
            pts.append((_center(rough)[1], _center(hits[0]["box"])[1]))
    if len(pts) < 3:
        return None
    slopes = sorted((y2 - y1) / (x2 - x1) for (x1, y1), (x2, y2) in combinations(pts, 2) if abs(x2 - x1) > 20)
    if not slopes:
        return None
    a = slopes[len(slopes) // 2]
    if not 0.3 <= a <= 3:
        return None
    b = sorted(y - a * x for x, y in pts)[len(pts) // 2]
    return a, b


def stretch(box, fit):
    """calibrate 로 잰 (a, b)로 상자의 세로 좌표를 바로잡는다. fit 이 없으면 그대로."""
    if not box or not fit:
        return box
    a, b = fit
    y0, y1 = (min(1000, max(0, round(a * y + b))) for y in (box[1], box[3]))
    return [box[0], y0, box[2], y1] if y0 < y1 else box


def grid(rows, found):
    """표의 칸 상자를 AI 좌표 대신 OCR 격자로 잡는다. rows: 위→아래 순서의 줄마다 [(값, AI 상자 또는 None, 칸 이름)].
    줄: AI가 읽은 줄과 OCR 가로줄을 위→아래로 하나씩 차례로 짝짓고, 글이 닮은 짝이 그 차례를 당긴다(건너뛰면 감점). 짝이 없는 줄은
    앞뒤 짝 사이의 빈 가로줄에 차례로 놓고, 모자라면 그 사이를 고르게 나눈다.
    열: 글이 확실히 같은 짝(그 가로줄에서 값과 0.8 넘게 닮은 글줄이 하나뿐)들의 가로 자리로 잰다. 잰 열이 둘 넘으면
    재지 못한 열은 AI 가로 좌표를 잰 열에 맞춰 옮기고, 아니면 AI 좌표를 쓴다.
    돌려줌: rows 와 같은 모양의 상자 목록. 짝지은 줄이 하나도 없으면 None."""
    bs = bands(found, 0.2)  # 줄 자리를 잡을 때는 흐린 글줄도 쓴다
    if not bs or not rows:
        return None
    weight = lambda v: 0 if not _norm(v) else (1.0 if len(_norm(v)) > 2 else 0.3)  # 한두 글자 값은 어디에나 들어맞는다
    def like(v, text):  # 긴 값은 한두 글자 글줄('3' · 'L')과 짝짓지 않는다. 그런 글줄은 어느 값에나 들어 있다
        return 0.0 if len(_norm(v)) > 2 and len(_norm(text)) <= 2 else _sim(v, text)
    score = [[sum(weight(v) * max((like(v, found[i]["text"]) for i in idx), default=0) for v, _, _ in r) for idx, _ in bs]
             for r in rows]
    R, B = len(rows), len(bs)
    skip_row, skip_band = 0.3, 0.2  # 줄 · 가로줄을 건너뛰는 감점. 멀리 있는 그럴듯한 짝보다 차례대로 하나씩 짝짓는 쪽을 고른다
    NEG = float("-inf")
    f = [[0.0] * (B + 1)] + [[-skip_row * i] + [NEG] * B for i in range(1, R + 1)]  # 맨 위 머리글 가로줄은 감점 없이 건너뛴다
    for i in range(1, R + 1):
        for j in range(1, B + 1):
            take = f[i - 1][j - 1] + score[i - 1][j - 1]  # 글이 닮지 않아도 차례대로 하나씩 놓는 것이 기본, 닮은 글이 당긴다
            f[i][j] = max(f[i - 1][j] - skip_row, f[i][j - 1] - skip_band, take)
    j = max(range(B + 1), key=lambda k: f[R][k])  # 맨 아래 남은 가로줄도 감점 없이 둔다
    at, i = [None] * R, R
    while i and j:
        if f[i][j] == f[i - 1][j - 1] + score[i - 1][j - 1]:
            at[i - 1] = j - 1; i -= 1; j -= 1
        elif f[i][j] == f[i - 1][j] - skip_row:
            i -= 1
        else:
            j -= 1
    anchors = [n for n in range(R) if at[n] is not None]
    if not anchors:
        return None
    height = sorted(b[3] - b[1] for _, b in bs)[B // 2]
    ys = [None] * R
    for n in anchors:
        ys[n] = bs[at[n]][1][1], bs[at[n]][1][3]
    edges = [(-1, -1)] + [(n, at[n]) for n in anchors] + [(R, B)]
    for (n0, j0), (n1, j1) in zip(edges, edges[1:]):
        gap = list(range(n0 + 1, n1))
        if not gap:
            continue
        free = list(range(j0 + 1, j1))
        if n0 < 0:
            free = free[-len(gap):]  # 첫 짝 위의 줄은 바로 위 가로줄부터
        if len(free) >= len(gap):
            for n, j in zip(gap, free):
                ys[n] = bs[j][1][1], bs[j][1][3]
        else:  # 빈 가로줄이 모자라면 앞뒤 짝의 가운데 사이를 고르게 나누고 높이는 보통 줄 높이
            c0 = (ys[n0][0] + ys[n0][1]) / 2 if n0 >= 0 else (ys[n1][0] + ys[n1][1]) / 2 - height * (len(gap) + 1)
            c1 = (ys[n1][0] + ys[n1][1]) / 2 if n1 < R else c0 + height * (len(gap) + 1)
            step = (c1 - c0) / (len(gap) + 1)
            for k, n in enumerate(gap, 1):
                c = c0 + k * step
                ys[n] = max(0, round(c - height / 2)), min(1000, round(c + height / 2))
    xs = {}
    for r, j in zip(rows, at):
        if j is None:
            continue
        for v, _, label in r:
            if len(_norm(v)) <= 2:
                continue
            hits = [i for i in bs[j][0] if len(_norm(found[i]["text"])) > 2 and _sim(v, found[i]["text"]) >= 0.8]
            if len(hits) == 1 and found[hits[0]]["box"][2] - found[hits[0]]["box"][0] <= 300:  # 여러 열에 걸친 글줄은 빼고
                xs.setdefault(label, []).append(found[hits[0]]["box"])
    mid = lambda v: sorted(v)[len(v) // 2]
    cols = {label: [mid([b[0] for b in v]), mid([b[2] for b in v])] for label, v in xs.items()}
    ai = {}
    for r in rows:
        for _, rough, label in r:
            if rough:
                ai.setdefault(label, []).append(rough)
    ai = {label: [mid([b[0] for b in v]), mid([b[2] for b in v])] for label, v in ai.items()}
    pts = [((ai[l][0] + ai[l][1]) / 2, (cols[l][0] + cols[l][1]) / 2) for l in cols if l in ai]
    fit = None
    if len(pts) >= 2:
        from itertools import combinations
        slopes = sorted((y2 - y1) / (x2 - x1) for (x1, y1), (x2, y2) in combinations(pts, 2) if abs(x2 - x1) > 20)
        if slopes and 0.2 <= slopes[len(slopes) // 2] <= 5:
            a = slopes[len(slopes) // 2]
            fit = a, mid([y - a * x for x, y in pts])
    def column(label, rough):
        if label in cols:
            return cols[label]
        if label in ai and fit:
            a, b = fit
            half = (ai[label][1] - ai[label][0]) * a / 2
            c = a * (ai[label][0] + ai[label][1]) / 2 + b
            return [max(0, round(c - half)), min(1000, round(c + half))]
        return [rough[0], rough[2]] if rough else None
    out = []
    for r, y in zip(rows, ys):
        line_ = []
        for _, rough, label in r:
            x = column(label, rough)
            line_.append([x[0], y[0], x[1], y[1]] if x and y and x[0] < x[1] and y[0] < y[1] else rough)
        out.append(line_)
    return out


def bands(found, least=0.5):
    """판독한 글줄(글자가 있고 확신 least 이상)을 가로줄로 묶는다. 세로 범위가 작은 쪽 높이의 절반 넘게 겹치면 같은 가로줄.
    [(글줄 번호들, 감싸는 상자)]를 위에서 아래 순서로 돌려준다."""
    out = []
    keep = [i for i, l in enumerate(found) if l.get("conf", 0) >= least and _norm(l["text"])]
    for i in sorted(keep, key=lambda i: found[i]["box"][1]):
        b = found[i]["box"]
        for idx, box in out:
            if min(box[3], b[3]) - max(box[1], b[1]) >= 0.5 * min(box[3] - box[1], b[3] - b[1]):
                idx.append(i)
                box[:] = [min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3])]
                break
        else:
            out.append(([i], list(b)))
    return out


def unread(found, used, labels=()):
    """읽은 값과 짝지어진 글줄이 하나도 없는 가로줄. 처음 읽은 가로줄보다 위(제목·머리글)와
    칸 이름만 적힌 글줄은 셈하지 않는다. {"bands": 센 가로줄 수, "unread": [상자], "read_to": 마지막으로 읽은 가로줄의 아래}"""
    names = sorted({_norm(x) for x in labels if _norm(x)}, key=len, reverse=True)

    def header(text):
        rest = full = _norm(text)
        for n in names:
            rest = rest.replace(n, "")
        return rest != full and len(rest) <= 1

    rows = [(any(i in used for i in idx), all(header(found[i]["text"]) for i in idx), box) for idx, box in bands(found)]
    first = next((n for n, (hit, _, _) in enumerate(rows) if hit), None)
    if first is None:
        return {"bands": sum(not h for _, h, _ in rows), "unread": [b for _, h, b in rows if not h], "read_to": None}
    rows = [r for r in rows[first:] if not r[1]]
    return {"bands": len(rows), "unread": [b for hit, _, b in rows if not hit],
            "read_to": max(b[3] for hit, _, b in rows if hit)}


if __name__ == "__main__":
    fetch()
    print("OCR 모델 준비됨" if ready() else "OCR 모델을 받지 못했어요")
