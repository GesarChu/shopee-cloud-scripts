# -*- coding: utf-8 -*-
"""PH9 商品片樣品（蝦皮 App 限定，王 10/1 #115／#116）：真商品場景圖＋程式縮放＋台灣女聲旁白＋大字幕跳字＋轉場＋墊樂。
2026-10-01 第 31 棒。同一份畫面，換旁白聲音出 A／B／C 三版給王挑。
用法：py -3 build_ph9_sample.py --vo A|B|C [--nopop]
  A＝GPT-SoVITS tw01 訓練聲（voice-takes.py 快取）  B＝IndexTTS 2.5 克隆王授權台灣女聲（voiceB/lineNN.*）
  C＝第二女聲 IndexTTS 克隆（voiceC/lineNN.*）  C2＝第二女聲 GPT-SoVITS 專屬模型 voice2（voice-takes 快取）
字幕位置：浮水印在左上 x=130 y=260（brand-stamp），字幕放 y 450／590，避開浮水印與瓶身。
⛔ 不報價、不寫絕對字；每句照賣場原文（台灣生產、天然礦物質、鹼性離子水）。
"""
import argparse, glob, hashlib, json, os, subprocess
os.chdir(os.path.dirname(os.path.abspath(__file__)))
ROOT = r"C:\Users\GesarChu\Desktop\Claude Code\shopee"
ap = argparse.ArgumentParser(); ap.add_argument("--vo", default="A"); ap.add_argument("--nopop", action="store_true")
ap.add_argument("--cfg", default="", help="別的商品：sample_<名>.json（lines／real／music／scenes／key／pre）；不給＝PH9")
a = ap.parse_args()
# 🔴 2026-10-06 寫死（CLAUDE #141；王「現在開始每件對的SOP就寫死」）：組片前先過 tools/prodfilm.py gate。沒有跳過參數。
#    擋的是源頭：場景圖裡的商品是模型重畫的，沒把商品卡的真品貼回去、貼壞、真品照太小、字幕壓到商品字或撞浮水印、片尾卡不是商品卡的去背照，都不准組片。
import sys
if not a.cfg:
    sys.exit("⛔ 要給 --cfg sample_<簡稱>.json。沒有設定檔的 PH9 舊預設值不能再組（場景圖沒有貼回憑證）。")
if subprocess.run(["py", "-3", "C:/Users/GesarChu/Desktop/Claude Code/shopee/tools/prodfilm.py", "gate", os.path.abspath(a.cfg)]).returncode != 0:
    sys.exit("⛔ 商品片擋門沒過，不組片。照上面每一條修好再跑。")
C = "../首幀/_候選/"
REAL = "E:/ComfyUI-Qwen/ComfyUI/input/ph_bottle.jpg"
SFX = "C:/Users/GesarChu/.claude/skills/beat-cut-editor/sfx-library/"
MUSIC = "C:/Users/GesarChu/.claude/skills/beat-cut-editor/music-library/happy/Sunlit Sidewalk.mp3"
lines = [l.strip() for l in open("lines_ph9.txt", encoding="utf-8") if l.strip()]
# 每句對一張圖、一種動態：(圖, 縮放起, 縮放迄, 中心 x, 中心 y)（中心＝0–1 的畫面比例）
SC = [(C + "prod1001c_ph2_s900331_真標.png", 1.00, 1.10, 0.50, 0.38),
      (C + "prod1001c_ph1_s900331_真標.png", 1.06, 1.00, 0.50, 0.55),
      (C + "prod1001c_ph1_s900197_真標.png", 1.00, 1.28, 0.50, 0.48),
      (C + "prod1001c_ph3_s900331_真標.png", 1.08, 1.00, 0.42, 0.55),
      (C + "prod1001c_ph4_s900331_真標.png", 1.00, 1.12, 0.48, 0.40),
      ("CARD", 0, 0, 0, 0)]
