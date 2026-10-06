# -*- coding: utf-8 -*-
"""kb-render.py — 靜態場景圖 → 慢推／慢拉鏡頭影片（次像素，取代 ffmpeg zoompan）｜2026-10-06 第 34 棒

為什麼：build_ph9_sample.py 用 2× 放大＋zoompan，zoompan 的裁切位置是整數像素 ⇒ 半像素一步一步跳
（商品區逐格差 0.8↔2.5 規律擺盪、靜止段每 5 格跳一次；10/2 舊片同型）。模型畫的軟字看不出來；
貼回的真品標籤很銳利就會閃（王 10/6 退花王「字體是有清楚但是會略帶閃爍」、「為什麼今天的片很多閃爍?」）。
做法：每一格用 PIL 的浮點 box 做 LANCZOS resize（真正次像素），rawvideo 餵 ffmpeg 無損（libx264 CRF 0，照事實 #8）。
用法：py -3 tools/kb-render.py <場景圖> <輸出.mp4> <z0> <z1> <cx> <cy> <格數> <fps>
  z＝放大倍率（1.0＝整張；1.2＝取中間 1/1.2），cx cy＝取景中心（0–1），跟 zoompan 的 x='iw*cx-(iw/zoom/2)' 同義。
驗：tools 裡沒有獨立擋門，組片後用「商品區逐格差」看：應該平滑、沒有規律擺盪（第 34 棒 16:5x 的量法見 現況 §🔴）。
"""
import subprocess, sys
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
src, out = sys.argv[1], sys.argv[2]
z0, z1, cx, cy = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])
n, fps = int(sys.argv[7]), int(sys.argv[8])
OW, OH = 1080, 1920
im = Image.open(src).convert("RGB")
if abs(im.width / im.height - OW / OH) > 1e-3:   # 舊路徑 scale=2160:3840 是不保比例硬拉成 9:16，這裡照做，畫面才跟以前一樣
    im = im.resize((im.width, round(im.width * OH / OW)), Image.LANCZOS)
if im.width < OW:   # 小圖先放大到輸出尺寸，取景窗才不會比輸出小太多
    im = im.resize((OW, OH), Image.LANCZOS)
W, H = im.size
p = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                      "-s", "%dx%d" % (OW, OH), "-r", str(fps), "-i", "-",
                      "-c:v", "libx264", "-preset", "veryfast", "-crf", "0", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
for i in range(n):
    z = max(1.0, z0 + (z1 - z0) * (i / max(n - 1, 1)))   # zoompan 的 zoom 下限也是 1
    w, h = W / z, H / z
    x0 = min(max(cx * W - w / 2, 0.0), W - w)   # 取景窗夾在圖內（zoompan 同）
    y0 = min(max(cy * H - h / 2, 0.0), H - h)
    p.stdin.write(im.resize((OW, OH), Image.LANCZOS, box=(x0, y0, x0 + w, y0 + h)).tobytes())
p.stdin.close()
rc = p.wait()
print("kb-render %s：%d 格 rc=%d" % (out, n, rc))
sys.exit(rc)
