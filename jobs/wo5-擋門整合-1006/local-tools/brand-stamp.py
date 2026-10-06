# -*- coding: utf-8 -*-
r"""品牌化成片：加「特別蝦」浮水印（全程）＋片尾品牌卡 — 2026-09-09 Nora 建，王當場定案。

王 2026-09-09 拍板的參數：
  浮水印  左上角 x=130 y=260（避開手機裁切與 iOS/FB 介面；王手機實看後定案）／不透明度 **80%**／**全程都在**
  片尾卡  1.25 秒，白底置中全 logo（正片不縮短，卡是加法）

🔴 為什麼是「臉＋另外打字」而不是直接縮小整個 logo（9/9 三版實測）：
   整個 logo 縮到 190px 後，下方「特別蝦！Too shrimp」會糊成一團認不出字，
   等於沒有署名效果、防不了盜用。所以拆成：臉去背當圖示 ＋ 字用字型重打（字級獨立、永遠清晰）。

🔴 片尾卡不是為了「剪掉就不足 10 秒」——那個說法只在正片短於 10 秒時成立（9/9 王問出來的）。
   ⛔ 不要為了它把正片壓到 9 秒：10 秒是 FB 商品橫幅的硬條件，正片 9 秒等於把資格押在片尾卡上。

用法：
  py -3 tools/brand-stamp.py --in <來源.mp4> --out <輸出.mp4>
  py -3 tools/brand-stamp.py --in a.mp4 --out b.mp4 --no-card      # 只加浮水印
  py -3 tools/brand-stamp.py --in a.mp4 --out b.mp4 --opacity 0.6  # 改不透明度
"""
import argparse
import os
import subprocess
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOGO = r'C:\Users\GesarChu\Desktop\翠發文\蝦皮優惠資訊FB粉絲專頁原圖\特別蝦粉絲專頁 頭貼-02.jpg'
FONT = "C\\:/Windows/Fonts/msjhbd.ttc"   # 微軟正黑體 Bold；filter 內冒號要跳脫

# 從 5001×5001 原圖切出「臉」的區域（避開下方會糊掉的文字）
FACE_CROP = 'crop=2900:3300:950:250'
# 🔴 2026-09-09 王手機實看後修正（原本 40,80 在手機上會被裁掉一半）：
#    手機把 9:16 影片放大填滿 19.5:9 螢幕 → 左右各裁掉約 97px；左上還有圓角與 iOS 狀態列。
#    x=130（2026-09-09 定案）。決策依據：
#      🔬 只有 iPhone 會裁（滿版填滿，單邊 97px）；Android 貼齊寬度、上下留黑、【不裁】。
#         ⇒ 同一個 x：iPhone 有效位置 = x−97，Android 有效位置 = x。
#         ⇒ x 加得越多【只有 Android 在付代價】，iPhone 過了 97 就夠。
#      x=130 → iPhone 距可見左緣 33px（貼角）、Android 內縮 12%。兩邊都是角落。
#      ⛔ 中途曾依「20:9/21:9 裁切表」改成 150，那張表【對 Android 不適用】（它不裁），已作廢。
#    y=260 → 避開 iOS 狀態列(<160)、FB 返回鍵(185~255) 與螢幕圓角
WM_X, WM_Y, WM_W = 130, 260, 96
TEXT_X, TEXT_Y, TEXT_SIZE = WM_X + 106, WM_Y + 30, 46
CARD_SEC, CARD_LOGO_W = 1.25, 880


def build(src, dst, opacity, with_card, crf=0):
    a = '%.2f' % opacity
    parts = [
        "[1:v]%s,colorkey=0xFFFFFF:0.10:0.0,scale=%d:-1,format=rgba,"
        "colorchannelmixer=aa=%s[wm];" % (FACE_CROP, WM_W, a),
        "[0:v]fps=24,setsar=1[v0];",
        "[v0][wm]overlay=%d:%d[vw];" % (WM_X, WM_Y),
        "[vw]drawtext=fontfile='%s':text='特別蝦':fontcolor=white@%s:fontsize=%d:x=%d:y=%d:"
        "shadowcolor=black@%.2f:shadowx=3:shadowy=3,format=yuv420p[vmain];"
        % (FONT, a, TEXT_SIZE, TEXT_X, TEXT_Y, opacity * 0.55),
    ]
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', src, '-i', LOGO]
    if with_card:
        cmd += ['-loop', '1', '-t', str(CARD_SEC), '-i', LOGO,
                '-f', 'lavfi', '-t', str(CARD_SEC), '-i', 'anullsrc=r=48000:cl=stereo']
        parts += [
            "[2:v]scale=%d:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:white,fps=24,setsar=1,"
            "format=yuv420p[card];" % CARD_LOGO_W,
            "[vmain][0:a][card][3:a]concat=n=2:v=1:a=1[v][a]",
        ]
        maps = ['-map', '[v]', '-map', '[a]']
    else:
        parts[-1] = parts[-1].replace('[vmain];', '[v]')
        maps = ['-map', '[v]', '-map', '0:a?']
    # 2026-09-11 王：「都不要用壓縮的」「記得要無損」。原本 CRF 21/medium＋AAC 128k 會把母片 7.5 Mbps 壓到 4.3 Mbps
    # （王在 PC 上看出畫質稍差）。現在預設 --crf 0＝libx264 無損（檔案會大很多）；音軌沒片尾卡時直接 copy，
    # 有片尾卡要 concat 才重編（AAC 256k）。要小檔自己指定 --crf 17（與母片同級）。
    audio = ['-c:a', 'aac', '-b:a', '256k'] if with_card else ['-c:a', 'copy']
    # CRF 0 是數學無損，但 libx264 無損會把 profile 變成 High 4:4:4 Predictive，iPhone／多數手機硬解不支援
    # （9/11 實測：無損檔 profile=High 4:4:4 Predictive）。交付給手機上傳的檔要能播，所以：
    #   --crf 0  ＝ 無損（母片、中間檔用）
    #   --crf 10 ＝ 預設：High profile、視覺上與無損無法分辨（約 30–50 Mbps），手機與平台都能播
    preset = 'veryfast' if crf == 0 else 'slow'
    profile = [] if crf == 0 else ['-profile:v', 'high']
    cmd += ['-filter_complex', ''.join(parts)] + maps + [
        '-c:v', 'libx264', '-preset', preset, '-crf', str(crf)] + profile + ['-pix_fmt', 'yuv420p'] + audio + [
        '-movflags', '+faststart', dst]
    return cmd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--out', dest='dst', required=True)
    ap.add_argument('--opacity', type=float, default=0.80)
    ap.add_argument('--no-card', action='store_true')
    ap.add_argument('--crf', type=int, default=10, help='10＝預設（High profile，手機可播，視覺無損）；0＝數學無損（4:4:4 profile，手機硬解不支援，只給母片用）')
    a = ap.parse_args()

    for p in (a.src, LOGO):
        if not os.path.exists(p):
            raise SystemExit('⛔ 找不到檔案：%s' % p)

    cmd = build(a.src, a.dst, a.opacity, not a.no_card, a.crf)
    r = subprocess.run(cmd)
    if r.returncode:
        raise SystemExit('⛔ ffmpeg 失敗（returncode=%d）' % r.returncode)

    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration,size',
                          '-of', 'default=nw=1', a.dst], capture_output=True, text=True).stdout
    print('✅ %s' % a.dst)
    print(out.strip())
    print('⚠️ FB Reel 硬條件：長度必須 > 10 秒，否則沒有商品橫幅資格。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
