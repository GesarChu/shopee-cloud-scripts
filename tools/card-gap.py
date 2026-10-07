#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""card-gap.py — 片尾卡真品照離浮水印 ≥ 20 px（工單 #5-D）。

規則（寫死）：真品照外框（alpha 非零的 bbox）跟浮水印框的距離 ≥ MIN_GAP（20 px）。
  距離＝兩個框之間最近的距離（重疊＝0；斜對角用歐氏距離）；框都用「左上含、右下不含」的像素座標，
  所以 20 ＝ 中間至少空 20 行（或 20 欄）底色。
  浮水印框 WM_BOX＝brand-stamp.py 疊上去的範圍：圖示左上 (130,260)、寬 96、高 96×3300/2900≈109（FACE_CROP 2900×3300）→ 到 y 369；
  「特別蝦」x=236 y=290 字級 46×3 字＋陰影 3 → 到 x≈380、y≈350 ⇒ (130,260)–(380,370)。
  （prodfilm.py 的 WM＝(130,260,380,360) 是字幕避讓用的；圖示其實到 369，這裡取 370。）

兩個子命令：
  layout：組片前算真品照放哪（build_ph9_sample.py 的 CARD 分支呼叫）。
    原位置＝scale=CARDW:1000 等比縮（force_original_aspect_ratio=decrease）、x 置中、底貼 y=1290（overlay y='(1290-h)'）。
    原位置就夠 ⇒ changed=false，builder 照用原本的濾鏡（成片逐位元組不變）。
    不夠 ⇒ ① 先往下移（最少移多少就移多少）；真品照實體下緣不能低於 cta_y − CTA_CLEAR（CTA 紅底框彈到 110% 時頂 ≈ cta_y−72，留 ≥18 px）；
            ② 移到底還不夠 ⇒ 等比縮小（每次 1%，下緣貼住下限），縮到夠為止；縮到 SHRINK_MIN 還不夠 ⇒ exit 1（builder 停）。
    算的時候多留 LAYOUT_MARGIN（2 px）：PIL 跟 ffmpeg 的 lanczos、yuv420 色度、CRF 10 的邊緣會差一兩點，成片量才穩過 20。
    overlay 在 yuv420 上 x、y 會被截成偶數（vf_overlay normalize_xy），這裡照算。
    彈跳：builder 的 y＝鎖死位置 − 60·e^(−6t)·cos(14t)（0.9 秒內），第 0–3 格往上 60／44／24／6 px ⇒ 鎖死時夠 20 px 也會在那幾格壓到浮水印。
    所以另外給 y_min（真品照最高只能到這裡、仍 ≥ 20＋2 px）：builder 把 y 包成 max(y_min, …)，只有會壓到的那幾格被擋住，
    其他格數值不變（沒壓到的片逐位元組不變）。真品照左右已經離浮水印 ≥ 22 px 時 y_min＝null（不用擋）。
  check：量成片片尾卡那格。底色（整格中位數，要接近 0xEAF4FB 才算片尾卡）以外、浮水印框（外擴 WM_PAD）以外的像素＝前景；
    連通塊裡頂端在 CTA 區（cta_y − 80）以上的＝真品照，取它們的外接框量到 WM_BOX 的距離；< 20 ⇒ FAIL。
    有前景碰到畫面邊緣＝轉場中（上一鏡還在）或不是片尾卡 ⇒ 量不了（硬擋那格 exit 2；彈跳期那格跳過）。
    母片（沒浮水印）、蝦皮版（有浮水印：框內遮掉不算）都能量。
    --card-start 秒：硬擋量 start + 1.0 秒那格（彈跳 0.9 秒後鎖死）；彈跳期 start…start+0.9 每格另外印最小距離（只警示：
    那幾格多半在 xfade 轉場裡、底色不是片尾卡就跳過不量；builder 有 y_min 擋住時應該也 ≥ 20）。

用法：
  python tools/card-gap.py layout --real ts_alpha.png [--card-w 900] [--cta-y 1390]          → 印 JSON（builder 讀）
  python tools/card-gap.py check --video 成片.mp4 --card-start 17.0 [--out 標記.jpg] [--json 結果.json]
  python tools/card-gap.py check --image 片尾卡格.jpg [--out 標記.jpg]
  python tools/card-gap.py --selftest            （要 ffmpeg：FFMPEG_BIN 或 PATH）
