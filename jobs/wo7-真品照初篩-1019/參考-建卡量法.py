"""參考：本機建卡程式（prodfilm.py card 階段）量真品照的方法——節錄，只給定義，⛔ 直接 import。
初篩工具的「實心度」「物件數」「前景比」要用一模一樣的定義，初篩結果才能預告建卡會不會被擋。
（2026-10-19 Kai程式專線從本機 shopee/tools/prodfilm.py 第 83–100、373–384 行節錄；本機門檻 ⛔ 放寬。）
"""
import cv2
import numpy as np
from PIL import Image

RULE = {
    # 真品去背照「實心度」＝商品面積／外凸包面積。白瓶身被去背吃掉（0.63）、透明杯（0.79）會低；好的都 ≥0.89。
    "solidity_min": 0.88,
    "solidity_halo_min": 0.75,  # 袋形凹商品走 halo_flood 清白邊後的下限（建卡另有一套條件，初篩只要標「要本機建卡試」）
    # 成片上真品照被放大幾倍（>1＝真品照比畫面需要的小，貼回去會軟）。上限 1.30＝王 10/6 看對照圖定的。⛔ 再放寬。
    # 真品照通常只有 600–900 像素高 ⇒ 商品在成片上最多約 780–1170 像素高。
    "final_scale_max": 1.30,
}


def measure_alpha(p, alpha=None):
    a = np.asarray(Image.open(p).convert("RGBA"))[..., 3] if alpha is None else alpha
    fg = (a > 128).astype(np.uint8); H, W = fg.shape
    if fg.sum() < 400:
        raise ValueError("去背之後幾乎沒有東西，這張真品照不能用。")
    pts = np.argwhere(fg > 0)[:, ::-1].astype(np.int32)
    solid = float(fg.sum()) / max(1.0, float(cv2.contourArea(cv2.convexHull(pts))))
    n, _, st, _ = cv2.connectedComponentsWithStats(fg, 8)
    # 連通塊面積 ≥ 前景總面積 3% 才算「一個東西」；建卡要求剛好 1 個
    nobj = sum(1 for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 0.03 * fg.sum())
    ys, xs = np.where(fg > 0)
    return {"size": [int(W), int(H)], "solidity": round(solid, 3), "n_objects": int(nobj), "fg_ratio": round(float(fg.mean()), 3),
            "bbox_n": [round(float(xs.min()) / W, 4), round(float(ys.min()) / H, 4), round(float(xs.max() + 1) / W, 4), round(float(ys.max() + 1) / H, 4)]}
