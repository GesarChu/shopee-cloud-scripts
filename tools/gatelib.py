# -*- coding: utf-8 -*-
"""gatelib — 工單 #4 擋門工具共用的小函式（motion-gate／ghost-text-gate／review-sheet／composite-real）。

只用 numpy／opencv／Pillow。路徑一律相對 repo（不寫本機路徑）。
中文路徑：Windows 上 cv2.imread／imwrite／VideoCapture 吃不了非 ASCII 路徑 ⇒ 圖片走 bytes 解碼，影片打不開就先複製到暫存檔。
"""
import os
import shutil
import tempfile

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "jobs", "wo4-擋門與合成-1006", "fixtures")


# ── 讀寫 ──────────────────────────────────────────────────────────────────────
def imread(path, alpha=False):
    """讀圖（中文路徑也可以）；alpha=True 保留透明通道。讀不到丟 FileNotFoundError。"""
    data = np.fromfile(path, dtype=np.uint8) if os.path.exists(path) else None
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED if alpha else cv2.IMREAD_COLOR) if data is not None and data.size else None
    if img is None:
        raise FileNotFoundError("讀不到圖：%s" % path)
    return img


def imwrite(path, img, quality=90):
    """寫圖（中文路徑也可以）；副檔名決定格式。回傳檔案大小（bytes）。"""
    ext = os.path.splitext(path)[1].lower() or ".jpg"
    params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)] if ext in (".jpg", ".jpeg") else []
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        raise IOError("編碼失敗：%s" % path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    buf.tofile(path)
    return int(buf.size)


def read_gray_frames(path, box=None):
    """讀影片每一格 → float32 灰階（有 box 就只取那塊）。回傳 (frames list, fps)。"""
    if not os.path.exists(path):
        raise FileNotFoundError("找不到影片：%s" % path)
    cap, tmp = cv2.VideoCapture(path), None
    if not cap.isOpened():   # Windows 中文路徑：複製到 ASCII 暫存檔再開
        fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(path)[1] or ".mp4")
        os.close(fd)
        shutil.copyfile(path, tmp)
        cap = cv2.VideoCapture(tmp)
    try:
        if not cap.isOpened():
            raise IOError("OpenCV 打不開影片：%s" % path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            if box:
                x, y, w, h = box
                f = f[y:y + h, x:x + w]
            frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32))
        return frames, fps
    finally:
        cap.release()
        if tmp:
            os.remove(tmp)


def parse_box(text):
    """'x,y,w,h' → (x, y, w, h) 整數。"""
    parts = [int(round(float(v))) for v in text.replace(" ", "").split(",")]
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise ValueError("box 要寫 x,y,w,h（w、h > 0）：%r" % text)
    return tuple(parts)


# ── 框 ────────────────────────────────────────────────────────────────────────
def clip_box(box, shape):
    x, y, w, h = box
    H, W = shape[:2]
    x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
    x1, y1 = min(W, int(round(x + w))), min(H, int(round(y + h)))
    return (int(x0), int(y0), int(max(0, x1 - x0)), int(max(0, y1 - y0)))


def expand_box(box, shape, up=0.0, down=0.0, left=0.0, right=0.0, pad_px=0):
    """往外擴：比例以框本身的寬高計；再加 pad_px；最後裁在圖內。"""
    x, y, w, h = box
    nx, ny = x - w * left - pad_px, y - h * up - pad_px
    nw, nh = w * (1 + left + right) + 2 * pad_px, h * (1 + up + down) + 2 * pad_px
    return clip_box((nx, ny, nw, nh), shape)


# label 框偵測門檻（`|後−前|`）：JPEG 雜訊通常 < 12；貼回的標籤跟模型原本畫的差異多半 > 30
LABEL_DIFF_THR = 25      # 灰階絕對差 > 這個才算「有貼東西」
LABEL_MIN_FRAC = 0.002   # 差異區塊面積至少佔整張的 0.2%（擋 JPEG 雜點、壓縮塊）
LABEL_DILATE_PX = 6      # label 框往外膨脹幾個像素（工單：膨脹幾個像素）


def label_box(after, before, thr=LABEL_DIFF_THR, min_frac=LABEL_MIN_FRAC, dilate_px=LABEL_DILATE_PX):
    """貼回前後的差異 → label 框 (x,y,w,h)（已膨脹）與差異遮罩。找不到丟 ValueError。

    做法：三通道取最大絕對差 → 門檻 → 閉運算把字縫補起來 → 取面積最大的連通塊，
    再把面積 ≥ 最大塊 20% 且跟它相鄰（距離 < 框高 10%）的塊併進來（標籤被手指切成兩半時）。
    """
    if after.shape != before.shape:
        raise ValueError("貼回前後兩張圖尺寸不同：%s vs %s" % (after.shape, before.shape))
    diff = cv2.absdiff(after, before).max(axis=2) if after.ndim == 3 else cv2.absdiff(after, before)
    mask = (diff > thr).astype(np.uint8)
    k = max(3, int(round(min(after.shape[:2]) * 0.006)) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        raise ValueError("貼回前後幾乎一樣，找不到 label 框")
    order = np.argsort(-stats[1:, cv2.CC_STAT_AREA]) + 1
    big = order[0]
    if stats[big, cv2.CC_STAT_AREA] < min_frac * mask.size:
        raise ValueError("差異區塊太小（%d px），找不到 label 框" % stats[big, cv2.CC_STAT_AREA])
    x, y, w, h = stats[big, :4]
    x0, y0, x1, y1 = x, y, x + w, y + h
    for i in order[1:]:
        if stats[i, cv2.CC_STAT_AREA] < 0.2 * stats[big, cv2.CC_STAT_AREA]:
            break
        bx, by, bw, bh = stats[i, :4]
        gap = max(bx - x1, x0 - (bx + bw), by - y1, y0 - (by + bh), 0)
        if gap < 0.1 * (y1 - y0):
            x0, y0, x1, y1 = min(x0, bx), min(y0, by), max(x1, bx + bw), max(y1, by + bh)
    box = clip_box((x0 - dilate_px, y0 - dilate_px, x1 - x0 + 2 * dilate_px, y1 - y0 + 2 * dilate_px), after.shape)
    return box, (lab > 0).astype(np.uint8) * mask


def draw_box(img, box, color, thick=3, text=None):
    x, y, w, h = box
    cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), color, thick)
    if text:
        cv2.putText(img, text, (x + 4, max(18, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)
    return img


def fixture(*parts):
    return os.path.join(FIXTURES, *parts)


def missing(paths):
    return [os.path.relpath(p, ROOT) for p in paths if not os.path.exists(p)]
