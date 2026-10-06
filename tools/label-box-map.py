#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""label-box-map.py — lw 貼回憑證的框（場景座標）→ 成片每一格的 label 框（1080×1920 座標）（工單 #5-B）。

為什麼：#4 的 ghost-text-gate／review-sheet 需要「貼回的標籤在成片裡的位置」，從前後差異推不出來（見工單4報告）。
  貼回引擎（prodfilm.py lw）在憑證 .lw.json 裡記了 paste_box／quad（場景圖座標），
  組片（build_ph9_sample.py → kb-render.py）只是把場景圖推近、縮成 1080×1920 ⇒ 用同一套算式換算就知道每一格標籤在哪。

用法：
  python tools/label-box-map.py --lw 鏡1.png.lw.json --zoom z0 z1 cx cy --n 格數 [--fps 30] [--frames first,last|all|0,15,98] [--out boxes.json]
  python tools/label-box-map.py --lw 鏡1.png.lw.json --sample sample_ts.json --shot 1 --n 格數 …   # z0 z1 cx cy 從組片設定讀
  python tools/label-box-map.py … --draw 成片格.jpg --draw-frame 3 --draw-out 標框.jpg            # 把框畫在成片格上給人眼驗
  python tools/label-box-map.py --selftest
輸出 JSON（同 fixtures/ghost/label_boxes.json，鍵多一段 @格號）：
  {"_note": …, "<名稱>@<格號>": [x, y, w, h], …, "_frames": [{"frame": i, "time": 秒, "box": […], "quad": [[x,y]×4], "zoom": z}, …]}
  box＝paste_box（實際貼上去的那塊）換算後的外接框；quad＝lw 的四角（管身／盒面）換算後的四點。

kb-render.py 的算法（照抄，改它就要改這裡）：
  1. 場景圖寬高比 ≠ 9:16 ⇒ 寬不變、高硬拉成 round(寬 × 1920/1080)（scale=2160:3840 不保比例的舊行為）；寬 < 1080 ⇒ 整張拉成 1080×1920。
  2. 第 i 格（0 起算、共 n 格）：z = max(1, z0 + (z1−z0)·i/(n−1))；取景窗 w = W/z、h = H/z；
     x0 = clamp(cx·W − w/2, 0, W−w)、y0 = clamp(cy·H − h/2, 0, H−h)；取景窗 LANCZOS 縮到 1080×1920。
  ⇒ 場景點 (X, Y) → 成片 (u, v) = ((X·sx − x0)·1080/w, (Y·sy − y0)·1920/h)，sx、sy＝第 1 步的拉伸比例。
注意：成片裡每一鏡的第 i 格＝組片時間 starts[k] + i/fps（xfade 轉場那 0.3 秒兩鏡疊在一起，框只對本鏡那層有效）。
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gatelib  # noqa: E402

OW, OH = 1080, 1920


def kb_stretch(scene_w, scene_h):
    """kb-render 第 1 步：回傳 (W, H, sx, sy)＝拉伸後的場景尺寸與兩軸比例。"""
    W, H = scene_w, scene_h
    if abs(W / H - OW / OH) > 1e-3:
        H = round(W * OH / OW)
    if W < OW:
        W, H = OW, OH
    return W, H, W / float(scene_w), H / float(scene_h)


def kb_window(scene_w, scene_h, z0, z1, cx, cy, n, i):
    """第 i 格的取景窗 (x0, y0, w, h)（拉伸後座標）＋倍率 z。"""
    W, H, _, _ = kb_stretch(scene_w, scene_h)
    z = max(1.0, z0 + (z1 - z0) * (i / max(n - 1, 1)))
    w, h = W / z, H / z
    x0 = min(max(cx * W - w / 2, 0.0), W - w)
    y0 = min(max(cy * H - h / 2, 0.0), H - h)
    return x0, y0, w, h, z


def map_points(pts, scene_size, z0, z1, cx, cy, n, i):
    """場景座標的點（N×2）→ 第 i 格成片座標。"""
    sw, sh = scene_size
    _, _, sx, sy = kb_stretch(sw, sh)
    x0, y0, w, h, z = kb_window(sw, sh, z0, z1, cx, cy, n, i)
    p = np.asarray(pts, dtype=np.float64)
    u = (p[:, 0] * sx - x0) * OW / w
    v = (p[:, 1] * sy - y0) * OH / h
    return np.stack([u, v], 1), z


def map_lw(lw, z0, z1, cx, cy, n, frames, fps=30):
    """讀進來的 .lw.json → [{"frame", "time", "box", "quad", "zoom"}]。"""
    m = lw["metrics"]
    sw, sh = m["scene_size"]
    px0, py0, px1, py1 = m["paste_box"]
    out = []
    for i in frames:
        corners, z = map_points([[px0, py0], [px1, py0], [px1, py1], [px0, py1]], (sw, sh), z0, z1, cx, cy, n, i)
        quad, _ = map_points(m["quad"], (sw, sh), z0, z1, cx, cy, n, i)
        bx0, by0 = corners.min(0)
        bx1, by1 = corners.max(0)
        box = gatelib.clip_box((bx0, by0, bx1 - bx0, by1 - by0), (OH, OW))
        out.append(dict(frame=int(i), time=round(i / float(fps), 3), box=list(box), zoom=round(z, 5),
                        quad=[[round(float(x), 1), round(float(y), 1)] for x, y in quad]))
    return out