退出碼：0 PASS／1 FAIL（layout：移、縮都救不回）／2 量不了（不是片尾卡、讀不到檔、找不到真品照）。
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')
import tempfile

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gatelib  # noqa: E402

OW, OH = 1080, 1920
WM_BOX = (130, 260, 380, 370)      # 浮水印框 x0,y0,x1,y1（右下不含），來源見檔頭
MIN_GAP = 20                       # 規則：真品照外框離浮水印框 ≥ 20 px
LAYOUT_MARGIN = 2                  # layout 多留的 px（見檔頭）
CARD_BG = (234, 244, 251)          # builder 片尾卡底色 0xEAF4FB（RGB）
CARD_H, CARD_BOTTOM = 1000, 1290   # builder：scale=CARDW:1000、overlay y='(1290-h)-彈跳'
CARD_SETTLE = 0.9                  # 彈跳 if(gt(t,0.9),0,…)：0.9 秒後鎖死
CTA_Y = 1390                       # builder 片尾卡 CTA：\an5\pos(540,1390)（cfg cta_y 可改）
CTA_CLEAR = 90                     # 真品照實體下緣 ≤ cta_y − 90：Box 字級 88＋框 18，100% 高 ≈131（成片 t=0.1 量 127 px@97%），110% 頂 ≈ cta_y−72
CTA_ZONE = 80                      # check：頂端在 cta_y − 80 以下的連通塊當 CTA／字幕，不算真品照
KEY_SIM = 0.08                     # builder 非 *_alpha.png 的 colorkey=0xFFFFFF:0.08:0.02
SHRINK_STEP, SHRINK_MIN = 0.01, 0.50
BG_TOL = 10                        # 跟底色差（RGB 最大通道）> 10 算前景（CRF 10 平面底色雜訊 ±2）
BG_MATCH = 8                       # 整格中位數顏色在 0xEAF4FB ±8 內才算片尾卡
WM_PAD = 4                         # 浮水印框外擴 4 px 一起遮掉（陰影、色度滲色）
MIN_AREA = 150                     # 連通塊小於 150 px 當雜點


# ── 幾何 ──────────────────────────────────────────────────────────────────────
def rect_gap(a, b):
    """兩個框 (x0,y0,x1,y1)（右下不含）之間的距離；重疊＝0。"""
    dx = max(0, b[0] - a[2], a[0] - b[2])
    dy = max(0, b[1] - a[3], a[1] - b[3])
    return float(math.hypot(dx, dy))


def floor_even(v):
    """vf_overlay 在 yuv420 上把 x、y 截成整數再清掉最低位（normalize_xy）。"""
    return int(math.floor(v)) & ~1


