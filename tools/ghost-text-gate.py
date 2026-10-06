#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ghost-text-gate.py — 貼回真品標籤之後，商品別面（盒頂、側面）還有模型畫的假字 ⇒ 擋下（工單 #4-B）。

為什麼：10/6 味王咖哩第 4 鏡，正面標籤貼回真品了，盒頂卻還有模型畫的倒字（王：「上方的字變雙重的」）。
  貼回只換正面那一塊，別面的假字要另外抓。

用法：
  python tools/ghost-text-gate.py --after 後.jpg --before 前.jpg [--out 標記圖.jpg] [--product-box x,y,w,h]
  python tools/ghost-text-gate.py --selftest
回傳：0＝PASS、1＝FAIL（框外有字）、2＝讀檔錯誤／selftest 缺樣本（驗收沒跑）。

做法（不用 OCR、不連網、不用模型權重）：
  ① label 框＝`|後−前|` 的最大差異區塊（gatelib.label_box，膨脹幾個像素）。
  ② 搜尋範圍＝label 框往上 SEARCH_UP、左右各 SEARCH_SIDE（或 --product-box），扣掉 label 框本身。
  ③ 在範圍內找「字」：
     - 筆畫圖＝黑帽（深字）、白帽（淺字）分開做，核大小跟 label 框高度成比例；
     - 二值化後的連通塊，留「字大小」的（高度、寬高比、填滿率都在範圍內）；
     - 高度相近、上下對齊、左右間距小的塊串成一列；一列 ≥ LINE_MIN_CHARS 個塊才算一行字；
     - 那一列的邊緣方向要夠分散（字有橫豎撇捺；木紋、條紋只有一個方向）。
  ④ 有任何一行字 ⇒ FAIL，標記圖上畫紅框。
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

# ── 門檻（怎麼定的寫在旁邊；用樣本校準的結果見 out/工單4-報告.md）────────────────────
SEARCH_UP = 0.60          # 工單：label 框往上 60%（盒頂、瓶肩）
SEARCH_SIDE = 0.25        # 工單：左右各 25%（盒子側面）
SEARCH_DOWN = 0.0         # 下面通常是手或桌面，不找
EXCLUDE_PAD = 0.03        # label 框再往外多扣 3%（框邊貼合的反鋸齒、陰影）
STROKE_K = 0.045          # 筆畫核＝label 框高 × 4.5%（大概是一個中等字的字高）；夾在 5–31 px
STROKE_THR = 28           # 筆畫圖 > 28 灰階才算筆畫（JPEG 雜訊、柔和陰影多在 15 以下）
CHAR_H = (0.018, 0.20)    # 字高相對 label 框高：1.8%–20%（太小是雜點、太大是商品輪廓）
CHAR_MIN_PX = 6           # 字高至少 6 px
CHAR_ASPECT = (0.12, 3.5) # 寬/高（含「一」這種扁字會被切掉：寧可少抓一個字，靠一整列判）
CHAR_FILL = (0.12, 0.85)  # 連通塊面積 / 外框面積：筆畫不會是實心塊，也不會只剩細線
LINE_GAP = 1.6            # 同一列相鄰兩字的水平間距 ≤ 字高 × 1.6
LINE_DY = 0.55            # 中心上下差 ≤ 字高 × 0.55（容許透視造成的微斜）
LINE_HRATIO = 2.0         # 相鄰兩字高度比 ≤ 2
LINE_MIN_CHARS = 3        # 一列至少 3 個字狀塊
ORIENT_MIN = 0.55         # 邊緣方向熵（8 格、正規化到 0–1）：字通常 > 0.7；單向條紋 < 0.4


def stroke_maps(gray, k):
    """深字用黑帽、淺字用白帽，分開回傳（合在一起的話，深字之間的淺色字縫會被白帽當筆畫，整列黏成一塊）。"""
    se = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    return {"dark": cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, se), "light": cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, se)}