def parse_frames(spec, n):
    if spec in (None, "first,last"):
        return sorted({0, n - 1})
    if spec == "all":
        return list(range(n))
    fr = sorted({int(x) for x in spec.split(",") if x.strip() != ""})
    bad = [f for f in fr if not 0 <= f < n]
    if bad:
        raise ValueError("格號超出 0–%d：%s" % (n - 1, bad))
    return fr


def scene_params(sample_path, shot):
    """從組片設定（sample_*.json）的 scenes 讀第 shot 鏡（1 起算）的 [z0, z1, cx, cy]。"""
    cf = json.load(open(sample_path, encoding="utf-8"))
    sc = cf["scenes"][shot - 1]
    if sc[0] == "CARD":
        raise ValueError("第 %d 鏡是片尾卡（CARD），沒有貼回標籤" % shot)
    return [float(v) for v in sc[1:5]]


def draw(frame_path, entries, out_path):
    import cv2
    img = gatelib.imread(frame_path)
    colors = [(0, 220, 0), (0, 160, 255), (255, 0, 255), (255, 200, 0)]
    for k, e in enumerate(entries):
        c = colors[k % len(colors)]
        q = np.array(e["quad"], np.int32)
        cv2.polylines(img, [q], True, c, 2, cv2.LINE_AA)
        gatelib.draw_box(img, tuple(e["box"]), c, 3, "label f%d" % e["frame"])
    gatelib.imwrite(out_path, img, 90)


def build_json(name, entries, note):
    d = {"_note": note}
    for e in entries:
        d["%s@%d" % (name, e["frame"])] = e["box"]
    d["_frames"] = entries
    return d


# ── 自測 ──────────────────────────────────────────────────────────────────────
TS_DIR = os.path.join(gatelib.ROOT, "jobs", "wo5-擋門整合-1006", "fixtures", "ts")
SAMPLE_TS = os.path.join(gatelib.ROOT, "jobs", "wo5-擋門整合-1006", "local-tools", "sample_ts.json")
TS_SHOTS = [("prod1006_ts1_s900331_lw2x.png.lw.json", "ts_shot1_t0.10.jpg"), ("prod1006_ts2_s900197_lw2x.png.lw.json", "ts_shot2_t3.40.jpg"),
            ("prod1006_ts3_s900197_lw2x.png.lw.json", "ts_shot3_t7.90.jpg"), ("prod1006_ts4_s900331_lw2x.png.lw.json", "ts_shot4_t10.80.jpg"),
            ("prod1006_ts5_s900197_lw2x.png.lw.json", "ts_shot5_t13.90.jpg")]


def _synthetic_check():
    """照 kb-render 算法真的渲染一張場景（只有一個色塊），看換算出的框跟渲染結果差幾 px。"""
    from PIL import Image
    sw, sh = 1536, 2688
    scene = Image.new("RGB", (sw, sh), (40, 40, 40))
    pb = (650, 1109, 894, 1848)
    scene.paste((250, 250, 250), pb)
    W, H, _, _ = kb_stretch(sw, sh)
    im = scene.resize((W, H), Image.LANCZOS)
    worst = 0.0
    for z0, z1, cx, cy, n, i in ((1.0, 1.05, 0.5, 0.45, 99, 0), (1.0, 1.05, 0.5, 0.45, 99, 98), (1.05, 1.0, 0.5, 0.45, 120, 60), (1.2, 1.3, 0.3, 0.7, 50, 49)):
        x0, y0, w, h, _ = kb_window(sw, sh, z0, z1, cx, cy, n, i)
        frame = np.asarray(im.resize((OW, OH), Image.LANCZOS, box=(x0, y0, x0 + w, y0 + h)).convert("L"))
        ys, xs = np.where(frame > 145)
        rendered = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        e = map_lw({"metrics": {"scene_size": [sw, sh], "paste_box": list(pb), "quad": [[0, 0]] * 4}}, z0, z1, cx, cy, n, [i])[0]
        bx, by, bw, bh = e["box"]
        err = max(abs(rendered[0] - bx), abs(rendered[1] - by), abs(rendered[2] - (bx + bw)), abs(rendered[3] - (by + bh)))
        worst = max(worst, err)
        print("  z %.2f→%.2f c(%.2f,%.2f) 第 %d/%d 格：換算 %s／渲染 %s ⇒ 差 %d px" % (z0, z1, cx, cy, i, n, e["box"],
              [int(rendered[0]), int(rendered[1]), int(rendered[2] - rendered[0]), int(rendered[3] - rendered[1])], err))
    return worst <= 2


