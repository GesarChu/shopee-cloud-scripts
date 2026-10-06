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


def read_gray_frames(path, box=None, start=None, end=None):
    """讀影片每一格 → float32 灰階（有 box 就只取那塊）。回傳 (frames list, fps)。
    start／end（秒）：只留 start ≤ 格的時間 < end 的格（第一格的格號存在 read_gray_frames.first）。"""
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
        frames, idx, read_gray_frames.first = [], -1, None
        while True:
            ok, f = cap.read()
            if not ok:
                break
            idx += 1
            t = idx / fps
            if (start is not None and t < start - 1e-6) or (end is not None and t >= end - 1e-6):
                if end is not None and t >= end - 1e-6:
                    break
                continue
            if read_gray_frames.first is None:
                read_gray_frames.first = idx
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


# 版型帶：特別蝦版型的標題、浮水印、字幕都在畫面上方（樣本實測字幕最低到 y≈455／1920）⇒ 上方 25.5% 不找假字、不拿來對齊
OVERLAY_TOP_FRAC = 0.255

# label 框自動偵測（`|後−前|`，先對齊）——只在「貼回前、後是同一格」時可靠；10/6 樣本三組都不是（見報告）
LABEL_DIFF_THR = 25      # 對齊後灰階絕對差 > 25 才算「有貼東西」（JPEG 雜訊、重新取樣殘差多在 15 以下）
LABEL_MIN_FRAC = 0.005   # 最大差異塊（閉運算後）至少佔整張 0.5%，否則判「前後幾乎一樣、找不到」
LABEL_MIN_FILL = 0.35    # 差異塊面積 ÷ 外框面積 ≥ 0.35：貼回的標籤是一整塊；重新取樣殘差是散的細邊
LABEL_DILATE_PX = 6      # label 框往外膨脹幾個像素（工單：膨脹幾個像素）
ALIGN_MIN_INLIERS = 80   # ORB 配對的 RANSAC 內點少於 80 就不對齊（畫面差太多，對了也不準）


class LabelBoxError(ValueError):
    """前後差異找不到可靠的 label 框 ⇒ 要由貼回步驟給 --label-box。"""


def align(before, after, ignore_top=0):
    """把「貼回前」對齊到「貼回後」（ORB 特徵＋RANSAC 相似變換；kb-render 推近造成的縮放／平移）。
    回傳 (對齊後的 before, 有效區遮罩, 說明)；配不起來就原樣回傳。"""
    ga, gb = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY), cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)
    mask = np.full(ga.shape, 255, np.uint8)
    mask[:ignore_top] = 0
    orb = cv2.ORB_create(5000)
    ka, da = orb.detectAndCompute(ga, mask)
    kb, db = orb.detectAndCompute(gb, mask)
    full = np.full(ga.shape, 255, np.uint8)
    if da is None or db is None or len(ka) < 10 or len(kb) < 10:
        return before, full, "特徵點太少，沒有對齊"
    m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(db, da)
    if len(m) < ALIGN_MIN_INLIERS:
        return before, full, "配對太少（%d），沒有對齊" % len(m)
    src = np.float32([kb[x.queryIdx].pt for x in m])
    dst = np.float32([ka[x.trainIdx].pt for x in m])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if M is None or int(inl.sum()) < ALIGN_MIN_INLIERS:
        return before, full, "RANSAC 內點太少，沒有對齊"
    size = (after.shape[1], after.shape[0])
    warped = cv2.warpAffine(before, M, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    valid = cv2.warpAffine(full, M, size, flags=cv2.INTER_NEAREST)
    valid = cv2.erode(valid, np.ones((25, 25), np.uint8))   # 邊界補出來的像素不算
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    return warped, valid, "已對齊：縮放 %.3f、平移 (%.0f, %.0f)、內點 %d" % (scale, M[0, 2], M[1, 2], int(inl.sum()))


def label_box(after, before, thr=LABEL_DIFF_THR, min_frac=LABEL_MIN_FRAC, dilate_px=LABEL_DILATE_PX, overlay_top=OVERLAY_TOP_FRAC):
    """貼回前後的差異 → label 框 (x,y,w,h)（已膨脹）與說明。找不到可靠的框丟 LabelBoxError。

    做法：先對齊（kb-render 推近）→ 三通道取最大絕對差 → 扣掉上方版型帶、對齊補邊 → 門檻 → 閉運算把字縫補起來
    → 最大連通塊；面積太小或太散（不像一整塊貼上去的標籤）⇒ 不猜，丟錯要求 --label-box。
    """
    if after.shape != before.shape:
        raise ValueError("貼回前後兩張圖尺寸不同：%s vs %s" % (after.shape, before.shape))
    top = int(round(after.shape[0] * overlay_top))
    warped, valid, note = align(before, after, top)
    diff = cv2.absdiff(after, warped).max(axis=2) if after.ndim == 3 else cv2.absdiff(after, warped)
    diff[valid == 0] = 0
    diff[:top] = 0
    mask = (diff > thr).astype(np.uint8)
    k = max(3, int(round(min(after.shape[:2]) * 0.01)) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        raise LabelBoxError("貼回前後幾乎一樣（%s），找不到 label 框 ⇒ 請給 --label-box" % note)
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = (int(v) for v in stats[big])
    fill = area / float(w * h)
    if area < min_frac * mask.size or fill < LABEL_MIN_FILL:
        raise LabelBoxError("差異不成一整塊（最大塊 %d px、佔外框 %.0f%%；%s），不像貼回的標籤 ⇒ 請給 --label-box"
                            % (area, fill * 100, note))
    box = clip_box((x - dilate_px, y - dilate_px, w + 2 * dilate_px, h + 2 * dilate_px), after.shape)
    return box, note


def load_label_boxes(path):
    """讀 label_boxes.json：{"檔名.jpg": [x, y, w, h], ...}（以 _ 開頭的鍵是備註）。"""
    import json
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: tuple(int(v) for v in b) for k, b in data.items() if not k.startswith("_")}


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