def orientation_entropy(gray):
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    if mag.sum() <= 1e-6:
        return 0.0
    ang = (np.arctan2(gy, gx) % math.pi)   # 0–π：方向不分正反
    hist, _ = np.histogram(ang, bins=8, range=(0, math.pi), weights=mag)
    p = hist / hist.sum()
    p = p[p > 0]
    return float(-(p * np.log(p)).sum() / math.log(8))


def find_text_lines(gray, region, exclude, label_h):
    """在 region（扣掉 exclude）找一列一列的字 → [dict(box, n, entropy, contrast)]。"""
    rx, ry, rw, rh = region
    if rw < 10 or rh < 10:
        return [], None
    sub = gray[ry:ry + rh, rx:rx + rw]
    k = int(np.clip(round(label_h * STROKE_K), 5, 31)) | 1
    ex, ey, ew, eh = exclude
    x0, y0 = max(0, ex - rx), max(0, ey - ry)
    hmin, hmax = max(CHAR_MIN_PX, CHAR_H[0] * label_h), CHAR_H[1] * label_h
    lines, nchars = [], 0
    for polarity, sm in stroke_maps(sub, k).items():
        binm = (sm > STROKE_THR).astype(np.uint8)
        binm[y0:max(0, ey + eh - ry), x0:max(0, ex + ew - rx)] = 0
        n, lab, st, _ = cv2.connectedComponentsWithStats(binm, 8)
        chars = []
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if not (hmin <= h <= hmax):
                continue
            if not (CHAR_ASPECT[0] <= w / h <= CHAR_ASPECT[1]):
                continue
            if not (CHAR_FILL[0] <= a / float(w * h) <= CHAR_FILL[1]):
                continue
            chars.append((x, y, w, h, float(sm[lab == i].mean())))
        nchars += len(chars)
        lines += [dict(l, polarity=polarity) for l in _group_lines(chars, sub, rx, ry)]
    return _dedupe(lines), dict(kernel=k, chars=nchars)


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw, ih = max(0, min(ax + aw, bx + bw) - max(ax, bx)), max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    return inter / float(aw * ah + bw * bh - inter) if inter else 0.0


def _dedupe(lines):
    """深字的字縫在白帽圖裡也會成列 ⇒ 兩種極性重疊 > 50% 的列只留塊數多的那列。"""
    keep = []
    for l in sorted(lines, key=lambda l: -l["n"]):
        if all(_iou(l["box"], k["box"]) <= 0.5 for k in keep):
            keep.append(l)
    return keep


def _group_lines(chars, sub, rx, ry):
    """字狀塊串成列：貪婪地把右邊最近、對齊、高度相近的塊接上。"""
    chars.sort(key=lambda c: c[0])
    used, lines = [False] * len(chars), []
    for i in range(len(chars)):
        if used[i]:
            continue
        line, used[i] = [chars[i]], True
        while True:
            x, y, w, h, _ = line[-1]
            cy, best, bj = y + h / 2, None, -1
            for j in range(len(chars)):
                if used[j]:
                    continue
                X, Y, W_, H_, _ = chars[j]
                gap = X - (x + w)
                if gap < -0.3 * h or gap > LINE_GAP * max(h, H_):
                    continue
                if abs((Y + H_ / 2) - cy) > LINE_DY * max(h, H_):
                    continue
                if max(h, H_) / max(1, min(h, H_)) > LINE_HRATIO:
                    continue
                if best is None or gap < best:
                    best, bj = gap, j
            if bj < 0:
                break
            used[bj] = True
            line.append(chars[bj])
        if len(line) >= LINE_MIN_CHARS:
            lx0, ly0 = min(c[0] for c in line), min(c[1] for c in line)
            lx1, ly1 = max(c[0] + c[2] for c in line), max(c[1] + c[3] for c in line)
            ent = orientation_entropy(sub[ly0:ly1, lx0:lx1].astype(np.float32))
            lines.append(dict(box=(int(lx0 + rx), int(ly0 + ry), int(lx1 - lx0), int(ly1 - ly0)), n=len(line), entropy=ent,
                              contrast=float(np.mean([c[4] for c in line])), text_like=ent >= ORIENT_MIN))
    return lines