KEY = ["一身汗", "要帶水", "統一鹼性離子水", "台灣生產", "天然礦物質", "想喝就拿", "冰箱", "點進去"]
TRANS = ["slideleft", "zoomin", "slideup", "smoothleft", "circleopen"]
X = 0.30  # 轉場長度
SUBSTYLE, MIDY, TITLE = "top", 1100, ""
MIDFS, MIDYS = 100, []
SUBY, CTAY = [420, 560, 480], None   # 兩行字幕的上／下行 y、單行 y；CTA y（None＝有商品卡 1390、沒有 470）
CARDW = 900   # 片尾商品卡最大寬度；真品照解析度不夠時調小（縮小顯示比放大清楚，10/3 Hoppi 822px 原圖）
PRE, NAME = "", "PH9"   # PRE＝聲音資料夾／中間檔前綴（PH9 沿用舊名不加）
if a.cfg:
    cf = json.load(open(a.cfg, encoding="utf-8"))
    PRE, NAME, REAL = cf["pre"], cf["name"], cf["real"]
    MUSIC = cf.get("music", MUSIC)
    CARDW = cf.get("card_w", CARDW)
    lines = [l.strip() for l in open(cf["lines"], encoding="utf-8") if l.strip()]
    C = cf.get("img_dir", C)   # 圖片資料夾；scenes 檔名可寫「../別的包/首幀/_候選/xxx.png」這種相對路徑（相對 img_dir）
    SC = [tuple([C + s[0] if s[0] != "CARD" else "CARD"] + s[1:]) for s in cf["scenes"]]
    KEY = cf["key"]
    TRANS = cf.get("trans", TRANS)
    SUBY = cf.get("sub_y", SUBY)   # 人物片：字幕放下半部（臉在上面）
    CTAY = cf.get("cta_y", CTAY)
    SUBSTYLE = cf.get("sub_style", "top")   # 10/3 第 33 棒：mid＝人哥／衛生紙片那種中下方一行大字、每句換配色（王：字幕撞左上浮水印）
    MIDY = cf.get("mid_y", 1100)
    MIDFS = cf.get("mid_fs", 100)          # 10/3 晚：王看人哥字幕「小、放商品邊緣」⇒ 字縮小（60＝72 號字，人哥講話那行約 68）
    MIDYS = cf.get("sub_ys", [])            # 每個場景各自的字幕 y（避開商品標籤）；沒給就用 mid_y
    TITLE = cf.get("title", "")             # 上方固定標題卡（人哥片的「德國Donkey招財貓」那層），放在浮水印上面

def dur(f):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f], capture_output=True, text=True).stdout)

def vo_files():
    spf = ("voice_%s%s.json" % (PRE, a.vo)) if PRE else ("voice_ph9_%s.json" % a.vo)
    if os.path.exists(spf) and a.vo not in ("B", "C"):   # voice-takes（GPT-SoVITS）快取：A、C2
        sp = json.load(open(spf, encoding="utf-8")); out = []
        for t in lines:
            key = json.dumps([sp.get("voice_backend", "edge"), sp.get("voice"), sp.get("rate"), sp.get("sovits_ref"), sp.get("sovits_speed"), t], ensure_ascii=False)
            out.append(os.path.join(ROOT, sp["folder"], "_jy", "_voice_cache", "v_%s.wav" % hashlib.md5(key.encode("utf-8")).hexdigest()[:12]))
        return out
    return [sorted(glob.glob("%svoice%s/line%02d.*" % (PRE, a.vo, i)))[0] for i in range(1, len(lines) + 1)]

def trim(files):
    """頭尾靜音修掉（IndexTTS 常帶 0.5–1 秒尾巴），留 0.05 秒；修好的放 _trim_<vo>/，原檔不動。"""
    out = []; td = "_trim_%s%s" % (PRE, a.vo); os.makedirs(td, exist_ok=True)
    for i, f in enumerate(files, 1):
        o = os.path.join(td, "line%02d.wav" % i)
        af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
              "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", f, "-af", af, "-ar", "48000", "-ac", "1", o], check=True)
        out.append(o)
    return out

vo = trim(vo_files()); vd = [dur(f) for f in vo]
LEAD0, LEAD, TAIL, TAIL_LAST = 0.30, 0.15, 0.30, 1.10
d = []
for k, v in enumerate(vd):
    d.append((LEAD0 if k == 0 else LEAD) + v + (TAIL_LAST if k == len(vd) - 1 else TAIL))
total = sum(d)
if total < 15.2:   # 正片 ≥15 秒（#10）：差多少平均補在每段尾巴（停留久一點，不灌重複畫面）
    add = (15.2 - total) / len(d); d = [x + add for x in d]; total = sum(d)
starts = [sum(d[:k]) for k in range(len(d))]
vstart = [starts[k] + (LEAD0 if k == 0 else LEAD) for k in range(len(d))]
print("旁白 %s：%s" % (a.vo, " / ".join("%.2f" % v for v in vd)), "總長 %.2f 秒" % total)