def ff_decrease(iw, ih, w, h):
    """ffmpeg scale=w:h:force_original_aspect_ratio=decrease 的輸出尺寸（av_rescale 四捨五入）。"""
    tw = (h * iw + ih // 2) // ih
    th = (w * ih + iw // 2) // iw
    return min(tw, w), min(th, h)


# ── layout ────────────────────────────────────────────────────────────────────
class Product:
    """真品照：照 builder 的濾鏡（scale lanczos → format=rgba →〔非 *_alpha.png〕colorkey 白 0.08）算縮放後不透明的外框。"""

    def __init__(self, path):
        self.path = path
        self.img = Image.open(path)
        self.img.load()
        self.keyed = not os.path.basename(path).endswith("_alpha.png")
        self._bb = {}

    def bbox(self, w, h):
        """縮到 w×h 後 alpha>0 的外框 (x0,y0,x1,y1)，相對真品照左上。"""
        if (w, h) not in self._bb:
            if self.keyed:   # colorkey 會蓋掉原本的 alpha，只看顏色離白多遠
                rgb = np.asarray(self.img.convert("RGB").resize((w, h), Image.LANCZOS)).astype(np.float64)
                m = np.sqrt(((rgb - 255.0) ** 2).sum(2) / (3 * 255.0 ** 2)) > KEY_SIM
            elif "A" in self.img.getbands():
                m = np.asarray(self.img.getchannel("A").resize((w, h), Image.LANCZOS)) > 0
            else:
                m = np.ones((h, w), bool)
            ys, xs = np.nonzero(m)
            if not len(xs):
                raise ValueError("真品照整張透明：%s" % self.path)
            self._bb[(w, h)] = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        return self._bb[(w, h)]

    def place(self, w, h, y, wm, need=None):
        x = floor_even((OW - w) / 2.0)
        b = self.bbox(w, h)
        box = (x + b[0], y + b[1], x + b[2], y + b[3])
        r = dict(w=w, h=h, x=x, y=y, bbox=list(box), gap=round(rect_gap(box, wm), 2))
        if need is not None:   # 彈跳最高只能到 y_min：外框頂 ≥ 浮水印框底 + √(need² − dx²)（偶數、往下取）
            dx = max(0, wm[0] - box[2], box[0] - wm[2])
            r["y_min"] = None if dx >= need else (int(math.ceil(wm[3] + math.sqrt(need * need - dx * dx) - b[1])) + 1) & ~1
        return r


def card_layout(real, card_w=900, cta_y=CTA_Y, wm=WM_BOX, gap=MIN_GAP, margin=LAYOUT_MARGIN):
    """回傳 dict：changed、w、h、x、y（彈跳鎖死後的 overlay 左上）、bbox、gap、scale、moved、how、default…；救不回 ⇒ ok=False。"""
    p = Product(real)
    iw, ih = p.img.size
    w, h = ff_decrease(iw, ih, card_w, CARD_H)
    need = gap + margin
    bottom_max = cta_y - CTA_CLEAR
    d = p.place(w, h, floor_even(CARD_BOTTOM - h), wm, need)
    res = dict(real=os.path.basename(real), size=[iw, ih], keyed=p.keyed, card_w=card_w, cta_y=cta_y, wm_box=list(wm),
               min_gap=gap, margin=margin, bottom_max=bottom_max, default=d)
    if d["gap"] >= need:
        res.update(d, ok=True, changed=False, scale=1.0, moved=0, how="原位置就夠（%.1f px）" % d["gap"])
        return res
    floor = max(bottom_max, d["bbox"][3])   # 下緣下限：CTA 上面；原本就比下限低的不再往下
    # ① 往下移：最少移多少
    b = d["bbox"]
    dx = max(0, wm[0] - b[2], b[0] - wm[2])
    dy_need = math.sqrt(max(need * need - dx * dx, 0.0))
    y = d["y"] + int(math.ceil(wm[3] + dy_need - b[1]))
    y += y & 1   # 偶數（往上取）
    m = p.place(w, h, y, wm, need)
    if m["bbox"][3] <= floor and m["gap"] >= need:
        res.update(m, ok=True, changed=True, scale=1.0, moved=y - d["y"], how="往下移 %d px（%.1f px）" % (y - d["y"], m["gap"]))
        return res
    # ② 移到底（實體下緣貼 floor）再等比縮
    k = 0
    while True:
        k += 1
        f = round(1.0 - k * SHRINK_STEP, 4)
        if f < SHRINK_MIN - 1e-9:
            break
        w2, h2 = max(1, int(round(w * f))), max(1, int(round(h * f)))
        y2 = floor_even(floor - p.bbox(w2, h2)[3])
        s = p.place(w2, h2, y2, wm, need)
        if s["gap"] >= need:
            res.update(s, ok=True, changed=True, scale=f, moved=y2 - d["y"],
                       how="往下移到底（實體下緣 %d）再縮到 %d%%（%.1f px）" % (s["bbox"][3], round(f * 100), s["gap"]))
            return res
    res.update(ok=False, changed=True, how="往下移到底、縮到 %d%% 都還不到 %d px" % (round(SHRINK_MIN * 100), need))
    return res


# ── check ─────────────────────────────────────────────────────────────────────
class NotCard(Exception):
    pass


def measure(rgb, wm=WM_BOX, cta_y=CTA_Y):
    """量一格片尾卡（RGB uint8 1080×1920）。回傳 dict：bg、bbox（真品照外框）、gap、comps；不是片尾卡丟 NotCard。"""
    if rgb.shape[:2] != (OH, OW):
        raise NotCard("尺寸 %dx%d 不是 1080x1920" % (rgb.shape[1], rgb.shape[0]))
    bg = np.median(rgb.reshape(-1, 3), axis=0)
    if np.abs(bg - np.array(CARD_BG)).max() > BG_MATCH:
        raise NotCard("底色 %s 不是片尾卡的 0xEAF4FB %s（轉場中、或不是這格）" % (bg.astype(int).tolist(), list(CARD_BG)))
    fg = (np.abs(rgb.astype(np.int16) - bg.astype(np.int16)).max(2) > BG_TOL).astype(np.uint8)
    x0, y0, x1, y1 = wm
    fg[max(0, y0 - WM_PAD):y1 + WM_PAD, max(0, x0 - WM_PAD):x1 + WM_PAD] = 0
    n, _, st, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in st[i])
        if a < MIN_AREA:
            continue
        if x == 0 or y == 0 or x + w == OW or y + h == OH:   # 片尾卡的真品照、CTA 都不會碰到畫面邊緣；碰到＝xfade 轉場裡的上一鏡
            raise NotCard("前景 %s 碰到畫面邊緣（轉場中、或不是片尾卡）" % [x, y, x + w, y + h])
        comps.append(dict(bbox=[x, y, x + w, y + h], area=a, product=y < cta_y - CTA_ZONE))
    prod = [c["bbox"] for c in comps if c["product"]]
    if not prod:
        raise NotCard("片尾卡上找不到真品照（底色以外沒有東西）")
    box = [min(b[0] for b in prod), min(b[1] for b in prod), max(b[2] for b in prod), max(b[3] for b in prod)]
    return dict(bg=bg.astype(int).tolist(), bbox=box, gap=round(rect_gap(box, wm), 2), comps=comps)


def verdict(gap, need=MIN_GAP):
    return "PASS" if gap >= need else "FAIL"


def draw(rgb, m, wm=WM_BOX, title=""):
    """標記圖（BGR）：浮水印框紅、真品照外框（過綠／不過紅）、最近距離黃線。"""
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok = m["gap"] >= MIN_GAP
    gatelib.draw_box(img, (wm[0], wm[1], wm[2] - wm[0], wm[3] - wm[1]), (0, 0, 255), 3, "WM")
    b = m["bbox"]
    gatelib.draw_box(img, (b[0], b[1], b[2] - b[0], b[3] - b[1]), (0, 180, 0) if ok else (0, 0, 255), 3, "gap %.1f px %s" % (m["gap"], "PASS" if ok else "FAIL"))
    px = min(max(wm[2], b[0]), b[2]) if not (b[2] <= wm[0]) else b[2]
    py = min(max(wm[3], b[1]), b[3])
    qx, qy = min(max(px, wm[0]), wm[2]), min(max(py, wm[1]), wm[3])
    cv2.line(img, (int(qx), int(qy)), (int(px), int(py)), (0, 220, 255), 3)
    if title:
        cv2.putText(img, title, (30, 1880), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3, cv2.LINE_AA)
    return img


def read_frames_at(path, times):
    """讀影片在指定秒數的格（RGB）。回傳 ({秒: (格號, rgb)}, fps, 總格數)；超過片長就拿最後一格。"""
    if not os.path.exists(path):
        raise FileNotFoundError("找不到影片：%s" % path)
    cap, tmp = cv2.VideoCapture(path), None
    if not cap.isOpened():   # Windows 中文路徑
        fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(path)[1] or ".mp4")
        os.close(fd)
        shutil.copyfile(path, tmp)
        cap = cv2.VideoCapture(tmp)
    try:
        if not cap.isOpened():
            raise IOError("OpenCV 打不開影片：%s" % path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        want = {t: int(round(t * fps)) for t in times}
        top, got, idx, last = max(want.values()), {}, -1, None
        while idx < top:
            ok, f = cap.read()
            if not ok:
                break
            idx += 1
            last = (idx, f)
            for t, i in want.items():
                if i == idx:
                    got[t] = (idx, cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        for t in want:
            if t not in got and last is not None:
                got[t] = (last[0], cv2.cvtColor(last[1], cv2.COLOR_BGR2RGB))
        return got, fps, idx + 1
    finally:
        cap.release()
        if tmp:
            os.remove(tmp)


def check_video(path, card_start=None, times=None, cta_y=CTA_Y, out=None, quiet=False):
    """硬擋格：card_start + 1.0（或 times）；彈跳期另外量（只警示）。回傳 (verdict, 結果 dict)。"""
    hard = list(times or [])
    bounce = []
    if card_start is not None:
        hard.append(round(card_start + CARD_SETTLE + 0.1, 3))
        bounce = [round(card_start + i / 30.0, 3) for i in range(int(CARD_SETTLE * 30) + 1)]
    if not hard:
        raise ValueError("要給 --card-start 或 --t")
    got, fps, nfr = read_frames_at(path, hard + bounce)
    res = dict(file=os.path.basename(path), fps=round(fps, 3), min_gap=MIN_GAP, wm_box=list(WM_BOX), hard=[], bounce=[])
    v = "PASS"
    for t in hard:
        i, rgb = got[t]
        try:
            m = measure(rgb, cta_y=cta_y)
        except NotCard as e:
            res["hard"].append(dict(t=t, frame=i, error=str(e)))
            res["verdict"] = "ERROR"
            if not quiet:
                print("✗ %.2f 秒（第 %d 格）量不了：%s" % (t, i, e))
            return "ERROR", res
        vv = verdict(m["gap"])
        res["hard"].append(dict(t=t, frame=i, bbox=m["bbox"], gap=m["gap"], verdict=vv))
        if vv == "FAIL":
            v = "FAIL"
        if not quiet:
            print("%s %.2f 秒（第 %d 格）真品照外框 %s 離浮水印框 %s：%.1f px（要 ≥ %d）" % ("✓" if vv == "PASS" else "✗", t, i, m["bbox"], list(WM_BOX), m["gap"], MIN_GAP))
        if out:
            gatelib.imwrite(out, draw(rgb, m, title="t=%.2f  frame %d  (%s)" % (t, i, vv)))   # 只寫 ASCII：cv2 畫不了中文
    gaps = []
    for t in bounce:
        i, rgb = got[t]
        try:
            m = measure(rgb, cta_y=cta_y)
            res["bounce"].append(dict(t=t, frame=i, gap=m["gap"], top=m["bbox"][1]))
            gaps.append(m["gap"])
        except NotCard:
            res["bounce"].append(dict(t=t, frame=i, gap=None))
    if gaps and not quiet:
        g = min(gaps)
        print("%s 彈跳期 %.2f–%.2f 秒（只警示）：量得到的 %d 格最小 %.1f px%s" % ("⚠️" if g < MIN_GAP else "·", bounce[0], bounce[-1], len(gaps), g,
              "（< %d：彈跳往上那幾格會碰到浮水印）" % MIN_GAP if g < MIN_GAP else ""))
    res["bounce_min"] = min(gaps) if gaps else None
    res["verdict"] = v
    return v, res


# ── selftest ──────────────────────────────────────────────────────────────────
WO5 = os.path.join(gatelib.ROOT, "jobs", "wo5-擋門整合-1006", "fixtures", "ts")


def _ffmpeg():
    ff = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    return ff if ff and os.path.exists(ff) else None


def _synth(real, lay, wm_fake=False):
    """PIL 合一格片尾卡（彈跳鎖死後）：底色＋縮放後的真品照貼在 (x,y)；wm_fake＝在浮水印框裡畫假浮水印（模擬蝦皮版）。"""
    bg = Image.new("RGB", (OW, OH), CARD_BG)
    p = Image.open(real).convert("RGBA").resize((lay["w"], lay["h"]), Image.LANCZOS)
    bg.paste(p, (lay["x"], lay["y"]), p)
    a = np.asarray(bg).copy()
    if wm_fake:
        x0, y0, x1, y1 = WM_BOX
        a[y0 + 5:y1 - 5, x0 + 5:x0 + 90] = (240, 120, 60)     # 圖示
        a[y0 + 32:y0 + 80, x0 + 108:x1 - 6] = (255, 255, 255)  # 字
        a[y0 + 35:y0 + 83, x0 + 111:x1 - 3] = (40, 40, 40)     # 陰影
    return a


def builder_filters(lay, card_w):
    """builder CARD 分支（patch 版）用的 scale 與 overlay y 兩段字串；lay＝None 是原版。build_ph9_sample.patch 照這個寫，改一邊要改另一邊。"""
    if lay is None or not lay["changed"]:
        sc, y = "scale=%d:1000:force_original_aspect_ratio=decrease" % card_w, "(1290-h)"
    else:
        sc, y = "scale=%d:%d" % (lay["w"], lay["h"]), "%d" % lay["y"]
    y += "-if(gt(t,0.9),0,60*exp(-6*t)*cos(14*t))"
    if lay is not None and lay.get("y_min") is not None:
        y = "max(%d,%s)" % (lay["y_min"], y)
    return sc, y


def _render_builder(ff, real, card_w, lay, out, sec=2.0):
    """用 builder CARD 分支同一串濾鏡（原版或 patch 版）組 sec 秒片尾卡，CRF 10 high（同母片）。"""
    n = int(round(sec * 30))
    sc, y = builder_filters(lay, card_w)
    fc = ("color=c=0xEAF4FB:s=1080x1920:r=30:d=%.3f[bg0];"
          "[0:v]%s:flags=lanczos,format=rgba%s[pc0];"
          "[bg0][pc0]overlay=x='(W-w)/2':y='%s':shortest=0,format=yuv420p,setsar=1,trim=end_frame=%d[v0]"
          % (n / 30.0, sc, "" if real.endswith("_alpha.png") else ",colorkey=0xFFFFFF:0.08:0.02", y, n))
    r = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", real, "-filter_complex", fc, "-map", "[v0]", "-r", "30",
                        "-c:v", "libx264", "-crf", "10", "-profile:v", "high", "-pix_fmt", "yuv420p", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 失敗：" + r.stderr[-800:])


def selftest():
    ok_all = True

    def chk(cond, msg):
        nonlocal ok_all
        print(("  ✓ " if cond else "  ✗ ") + msg)
        ok_all = ok_all and bool(cond)

    alpha = os.path.join(WO5, "ts_alpha.png")
    shot6 = os.path.join(WO5, "ts_shot6_t17.00.jpg")
    miss = gatelib.missing([alpha, shot6])
    if miss:
        print("✗ 缺樣本：%s" % miss)
        return 2
    ff = _ffmpeg()
    if not ff:
        print("✗ 找不到 ffmpeg（設 FFMPEG_BIN 或放進 PATH）：第 4 組要用 builder 同一串濾鏡真的組片尾卡")
        return 2
    outd = os.path.join(gatelib.ROOT, "out", "工單5")

    print("1) 真片 ts_shot6_t17.00.jpg（成片片尾卡第一格；母片沒浮水印）：管頂左角壓進浮水印框 ⇒ 要 FAIL")
    rgb = np.asarray(Image.open(shot6).convert("RGB"))
    m = measure(rgb)
    print("     真品照外框 %s、距離 %.1f px" % (m["bbox"], m["gap"]))
    chk(verdict(m["gap"]) == "FAIL" and m["gap"] < 5, "FAIL（外框跟浮水印框重疊）")
    chk(abs(m["bbox"][1] - 315) <= 3, "外框頂 ≈ 315（鎖死該在 290＋27＝317 附近；往上 ~2–6 px＝還在彈跳）；左緣 %d＝浮水印框外擴 4 px 遮掉的管頂左角右邊" % m["bbox"][0])
    gatelib.imwrite(os.path.join(outd, "card_ts_shot6_現況.jpg"), draw(rgb, m, title="ts_shot6_t17.00 (now)"))

    print("2) layout（ts_alpha.png 400×950、CARDW 900、CTA 1390）")
    lay = card_layout(alpha, 900, CTA_Y)
    d = lay["default"]
    print("     原位置 %dx%d @(%d,%d) 外框 %s 距離 %.1f ⇒ %s；新位置 %dx%d @(%d,%d) 外框 %s 距離 %.1f"
          % (d["w"], d["h"], d["x"], d["y"], d["bbox"], d["gap"], lay["how"], lay["w"], lay["h"], lay["x"], lay["y"], lay["bbox"], lay["gap"]))
    chk(d["gap"] == 0 and lay["ok"] and lay["changed"], "原位置重疊（0 px）⇒ 要改位置")
    chk(lay["gap"] >= MIN_GAP + LAYOUT_MARGIN, "新位置距離 ≥ %d（20＋2）" % (MIN_GAP + LAYOUT_MARGIN))
    chk(lay["bbox"][3] <= CTA_Y - CTA_CLEAR, "實體下緣 %d ≤ %d（CTA 上面）" % (lay["bbox"][3], CTA_Y - CTA_CLEAR))
    chk(lay["y"] % 2 == 0 and lay["x"] % 2 == 0, "x、y 偶數（overlay yuv420 會截成偶數）")
    chk(lay["y_min"] is not None and lay["y_min"] % 2 == 0 and lay["y"] - 6 <= lay["y_min"] <= lay["y"],
        "彈跳上限 y_min=%s（鎖死 y=%d；管子左右壓在浮水印範圍內 ⇒ 往上最多 %d px）" % (lay["y_min"], lay["y"], lay["y"] - (lay["y_min"] or 0)))
    print("     builder 濾鏡：%s ／ overlay y='%s'" % builder_filters(lay, 900))

    print("3) PIL 合成片尾卡（鎖死後）：原位置 FAIL、新位置 PASS；加假浮水印（模擬蝦皮版）結果不變")
    for name, L in (("原位置", d), ("新位置", lay)):
        for wmk in (False, True):
            mm = measure(_synth(alpha, L, wmk))
            want = "FAIL" if name == "原位置" else "PASS"
            chk(verdict(mm["gap"]) == want and abs(mm["gap"] - L["gap"]) <= 3,
                "%s%s：量 %.1f px（layout 算 %.1f）⇒ %s" % (name, "＋假浮水印" if wmk else "", mm["gap"], L["gap"], verdict(mm["gap"])))

    print("4) ffmpeg 用 builder CARD 分支同一串濾鏡真的組 2 秒片尾卡（CRF 10 high），check --card-start 0")
    tmp = tempfile.mkdtemp(prefix="cardgap_")
    try:
        res4 = {}
        for name, L in (("原版", None), ("patch", lay)):
            mp4 = os.path.join(tmp, "card_%s.mp4" % name)
            _render_builder(ff, alpha, 900, L, mp4)
            v, r = check_video(mp4, card_start=0.0, quiet=True)
            res4[name] = r
            h = r["hard"][0]
            print("     %s：第 %d 格外框 %s 距離 %.1f ⇒ %s；彈跳期最小 %s px" % (name, h["frame"], h.get("bbox"), h.get("gap", -1), v, r["bounce_min"]))
            chk(v == ("FAIL" if name == "原版" else "PASS"), "%s ⇒ %s" % (name, "FAIL" if name == "原版" else "PASS"))
            if name == "patch":
                chk(abs(h["gap"] - lay["gap"]) <= 3, "成片量的距離跟 layout 算的差 ≤ 3 px（%.1f vs %.1f）" % (h["gap"], lay["gap"]))
                chk(r["bounce_min"] is not None and r["bounce_min"] >= MIN_GAP,
                    "彈跳期（沒有轉場、第 0 格全看得到）每格都 ≥ %d：最小 %.1f px（y_min 擋住往上那幾格）" % (MIN_GAP, r["bounce_min"] or -1))
                got, _, _ = read_frames_at(mp4, [1.0])
                gatelib.imwrite(os.path.join(outd, "card_ts_patch後.jpg"), draw(got[1.0][1], measure(got[1.0][1]), title="builder patch: t=1.00 (settled)"))
                got, _, _ = read_frames_at(mp4, [0.0])
                m0 = measure(got[0.0][1])
                gatelib.imwrite(os.path.join(outd, "card_ts_patch後_彈跳第0格.jpg"), draw(got[0.0][1], m0, title="builder patch: frame 0 (bounce -60px, no xfade)"))
        json.dump(res4, open(os.path.join(tmp, "res.json"), "w"), ensure_ascii=False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("5) 合成真品照：夠遠不改（changed=false）、要縮才夠、救不回（exit 1）")
    tmp = tempfile.mkdtemp(prefix="cardgap_")
    try:
        narrow = os.path.join(tmp, "narrow_alpha.png")   # 細長瓶：寬 120、置中 ⇒ 左緣 ~480，離浮水印右緣 380 有 100 px
        im = Image.new("RGBA", (240, 950), (0, 0, 0, 0))
        im.paste((40, 60, 90, 255), (60, 10, 180, 940))
        im.save(narrow)
        L = card_layout(narrow, 900, CTA_Y)
        chk(L["ok"] and not L["changed"] and L["gap"] >= 22, "細長瓶：原位置 %.1f px ⇒ 不改（builder 照原濾鏡）" % L["gap"])
        wide = os.path.join(tmp, "wide_alpha.png")       # 寬盒：900×1000 全不透明 ⇒ 要往下移 ~102 px，超過 CTA 上限 ⇒ 縮
        Image.new("RGBA", (900, 1000), (200, 40, 40, 255)).save(wide)
        L = card_layout(wide, 900, CTA_Y)
        chk(L["ok"] and L["scale"] < 1.0 and L["gap"] >= 22 and L["bbox"][3] <= CTA_Y - CTA_CLEAR,
            "寬盒：%s；外框 %s" % (L["how"], L["bbox"]))
        mm = measure(_synth(wide, L))
        chk(verdict(mm["gap"]) == "PASS", "寬盒新位置 PIL 合成量 %.1f px ⇒ PASS" % mm["gap"])
        L = card_layout(wide, 900, CTA_Y, wm=(0, 0, OW, 1700))   # 假的超大浮水印框：縮到一半也不夠
        chk(not L["ok"], "浮水印框假裝蓋到 y 1700：%s ⇒ ok=false（CLI exit 1，builder 停）" % L["how"])
        clear = os.path.join(tmp, "clear_alpha.png")
        Image.new("RGBA", (400, 950), (0, 0, 0, 0)).save(clear)
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "layout", "--real", clear],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        chk(r.returncode == 2, "整張透明的真品照 ⇒ CLI exit %d（量不了，builder 停）" % r.returncode)
        keyed = os.path.join(tmp, "white_bg.png")         # 非 *_alpha.png：builder 走 colorkey，白底不算外框
        im = Image.new("RGB", (400, 950), (255, 255, 255))
        im.paste((30, 30, 30), (100, 100, 300, 900))
        im.save(keyed)
        L = card_layout(keyed, 900, CTA_Y)
        b = L["default"]["bbox"]
        chk(abs((b[2] - b[0]) - 200 * 1000 / 950) <= 4, "白底圖走 colorkey：外框寬 %d ≈ 211（白底去掉）" % (b[2] - b[0]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("6) 不是片尾卡的格、轉場中的格 ⇒ 量不了（exit 2，不當 PASS）")
    other = os.path.join(WO5, "ts_shot1_t0.10.jpg")
    mix = _synth(alpha, lay)
    mix[:, :300] = np.asarray(Image.open(other).convert("RGB"))[:, :300]   # slideright 轉場：左邊還是上一鏡
    for name, img in (("ts_shot1", np.asarray(Image.open(other).convert("RGB"))), ("轉場中（左 300 px 是上一鏡）", mix)):
        try:
            measure(img)
            chk(False, "%s 應該丟 NotCard" % name)
        except NotCard as e:
            chk(True, "%s：%s" % (name, e))

    print("selftest %s" % ("全部通過" if ok_all else "有失敗"))
    return 0 if ok_all else 1


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("layout", help="組片前算真品照位置（印 JSON）")
    a1.add_argument("--real", required=True, help="真品照（*_alpha.png 看 alpha；其他照 builder 走 colorkey 白）")
    a1.add_argument("--card-w", type=int, default=900, help="builder CARDW（cfg card_w）")
    a1.add_argument("--cta-y", type=int, default=CTA_Y, help="片尾卡 CTA 的 y（builder CTAY，沒給＝1390）")
    a2 = sub.add_parser("check", help="量成片片尾卡那格")
    g = a2.add_mutually_exclusive_group(required=True)
    g.add_argument("--video")
    g.add_argument("--image")
    a2.add_argument("--card-start", type=float, help="片尾卡開始秒數（builder starts[-1]）：量 +1.0 秒那格＋彈跳期警示")
    a2.add_argument("--t", type=float, action="append", help="另外指定要硬擋的秒數（可多次）")
    a2.add_argument("--cta-y", type=int, default=CTA_Y)
    a2.add_argument("--out", help="標記圖（jpg）")
    a2.add_argument("--json", help="結果 JSON")
    a = ap.parse_args(argv)
    if a.cmd == "layout":
        try:
            r = card_layout(a.real, a.card_w, a.cta_y)
        except (OSError, ValueError) as e:
            print("✗ 讀不了真品照：%s" % e, file=sys.stderr)
            return 2
        print(json.dumps(r, ensure_ascii=False))
        if not r["ok"]:
            print("✗ %s：%s" % (r["real"], r["how"]), file=sys.stderr)
            return 1
        return 0
    try:
        if a.image:
            rgb = np.asarray(Image.open(a.image).convert("RGB"))
            m = measure(rgb, cta_y=a.cta_y)
            v = verdict(m["gap"])
            res = dict(file=os.path.basename(a.image), min_gap=MIN_GAP, wm_box=list(WM_BOX), bbox=m["bbox"], gap=m["gap"], verdict=v)
            print("%s 真品照外框 %s 離浮水印框 %s：%.1f px（要 ≥ %d）" % ("✓" if v == "PASS" else "✗", m["bbox"], list(WM_BOX), m["gap"], MIN_GAP))
            if a.out:
                gatelib.imwrite(a.out, draw(rgb, m, title=res["file"] if res["file"].isascii() else ""))
        else:
            v, res = check_video(a.video, a.card_start, a.t, a.cta_y, a.out)
    except NotCard as e:
        print("✗ 量不了：%s" % e)
        v, res = "ERROR", dict(error=str(e), verdict="ERROR")
    except (OSError, ValueError) as e:
        print("✗ %s" % e)
        return 2
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print("片尾卡離浮水印：%s" % v)
    return {"PASS": 0, "FAIL": 1}.get(v, 2)


if __name__ == "__main__":
    sys.exit(main())
