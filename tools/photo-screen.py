#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""photo-screen.py — 真品照初篩（工單 #7）：丟候選圖，排出「收／要人眼／不收」並寫原因。

判準照本機正本（商品片SOP §2＋建卡程式 prodfilm.py card 的量法），⛔ 自己發明更鬆的。
實心度、物件數、前景比用建卡**一模一樣**的定義（jobs/wo7-真品照初篩-1019/參考-建卡量法.py 的 measure_alpha），
初篩過的圖去建卡，才不會再被這兩條擋回來。只用 numpy／opencv／Pillow（視覺模型的 HTTP 介面用標準庫 urllib，預設不連）。

用法：
  python tools/photo-screen.py <圖或資料夾>… [--json out.json] [--md out.md] [--sheet out.jpg]
                               [--judge none|http --judge-url http://127.0.0.1:8080 --judge-model 名稱]
  吃 jpg／png（含 RGBA 去背）／webp。資料夾裡排序：收（長邊大的先）→ 要人眼 → 不收。

結論：收（全部過）／要人眼（有一條要人判）／不收（有一條硬擋）。任何一條不收 ⇒ 不收。
退出碼：0 跑完（不管判什麼）／2 參數錯或一張圖都讀不到。
"""
import argparse
import base64
import io
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 門檻（集中在這裡；每條寫來源。⛔ 放寬本機門檻：長邊 700、高 600、實心度 0.88／0.75、物件數 1、放大 1.30） ──────────
ALPHA_THR = 128            # 建卡 measure_alpha：alpha > 128 算商品
MIN_FG_PX = 400            # 建卡 measure_alpha：前景 < 400 px ＝「去背之後幾乎沒有東西」
OBJ_MIN_FRAC = 0.03        # 建卡 n_objects：連通塊 ≥ 前景 3% 才算一個東西；建卡要求剛好 1 個（SOP §2）
SOLIDITY_MIN = 0.88        # 建卡 solidity_min：< 0.88 建卡會擋
SOLIDITY_HALO = 0.75       # 建卡 halo 0.75：0.75–0.88 ⇒ 要人眼（袋形凹商品走 halo_flood、白色透明先 cutout）；< 0.75 ⇒ 不收
LONG_OK = 1000             # 商品長邊 ≥ 1000 ＝尺寸過（候選-20261011-晚上 條件）
LONG_MIN = 700             # 商品長邊 700–999 ＝「大字包裝才收」⇒ 要人眼；< 700 ⇒ 不收、⛔ 例外（44 10/19 07:1x 判愛康 598）
HEIGHT_MIN = 600           # 商品本身高 ≥ 600（SOP §2）；不夠 ⇒ 不收
WIDE_RATIO = 1.6           # 寬高比 ≥ 1.6 的寬包高不夠 ⇒ 要人眼（Fable 42 10/12，sf 蘇菲三包入；寬包放大倍數另算）
FINAL_SCALE_MAX = 1.30     # 建卡 final_scale_max：成片放大上限（只拿來算「成片最高幾 px」的參考值，不另外判）
BADGE_GAP_MIN = 4          # 跟商品分開的標章／貼字：間隔 ≥ 4 px 才能塗（Fable 42 10/11 22:3x，mx 標章間隔 4 px 塗白）

# 這張單沒給數字的，先用合成圖定（out/工單7-報告.md 第 2 節），本機再用真圖校
BG_RING = 0.01             # 背景色取四邊外圈（短邊 1%，至少 2 px）的中位數
BG_TOL = 14                # 跟背景色差（RGB 最大通道）≤ 14 算背景：照建卡 prodfilm.py to_alpha 預設 tol=14（工單 #8；原 24 比建卡寬，
                           # 本機 124 張正例有 7 張白／淺色商品身體被當背景挖掉）。JPEG 雜訊 < 10；RGB 241 以上的白身體仍會被當背景 ⇒ 白色商品走 cutout
BG_UNIFORM_MIN = 0.60      # 外圈 ≥ 60% 是背景色才算單色背景；不然量不準 ⇒ 要人眼
WHITE_FRAC = 0.50          # 商品框裡 ≥ 50% 的像素跟背景同色 ⇒ 白色／透明商品，分不準 ⇒ 要人眼（走 cutout-product.py）
FAINT_DIFF_MAX = 110       # 框外小塊平均跟背景差 ≤ 110 ＝淡色（半透明浮水印：alpha 0.2 黑字差 ≈ 51、0.4 ≈ 102；實心字 ≥ 200）
WM_MIN_MARKS = 6           # 淡色小塊 ≥ 6 塊才算浮水印嫌疑（少數幾點是陰影、雜點）
FAINT_PAINT_MIN = 0.0005   # 不到浮水印塊數的淡色塊 ≥ 圖面積 0.05% 才給「塗背景色」建議（更小的當雜點）
WM_SIDES_MIN = 3           # 淡色小塊出現在商品上下左右 ≥ 3 邊 ⇒ 整張重複、多半也蓋到商品 ⇒ 要人眼；少於 3 邊 ⇒ 只在背景、可塗掉
CHAR_H = (6, 0.12)         # 字狀小塊高：6 px ～ 圖高 12%
LINE_MIN_CHARS = 3         # 一列至少 3 個字狀塊
RECT_MIN = 0.90            # 正面（盒）：商品面積 ／ 外框面積 ≥ 0.90
EDGE_DEV_MAX = 8.0         # 正面（盒）：輪廓擬合多邊形的邊（長度 ≥ 周長 4%）偏離水平／垂直 ≤ 8°
EDGE_MIN_FRAC = 0.04
SYM_MIN = 0.92             # 正面（瓶罐）：左右鏡射 IoU ≥ 0.92；斜角「不收」也要左右不對稱（合成斜角盒 0.904）
FACE_SPAN = 0.60           # 第二面：一條直／橫強邊貫穿商品 ≥ 60%
FACE_DIFF = 15             # 第二面：強邊兩側亮度差 ≥ 15（灰階）
FACE_FRAC = (0.06, 0.45)   # 第二面：窄的那面占寬或高 6%–45%（京工盒頂 16%、波蜜側面 30%）
FACE_MARGIN = 0.04         # 量第二面時商品外框往內縮 4%（外輪廓本身不算）
REPEAT_MIN = 0.75          # 重複圖樣：商品框裡平移後的邊緣圖相關 ≥ 0.75 ⇒ 疑似多包疊放／拼接（合成：單一商品最高 0.594、重複多包最低 0.991）
BAR_DIFF = 60              # 商品裡的橫條：跟商品主色差 > 60
BAR_ROW_FRAC = 0.85        # 一行裡 ≥ 85% 是橫條色
BAR_H = (0.02, 0.25)       # 橫條高占商品高 2%–25%，而且不碰商品上下 5%
PROT_FRAC, PROT_MIN_PX = 0.03, 6   # 跨輪廓色條：商品中段一條橫帶左右兩邊都比本體寬 ≥ 3%（至少 6 px）
PROT_MAX_H = 0.30          # 那條橫帶高 ≤ 商品高 30%，而且不碰商品上下 5%（瓶蓋比瓶身寬那種在最上面，不算）
SHEET_MAX_W = 3800         # --sheet：整張寬 ≤ 3800（工單）
SHEET_MAX_BYTES = 3 * 1024 * 1024   # --sheet：檔案 ≤ 3 MB（工單）
SHEET_CELL = 360
SHEET_PER_PAGE = 100       # --sheet 一張最多幾格（10 欄 × 10 列，高約 4,300 px）；超過自動分張、檔名加 -1、-2…（工單 #8：JPEG 高度上限 65,535）

EXTS = (".jpg", ".jpeg", ".png", ".webp")
ORDER = {"收": 0, "要人眼": 1, "不收": 2}


# ── 建卡同一定義（照 參考-建卡量法.py 的 measure_alpha 抄，⛔ 改） ─────────────────────────────────────────────
def card_measure(fg):
    """fg：0/1 uint8。回傳 size／solidity／n_objects／fg_ratio／bbox_n，跟建卡 measure_alpha 一樣；前景 < 400 丟 ValueError。"""
    fg = fg.astype(np.uint8)
    H, W = fg.shape
    if fg.sum() < MIN_FG_PX:
        raise ValueError("去背之後幾乎沒有東西")
    pts = np.argwhere(fg > 0)[:, ::-1].astype(np.int32)
    solid = float(fg.sum()) / max(1.0, float(cv2.contourArea(cv2.convexHull(pts))))
    n, _, st, _ = cv2.connectedComponentsWithStats(fg, 8)
    nobj = sum(1 for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= OBJ_MIN_FRAC * fg.sum())
    ys, xs = np.where(fg > 0)
    return {"size": [int(W), int(H)], "solidity": round(solid, 3), "n_objects": int(nobj), "fg_ratio": round(float(fg.mean()), 3),
            "bbox_n": [round(float(xs.min()) / W, 4), round(float(ys.min()) / H, 4), round(float(xs.max() + 1) / W, 4), round(float(ys.max() + 1) / H, 4)]}


# ── 讀圖、分出商品 ─────────────────────────────────────────────────────────────
def load(path):
    """回傳 (RGB uint8（透明處合成白底）, alpha 或 None)。alpha 全不透明的 PNG 當沒有 alpha。"""
    im = Image.open(path)
    im.load()
    has_a = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    rgba = np.asarray(im.convert("RGBA"))
    a = rgba[..., 3]
    if not has_a or not (a <= ALPHA_THR).any():
        return np.ascontiguousarray(rgba[..., :3]), None
    w = a[..., None].astype(np.float32) / 255.0
    rgb = (rgba[..., :3].astype(np.float32) * w + 255.0 * (1 - w)).round().astype(np.uint8)
    return rgb, a


def background(rgb):
    """四邊外圈的中位數當背景色；回傳 (bg, 外圈是背景色的比例)。"""
    H, W = rgb.shape[:2]
    b = max(2, int(round(min(H, W) * BG_RING)))
    ring = np.concatenate([rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3), rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3)])
    bg = np.median(ring, axis=0)
    uni = float((np.abs(ring.astype(np.int16) - bg.astype(np.int16)).max(1) <= BG_TOL).mean())
    return bg, uni


def split_fg(rgb, bg):
    """背景色容許差內、而且從四邊連得到的＝背景（flood fill）；其他＝前景。回傳 (fg bool, 跟背景差 d, near bool)。"""
    d = np.abs(rgb.astype(np.int16) - bg.astype(np.int16)).max(2)
    near = (d <= BG_TOL).astype(np.uint8)
    _, lab = cv2.connectedComponents(near, connectivity=4)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    edge = edge[edge > 0]
    return ~np.isin(lab, edge), d, near.astype(bool)


def bbox_of(mask):
    ys, xs = np.nonzero(mask)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def box_gap(a, b):
    dx = max(0, b[0] - a[2], a[0] - b[2])
    dy = max(0, b[1] - a[3], a[1] - b[3])
    return math.hypot(dx, dy)


def group_lines(chars):
    """字狀小塊（x0,y0,x1,y1）分成一列一列：高度重疊 ≥ 一半、水平間隔 ≤ 1.5 個字高。回傳 [[index…]…]。"""
    n = len(chars)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    order = sorted(range(n), key=lambda i: chars[i][0])
    for ii, i in enumerate(order):
        a = chars[i]
        ha = a[3] - a[1]
        for j in order[ii + 1:]:
            b = chars[j]
            hb = b[3] - b[1]
            hm = max(ha, hb)
            if b[0] - a[2] > 1.5 * hm:
                break
            ov = min(a[3], b[3]) - max(a[1], b[1])
            if ov >= 0.5 * min(ha, hb):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


# ── 正面、重複、橫條 ───────────────────────────────────────────────────────────
def front_features(mask, gray, box):
    """①輪廓擬合多邊形最斜的邊、②貫穿的第二面、③左右對稱、外框填滿度。"""
    x0, y0, x1, y1 = box
    m = mask[y0:y1, x0:x1].astype(np.uint8)
    w, h = x1 - x0, y1 - y0
    k = max(3, int(min(w, h) * 0.01) | 1)
    mc = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    cs, _ = cv2.findContours(mc, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    per = cv2.arcLength(c, True)
    poly = cv2.approxPolyDP(c, 0.01 * per, True).reshape(-1, 2)
    dev = 0.0
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        L = float(np.hypot(*(q - p)))
        if L < EDGE_MIN_FRAC * per:
            continue
        ang = abs(math.degrees(math.atan2(float(q[1] - p[1]), float(q[0] - p[0])))) % 90.0
        dev = max(dev, min(ang, 90.0 - ang))
    rect = float(mc.sum()) / float(w * h)
    sym = float(np.logical_and(mc, mc[:, ::-1]).sum()) / max(1.0, float(np.logical_or(mc, mc[:, ::-1]).sum()))
    face = second_face(mc, gray[y0:y1, x0:x1].astype(np.float32))
    return {"rect_ratio": round(rect, 3), "max_edge_dev": round(dev, 1), "symmetry": round(sym, 3), "second_face": face,
            "polygon": len(poly)}


def second_face(m, g):
    """商品裡一條貫穿的直／橫強邊，把商品分成亮度不同的兩面。回傳最強的那條或 None。"""
    h, w = m.shape
    mg = int(round(min(h, w) * FACE_MARGIN))
    inner = cv2.erode(m, np.ones((2 * mg + 1, 2 * mg + 1), np.uint8)) if mg > 0 else m
    gx = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3))
    gy = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    best = None
    win = max(4, int(min(h, w) * 0.03))
    for direction, grad, n, other in (("直", gx, w, h), ("橫", gy, h, w)):
        for pos in range(int(n * FACE_FRAC[0]), int(n * (1 - FACE_FRAC[0])) + 1):
            frac = min(pos, n - pos) / float(n)
            if not (FACE_FRAC[0] <= frac <= FACE_FRAC[1]):
                continue
            if direction == "直":
                inside = inner[:, pos] > 0
                strong = grad[:, max(0, pos - 1):pos + 2].max(1) > 4 * FACE_DIFF
                a = g[:, max(0, pos - win):max(1, pos - 2)]
                b = g[:, pos + 2:pos + win]
                ina = inner[:, max(0, pos - win):max(1, pos - 2)] > 0
                inb = inner[:, pos + 2:pos + win] > 0
            else:
                inside = inner[pos, :] > 0
                strong = grad[max(0, pos - 1):pos + 2, :].max(0) > 4 * FACE_DIFF
                a = g[max(0, pos - win):max(1, pos - 2), :]
                b = g[pos + 2:pos + win, :]
                ina = inner[max(0, pos - win):max(1, pos - 2), :] > 0
                inb = inner[pos + 2:pos + win, :] > 0
            span_all = inside.sum()
            if span_all < 0.5 * other:
                continue
            span = float((strong & inside).sum()) / float(other)
            if span < FACE_SPAN or not ina.any() or not inb.any():
                continue
            diff = abs(float(a[ina].mean()) - float(b[inb].mean()))
            if diff < FACE_DIFF:
                continue
            cand = {"dir": direction, "pos": int(pos), "narrow_frac": round(frac, 3), "span": round(span, 3), "diff": round(diff, 1)}
            if best is None or span * diff > best["span"] * best["diff"]:
                best = cand
    return best


def repeat_score(gray, mask, box):
    """商品框裡的邊緣圖左右（或上下）平移 L 後的相關係數最大值（L＝框寬／高的 1/8～1/2）。同一包重複排 ⇒ 接近 1。"""
    x0, y0, x1, y1 = box
    g = gray[y0:y1, x0:x1].astype(np.float32)
    m = mask[y0:y1, x0:x1]
    s = 240.0 / max(g.shape)
    if s < 1:
        g = cv2.resize(g, (max(8, int(g.shape[1] * s)), max(8, int(g.shape[0] * s))), interpolation=cv2.INTER_AREA)
        m = cv2.resize(m.astype(np.uint8), (g.shape[1], g.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    e = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    e[~m] = 0
    best = (0.0, None, 0)
    for axis in (1, 0):
        n = e.shape[axis]
        for L in range(max(4, n // 8), n // 2 + 1):
            a = e[:, :-L] if axis == 1 else e[:-L, :]
            b = e[:, L:] if axis == 1 else e[L:, :]
            a, b = a.ravel() - a.mean(), b.ravel() - b.mean()
            den = float(np.sqrt((a * a).sum() * (b * b).sum()))
            if den <= 1e-6:
                continue
            r = float((a * b).sum()) / den
            if r > best[0]:
                best = (r, "橫" if axis == 1 else "直", int(round(L / s)) if s < 1 else L)
    return {"score": round(best[0], 3), "dir": best[1], "lag": best[2]}


def protrusion_band(rgb, mask, box):
    """商品中段一條橫帶，左右兩邊都比商品本體寬（伸出去）⇒ 疑似跨輪廓的色條（色條跟商品連成一塊，字狀塊抓不到時用這條）。"""
    x0, y0, x1, y1 = box
    m = mask[y0:y1, x0:x1]
    h, w = m.shape
    has = m.any(1)
    if has.sum() < 10:
        return None
    left = np.where(has, m.argmax(1), -1)
    right = np.where(has, w - 1 - m[:, ::-1].argmax(1), -1)
    bl, br = float(np.median(left[has])), float(np.median(right[has]))
    P = max(PROT_MIN_PX, PROT_FRAC * w)
    prot = has & (left < bl - P) & (right > br + P)
    lo, hi = int(h * 0.05), int(h * 0.95)
    r = lo
    while r < hi:
        if not prot[r]:
            r += 1
            continue
        s = r
        while r < hi and prot[r]:
            r += 1
        if r - s <= PROT_MAX_H * h and s > lo and r < hi:
            c = rgb[y0 + s:y0 + r, x0:x1].astype(np.int16)
            mm = m[s:r].copy()
            mm[:, int(bl):int(br) + 1] = False   # 只看伸出去的兩端
            if not mm.any():
                continue
            band = c[mm]
            txt = float((np.abs(band - np.median(band, axis=0)).max(1) > BAR_DIFF).mean())
            return {"box": [x0, y0 + s, x1, y0 + r], "protrude_px": int(min(bl - left[s:r].max(), right[s:r].min() - br)),
                    "text_frac": round(txt, 3)}
    return None


def inside_bar(rgb, mask, box):
    """商品裡一條橫條（顏色跟商品主色不同、橫跨 ≥85% 寬、上下有商品）＋裡面有字 ⇒ 疑似後加字條（或包裝本身印的）。"""
    x0, y0, x1, y1 = box
    h = y1 - y0
    m = mask[y0:y1, x0:x1]
    c = rgb[y0:y1, x0:x1].astype(np.int16)
    if m.sum() == 0:
        return None
    main = np.median(c[m], axis=0)
    far = (np.abs(c - main).max(2) > BAR_DIFF) & m
    cnt = m.sum(1)
    rows = (cnt > 0) & (far.sum(1) >= BAR_ROW_FRAC * np.maximum(cnt, 1))
    lo, hi = int(h * 0.05), int(h * 0.95)
    r = lo
    while r < hi:
        if not rows[r]:
            r += 1
            continue
        s = r
        while r < hi and rows[r]:
            r += 1
        bh = r - s
        if BAR_H[0] * h <= bh <= BAR_H[1] * h:
            band = c[s:r][m[s:r]]
            bc = np.median(band, axis=0)
            txt = float((np.abs(band - bc).max(1) > BAR_DIFF).mean())
            if 0.02 <= txt <= 0.6:
                return {"box": [x0, y0 + s, x1, y0 + r], "height_frac": round(bh / float(h), 3), "text_frac": round(txt, 3)}
    return None


# ── 一張圖 ────────────────────────────────────────────────────────────────────
class Result:
    def __init__(self, path):
        self.path, self.reasons, self.suggest, self.m = path, [], [], {}
        self.delegated = []   # 交給視覺模型的問題（沒接 ⇒ 要人眼）

    def add(self, level, code, text):
        self.reasons.append({"level": level, "code": code, "text": text})

    @property
    def verdict(self):
        lv = [r["level"] for r in self.reasons]
        return "不收" if "不收" in lv else ("要人眼" if "要人眼" in lv else "收")

    def as_dict(self):
        return {"file": self.path, "verdict": self.verdict, "reasons": self.reasons, "suggestions": self.suggest, "measure": self.m,
                "judge": getattr(self, "judge", None)}


def screen(path):
    r = Result(path)
    try:
        rgb, alpha = load(path)
    except Exception as e:   # noqa: BLE001 — 讀不了的檔也要列出來
        r.add("不收", "read", "讀不了這張圖：%s" % e)
        return r
    H, W = rgb.shape[:2]
    r.m["image_size"] = [W, H]
    r.m["source"] = "alpha" if alpha is not None else "背景估計"
    if alpha is not None:
        fg = alpha > ALPHA_THR
        d = np.where(fg, 255, 0).astype(np.int16)
        near = ~fg
    else:
        bg, uni = background(rgb)
        r.m["background"] = [int(v) for v in bg]
        r.m["background_uniform"] = round(uni, 3)
        if uni < BG_UNIFORM_MIN:
            r.add("要人眼", "bg", "背景不是單色（四邊只有 %.0f%% 是同一色），商品分不準" % (uni * 100))
        fg, d, near = split_fg(rgb, bg)
    try:
        r.m["card_raw"] = card_measure(fg)   # 建卡同一定義、整張前景（沒塗之前）
    except ValueError:
        r.add("要人眼", "nofg", "分不出商品（前景 < %d px）：白色／透明商品先跑 cutout-product.py，或背景太花" % MIN_FG_PX)
        return r
    total = int(fg.sum())
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg.astype(np.uint8), 8)
    area = st[:, cv2.CC_STAT_AREA]
    meand = np.bincount(lab.ravel(), weights=d.ravel().astype(np.float64), minlength=n) / np.maximum(area, 1)
    objs = [i for i in range(1, n) if area[i] >= OBJ_MIN_FRAC * total]
    if not objs:
        objs = [int(np.argmax(area[1:]) + 1)]
    pbox = [int(st[objs, 0].min()), int(st[objs, 1].min()), int((st[objs, 0] + st[objs, 2]).max()), int((st[objs, 1] + st[objs, 3]).max())]

    def cbox(i):
        return [int(st[i, 0]), int(st[i, 1]), int(st[i, 0] + st[i, 2]), int(st[i, 1] + st[i, 3])]

    def inside(b):
        return b[0] >= pbox[0] and b[1] >= pbox[1] and b[2] <= pbox[2] and b[3] <= pbox[3]
    small = [i for i in range(1, n) if i not in objs and area[i] >= 12]
    faint = [i for i in small if alpha is None and meand[i] <= FAINT_DIFF_MAX and not inside(cbox(i))]
    strong = [i for i in small if i not in faint]
    chars = [i for i in strong if CHAR_H[0] <= st[i, 3] <= CHAR_H[1] * H]
    lines = [[chars[k] for k in g] for g in group_lines([cbox(i) for i in chars]) if len(g) >= LINE_MIN_CHARS]
    in_line = {i for ln in lines for i in ln}

    # 跨輪廓的字（一列字，一部分在商品框外、一部分在框裡）⇒ 要人眼（工單 #8 從不收降下來）
    crossing, cross_chars, cross_info, outside_lines, inner_lines = [], set(), [], [], []
    for ln in lines:
        bs = [cbox(i) for i in ln]
        lb = [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]
        cx = [(b[0] + b[2]) / 2.0 for b in bs]
        cy = (lb[1] + lb[3]) / 2.0
        n_in = sum(1 for x in cx if pbox[0] <= x <= pbox[2])
        n_out = len(cx) - n_in
        if pbox[1] <= cy <= pbox[3] and n_in and n_out:
            crossing.append(lb)
            cross_chars.update(ln)
            cross_info.append((len(ln), n_in, n_out, max(0, pbox[0] - lb[0], lb[2] - pbox[2]), lb[3] - lb[1]))
        elif n_in == 0 or not (pbox[1] <= cy <= pbox[3]):
            outside_lines.append((lb, ln))
        else:
            inner_lines.append(lb)
    paint_src = [(lb, ln, "貼字") for lb, ln in outside_lines]
    paint_src += [(cbox(i), [i], "標章") for i in strong if i not in in_line and not inside(cbox(i))]

    # 商品本身（物件＋框裡的小塊；跨輪廓字也算進去：塗不掉）
    keep = np.zeros(n, bool)
    keep[objs] = True
    for i in strong:
        if inside(cbox(i)) or i in cross_chars:
            keep[i] = True
    prod = keep[lab]
    r.m["product_box"] = bbox_of(prod)
    pb = r.m["product_box"]
    pw, ph = pb[2] - pb[0], pb[3] - pb[1]
    r.m.update(width=pw, height=ph, long_side=max(pw, ph))
    pm = card_measure(prod)
    r.m.update(solidity=pm["solidity"], n_objects=pm["n_objects"], fg_ratio=pm["fg_ratio"])
    r.m["touches_edge"] = [s for s, v in (("左", pb[0] <= 0), ("上", pb[1] <= 0), ("右", pb[2] >= W), ("下", pb[3] >= H)) if v]

    # 標章／貼字（跟商品分開）：間隔 ≥ 4 px 才塗
    dist = cv2.distanceTransform((~prod).astype(np.uint8), cv2.DIST_L2, 5)
    r.m["paint"] = []
    for b, comps, kind in paint_src:
        pix = np.isin(lab[b[1]:b[3], b[0]:b[2]], comps)
        gap = int(math.floor(float(dist[b[1]:b[3], b[0]:b[2]][pix].min()))) - 1
        if gap >= BADGE_GAP_MIN:
            e = min(3, (gap - 1) // 2)
            pbx = [max(0, b[0] - e), max(0, b[1] - e), min(W, b[2] + e), min(H, b[3] + e)]
            if prod[pbx[1]:pbx[3], pbx[0]:pbx[2]].any():
                pbx = b
            r.m["paint"].append({"kind": kind, "box": pbx, "gap": gap})
            r.suggest.append("塗背景色 x %d–%d、y %d–%d（%s，離商品 %d px）後可建卡" % (pbx[0], pbx[2], pbx[1], pbx[3], kind, gap))
        else:
            r.m["paint"].append({"kind": kind, "box": b, "gap": gap, "too_close": True})
            r.add("要人眼", "near-mark", "%s離商品只有 %d px（< %d），塗不乾淨" % (kind, max(gap, 0), BADGE_GAP_MIN))

    # ── 判 ──
    if crossing:
        r.m["crossing_text"] = crossing
        r.add("要人眼", "cross-text", "疑似貼字條跨過商品輪廓：%s" % "；".join(
            "一列 %d 個字狀塊、%d 個在商品框裡、%d 個在框外，伸出商品框 %d px、字高 %d px" % x for x in cross_info))
    if not crossing:
        pr = protrusion_band(rgb, prod, pb)
        if pr:
            r.m["protrusion"] = pr
            band_h = pr["box"][3] - pr["box"][1]
            nums = "左右都比商品本體寬 %d px、橫帶高 %d px（商品高 %.0f%%）、伸出段字狀像素 %.0f%%" % (
                pr["protrude_px"], band_h, band_h * 100.0 / max(1, ph), pr["text_frac"] * 100)
            if pr["text_frac"] >= 0.02:   # 工單 #8：瓶肩、袋腰也會這樣 ⇒ 不直接不收
                r.add("要人眼", "cross-bar", "疑似跨輪廓貼字條（也可能是瓶肩、袋腰、封口）：" + nums)
            else:
                r.add("要人眼", "cross-bar?", "商品中段一條橫帶伸出商品本體（像跨輪廓的條，沒看到字；也可能是瓶肩、袋腰）：" + nums)
    if inner_lines:
        r.m["inner_text"] = inner_lines
        r.delegated.append(("added_text", "商品裡有跟背景連通的字塊（可能是後加字條）"))
    L, Hh = r.m["long_side"], ph
    if L < LONG_MIN:
        r.add("不收", "long<700", "商品長邊 %d < %d（⛔ 例外）" % (L, LONG_MIN))
    elif L < LONG_OK:
        r.add("要人眼", "long700-999", "商品長邊 %d（%d–%d：大字包裝才收）" % (L, LONG_MIN, LONG_OK - 1))
    if Hh < HEIGHT_MIN:
        if pw / float(max(Hh, 1)) >= WIDE_RATIO:
            r.add("要人眼", "wide", "商品高 %d < %d，但寬高比 %.2f ≥ %.1f（寬包，放大倍數另算）" % (Hh, HEIGHT_MIN, pw / float(Hh), WIDE_RATIO))
        else:
            r.add("不收", "h<600", "商品高 %d < %d（成片放大上限 %.2f）" % (Hh, HEIGHT_MIN, FINAL_SCALE_MAX))
    r.m["film_height_max"] = int(Hh * FINAL_SCALE_MAX)
    if pm["n_objects"] != 1:
        r.add("不收", "n_obj", "%d 個東西（建卡要剛好 1 個；連通塊 ≥ 前景 %d%%）%s" % (
            pm["n_objects"], int(OBJ_MIN_FRAC * 100), "：貼字條把商品切開了" if crossing and pm["n_objects"] > 1 else ""))
    if pm["solidity"] < SOLIDITY_HALO:
        r.add("不收", "solid<.75", "實心度 %.3f < %.2f" % (pm["solidity"], SOLIDITY_HALO))
    elif pm["solidity"] < SOLIDITY_MIN:
        r.add("要人眼", "solid.75-.88", "實心度 %.3f（%.2f–%.2f：袋形凹走建卡 halo_flood，白色／透明先 cutout-product.py）" % (
            pm["solidity"], SOLIDITY_HALO, SOLIDITY_MIN))
    if alpha is None:
        wf = float((near & prod).sum()) / max(1, int(prod.sum()))
        r.m["white_frac"] = round(wf, 3)
        if wf >= WHITE_FRAC:
            r.add("要人眼", "white", "商品 %.0f%% 跟背景同色（白色／透明商品），量不準：先跑 cutout-product.py" % (wf * 100))
            r.suggest.append("白色商品：先跑 cutout-product.py 去背，再用 RGBA 重篩")
        sides = set()
        for i in faint:
            b = cbox(i)
            cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
            if cx < pb[0]:
                sides.add("左")
            if cx > pb[2]:
                sides.add("右")
            if cy < pb[1]:
                sides.add("上")
            if cy > pb[3]:
                sides.add("下")
        r.m["watermark"] = {"faint_marks": len(faint), "sides": sorted(sides)}
        if faint and len(faint) < WM_MIN_MARKS:   # 不到浮水印的塊數：背景淡色塊（陰影、雜點），能塗就給塗的框
            for i in faint:
                b, fm = cbox(i), lab == i
                gap = int(math.floor(float(dist[fm].min()))) - 1
                if area[i] >= FAINT_PAINT_MIN * H * W and gap >= BADGE_GAP_MIN:
                    r.m["paint"].append({"kind": "背景淡色塊", "box": b, "gap": gap})
                    r.suggest.append("塗背景色 x %d–%d、y %d–%d（背景淡色塊，離商品 %d px）" % (b[0], b[2], b[1], b[3], gap))
        if len(faint) >= WM_MIN_MARKS:
            if len(sides) >= WM_SIDES_MIN:
                r.m["watermark"]["suspect"] = "整張"
                r.add("要人眼", "wm", "浮水印嫌疑：淡色字樣 %d 塊、分布在商品%s %d 邊（整張重複，多半也蓋到商品）" % (len(faint), "".join(sorted(sides)), len(sides)))
            else:
                fm = np.isin(lab, faint)
                b = bbox_of(fm)
                gap = int(math.floor(float(dist[fm].min()))) - 1
                r.m["watermark"]["suspect"] = "只在背景"
                if gap >= BADGE_GAP_MIN:
                    r.m["paint"].append({"kind": "浮水印", "box": b, "gap": gap})
                    r.suggest.append("塗背景色 x %d–%d、y %d–%d（浮水印只在背景，離商品 %d px）" % (b[0], b[2], b[1], b[3], gap))
                else:
                    r.add("要人眼", "wm-near", "浮水印離商品只有 %d px，塗不乾淨" % max(gap, 0))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ff = front_features(prod, gray, pb)
    r.m["front"] = ff
    slant = ff["max_edge_dev"] > EDGE_DEV_MAX
    clear = ((not slant and ff["rect_ratio"] >= RECT_MIN) or ff["symmetry"] >= SYM_MIN) and ff["second_face"] is None
    if slant and ff["second_face"] and ff["symmetry"] < SYM_MIN:   # 左右對稱的（瓶罐肩膀＋標籤邊）不直接不收，交模型／人
        sf = ff["second_face"]
        r.add("不收", "slant", "斜角嫌疑：輪廓有斜邊（偏 %.0f°）＋商品裡有一條%s向強邊分出第二面（窄面占 %.0f%%、亮度差 %.0f）" % (
            ff["max_edge_dev"], sf["dir"], sf["narrow_frac"] * 100, sf["diff"]))
    elif not clear:
        why = []
        if slant:
            why.append("輪廓有斜邊（偏 %.0f°）" % ff["max_edge_dev"])
        if ff["second_face"]:
            why.append("有一條%s向強邊分出亮度不同的兩面（窄面占 %.0f%%）" % (ff["second_face"]["dir"], ff["second_face"]["narrow_frac"] * 100))
        if not why:
            why.append("輪廓不是正立矩形（填滿 %.2f）、左右也不對稱（%.2f）" % (ff["rect_ratio"], ff["symmetry"]))
        r.delegated.append(("front_view", "正面判不準：" + "、".join(why)))
    rep = repeat_score(gray, prod, pb)
    r.m["repeat"] = rep
    if rep["score"] >= REPEAT_MIN:
        r.add("要人眼", "repeat", "重複圖樣：商品框裡%s向每 %d px 重複（相關 %.2f）⇒ 疑似多包疊放／拼接" % (rep["dir"], rep["lag"], rep["score"]))
    bar = inside_bar(rgb, prod, pb)
    if bar:
        r.m["inner_bar"] = bar
        r.delegated.append(("added_text", "商品裡有一條橫條帶字（占高 %.0f%%），分不出是後加字條還是包裝印的" % (bar["height_frac"] * 100)))
    if r.m["touches_edge"]:
        r.add("備註", "edge", "商品碰到圖片%s邊（只備註，不扣分）" % "、".join(r.m["touches_edge"]))
    return r


# ── 視覺模型介面（只留介面；預設不連） ─────────────────────────────────────────
QUESTIONS = {
    "single_product": "畫面裡是不是只有一個商品（不是組合圖、不是盒＋瓶、不是好幾包分開擺）？",
    "front_view": "商品是不是正面平視（看不到頂面、側面）？",
    "added_text": "商品上有沒有後加的字條、標章、浮水印（不是包裝本身印的）？",
    "multi_pack": "是不是多包合成（好幾包疊在一起或拼起來）？",
}
BAD_ANSWER = {"single_product": False, "front_view": False, "added_text": True, "multi_pack": True}


class Judge:
    """ask(image_path, product_box, questions) -> dict。回傳 {"status": "ok", "answers": {鍵: bool}} 或 {"status": 其他, …}。"""

    def ask(self, image_path, product_box, questions):
        raise NotImplementedError


class NullJudge(Judge):
    def ask(self, image_path, product_box, questions):
        return {"status": "not_connected"}


class HttpJudge(Judge):
    """OpenAI 相容 /v1/chat/completions（本機 llama.cpp server 那類）。圖用 base64 data URL；模型要回 JSON。"""

    def __init__(self, url, model, timeout=120.0, max_side=1024):
        u = url.rstrip("/")
        self.url = u if u.endswith("/chat/completions") else u + ("/chat/completions" if u.endswith("/v1") else "/v1/chat/completions")
        self.model, self.timeout, self.max_side = model, timeout, max_side

    def payload(self, image_path, product_box, questions):
        im = Image.open(image_path).convert("RGB")
        s = self.max_side / float(max(im.size))
        if s < 1:
            im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        ask = "\n".join("- %s：%s" % (k, q) for k, q in questions.items())
        text = ("這是一張賣場商品圖（%d×%d），程式量到商品框 %s（左、上、右、下）。請只看圖回答，回一個 JSON 物件，鍵如下、值只能 true／false：\n%s\n"
                "另外可以加一個 \"note\" 字串。不確定就照比較嚴的答（例如看不清楚是不是正面就答 false）。" % (
                    Image.open(image_path).size + (product_box, ask)))
        return {"model": self.model, "temperature": 0, "messages": [
            {"role": "system", "content": "你是電商真品照的審圖員，只回 JSON。"},
            {"role": "user", "content": [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": url}}]}]}

    def ask(self, image_path, product_box, questions):
        import urllib.request   # 只有接模型時才用；預設 NullJudge 不會走到這裡
        try:
            body = json.dumps(self.payload(image_path, product_box, questions)).encode("utf-8")
            req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
            s, e = content.find("{"), content.rfind("}")
            ans = json.loads(content[s:e + 1])
            out = {k: ans[k] for k in questions if isinstance(ans.get(k), bool)}
            return {"status": "ok", "answers": out, "note": str(ans.get("note", ""))[:300], "missing": [k for k in questions if k not in out]}
        except Exception as e:   # noqa: BLE001 — 模型掛了不能讓初篩掛掉；當作沒接
            return {"status": "error", "error": "%s: %s" % (type(e).__name__, e)}


def apply_judge(r, judge):
    """模型只能從嚴：可以把「收」改成「要人眼」，⛔ 讓任何一條變鬆。交給模型的問題：沒接／出錯 ⇒ 要人眼；
    模型說沒問題也一樣要人眼（模型只能加嚴，不能替人放行；回答記在 judge 給人參考）。"""
    if r.verdict == "不收":
        r.judge = {"status": "skipped", "why": "程式已判不收"}
    else:
        r.judge = judge.ask(r.path, r.m.get("product_box"), QUESTIONS)
    for key, why in r.delegated:
        r.add("要人眼", "judge:" + key, why + ("（視覺模型沒接）" if r.judge.get("status") != "ok" else "（模型答案只參考，交人判）"))
    if r.judge.get("status") == "ok":
        for k, bad in BAD_ANSWER.items():
            if r.judge["answers"].get(k) is bad:
                r.add("要人眼", "model:" + k, "模型：%s ⇒ %s" % (QUESTIONS[k], "否" if bad is False else "是"))
    return r


# ── 輸出 ──────────────────────────────────────────────────────────────────────
def collect(inputs):
    files = []
    for p in inputs:
        if os.path.isdir(p):
            files += sorted(os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(EXTS))
        elif os.path.isfile(p):
            files.append(p)
    return files


def sort_results(rs):
    return sorted(rs, key=lambda r: (ORDER[r.verdict], -r.m.get("long_side", 0), r.path))


def write_md(rs, path):
    lines = ["# 真品照初篩", "", "| # | 檔 | 結論 | 商品框（寬×高） | 長邊 | 實心度 | 物件數 | 原因 | 建議 |", "|---|---|---|---|---|---|---|---|---|"]
    for k, r in enumerate(rs, 1):
        m = r.m
        why = "；".join("【%s】%s" % (x["level"], x["text"]) for x in r.reasons) or "—"
        lines.append("| %d | %s | **%s** | %s | %s | %s | %s | %s | %s |" % (
            k, os.path.basename(r.path), r.verdict, ("%d×%d" % (m["width"], m["height"])) if "width" in m else "—", m.get("long_side", "—"),
            m.get("solidity", "—"), m.get("n_objects", "—"), why.replace("|", "｜"), "；".join(r.suggest).replace("|", "｜") or "—"))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


LABEL = {"收": ("OK", (40, 160, 40)), "要人眼": ("CHECK", (230, 140, 0)), "不收": ("REJECT", (210, 40, 40))}


def write_sheet(rs, path):
    """驗圖：每張縮圖畫商品框（綠）、要塗的框（藍）、跨輪廓字（紅）、結論字。每張寬 ≤ 3800、檔案 ≤ 3 MB；
    超過 SHEET_PER_PAGE 格就分張，檔名加 -1、-2…（只有一張時檔名不變）。回傳 [(檔名, (寬, 高), bytes)…]。"""
    per = max(1, int(SHEET_PER_PAGE))
    pages = [rs[i:i + per] for i in range(0, len(rs), per)] or [[]]
    root, ext = os.path.splitext(path)
    out = []
    for n, page in enumerate(pages, 1):
        p = path if len(pages) == 1 else "%s-%d%s" % (root, n, ext or ".jpg")
        size, nbytes = _sheet_page(page, (n - 1) * per, p)
        out.append((p, size, nbytes))
    return out


def _sheet_page(rs, start, path):
    cell, cap = SHEET_CELL, 64
    cols = max(1, min(max(len(rs), 1), SHEET_MAX_W // (cell + 8)))
    rows = max(1, (len(rs) + cols - 1) // cols)
    sheet = np.full((rows * (cell + cap + 8) + 8, cols * (cell + 8) + 8, 3), 245, np.uint8)
    for j, r in enumerate(rs):
        k = start + j
        x, y = 8 + (j % cols) * (cell + 8), 8 + (j // cols) * (cell + cap + 8)
        try:
            img, _ = load(r.path)
        except Exception:   # noqa: BLE001
            img = np.full((cell, cell, 3), 200, np.uint8)
        s = cell / float(max(img.shape[:2]))
        th = cv2.resize(img, (max(1, int(img.shape[1] * s)), max(1, int(img.shape[0] * s))), interpolation=cv2.INTER_AREA).copy()

        def rect(b, color, t=2):
            cv2.rectangle(th, (int(b[0] * s), int(b[1] * s)), (int(b[2] * s) - 1, int(b[3] * s) - 1), color, t)
        if "product_box" in r.m:
            rect(r.m["product_box"], (0, 170, 0), 2)
        for p in r.m.get("paint", []):
            rect(p["box"], (30, 90, 230) if not p.get("too_close") else (230, 140, 0), 2)
        for b in r.m.get("crossing_text", []):
            rect(b, (220, 30, 30), 2)
        sheet[y:y + th.shape[0], x:x + th.shape[1]] = th
        lab, col = LABEL[r.verdict]
        cv2.putText(sheet, "%d %s" % (k + 1, lab), (x + 2, y + cell + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2, cv2.LINE_AA)
        codes = ",".join(c["code"].split(":")[-1] for c in r.reasons if c["level"] != "備註")[:44]
        cv2.putText(sheet, codes or "-", (x + 2, y + cell + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1, cv2.LINE_AA)
    im = Image.fromarray(sheet)
    if im.width > SHEET_MAX_W:
        im = im.resize((SHEET_MAX_W, int(im.height * SHEET_MAX_W / float(im.width))), Image.LANCZOS)
    for q in (88, 80, 70, 60, 50):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q)
        if buf.tell() <= SHEET_MAX_BYTES:
            break
    while buf.tell() > SHEET_MAX_BYTES:
        im = im.resize((int(im.width * 0.85), int(im.height * 0.85)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=60)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return im.size, len(buf.getvalue())


def main(argv=None):
    ap = argparse.ArgumentParser(description="真品照初篩：收／要人眼／不收")
    ap.add_argument("inputs", nargs="+", help="圖或資料夾")
    ap.add_argument("--json")
    ap.add_argument("--md")
    ap.add_argument("--sheet")
    ap.add_argument("--judge", choices=("none", "http"), default="none")
    ap.add_argument("--judge-url", help="OpenAI 相容伺服器，例：http://127.0.0.1:8080（會補 /v1/chat/completions）")
    ap.add_argument("--judge-model", default="local")
    ap.add_argument("--judge-timeout", type=float, default=120.0)
    a = ap.parse_args(argv)
    if a.judge == "http" and not a.judge_url:
        ap.error("--judge http 要給 --judge-url")
    files = collect(a.inputs)
    if not files:
        print("✗ 沒有圖（吃 %s）" % "、".join(EXTS))
        return 2
    judge = HttpJudge(a.judge_url, a.judge_model, a.judge_timeout) if a.judge == "http" else NullJudge()
    rs = sort_results([apply_judge(screen(f), judge) for f in files])
    for k, r in enumerate(rs, 1):
        m = r.m
        print("%2d. %-4s %s｜%s｜%s" % (k, r.verdict, os.path.basename(r.path),
              ("商品 %d×%d、實心度 %s、%s 個" % (m["width"], m["height"], m["solidity"], m["n_objects"])) if "width" in m else "—",
              "；".join(x["text"] for x in r.reasons if x["level"] != "備註") or "全部過"))
        for s in r.suggest:
            print("      建議：" + s)
    cnt = {v: sum(1 for r in rs if r.verdict == v) for v in ORDER}
    print("共 %d 張：收 %d、要人眼 %d、不收 %d" % (len(rs), cnt["收"], cnt["要人眼"], cnt["不收"]))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump([r.as_dict() for r in rs], f, ensure_ascii=False, indent=1)
    if a.md:
        write_md(rs, a.md)
    if a.sheet:
        for p, size, nbytes in write_sheet(rs, a.sheet):
            print("驗圖：%s（%d×%d、%.2f MB）" % (p, size[0], size[1], nbytes / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