def selftest():
    ok = True
    print("== 算式自測（照 kb-render 真的渲染，框要對到 ±2 px）")
    good = _synthetic_check()
    ok &= good
    print("  %s\n" % ("✅ 通過" if good else "❌ 換算跟渲染對不上"))
    miss = gatelib.missing([os.path.join(TS_DIR, a) for a, _ in TS_SHOTS] + [os.path.join(TS_DIR, b) for _, b in TS_SHOTS] + [SAMPLE_TS])
    print("== 樣本（tsaio 五鏡：憑證框畫到成片格上 ⇒ out/工單5/ts_shot*_box.jpg，人眼看框是不是落在管身標籤）")
    if miss:
        print("  ⚠️ 缺樣本：" + "、".join(miss))
        return 2
    out_dir = os.path.join(gatelib.ROOT, "out", "工單5")
    all_boxes = {"_note": "tsaio 五鏡，label-box-map 依 .lw.json＋sample_ts.json 換算；n＝每鏡格數（未知時用 99＝3.3 秒）；"
                          "fixtures 的成片格不知道是本鏡第幾格 ⇒ 每鏡給首、末兩格的框，真的位置在兩者之間。"}
    for k, (lwf, frame) in enumerate(TS_SHOTS, 1):
        lw = json.load(open(os.path.join(TS_DIR, lwf), encoding="utf-8"))
        z0, z1, cx, cy = scene_params(SAMPLE_TS, k)
        n = 99
        entries = map_lw(lw, z0, z1, cx, cy, n, [0, n - 1])
        for e in entries:
            all_boxes["ts_shot%d@%d" % (k, e["frame"])] = e["box"]
        draw(os.path.join(TS_DIR, frame), entries, os.path.join(out_dir, "ts_shot%d_box.jpg" % k))
        print("  鏡%d z %.2f→%.2f：首格框 %s、末格框 %s ⇒ out/工單5/ts_shot%d_box.jpg" % (k, z0, z1, entries[0]["box"], entries[-1]["box"], k))
    with open(os.path.join(out_dir, "ts_label_boxes.json"), "w", encoding="utf-8") as f:
        json.dump(all_boxes, f, ensure_ascii=False, indent=1)
    print("結果：%s（框的位置要人眼看 out/工單5/ts_shot*_box.jpg）" % ("算式自測通過" if ok else "有沒過的"))
    return 0 if ok else 1


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="lw 憑證的框 → 成片座標（照 kb-render 算法）")
    ap.add_argument("--lw", help=".lw.json 貼回憑證")
    ap.add_argument("--zoom", nargs=4, type=float, metavar=("Z0", "Z1", "CX", "CY"), help="這一鏡的推近參數（同 sample_*.json scenes）")
    ap.add_argument("--sample", help="組片設定 sample_*.json（給了就從 scenes 讀 z0 z1 cx cy）")
    ap.add_argument("--shot", type=int, help="第幾鏡（1 起算，配 --sample）")
    ap.add_argument("--n", type=int, help="這一鏡的格數（builder：round((d[k]+轉場0.3)×fps)，最後一鏡不加轉場）")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--frames", help="first,last（預設）／all／逗號分隔的格號")
    ap.add_argument("--name", help="JSON 鍵的名稱（預設 lw 檔名）")
    ap.add_argument("--out", help="輸出 JSON")
    ap.add_argument("--draw", help="成片格 jpg：把框畫上去")
    ap.add_argument("--draw-frame", type=int, help="畫哪一格的框（預設首、末格都畫）")
    ap.add_argument("--draw-out", help="畫框後的輸出圖")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.lw or not a.n or not (a.zoom or (a.sample and a.shot)):
        ap.error("要給 --lw、--n，以及 --zoom 或 --sample＋--shot（或 --selftest）")
    try:
        lw = json.load(open(a.lw, encoding="utf-8"))
        z0, z1, cx, cy = a.zoom if a.zoom else scene_params(a.sample, a.shot)
        entries = map_lw(lw, z0, z1, cx, cy, a.n, parse_frames(a.frames, a.n), a.fps)
    except (OSError, ValueError, KeyError) as e:
        print("❌ %s" % e, file=sys.stderr)
        return 2
    name = a.name or os.path.basename(a.lw).replace(".png.lw.json", "").replace(".lw.json", "")
    data = build_json(name, entries, "label-box-map：%s，z %.3f→%.3f c(%.3f,%.3f) n=%d fps=%d" % (os.path.basename(a.lw), z0, z1, cx, cy, a.n, a.fps))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    for e in entries:
        print("%s@%d  t=%.3fs  z=%.4f  box=%s" % (name, e["frame"], e["time"], e["zoom"], e["box"]))
    if a.draw:
        sel = [e for e in entries if a.draw_frame is None or e["frame"] == a.draw_frame]
        if not sel:
            sel = map_lw(lw, z0, z1, cx, cy, a.n, [a.draw_frame], a.fps)
        draw(a.draw, sel, a.draw_out or os.path.splitext(a.draw)[0] + "_box.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
