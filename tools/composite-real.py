#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""composite-real.py — 真品去背照合成進模型畫的場景，做到「不假、不浮」（工單 #4-D：研究＋原型）。

為什麼：10/6 東尼玉米片整支換真品，王：「商品太假跟浮空」——沒有接觸陰影、照片比場景銳利、色溫不同、透視跟桌面對不上。

用法：
  python tools/composite-real.py --scene 場景.jpg --product 真品去背.png --box x,y,w,h \
      [--out 合成.jpg] [--compare 對照.jpg --fake 現行貼法.jpg] [--shadow-dir auto|left|right|down]
  python tools/composite-real.py --selftest
  --box＝場景裡模型畫的商品外框（真品會等比縮到這個高度、底邊中心對齊框的底邊中心）。
回傳：0＝合成完成且透視可以貼、1＝透視判斷「不能貼」（照樣輸出給人看）、2＝讀檔錯誤／selftest 缺樣本。

三步（照工單順序）：
  1. 接觸陰影：比較模型盒子底部左右兩側地面的亮度 ⇒ 場景影子落在哪邊；
     畫三層：貼地深線（接觸線）＋底部軟陰影（環境遮蔽）＋往影子方向拖的投影；深度跟場景原有影子一樣深。
  2. 色調／銳利度對齊：模型在場景光線下畫的那個盒子＝色彩參考 ⇒ Lab 均值／標準差部分轉移（不洗掉真品顏色）；
     銳利度用拉普拉斯能量配對，模糊上限 MAX_BLUR（字要清楚）；再補上場景的顆粒雜訊；邊緣羽化 1px。
  3. 透視判斷：GrabCut 從場景把模型盒子分割出來 ⇒ 跟真品去背輪廓比（形狀 IoU、頂邊斜角、左右鏡像哪個比較像）；
     加上「缺角在哪一組對角」判朝向（3/4 角盒子的輪廓接近對稱，只比 IoU 分不出左右）；差太多 ⇒ 回「不能貼」。