def t(s):
    return "%d:%02d:%05.2f" % (int(s // 3600), int(s % 3600 // 60), s % 60)

def colour(txt):
    for k in KEY:
        txt = txt.replace(k, r"{\c&H0000E5FF&}" + k + r"{\c&HFFFFFF&}")
    return txt

def pop(y, n, cap=100):
    """跳字：30% → 118% → 定格；字多（120 號字 >8 個）就等比縮到寬 ≤960，不出框"""
    s = min(cap, int(960 / (max(n, 1) * 120) * 100))
    return r"{\an5\pos(540,%d)\fscx30\fscy30\t(0,110,\fscx%d\fscy%d)\t(110,200,\fscx%d\fscy%d)}" % (y, int(s * 1.18), int(s * 1.18), s, s)
L = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
     "[V4+ Styles]",
     "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
     "Style: Big,Microsoft JhengHei,120,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,9,4,5,20,20,0,1",
     "Style: Box,Microsoft JhengHei,88,&H00FFFFFF,&H000000FF,&H002B2BE8,&H002B2BE8,-1,0,0,0,100,100,1,0,3,18,0,5,40,40,0,1", "",
     "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
pops = []
for k, txt in enumerate(lines):
    end = starts[k] + d[k] + (0 if k == len(lines) - 1 else X * 0.5)
    if k == len(lines) - 1:   # 最後一句＝紅底 CTA，跳兩下
        L.append("Dialogue: 2,%s,%s,Box,,0,0,0,,%s%s ▼" % (t(vstart[k]), t(end),
                 (r"{\an5\pos(540,%d)" % (CTAY or (1390 if SC[-1][0] == "CARD" else 470))) + r"\fscx30\fscy30\t(0,120,\fscx110\fscy110)\t(120,220,\fscx100\fscy100)\t(700,1000,\fscx106\fscy106)\t(1000,1300,\fscx100\fscy100)}", txt))
        pops.append(vstart[k]); continue
    parts = txt.split("，")
    if SUBSTYLE == "mid":
        MIDC = [r"{\c&HFFFFFF&\3c&H000000&\bord9}", r"{\c&H3CC8FF&\3c&H1A2A5A&\bord9\blur1}", r"{\c&HB469FF&\3c&HFFFFFF&\bord9}"]
        sty = MIDC[k % len(MIDC)]
        yk = MIDYS[k] if k < len(MIDYS) else MIDY
        if len(parts) == 1 and len(txt) > 8:
            parts = [txt.split("、")[0], txt.split("、", 1)[1]] if "、" in txt else [txt[:len(txt) // 2], txt[len(txt) // 2:]]
        if len(parts) == 1:
            L.append("Dialogue: 1,%s,%s,Big,,0,0,0,,%s%s%s" % (t(vstart[k]), t(end), pop(yk, len(parts[0]), MIDFS), sty, parts[0])); pops.append(vstart[k])
        else:
            t2 = vstart[k] + vd[k] * len(parts[0]) / len(txt.replace("，", "").replace("、", ""))
            L.append("Dialogue: 1,%s,%s,Big,,0,0,0,,%s%s%s" % (t(vstart[k]), t(t2), pop(yk, len(parts[0]), MIDFS), sty, parts[0]))
            L.append("Dialogue: 1,%s,%s,Big,,0,0,0,,%s%s%s" % (t(t2), t(end), pop(yk, len(parts[1]), MIDFS), sty, parts[1]))
            pops += [vstart[k], t2]
        continue
    if len(parts) == 1 and len(txt) > 8:   # 一句沒逗號又長：在「、」切，沒有就對半切
        parts = [txt.split("、")[0], txt.split("、", 1)[1]] if "、" in txt else [txt[:len(txt) // 2], txt[len(txt) // 2:]]
    if len(parts) == 1:
        L.append("Dialogue: 1,%s,%s,Big,,0,0,0,,%s%s" % (t(vstart[k]), t(end), pop(SUBY[2], len(parts[0])), colour(parts[0]))); pops.append(vstart[k])
    else:
        t2 = vstart[k] + vd[k] * len(parts[0]) / len(txt.replace("，", "").replace("、", ""))
        L.append("Dialogue: 1,%s,%s,Big,,0,0,0,,%s%s" % (t(vstart[k]), t(end), pop(SUBY[0], len(parts[0])), colour(parts[0])))
        L.append("Dialogue: 1,%s,%s,Big,,0,0,0,,%s%s" % (t(t2), t(end), pop(SUBY[1], len(parts[1])), colour(parts[1])))
        pops += [vstart[k], t2]
if TITLE:
    tend = starts[-1] if SC[-1][0] == "CARD" else sum(d) + X * (len(d) - 1)
    L.append("Dialogue: 3,%s,%s,Big,,0,0,0,,%s%s" % (t(0.15), t(tend), r"{\an5\pos(540,195)\fs%d\c&H0000E5FF&\3c&H000000&\bord8\shad3\i1\fad(250,0)}" % min(100, int(1250 / max(len(TITLE), 1))), TITLE))
tag = a.vo + ("-無跳字音" if a.nopop else "")
ass = "%ssample_%s.ass" % (PRE or "ph9_", tag)
open(ass, "w", encoding="utf-8").write("\n".join(L) + "\n")

cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
fc = []
FPS = 30
SWAY = "C:/Users/GesarChu/Desktop/Claude Code/shopee/tools/hand-sway.py"
KBR = "C:/Users/GesarChu/Desktop/Claude Code/shopee/tools/kb-render.py"
KB = os.environ.get("KB_OLD") != "1"   # 10/6：預設走次像素
for k, (img, z0, z1, cx, cy) in enumerate(SC):
    n = int(round((d[k] + (X if k < len(SC) - 1 else 0)) * FPS))
    if img.endswith("#sway"):   # 10/4 第 33 棒：手拿商品靜態圖 → 程式擺動成影片（王 10/3「這個也可以」；字是真圖、不給 AI 重畫）
        src = img[:-5]; os.makedirs("_sway", exist_ok=True)
        img = os.path.join("_sway", "%s%s_%d.mp4" % (PRE, os.path.splitext(os.path.basename(src))[0], k))
        subprocess.run(["py", "-3", SWAY, src, img, "%.2f" % (n / FPS + 0.4)], check=True)
    if img == "CARD":   # 收尾商品卡：真商品照放大彈進來，底色淡藍
        cmd += ["-i", REAL]
        fc.append("color=c=0xEAF4FB:s=1080x1920:r=%d:d=%.3f[bg%d]" % (FPS, n / FPS, k))
        fc.append("[%d:v]scale=%d:1000:force_original_aspect_ratio=decrease:flags=lanczos,format=rgba%s[pc%d]" % (k, CARDW, "" if REAL.endswith("_alpha.png") else ",colorkey=0xFFFFFF:0.08:0.02", k))  # 10/5：白色商品（OBgE）colorkey 會把白瓶身一起去掉 ⇒ 用 *_alpha.png（只去外圍白底）就不再 colorkey
        fc.append("[bg%d][pc%d]overlay=x='(W-w)/2':y='(1290-h)-if(gt(t,0.9),0,60*exp(-6*t)*cos(14*t))':shortest=0,format=yuv420p,setsar=1,trim=end_frame=%d[v%d]" % (k, k, n, k))
        continue
    cmd += ["-i", img]
    zexpr = "%.4f+(%.4f)*on/%d" % (z0, z1 - z0, max(n - 1, 1))
    if img.lower().endswith(".mp4"):   # 10/2 第 32 棒：影片鏡頭（H3 片段）——從 0.1 秒切入（略過第 0 格雜音），不夠長就停在最後一格，一樣可慢推
        fc.append("[%d:v]trim=start=0.1,setpts=PTS-STARTPTS,fps=%d,tpad=stop_mode=clone:stop_duration=10,trim=end_frame=%d,scale=2160:3840:flags=lanczos,"
                  "zoompan=z='%s':x='iw*%.3f-(iw/zoom/2)':y='ih*%.3f-(ih/zoom/2)':d=1:s=1080x1920:fps=%d,setsar=1,format=yuv420p[v%d]"
                  % (k, FPS, n, zexpr, cx, cy, FPS, k))
        continue
    if KB:   # 10/6 16:5x 第 34 棒：zoompan 整數跳格讓貼回的真品字閃（王退花王「字會略帶閃爍」）⇒ 改 tools/kb-render.py 浮點 box 逐格 LANCZOS（次像素）；KB_OLD=1 走舊路
        os.makedirs("_kb", exist_ok=True)
        kbm = os.path.join("_kb", "%s%d_%s.mp4" % (PRE, k, os.path.splitext(os.path.basename(img))[0]))
        subprocess.run(["py", "-3", KBR, img, kbm, "%.4f" % z0, "%.4f" % z1, "%.3f" % cx, "%.3f" % cy, str(n), str(FPS)], check=True)
        cmd[-1] = kbm   # 換掉上面剛加的 -i img
        fc.append("[%d:v]fps=%d,trim=end_frame=%d,setsar=1,format=yuv420p[v%d]" % (k, FPS, n, k))
        continue
    fc.append("[%d:v]scale=2160:3840:flags=lanczos,zoompan=z='%s':x='iw*%.3f-(iw/zoom/2)':y='ih*%.3f-(ih/zoom/2)':d=%d:s=1080x1920:fps=%d,setsar=1,format=yuv420p[v%d]"
              % (k, zexpr, cx, cy, n, FPS, k))
prev = "v0"
for k in range(1, len(SC)):
    out = "x%d" % k
    fc.append("[%s][v%d]xfade=transition=%s:duration=%.2f:offset=%.3f[%s]" % (prev, k, TRANS[(k - 1) % len(TRANS)], X, starts[k], out)); prev = out
fc.append("[%s]subtitles=%s[vout]" % (prev, ass))
ni = len(SC)
# 聲音：旁白（標準化）＋墊樂（小聲、尾端淡出）＋轉場 whoosh（王：不要太大聲）＋跳字 pop（可關）
for f in vo:
    cmd += ["-i", f]
cmd += ["-i", MUSIC, "-i", SFX + "transition/whoosh-1.mp3", "-i", SFX + "accent/bubble-pop-1.mp3"]
im, iw, ip = ni + len(vo), ni + len(vo) + 1, ni + len(vo) + 2
vl = []
for k in range(len(vo)):
    ms = int(vstart[k] * 1000)
    fc.append("[%d:a]aresample=48000,aformat=channel_layouts=mono,adelay=%d|%d[a%d]" % (ni + k, ms, ms, k)); vl.append("[a%d]" % k)
fc.append("%samix=inputs=%d:normalize=0,apad,atrim=0:%.3f,loudnorm=I=-15:TP=-1.5:LRA=7,aresample=48000[vo]" % ("".join(vl), len(vl), total))
fc.append("[%d:a]atrim=0:%.3f,volume=0.13,afade=t=in:d=0.4,afade=t=out:st=%.3f:d=1.0,aresample=48000[mu]" % (im, total, total - 1.0))
wl = []
fc.append("[%d:a]asplit=%d%s" % (iw, len(SC) - 1, "".join("[w%d]" % k for k in range(1, len(SC)))))
for k in range(1, len(SC)):
    ms = int((starts[k] - 0.15) * 1000)
    fc.append("[w%d]volume=0.08,afade=t=in:d=0.12,adelay=%d|%d[wd%d]" % (k, ms, ms, k)); wl.append("[wd%d]" % k)
mix = ["[vo]", "[mu]"] + wl
if not a.nopop:
    fc.append("[%d:a]asplit=%d%s" % (ip, len(pops), "".join("[p%d]" % k for k in range(len(pops)))))
    for k, p in enumerate(pops):
        ms = int(p * 1000)
        fc.append("[p%d]volume=0.30,adelay=%d|%d[pd%d]" % (k, ms, ms, k)); mix.append("[pd%d]" % k)
fc.append("%samix=inputs=%d:normalize=0,apad,atrim=0:%.3f,alimiter=limit=0.89[aout]" % ("".join(mix), len(mix), total))
out = "%s商品片樣品_%s.mp4" % (NAME, tag)
cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]", "-t", "%.3f" % total, "-r", str(FPS),
        "-c:v", "libx264", "-crf", "10", "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", out]
r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("ffmpeg", r.returncode, r.stderr[-1500:])
if r.returncode == 0:
    print(out, "%.2f 秒" % dur(out))
    # 2026-10-06：憑證＝這支成片是過了擋門組出來的（交片程式會對檔案指紋；成片或設定檔一改就失效）
    json.dump({"tool": "build_ph9_sample.py", "cfg": os.path.abspath(a.cfg).replace(os.sep, "/"), "cfg_sha1": hashlib.sha1(open(a.cfg, "rb").read()).hexdigest(),
               "out_sha1": hashlib.sha1(open(out, "rb").read()).hexdigest(), "gate": "tools/prodfilm.py gate 通過", "time": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
               "starts": [round(x, 3) for x in starts], "d": [round(x, 3) for x in d], "total": round(total, 3)},
              open(out + ".built.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for s in [starts[k] + d[k] - 0.25 for k in range(len(lines))]:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % s, "-i", out, "-frames:v", "1", "-vf", "scale=360:-1", "_格_%s%s_%.1f.jpg" % (PRE, tag, s)])