def check(after_path, before_path, out_path=None, product_box=None, quiet=False):
    after, before = gatelib.imread(after_path), gatelib.imread(before_path)
    lbox, _ = gatelib.label_box(after, before)
    if product_box:
        region = gatelib.clip_box(product_box, after.shape)
    else:
        region = gatelib.expand_box(lbox, after.shape, up=SEARCH_UP, down=SEARCH_DOWN, left=SEARCH_SIDE, right=SEARCH_SIDE)
    exclude = gatelib.expand_box(lbox, after.shape, up=EXCLUDE_PAD, down=EXCLUDE_PAD, left=EXCLUDE_PAD, right=EXCLUDE_PAD)
    gray = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)
    lines, info = find_text_lines(gray, region, exclude, lbox[3])
    hits = [l for l in lines if l["text_like"]]
    verdict = "FAIL" if hits else "PASS"
    if not quiet:
        print("%s  label 框=%s  搜尋範圍=%s  筆畫核=%d  字狀塊=%d  成列=%d  判定字=%d"
              % (os.path.basename(after_path), lbox, region, info["kernel"] if info else 0, info["chars"] if info else 0, len(lines), len(hits)))
        for l in lines:
            print("   %s 列 %s（%s字）：%d 個塊、方向熵 %.2f、筆畫對比 %.0f"
                  % ("🔴" if l["text_like"] else "·", l["box"], "深" if l["polarity"] == "dark" else "淺", l["n"], l["entropy"], l["contrast"]))
        print("  ⇒ %s" % ("🔴 FAIL：label 框外有字（盒頂／側面假字）" if hits else "✅ PASS"))
    if out_path:
        vis = after.copy()
        gatelib.draw_box(vis, region, (0, 220, 255), 2, "search")
        gatelib.draw_box(vis, lbox, (0, 200, 0), 3, "label")
        for l in lines:
            gatelib.draw_box(vis, l["box"], (0, 0, 255) if l["text_like"] else (160, 160, 160), 3 if l["text_like"] else 1,
                             "TEXT?" if l["text_like"] else None)
        gatelib.imwrite(out_path, vis, 88)
    return verdict, dict(label=lbox, region=region, lines=lines)