"""
import argparse
import math
import os
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gatelib  # noqa: E402

# ── 參數（怎麼定的寫在旁邊）─────────────────────────────────────────────────────
SHADOW_PROBE_W = 0.45      # 判影子方向：盒子左右各看 0.45 個盒寬的地面
SHADOW_PROBE_H = 0.12      # 只看盒底往上 12% 盒高那條帶（太高會看到牆）
SHADOW_MIN_DIFF = 0.04     # 左右亮度差 < 4% ⇒ 光從正上方／正面來，影子往下壓
SHADOW_STRENGTH = (0.25, 0.65)   # 陰影最淺／最深（乘法變暗比例）；夾住避免全黑或看不到
CONTACT_OPACITY = 0.75     # 接觸線：相對陰影強度
AO_HEIGHT = 0.06           # 底部軟陰影高度＝商品高 × 6%
CAST_LEN = 0.35            # 投影長度＝商品高 × 35%（壓扁在桌面上）
COLOR_AMOUNT = 0.6         # Lab 轉移幅度：0＝不動、1＝完全照模型盒子（字的顏色會跑掉）
LIGHT_AMOUNT = 0.8         # 亮度（L 均值）跟著場景走的幅度
MAX_BLUR = 1.0             # 高斯模糊 sigma 上限（px）：再大小字就糊
PERSP_IOU_MIN = 0.80       # 形狀 IoU 低於這個 ⇒ 面向差太多
PERSP_TOP_DEG = 10.0       # 頂邊斜角差 > 10° ⇒ 透視對不上
PERSP_MIRROR_GAIN = 0.05   # 鏡像後 IoU 高出 0.05 以上 ⇒ 朝向相反（輔助；3/4 角盒子輪廓接近對稱，常常分不出來）
PERSP_CORNER = (0.25, 0.15)  # 缺角量測：角落取 25% 寬 × 15% 高
PERSP_ASYM_MIN = 0.12      # 對角缺角差 > 0.12 才算看得出朝向（太正面的照片不判）


# ── 小工具 ────────────────────────────────────────────────────────────────────
def lap_energy(gray, mask=None):
    lap = cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F, ksize=3)
    v = lap[mask > 0] if mask is not None else lap.ravel()
    return float(np.mean(v ** 2)) if v.size else 0.0


def noise_std(gray, mask=None):
    hp = gray.astype(np.float32) - cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 1.2)
    v = hp[mask > 0] if mask is not None else hp.ravel()
    if v.size == 0:
        return 0.0
    return float(1.4826 * np.median(np.abs(v - np.median(v))))   # MAD：邊緣不會把雜訊估太大


def place_product(rgba, box, scene_shape):
    """真品去背 → 等比縮到框高、底邊中心對齊框底中心。回傳 (bgr, alpha 0–1, (x, y))。"""
    a = rgba[:, :, 3]
    ys, xs = np.where(a > 8)
    if xs.size == 0:
        raise ValueError("去背圖是全透明的")
    rgba = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    bx, by, bw, bh = box
    s = bh / float(rgba.shape[0])
    nw, nh = max(1, int(round(rgba.shape[1] * s))), max(1, int(round(rgba.shape[0] * s)))
    rgba = cv2.resize(rgba, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    x = int(round(bx + bw / 2 - nw / 2))
    y = int(round(by + bh - nh))
    H, W = scene_shape[:2]
    if x < 0 or y < 0 or x + nw > W or y + nh > H:
        raise ValueError("縮放後的真品超出場景：位置 (%d,%d) 尺寸 %dx%d" % (x, y, nw, nh))
    return rgba[:, :, :3].copy(), rgba[:, :, 3].astype(np.float32) / 255.0, (x, y)


# ── 1. 接觸陰影 ───────────────────────────────────────────────────────────────
def estimate_shadow(scene, box, forced="auto"):
    """看模型盒子底部左右的地面，哪邊暗＝影子在哪邊。回傳 (方向 -1 左／+1 右／0 下, 強度, 說明)。"""
    gray = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY).astype(np.float32)
    H, W = gray.shape
    bx, by, bw, bh = box
    y0, y1 = int(by + bh * (1 - SHADOW_PROBE_H)), min(H, int(by + bh + bh * 0.03))
    pw = int(bw * SHADOW_PROBE_W)
    near_l = gray[y0:y1, max(0, bx - pw):bx]
    near_r = gray[y0:y1, bx + bw:min(W, bx + bw + pw)]
    far_l = gray[y0:y1, max(0, bx - 3 * pw):max(0, bx - 2 * pw)]
    far_r = gray[y0:y1, min(W, bx + bw + 2 * pw):min(W, bx + bw + 3 * pw)]
    ml, mr = (float(near_l.mean()) if near_l.size else np.nan), (float(near_r.mean()) if near_r.size else np.nan)
    fars = [float(f.mean()) for f in (far_l, far_r) if f.size]
    ground = float(np.mean(fars)) if fars else float(np.nanmax([ml, mr]))   # 盒子太靠邊、看不到遠處地面 ⇒ 用比較亮那側當地面
    darkest = np.nanmin([ml, mr])
    strength = float(np.clip(1 - darkest / max(ground, 1.0), *SHADOW_STRENGTH))
    if forced != "auto":
        d = {"left": -1, "right": 1, "down": 0}[forced]
        return d, strength, "指定方向 %s" % forced
    if np.isnan(ml) or np.isnan(mr) or abs(ml - mr) / max(ground, 1.0) < SHADOW_MIN_DIFF:
        return 0, strength, "左右地面亮度差不多（左 %.0f／右 %.0f）⇒ 影子往下壓" % (ml, mr)
    d = -1 if ml < mr else 1
    return d, strength, "盒底%s側地面較暗（左 %.0f／右 %.0f、遠處地面 %.0f）⇒ 影子往%s" % ("左" if d < 0 else "右", ml, mr, ground, "左" if d < 0 else "右")


def shadow_layer(alpha, pos, scene_shape, direction, strength):
    """回傳整張場景大小的「變暗比例」圖（0–1）。"""
    H, W = scene_shape[:2]
    ph, pw = alpha.shape
    x, y = pos
    layer = np.zeros((H, W), np.float32)
    # 底部輪廓：每一欄最下面的不透明點
    cols = np.where(alpha.max(axis=0) > 0.5)[0]
    if cols.size == 0:
        return layer
    bottoms = np.array([np.where(alpha[:, c] > 0.5)[0].max() for c in cols])
    base_y = y + int(np.median(bottoms))
    # (a) 接觸線：底部輪廓那條線，粗 3px、輕微模糊
    contact = np.zeros((H, W), np.float32)
    for c, b in zip(cols, bottoms):
        cv2.line(contact, (x + int(c), y + int(b) - 1), (x + int(c), min(H - 1, y + int(b) + 2)), 1.0, 1)
    contact = cv2.GaussianBlur(contact, (0, 0), 1.5)
    # (b) 底部軟陰影：底寬的扁橢圓，往影子方向偏一點
    ao = np.zeros((H, W), np.float32)
    cx = x + (cols.min() + cols.max()) / 2 + direction * pw * 0.06
    ax_, ay_ = (cols.max() - cols.min()) * 0.56, max(3, ph * AO_HEIGHT)
    cv2.ellipse(ao, (int(cx), int(base_y)), (int(ax_), int(ay_)), 0, 0, 360, 1.0, -1)
    ao = cv2.GaussianBlur(ao, (0, 0), max(2, ph * 0.025))
    # (c) 投影：把商品輪廓壓扁貼到桌面，往影子方向斜拖
    cast = np.zeros((H, W), np.float32)
    flat_h = max(2, int(ph * CAST_LEN * 0.35))
    sil = cv2.resize(alpha, (pw, flat_h), interpolation=cv2.INTER_AREA)
    sil = sil[::-1]   # 倒過來貼在底線之下（投影從底邊往外長）
    shear = direction * ph * CAST_LEN
    M = np.float32([[1, shear / max(flat_h, 1), 0], [0, 1, 0]])
    ext = int(abs(shear)) + pw
    canvas = np.zeros((flat_h, ext + pw), np.float32)
    off = ext if direction < 0 else 0
    canvas[:, off:off + pw] = sil
    canvas = cv2.warpAffine(canvas, M, (canvas.shape[1], flat_h))
    gx0 = x - off
    gy0 = base_y - int(flat_h * 0.15)
    xs0, xs1 = max(0, gx0), min(W, gx0 + canvas.shape[1])
    ys0, ys1 = max(0, gy0), min(H, gy0 + flat_h)
    if xs1 > xs0 and ys1 > ys0:
        cast[ys0:ys1, xs0:xs1] = canvas[ys0 - gy0:ys1 - gy0, xs0 - gx0:xs1 - gx0]
    cast = cv2.GaussianBlur(cast, (0, 0), max(3, ph * 0.04)) * (0.55 if direction != 0 else 0.3)
    layer = np.maximum.reduce([contact * CONTACT_OPACITY, ao * 0.8, cast]) * strength
    return np.clip(layer, 0, 0.9)


# ── 2. 色調／銳利度 ──────────────────────────────────────────────────────────
def match_tone(prod, alpha, scene, ref_mask):
    """Lab 均值／標準差往模型盒子靠（部分）。回傳 (調整後 bgr, 說明 dict)。"""
    pm = alpha > 0.5
    lab_p = cv2.cvtColor(prod, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_s = cv2.cvtColor(scene, cv2.COLOR_BGR2LAB).astype(np.float32)
    ref = lab_s[ref_mask > 0]
    src = lab_p[pm]
    if ref.size == 0 or src.size == 0:
        return prod, {}
    out = lab_p.copy()
    info = {}
    for c, amt in ((0, LIGHT_AMOUNT), (1, COLOR_AMOUNT), (2, COLOR_AMOUNT)):
        ms, ss = float(src[:, c].mean()), float(src[:, c].std()) + 1e-6
        mr, sr = float(ref[:, c].mean()), float(ref[:, c].std()) + 1e-6
        scale = 1 + amt * (np.clip(sr / ss, 0.6, 1.4) - 1)     # 對比最多調 ±40%
        shift = amt * (mr - ms)
        out[:, :, c] = (lab_p[:, :, c] - ms) * scale + ms + shift
        info["Lab"[c]] = (ms, mr, float(out[:, :, c][pm].mean()))
    out = np.clip(out, 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_LAB2BGR), info


def match_sharpness(prod, alpha, scene, ref_mask):
    """真品比場景銳利 ⇒ 找一個 sigma（≤ MAX_BLUR）讓拉普拉斯能量接近場景。回傳 (bgr, sigma, 前, 後, 目標)。"""
    pm = (alpha > 0.9).astype(np.uint8)
    pm = cv2.erode(pm, np.ones((5, 5), np.uint8))           # 不看輪廓邊（邊緣跟背景的落差不算）
    gp = cv2.cvtColor(prod, cv2.COLOR_BGR2GRAY)
    target = lap_energy(cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY), cv2.erode(ref_mask, np.ones((5, 5), np.uint8)))
    before = lap_energy(gp, pm)
    best, best_err = 0.0, abs(math.log((before + 1) / (target + 1)))
    for s in np.arange(0.2, MAX_BLUR + 1e-6, 0.1):
        e = lap_energy(cv2.GaussianBlur(gp, (0, 0), s), pm)
        err = abs(math.log((e + 1) / (target + 1)))
        if err < best_err:
            best, best_err = float(s), err
    out = cv2.GaussianBlur(prod, (0, 0), best) if best > 0 else prod
    return out, best, before, lap_energy(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), pm), target


# ── 3. 透視判斷 ───────────────────────────────────────────────────────────────
def segment_model_box(scene, box):
    """GrabCut（只用框初始化，不用任何模型權重）把場景裡模型畫的盒子切出來。"""
    mask = np.zeros(scene.shape[:2], np.uint8)
    x, y, w, h = box
    pad = int(0.04 * max(w, h))
    rect = gatelib.clip_box((x - pad, y - pad, w + 2 * pad, h + 2 * pad), scene.shape)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(scene, mask, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    m = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        m = (lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    return m


def _norm_shape(mask, size=(128, 192)):
    ys, xs = np.where(mask > 0)
    if xs.size == 0:
        return np.zeros(size[::-1], np.uint8)
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8) * 255
    return (cv2.resize(crop, size, interpolation=cv2.INTER_AREA) > 127).astype(np.uint8)


def _iou(a, b):
    inter, union = np.logical_and(a, b).sum(), np.logical_or(a, b).sum()
    return float(inter) / union if union else 0.0


def top_edge_angle(mask):
    """外輪廓凸包上，最上面那段（夠長的）邊的斜角（度）：盒頂往哪邊傾。"""
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return 0.0
    hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
    poly = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True).reshape(-1, 2).astype(np.float32)
    w = poly[:, 0].max() - poly[:, 0].min()
    best, best_y = 0.0, 1e9
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = q[0] - p[0], q[1] - p[1]
        if abs(dx) < 0.25 * w:            # 太短或太直的邊不算頂邊
            continue
        ang = math.degrees(math.atan2(dy, dx))
        ang = (ang + 90) % 180 - 90       # 方向不分正反，落在 -90～90
        if abs(ang) > 60:
            continue
        my = (p[1] + q[1]) / 2
        if my < best_y:
            best, best_y = ang, my
    return best


def corner_asym(mask):
    """3/4 角的盒子會在對角缺兩個三角：側面在右 ⇒ 左上＋右下缺；側面在左 ⇒ 右上＋左下缺。
    回傳 (左上＋右下缺) − (右上＋左下缺)：正＝側面在右、負＝側面在左、接近 0＝正面照。"""
    h, w = mask.shape
    cw, ch = int(w * PERSP_CORNER[0]), int(h * PERSP_CORNER[1])
    empty = lambda r: 1.0 - float(r.mean())
    tl, tr = empty(mask[:ch, :cw]), empty(mask[:ch, w - cw:])
    bl, br = empty(mask[h - ch:, :cw]), empty(mask[h - ch:, w - cw:])
    return (tl + br) - (tr + bl)


def perspective_check(scene, box, alpha):
    model = segment_model_box(scene, box)
    a = _norm_shape(model)
    b = _norm_shape(alpha > 0.5)
    iou, iou_m = _iou(a, b), _iou(a, b[:, ::-1])
    ta, tb = top_edge_angle(a), top_edge_angle(b)
    sa, sb = corner_asym(a), corner_asym(b)
    reasons = []
    if abs(sa) > PERSP_ASYM_MIN and abs(sb) > PERSP_ASYM_MIN and sa * sb < 0:
        reasons.append("真品跟模型盒子朝向相反（模型側面在%s、真品側面在%s）" % ("右" if sa > 0 else "左", "右" if sb > 0 else "左"))
    elif iou_m - iou > PERSP_MIRROR_GAIN:
        reasons.append("真品跟模型盒子朝向相反（左右鏡像後更像：IoU %.2f → %.2f）" % (iou, iou_m))
    if iou < PERSP_IOU_MIN:
        reasons.append("輪廓形狀差太多（IoU %.2f < %.2f）" % (iou, PERSP_IOU_MIN))
    if abs(ta - tb) > PERSP_TOP_DEG:
        reasons.append("頂邊斜角差 %.0f°（模型 %.0f°／真品 %.0f°）> %.0f°" % (abs(ta - tb), ta, tb, PERSP_TOP_DEG))
    return (not reasons), dict(iou=iou, iou_mirror=iou_m, top_model=ta, top_product=tb, asym_model=sa, asym_product=sb,
                               reasons=reasons, model_mask=model)


# ── 合成 ──────────────────────────────────────────────────────────────────────
def composite(scene, rgba, box, shadow_dir="auto", quiet=False):
    report = {}
    ok_persp, persp = perspective_check(scene, box, rgba[:, :, 3].astype(np.float32) / 255.0 if rgba.shape[2] == 4 else None)
    report["perspective"] = persp
    prod, alpha, pos = place_product(rgba, box, scene.shape)
    x, y = pos
    ph, pw = alpha.shape
    ref_mask = persp["model_mask"].copy()
    ref_local = ref_mask[y:y + ph, x:x + pw]
    # 2. 色調／銳利度（先做，陰影最後蓋在場景上）
    prod2, tone = match_tone(prod, alpha, scene, ref_mask)
    prod3, sigma, e0, e1, et = match_sharpness(prod2, alpha, scene, ref_mask)
    sn = noise_std(cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY), ref_mask)
    pn = noise_std(cv2.cvtColor(prod3, cv2.COLOR_BGR2GRAY), (alpha > 0.9).astype(np.uint8))
    add = math.sqrt(max(0.0, sn ** 2 - pn ** 2))
    if add > 0.3:
        rng = np.random.default_rng(0)
        prod3 = np.clip(prod3.astype(np.float32) + rng.normal(0, add, prod3.shape[:2])[:, :, None], 0, 255).astype(np.uint8)
    report.update(tone=tone, blur_sigma=sigma, sharp_before=e0, sharp_after=e1, sharp_target=et, grain_added=add)
    # 1. 接觸陰影
    d, strength, why = estimate_shadow(scene, box, shadow_dir)
    report.update(shadow_dir=d, shadow_strength=strength, shadow_why=why)
    shade = shadow_layer(alpha, pos, scene.shape, d, strength)
    out = scene.astype(np.float32) * (1 - shade[:, :, None])
    # 模型畫的盒子露在真品外面的部分要蓋掉（不然會看到兩層輪廓）⇒ 用附近背景做 inpaint
    leftover = (ref_mask > 0).astype(np.uint8)
    leftover[y:y + ph, x:x + pw] &= (alpha < 0.5).astype(np.uint8)
    leftover = cv2.dilate(leftover, np.ones((5, 5), np.uint8))
    report["model_leftover_px"] = int(leftover.sum())
    if leftover.any():
        out = cv2.inpaint(np.clip(out, 0, 255).astype(np.uint8), leftover, 7, cv2.INPAINT_TELEA).astype(np.float32)
    # 邊緣羽化 1px 後貼上
    a = cv2.GaussianBlur(alpha, (0, 0), 0.7)[:, :, None]
    roi = out[y:y + ph, x:x + pw]
    out[y:y + ph, x:x + pw] = roi * (1 - a) + prod3.astype(np.float32) * a
    out = np.clip(out, 0, 255).astype(np.uint8)
    _ = ref_local
    if not quiet:
        t = report["tone"]
        print("  2. 色調：L %.0f→%.0f（場景盒 %.0f）a %.0f→%.0f（%.0f）b %.0f→%.0f（%.0f）｜銳利度 %.0f→%.0f（目標 %.0f，模糊 σ=%.1f）｜補顆粒 %.1f"
              % (t["L"][0], t["L"][2], t["L"][1], t["a"][0], t["a"][2], t["a"][1], t["b"][0], t["b"][2], t["b"][1], e0, e1, et, sigma, add)
              if t else "  2. 色調：參考區塊是空的，略過")
        print("  1. 陰影：%s；強度 %.2f" % (why, strength))
        print("  3. 透視：%s（IoU %.2f、鏡像 IoU %.2f、頂邊 模型 %.0f°／真品 %.0f°、缺角 模型 %+.2f／真品 %+.2f）"
              % ("可以貼" if ok_persp else "🔴 不能貼：" + "；".join(persp["reasons"]), persp["iou"], persp["iou_mirror"],
                 persp["top_model"], persp["top_product"], persp["asym_model"], persp["asym_product"]))
    return out, ok_persp, report


def compare_image(fake, new, box, verdict_ok, reasons):
    """並排：左＝現行貼法、右＝新合成；上排商品區 1:1（上下多 150px），下排整格 40%。"""
    x, y, w, h = gatelib.expand_box(box, new.shape, up=0.3, down=0.3, left=0.3, right=0.3)
    y0, y1 = max(0, y - 150), min(new.shape[0], y + h + 150)
    crops = [im[y0:y1, x:x + w] for im in (fake, new)]
    wholes = [cv2.resize(im, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA) for im in (fake, new)]
    colw = max(crops[0].shape[1], wholes[0].shape[1])
    col_h = 44 + crops[0].shape[0] + 12 + wholes[0].shape[0]
    sheet = np.full((col_h + (40 if not verdict_ok else 0), colw * 2 + 36, 3), 40, np.uint8)
    for k, (c, wh, title) in enumerate(zip(crops, wholes, ("current paste (fake)", "composite-real"))):
        ox = 12 + k * (colw + 12)
        cv2.putText(sheet, title, (ox, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (235, 235, 235), 2, cv2.LINE_AA)
        sheet[44:44 + c.shape[0], ox:ox + c.shape[1]] = c
        sheet[56 + c.shape[0]:56 + c.shape[0] + wh.shape[0], ox:ox + wh.shape[1]] = wh
    if not verdict_ok:
        cv2.putText(sheet, "PERSPECTIVE MISMATCH: " + ("; ".join(r.split("（")[0] for r in reasons))[:80],
                    (12, sheet.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
    return sheet


def run(scene_path, product_path, box, out_path, compare_path=None, fake_path=None, shadow_dir="auto"):
    scene = gatelib.imread(scene_path)
    rgba = gatelib.imread(product_path, alpha=True)
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("真品圖要是有透明通道的 PNG：%s" % product_path)
    out, ok, report = composite(scene, rgba, box, shadow_dir)
    gatelib.imwrite(out_path, out, 92)
    print("  ⇒ 合成圖：%s" % out_path)
    if compare_path:
        fake = gatelib.imread(fake_path) if fake_path else scene
        if fake.shape != out.shape:
            fake = cv2.resize(fake, (out.shape[1], out.shape[0]))
        gatelib.imwrite(compare_path, compare_image(fake, out, box, ok, report["perspective"]["reasons"]), 90)
        print("  ⇒ 並排對照：%s" % compare_path)
    return ok, report, out


# ── 合成資料自測（樣本缺時：驗三步的邏輯；不能取代樣本、也不能取代人眼）──────────────
def _synth_box(face_w, face_h, depth, mirrored, front_bgr, side_bgr, top_bgr, text=True):
    """畫一個 3/4 角度的盒子：正面＋側面＋頂面。回傳 BGRA。"""
    pad = 20
    W, H = face_w + depth + 2 * pad, face_h + depth // 2 + 2 * pad
    img = np.zeros((H, W, 4), np.uint8)
    fx0, fy0 = pad + (depth if mirrored else 0), pad + depth // 2
    front = np.array([[fx0, fy0], [fx0 + face_w, fy0], [fx0 + face_w, fy0 + face_h], [fx0, fy0 + face_h]])
    s = -1 if mirrored else 1
    sx = fx0 + face_w if not mirrored else fx0
    side = np.array([[sx, fy0], [sx + s * depth, fy0 - depth // 2], [sx + s * depth, fy0 + face_h - depth // 2], [sx, fy0 + face_h]])
    top = np.array([[fx0, fy0], [fx0 + face_w, fy0], [fx0 + face_w + s * depth, fy0 - depth // 2], [fx0 + s * depth, fy0 - depth // 2]])
    for poly, col in ((side, side_bgr), (top, top_bgr), (front, front_bgr)):
        cv2.fillPoly(img, [poly.astype(np.int32)], tuple(col) + (255,))
    if text:
        cv2.putText(img, "TONY", (fx0 + 20, fy0 + face_h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255, 255), 4, cv2.LINE_AA)
        cv2.putText(img, "corn flakes 500g", (fx0 + 20, fy0 + face_h // 2 + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20, 255), 1, cv2.LINE_AA)
    return img


def _synth_scene(rng):
    W, H = 720, 1080
    wall = np.linspace(185, 160, 620)[:, None]
    table = np.linspace(150, 120, H - 620)[:, None]
    g = np.vstack([np.repeat(wall, W, 1), np.repeat(table, W, 1)])
    img = np.stack([g * 0.86, g * 0.97, g * 1.08], 2)            # 暖色光（B 低、R 高）
    img[620:] *= np.array([0.75, 0.88, 1.0])                      # 木頭桌面偏橘
    img += rng.normal(0, 4, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    box_rgba = _synth_box(240, 330, 60, False, (40, 70, 200), (30, 50, 150), (60, 100, 220), text=False)
    bx, by = 230, 940 - box_rgba.shape[0]
    # 場景原有影子：光從左來 ⇒ 盒子右邊地面較暗
    sh = np.zeros(img.shape[:2], np.float32)
    cv2.ellipse(sh, (bx + box_rgba.shape[1] - 10, 935), (130, 22), 0, 0, 360, 1.0, -1)
    sh = cv2.GaussianBlur(sh, (0, 0), 12) * 0.45
    img = (img.astype(np.float32) * (1 - sh[:, :, None])).astype(np.uint8)
    a = box_rgba[:, :, 3:4].astype(np.float32) / 255
    roi = img[by:by + box_rgba.shape[0], bx:bx + box_rgba.shape[1]].astype(np.float32)
    img[by:by + box_rgba.shape[0], bx:bx + box_rgba.shape[1]] = (roi * (1 - a) + box_rgba[:, :, :3] * a).astype(np.uint8)
    img = cv2.GaussianBlur(img, (0, 0), 1.3)                     # 場景比真品照軟
    ys, xs = np.where(box_rgba[:, :, 3] > 0)
    return img, (bx + xs.min(), by + ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)


def selftest():
    ok = True
    out_dir = os.path.join(gatelib.ROOT, "out", "工單4")
    fx = [gatelib.fixture("whole", n) for n in ("tn_shot1_scene_before_paste.jpg", "tn_alpha.png", "tn_shot1_current_paste_fake.jpg")]
    miss = gatelib.missing(fx)
    print("== 樣本（工單 #4-D：東尼玉米片第 1 鏡）")
    if miss:
        print("  ⚠️ 缺樣本，沒有跑：" + "、".join(miss))
    else:
        print("  ⚠️ 樣本模式要給模型盒子的框：python tools/composite-real.py --scene … --product … --box x,y,w,h --compare …")
    print("== 合成資料自測（暖光、光從左、場景比真品軟；驗三步的方向對不對）")
    rng = np.random.default_rng(3)
    scene, box = _synth_scene(rng)
    real = _synth_box(240, 330, 60, False, (40, 70, 200), (30, 50, 150), (60, 100, 220))
    real[:, :, :3] = np.clip(real[:, :, :3].astype(np.int16) + np.array([25, 5, -15]), 0, 255).astype(np.uint8)   # 真品照偏冷
    out, persp_ok, rep = composite(scene, real, box)
    checks = []
    checks.append(("影子方向判成往右", rep["shadow_dir"] == 1))
    bx, by, bw, bh = box
    g0, g1 = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY).astype(float), cv2.cvtColor(out, cv2.COLOR_BGR2GRAY).astype(float)
    strip = (slice(by + bh - 4, by + bh + 6), slice(bx + bw // 4, bx + 3 * bw // 4))
    checks.append(("盒底接觸線變暗", g1[strip].mean() < g0[strip].mean() - 3))
    t = rep["tone"]
    checks.append(("真品的冷色往場景暖色靠（Lab b 往模型盒子移）", abs(t["b"][2] - t["b"][1]) < abs(t["b"][0] - t["b"][1])))
    checks.append(("真品被柔化但模糊 ≤ %.1f" % MAX_BLUR, 0 < rep["blur_sigma"] <= MAX_BLUR))
    checks.append(("同朝向 ⇒ 透視可以貼", persp_ok))
    mirrored = _synth_box(240, 330, 60, True, (40, 70, 200), (30, 50, 150), (60, 100, 220))
    _, persp_ok_m, rep_m = composite(scene, mirrored, box, quiet=True)
    checks.append(("朝向相反 ⇒ 透視不能貼", not persp_ok_m))
    print("  （朝向相反那張：%s）" % "；".join(rep_m["perspective"]["reasons"]))
    for name, good in checks:
        ok &= good
        print("  %s %s" % ("✅" if good else "❌", name))
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "cmp.jpg")
        gatelib.imwrite(p, compare_image(scene, out, box, persp_ok, rep["perspective"]["reasons"]), 90)
    if miss:
        print("結果：合成自測%s；東尼樣本沒有跑（缺 %d 個檔）⇒ exit 2" % ("通過" if ok else "失敗", len(miss)))
        return 2
    print("結果：合成自測%s" % ("通過" if ok else "失敗"))
    return 0 if ok else 1


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="真品去背照合成進模型場景（接觸陰影＋色調銳利度對齊＋透視判斷）")
    ap.add_argument("--scene", help="模型畫的場景（貼回之前）")
    ap.add_argument("--product", help="真品去背 PNG（要有透明通道）")
    ap.add_argument("--box", help="場景裡模型畫的商品外框 x,y,w,h")
    ap.add_argument("--out", default=os.path.join("out", "工單4", "composite.jpg"))
    ap.add_argument("--compare", help="並排對照圖輸出路徑")
    ap.add_argument("--fake", help="現行貼法的成品（並排的左邊）")
    ap.add_argument("--shadow-dir", default="auto", choices=["auto", "left", "right", "down"])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not (a.scene and a.product and a.box):
        ap.error("要給 --scene、--product、--box，或 --selftest")
    try:
        ok, _, _ = run(a.scene, a.product, gatelib.parse_box(a.box), a.out, a.compare, a.fake, a.shadow_dir)
    except (OSError, ValueError) as e:
        print("❌ %s" % e, file=sys.stderr)
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
