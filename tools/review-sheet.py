#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review-sheet.py — 純商品片人眼重驗圖：每鏡一欄＝商品 1:1 特寫（上下多留 150px）＋整格 50%（工單 #4-C）。

為什麼：王退件的「浮空」「站邊緣會掉」「盒頂假字」都在商品底部跟頂部，整格縮圖看不出來 ⇒ 商品要 1:1 看，
  底下多留 150px 才看得到接觸影子跟桌緣。一張圖看完一支片。

用法：
  python tools/review-sheet.py --frames 鏡1.jpg … 鏡5.jpg --labels 前1.jpg … 前5.jpg --out sheet.jpg
  python tools/review-sheet.py --selftest
  --labels＝每鏡貼回之前的格（跟 ghost-text-gate 的 --before 一樣），用 `|後−前|` 找 label 框；
  某一鏡沒有貼回前的圖就給 `-`，那一鏡改用 --fallback-box（預設畫面中間 50%）。
回傳：0＝寫出且符合尺寸限制、1＝寫出但超過限制、2＝讀檔錯誤／selftest 缺樣本（驗收沒跑）。

限制（工單）：整張寬 ≤ MAX_W、檔案 ≤ MAX_BYTES。超過時先降 JPEG 品質，再縮整格縮圖；商品特寫一律保持 1:1。
"""
import argparse
import os
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gatelib  # noqa: E402

MAX_W = 3800                 # 工單
MAX_BYTES = 3 * 1024 * 1024  # 工單：≤ 3 MB
CROP_UP, CROP_DOWN, CROP_SIDE = 0.60, 0.25, 0.25   # 工單：商品框＝label 框往上 60%、下 25%、左右 25%
CROP_MARGIN_Y = 150          # 工單：商品特寫上下各多留 150px
WHOLE_SCALE = 0.5            # 工單：整格縮 50%
GAP = 16                     # 欄與欄、塊與塊之間的空白
HEADER_H = 44
BG = (40, 40, 40)
QUALITIES = (90, 82, 74, 66, 58)
WHOLE_FALLBACK_SCALES = (0.4, 0.33)


def product_crop_box(frame, before, fallback_box=None):
    """label 框（`|後−前|`）往外擴成商品框，再上下各加 150px。回傳 (crop_box, label_box or None, note)。"""
    lbox, note = None, ""
    if before is not None:
        try:
            lbox, _ = gatelib.label_box(frame, before)
        except ValueError as e:
            note = "找不到 label 框（%s），改用備用框" % e
    if lbox is None:
        H, W = frame.shape[:2]
        lbox = fallback_box or (W // 4, H // 4, W // 2, H // 2)
        note = note or "沒有貼回前的圖，改用備用框"
        used_label = None
    else:
        used_label = lbox
    pbox = gatelib.expand_box(lbox, frame.shape, up=CROP_UP, down=CROP_DOWN, left=CROP_SIDE, right=CROP_SIDE)
    x, y, w, h = pbox
    return gatelib.clip_box((x, y - CROP_MARGIN_Y, w, h + 2 * CROP_MARGIN_Y), frame.shape), used_label, note


def build_sheet(frames, befores, names, whole_scale=WHOLE_SCALE, fallback_box=None):
    cols, notes = [], []
    for i, (f, b) in enumerate(zip(frames, befores)):
        cbox, lbox, note = product_crop_box(f, b, fallback_box)
        if note:
            notes.append("鏡%d：%s" % (i + 1, note))
        x, y, w, h = cbox
        crop = f[y:y + h, x:x + w]
        whole = cv2.resize(f, None, fx=whole_scale, fy=whole_scale, interpolation=cv2.INTER_AREA)
        cv2.rectangle(whole, (int(x * whole_scale), int(y * whole_scale)), (int((x + w) * whole_scale), int((y + h) * whole_scale)), (0, 220, 255), 2)
        cw = max(crop.shape[1], whole.shape[1])
        col = np.full((HEADER_H + crop.shape[0] + GAP + whole.shape[0], cw, 3), BG, np.uint8)
        title = "shot %d  %s" % (i + 1, names[i][:40])
        cv2.putText(col, title, (6, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (235, 235, 235), 2, cv2.LINE_AA)
        if lbox is None:
            cv2.putText(col, "NO LABEL BOX", (cw - 210, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        col[HEADER_H:HEADER_H + crop.shape[0], :crop.shape[1]] = crop
        oy = HEADER_H + crop.shape[0] + GAP
        col[oy:oy + whole.shape[0], :whole.shape[1]] = whole
        cols.append(col)
    # 排版：一鏡一欄，超過 MAX_W 就換行
    rows, cur, cur_w = [], [], 0
    for c in cols:
        need = c.shape[1] + (GAP if cur else 0)
        if cur and cur_w + need > MAX_W - 2 * GAP:
            rows.append(cur)
            cur, cur_w = [], 0
            need = c.shape[1]
        cur.append(c)
        cur_w += need
    if cur:
        rows.append(cur)
    row_imgs = []
    for r in rows:
        h = max(c.shape[0] for c in r)
        w = sum(c.shape[1] for c in r) + GAP * (len(r) - 1)
        img = np.full((h, w, 3), BG, np.uint8)
        ox = 0
        for c in r:
            img[:c.shape[0], ox:ox + c.shape[1]] = c
            ox += c.shape[1] + GAP
        row_imgs.append(img)
    W = max(r.shape[1] for r in row_imgs) + 2 * GAP
    H = sum(r.shape[0] for r in row_imgs) + GAP * (len(row_imgs) + 1)
    sheet = np.full((H, W, 3), BG, np.uint8)
    oy = GAP
    for r in row_imgs:
        sheet[oy:oy + r.shape[0], GAP:GAP + r.shape[1]] = r
        oy += r.shape[0] + GAP
    return sheet, notes


def make(frame_paths, label_paths, out_path, fallback_box=None, quiet=False):
    if label_paths and len(label_paths) != len(frame_paths):
        raise ValueError("--labels 要跟 --frames 一樣多張（沒有的鏡給 -）：%d vs %d" % (len(label_paths), len(frame_paths)))
    frames = [gatelib.imread(p) for p in frame_paths]
    befores = []
    for k, p in enumerate(label_paths or ["-"] * len(frame_paths)):
        b = None if p == "-" else gatelib.imread(p)
        if b is not None and b.shape != frames[k].shape:
            raise ValueError("鏡%d 貼回前後尺寸不同：%s vs %s" % (k + 1, b.shape, frames[k].shape))
        befores.append(b)
    names = [os.path.basename(p) for p in frame_paths]
    for scale in (WHOLE_SCALE,) + WHOLE_FALLBACK_SCALES:
        sheet, notes = build_sheet(frames, befores, names, scale, fallback_box)
        for q in QUALITIES:
            ok, buf = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, q])
            if buf.size <= MAX_BYTES:
                break
        if buf.size <= MAX_BYTES and sheet.shape[1] <= MAX_W:
            break
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    buf.tofile(out_path)
    fits = buf.size <= MAX_BYTES and sheet.shape[1] <= MAX_W
    if not quiet:
        for n in notes:
            print("  ⚠️ " + n)
        print("  %s %s：%d×%d、%.2f MB、JPEG 品質 %d、整格縮 %d%%%s"
              % ("✅" if fits else "🔴", out_path, sheet.shape[1], sheet.shape[0], buf.size / 1048576, q, round(scale * 100),
                 "" if fits else "（超過限制：寬 ≤ %d、≤ %.0f MB）" % (MAX_W, MAX_BYTES / 1048576)))
    return fits, dict(width=sheet.shape[1], height=sheet.shape[0], bytes=int(buf.size), quality=q, whole_scale=scale, notes=notes)


# ── 合成資料（樣本缺時：驗排版與 3 MB／3800 限制；不能取代樣本）────────────────────
def _synthetic(tmp):
    rng = np.random.default_rng(11)
    frames, befores = [], []
    for k in range(5):
        W, H = 1080, 1920
        base = (np.linspace(90, 200, H)[:, None, None] + rng.normal(0, 22, (H, W, 3))).clip(0, 255).astype(np.uint8)   # 雜訊大＝JPEG 大，壓檔案上限
        x0, y0 = 300 + 30 * k, 700 + 20 * k
        cv2.rectangle(base, (x0, y0), (x0 + 420, y0 + 600), (60, 90, 190), -1)
        before = base.copy()
        cv2.putText(before, "MODEL %d" % k, (x0 + 40, y0 + 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (240, 240, 240), 4)
        after = base.copy()
        after[y0 + 60:y0 + 540, x0 + 30:x0 + 390] = 245
        cv2.putText(after, "REAL %d" % k, (x0 + 60, y0 + 300), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (30, 30, 160), 5)
        pa, pb = os.path.join(tmp, "f%d.jpg" % k), os.path.join(tmp, "b%d.jpg" % k)
        gatelib.imwrite(pa, after, 95)
        gatelib.imwrite(pb, before, 95)
        frames.append(pa)
        befores.append(pb)
    befores[4] = "-"   # 第 5 鏡沒有貼回前的圖 ⇒ 走備用框
    return frames, befores


def selftest():
    ok = True
    out_dir = os.path.join(gatelib.ROOT, "out", "工單4")
    trio = [("ww_shot4_fail.jpg", "ww_shot4_before_paste.jpg"), ("kw_shot1_pass.jpg", "kw_shot1_before_paste.jpg"),
            ("ax_shot2_pass.jpg", "ax_shot2_before_paste.jpg")]
    miss = gatelib.missing([gatelib.fixture("ghost", n) for pair in trio for n in pair])
    print("== 樣本驗收（工單 #4-C：ghost/ 三組，缺的鏡用同一張重複湊滿 5 鏡）")
    if miss:
        print("  ⚠️ 缺樣本，驗收沒跑：" + "、".join(miss))
    else:
        order = [0, 1, 2, 0, 1]
        fits, info = make([gatelib.fixture("ghost", trio[i][0]) for i in order], [gatelib.fixture("ghost", trio[i][1]) for i in order],
                          os.path.join(out_dir, "review_sheet_selftest.jpg"))
        ok &= fits and not info["notes"]
    print("== 合成資料自測（5 張 1080×1920 高雜訊格，第 5 鏡沒有貼回前的圖；驗排版與尺寸限制）")
    with tempfile.TemporaryDirectory() as tmp:
        frames, befores = _synthetic(tmp)
        fits, info = make(frames, befores, os.path.join(tmp, "sheet.jpg"))
        expect_note = any("鏡5" in n for n in info["notes"])
        ok &= fits and expect_note
        print("  %s 合成：寬 %d ≤ %d、%.2f MB ≤ 3 MB、第 5 鏡有改用備用框的提示：%s"
              % ("✅" if fits and expect_note else "❌", info["width"], MAX_W, info["bytes"] / 1048576, "是" if expect_note else "否"))
    if miss:
        print("結果：合成自測%s；樣本驗收未跑（缺 %d 個檔）⇒ exit 2" % ("通過" if ok else "失敗", len(miss)))
        return 2
    print("結果：%s" % ("全部通過" if ok else "有沒過的"))
    return 0 if ok else 1


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="純商品片人眼重驗圖")
    ap.add_argument("--frames", nargs="+", help="每鏡的成片格（貼回之後）")
    ap.add_argument("--labels", nargs="+", help="每鏡貼回之前的格；沒有的鏡給 -")
    ap.add_argument("--out", default="review_sheet.jpg", help="輸出 jpg")
    ap.add_argument("--fallback-box", help="找不到 label 框時的商品框 x,y,w,h（預設畫面中間 50%%）")
    ap.add_argument("--selftest", action="store_true", help="用 fixtures/ghost 三組跑一張")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.frames:
        ap.error("要給 --frames，或 --selftest")
    try:
        fits, _ = make(a.frames, a.labels, a.out, gatelib.parse_box(a.fallback_box) if a.fallback_box else None)
    except (OSError, ValueError) as e:
        print("❌ %s" % e, file=sys.stderr)
        return 2
    return 0 if fits else 1


if __name__ == "__main__":
    sys.exit(main())