# ── 合成資料（樣本缺時的邏輯自測；不能取代樣本驗收）──────────────────────────────
def _synthetic(tmp):
    rng = np.random.default_rng(7)
    W, H = 540, 960

    def scene():
        y = np.linspace(170, 120, H)[:, None]
        img = np.repeat(np.repeat(y, W, 1)[:, :, None], 3, 2) + rng.normal(0, 3, (H, W, 3))
        img[700:] = img[700:] * 0.8 + np.array([40, 60, 90]) * 0.2   # 桌面
        return img.clip(0, 255).astype(np.uint8)

    def box(img, top_text):
        fx0, fy0, fx1, fy1 = 170, 380, 370, 690
        cv2.rectangle(img, (fx0, fy0), (fx1, fy1), (40, 90, 200), -1)                              # 正面
        top = np.array([[fx0, fy0], [fx1, fy0], [fx1 + 40, fy0 - 70], [fx0 + 40, fy0 - 70]], np.int32)
        cv2.fillPoly(img, [top], (70, 130, 230))                                                   # 盒頂
        if top_text:
            t = np.zeros((40, 190, 3), np.uint8)
            t[:] = (70, 130, 230)
            cv2.putText(t, "CURRY BEEF", (6, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2, cv2.LINE_AA)
            t = cv2.rotate(t, cv2.ROTATE_180)                                                       # 倒過來的假字
            img[fy0 - 58:fy0 - 18, fx0 + 25:fx0 + 215] = t
        return img

    def model_front(img):   # 模型畫的亂字（貼回之前）
        for k in range(5):
            cv2.putText(img, "XQ%dZ" % k, (190, 450 + k * 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (230, 230, 230), 2)
        return img

    def real_label(img, small_top_text):
        lab = np.full((310, 200, 3), 245, np.uint8)
        cv2.putText(lab, "REAL", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (30, 30, 160), 4, cv2.LINE_AA)
        cv2.putText(lab, "LABEL", (25, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (30, 30, 160), 4, cv2.LINE_AA)
        if small_top_text:   # 像一匙靈：真品標籤頂端本來就有小字＋虛線
            cv2.putText(lab, "pour into bottle", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 40, 40), 1, cv2.LINE_AA)
            for x in range(10, 190, 14):
                cv2.line(lab, (x, 40), (x + 7, 40), (40, 40, 40), 2)
        img[380:690, 170:370] = lab
        return img

    cases = {}
    for name, top_text, small in (("fail_top_text", True, False), ("pass_clean", False, False), ("pass_label_smalltext", False, True)):
        before = model_front(box(scene(), top_text))
        after = real_label(before.copy(), small)
        pa, pb = os.path.join(tmp, name + "_after.jpg"), os.path.join(tmp, name + "_before.jpg")
        gatelib.imwrite(pa, after, 92)
        gatelib.imwrite(pb, before, 92)
        cases[name] = (pa, pb)
    return cases


def selftest(out_dir=None):
    ok = True
    cases = [("ww_shot4_fail.jpg", "ww_shot4_before_paste.jpg", "FAIL"),
             ("kw_shot1_pass.jpg", "kw_shot1_before_paste.jpg", "PASS"),
             ("ax_shot2_pass.jpg", "ax_shot2_before_paste.jpg", "PASS")]
    paths = [gatelib.fixture("ghost", c) for a, b, _ in cases for c in (a, b)]
    miss = gatelib.missing(paths)
    out_dir = out_dir or os.path.join(gatelib.ROOT, "out", "工單4")
    print("== 樣本驗收（工單 #4-B）")
    if miss:
        print("  ⚠️ 缺樣本，驗收沒跑：" + "、".join(miss))
    else:
        for a, b, want in cases:
            got, _ = check(gatelib.fixture("ghost", a), gatelib.fixture("ghost", b),
                           os.path.join(out_dir, "ghost_" + a.replace(".jpg", "_marked.jpg")))
            good = got == want
            ok &= good
            print("  %s %s：要 %s、得 %s\n" % ("✅" if good else "❌", a, want, got))
    print("== 合成資料自測（盒頂倒字／乾淨盒頂／標籤頂端自帶小字；只驗邏輯，不能取代樣本）")
    with tempfile.TemporaryDirectory() as tmp:
        for name, (pa, pb) in _synthetic(tmp).items():
            want = "FAIL" if name.startswith("fail") else "PASS"
            got, _ = check(pa, pb)
            good = got == want
            ok &= good
            print("  %s 合成 %s：要 %s、得 %s\n" % ("✅" if good else "❌", name, want, got))
    if miss:
        print("結果：合成自測%s；樣本驗收未跑（缺 %d 個檔）⇒ exit 2" % ("通過" if ok else "失敗", len(miss)))
        return 2
    print("結果：%s（標記圖在 %s）" % ("全部通過" if ok else "有沒過的", os.path.relpath(out_dir, gatelib.ROOT)))
    return 0 if ok else 1


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="貼回標籤框外的假字擋門")
    ap.add_argument("--after", help="貼回之後的格")
    ap.add_argument("--before", help="貼回之前的格（同尺寸）")
    ap.add_argument("--out", help="標記圖（綠＝label 框、黃＝搜尋範圍、紅＝判定為字）")
    ap.add_argument("--product-box", help="自己給搜尋範圍 x,y,w,h（不給就用 label 框往上 60%%、左右 25%%）")
    ap.add_argument("--selftest", action="store_true", help="跑樣本驗收（fixtures/ghost）")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not (a.after and a.before):
        ap.error("要給 --after 和 --before，或 --selftest")
    try:
        verdict, _ = check(a.after, a.before, a.out, gatelib.parse_box(a.product_box) if a.product_box else None)
    except (OSError, ValueError) as e:
        print("❌ %s" % e, file=sys.stderr)
        return 2
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
