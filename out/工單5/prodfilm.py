# -*- coding: utf-8 -*-
"""prodfilm.py — 純商品片的源頭擋門：商品卡＋真品貼回＋組片前檢查（2026-10-06 第 34 棒立）

為什麼有這支（王 10/6）：
  「現在開始每件對的SOP就寫死」「現在庫存不夠也是因為你們良率太差,所以先把源頭的問題解決」
  「像很多商品都有作過很多支了,但作過的商品後面也是有遇到圖片錯誤的問題,這部分我也認為不該發生才對」
查到的源頭：商品片每個場景都是 Qwen 畫的情境圖，畫面上的商品每次都被模型重畫一次，過不過關只看模型這次有沒有剛好畫對字；
  同一個商品做過十支，第十一支照樣會畫錯，因為沒有「一個商品一份驗過的真品素材」可以重用。
做法：一個商品建一張「商品卡」（驗過的真品去背照＋字的位置＋以前畫錯過什麼），之後這個商品每支片畫面上的商品一律從卡貼回去。
  沒有卡、沒人看過卡、沒貼回、貼壞、真品照太小、字幕壓到商品字或撞浮水印 ⇒ 組片程式中止。**沒有跳過參數。**

子指令：
  card    <商品卡簡稱> <真品照> --name <商品名> [--text-box x0,y0,x1,y1] [--inset 左右,上,下] [--note "以前畫錯過什麼"]
            建／更新商品卡：去背 → 量實心度與物件數 → 出確認圖。還不能用，要人打開確認圖看過再跑 card-ok。
            真品照條件：單一商品、不透明、正面、白底或已去背、越大越好（貼回去的清楚度上限＝這張照片的解析度）。
            text-box＝商品上「有印刷字」的範圍（相對商品外框的比例；不給＝用 inset 那一塊），字幕不准壓到這一塊。
  card-ok <商品卡簡稱> --by <誰看的> "<看到了什麼>"
            看過確認圖之後簽名（記下去背圖指紋，圖一換就失效）。
  lw      <設定檔簡稱> [--card <商品卡簡稱>] [--only 鏡號 …]
            設定檔每張場景圖：放大 2 倍 → tools/label-warp.py 把真品貼回 → 量測 → 寫憑證 → 總表圖；
            全部鏡頭都過，才把設定檔改成用貼回版（舊設定檔留備份）。
  gate    <設定檔路徑>
            組片前擋門。樣品/build_ph9_sample.py 一開始就會叫，回傳不是 0 就不組片；也可以單獨跑，看哪幾條沒過。
  sheet   <設定檔簡稱>
            組完片出驗片圖：加上蝦皮版浮水印後每鏡抓前後兩格＋每鏡一張「成片原尺寸的商品字區｜真品同一塊」並排。
            （工單 #5）出圖前先跑動態閃爍擋門 tools/motion-gate.py：量 30fps 母片的商品框，推近鏡頭有一段 FAIL 就不出圖、exit 2；
            片尾卡（彈跳之後）只警示。每鏡再用貼回憑證換算的 label 框跑 tools/ghost-text-gate.py，出「<商品名>-假字標記.jpg」（只警示）。
  film-ok <設定檔簡稱> --by <誰看的> "<每一鏡看到了什麼>"
            驗片圖都看過之後簽名。交片程式（產出/_1002交商品片2.py）沒有這張簽名就不交。
            （工單 #5）sheet 寫的動態閃爍結果（_驗片_<簡稱>/motion-gate.json）不在、指紋對不上、或不是 PASS ⇒ 拒簽。

整條流程（一個商品第一次做）：card → 看確認圖 → card-ok → 設定檔寫 title／sub_style=mid／mid_y=430／mid_fs=60 → lw → 看總表與每鏡對照
  → 組片（build_ph9_sample.py 自己會跑 gate）→ sheet → 看驗片圖 → film-ok → 交片到 P:/蝦皮短影音/_待驗-上架前/。
同一個商品第二次做：卡已經在，直接從 lw 開始。

門檻的依據（都寫在 RULE 旁邊）：10/6 凌晨 20 款 90 張批次貼回，人眼分好／壞之後回頭對量測數字（產出/對照/純商品做穩-20261006/批次結果2.tsv）。
"""
import argparse, hashlib, io, json, os, shutil, subprocess, sys, time
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = "C:/Users/GesarChu/Desktop/Claude Code/shopee"
PKG = ROOT + "/產出/腳本備妥-商品片樣品-20261002"
SMP = PKG + "/樣品"
CARDS = ROOT + "/素材/商品卡"
LWDIR = PKG + "/首幀/_貼回"
LW = ROOT + "/tools/label-warp.py"
WHOLE = ROOT + "/tools/prod-replace.py"
# 工單 #5（雲端 tools/ 四支 cp 進來：motion-gate.py、ghost-text-gate.py、label-box-map.py、gatelib.py；只靠 numpy／opencv／Pillow／ffmpeg）
MG = ROOT + "/tools/motion-gate.py"
GHOST = ROOT + "/tools/ghost-text-gate.py"
LBM = ROOT + "/tools/label-box-map.py"
GATE_BOX = "290,500,500,900"   # 動態閃爍量的商品框：builder 把商品放在畫面中央這一塊（工單 #5 校準用的就是這個框；設定檔 gate_box 可改）
XFADE, FILM_FPS = 0.30, 30     # build_ph9_sample.py 的轉場長度 X、母片格率 FPS（改 builder 要一起改）
CARD_SETTLE = 0.9              # 片尾卡真品照彈跳 0.9 秒後鎖死（build_ph9_sample.py CARD 分支 if(gt(t,0.9),0,…)）
FONT = "C:/Windows/Fonts/msjh.ttc"
OUT_W, OUT_H = 1080, 1920
DEF_INSET = "0.10,0.06,0.06"
# 浮水印佔的範圍（tools/brand-stamp.py：圖示左上角 130,260、寬 96；「特別蝦」三個字 x=236 y=290 字級 46＋陰影）
WM = (130, 260, 380, 360)

RULE = {
    # 貼回後跟貼之前比，整塊（模糊後）顏色平均差多少。只換字的話很小；真品照跟場景裡的商品不是同一個樣子、或貼歪，就會大。
    # 10/6 校準：人眼判「好」的 7 款 35 張有 32 張 ≤4.6；「貼壞」的 5 款 20 張全部 ≥5.6（多半 8–26）。
    # 被擋的 3 張好款（NIVEA 第 5 鏡 8.8＝瓶肩疊影、ELIXIR 第 1 鏡 7.1、第 5 鏡 5.8）放大看確實有輪廓不合，擋得對。
    "lowfreq_max": 5.0,
    # 真品去背照「實心度」＝商品面積／外凸包面積。白瓶身被去背吃掉（巴黎萊雅 0.63）、透明杯（evorie 0.79）會低；好的都 ≥0.89。
    "solidity_min": 0.88,
    # 貼片四個角偏離直角幾度、對邊長度比。好的 ≤4.6 度／≤1.10；貼歪的（Lador 16.9、32.6 度，歐客佬 11 度）遠超過。
    "angle_max": 5.0,
    "side_ratio_max": 1.10,
    # 成片上真品照被放大幾倍（>1＝真品照比畫面需要的小，貼回去會軟）。王 10/6 說「中間很清楚」的 NIVEA 第 3 鏡是 1.06。
    # 上限 1.30＝王 10/6 04:4x 看對照圖定的（同一瓶身放大 0.58／1.0／1.3／1.5／1.8 倍，圖在
    # 產出/對照/純商品做穩-20261006/清楚度對照-同一瓶身真品照放大不同倍數-成片原尺寸.jpg）：
    # 「最右邊開始可以清楚但明顯快開始糊了」「1.3比較保險」。⛔ 再放寬。
    # 真品照通常只有 600–900 像素高 ⇒ 商品在成片上最多約 780–1170 像素高（畫面高度的四到六成）；超過就換更大的真品照，或把場景裡的商品畫小一點。
    "final_scale_max": 1.30,
    "card_scale_max": 1.30,
    # 商品片定版樣式（王 10/3–10/5 核可，CLAUDE #124／#130）：上方品名標題 y=195＋講話那行小字 y≥430；往上會撞左上浮水印。
    "mid_y_min": 430,
    "mid_fs_max": 72,
}


class Stop(Exception):
    pass


def sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def jload(p):
    return json.load(io.open(p, encoding="utf-8"))


def jdump(o, p):
    io.open(p, "w", encoding="utf-8", newline="\n").write(json.dumps(o, ensure_ascii=False, indent=1) + "\n")


def same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


# ───────────────────────── 商品卡 ─────────────────────────
def to_alpha(src, out, tol=14):
    """真品照 → 去背 RGBA。原圖已去背就照用；白底的從四邊往內倒灌去白（商品裡面的白不動）。
    tol＝跟純白差多少以內算背景（預設 14）。白瓶、白蓋這種商品會被吃掉時用 --white-tol 2（10/6 Biore 瓶肩實測：瓶肩 251–253、背景 255）。"""
    im = Image.open(src)
    if im.mode == "RGBA" and (np.asarray(im)[..., 3] < 250).mean() > 0.03:
        im.save(out)
        return "原圖本來就去背"
    rgb = np.asarray(im.convert("RGB")); h, w = rgb.shape[:2]
    edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]); med = np.median(edge, 0)
    if med.min() < 222:
        raise Stop("真品照不是白底、也不是去背圖（四邊顏色 %s）。換一張白底或已去背的單一商品正面照。" % [int(v) for v in med])
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR); mask = np.zeros((h + 2, w + 2), np.uint8)
    pts = [(x, y) for x in range(0, w, 16) for y in (0, h - 1)] + [(x, y) for y in range(0, h, 16) for x in (0, w - 1)]
    for pt in pts:
        if rgb[pt[1], pt[0]].min() >= 222 and mask[pt[1] + 1, pt[0] + 1] == 0:
            cv2.floodFill(bgr.copy(), mask, pt, (0, 0, 0), (tol,) * 3, (tol,) * 3, flags=cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8))
    alpha = np.where(mask[1:-1, 1:-1] > 0, 0, 255).astype(np.uint8)
    alpha = cv2.GaussianBlur(cv2.erode(alpha, np.ones((3, 3), np.uint8)), (0, 0), 0.8)
    Image.fromarray(np.dstack([rgb, alpha])).save(out)
    return "白底去背" + ("" if tol == 14 else "（tol=%d）" % tol)


def measure_alpha(p):
    a = np.asarray(Image.open(p).convert("RGBA"))[..., 3]
    fg = (a > 128).astype(np.uint8); H, W = fg.shape
    if fg.sum() < 400:
        raise Stop("去背之後幾乎沒有東西，這張真品照不能用。")
    pts = np.argwhere(fg > 0)[:, ::-1].astype(np.int32)
    solid = float(fg.sum()) / max(1.0, float(cv2.contourArea(cv2.convexHull(pts))))
    n, _, st, _ = cv2.connectedComponentsWithStats(fg, 8)
    nobj = sum(1 for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 0.03 * fg.sum())
    ys, xs = np.where(fg > 0)
    return {"size": [int(W), int(H)], "solidity": round(solid, 3), "n_objects": int(nobj), "fg_ratio": round(float(fg.mean()), 3),
            "bbox_n": [round(float(xs.min()) / W, 4), round(float(ys.min()) / H, 4), round(float(xs.max() + 1) / W, 4), round(float(ys.max() + 1) / H, 4)]}


def inset_box(inset):
    ix, it, ib = [float(v) for v in inset.split(",")]
    return [ix, it, 1 - ix, 1 - ib]


def confirm_sheet(src, ref, outp, card):
    """確認圖：原圖｜去背貼洋紅底｜去背貼深灰底（綠框＝會貼回去的範圍、黃框＝有印刷字的範圍）。人要看：商品有沒有被吃掉、是不是單一正面、框有沒有框對。"""
    Hh = 900
    def fit(im):
        return im.resize((max(1, int(im.width * Hh / im.height)), Hh), Image.LANCZOS)
    o = fit(Image.open(src).convert("RGB"))
    r = Image.open(ref).convert("RGBA")
    def on(bg):
        b = Image.new("RGBA", r.size, bg); b.alpha_composite(r)
        return fit(b.convert("RGB"))
    m, g = on((255, 0, 255, 255)), on((60, 60, 60, 255))
    d = ImageDraw.Draw(g); bb = card["bbox_n"]; W, H = g.size
    def rect(tb, col):
        x0 = (bb[0] + tb[0] * (bb[2] - bb[0])) * W; x1 = (bb[0] + tb[2] * (bb[2] - bb[0])) * W
        y0 = (bb[1] + tb[1] * (bb[3] - bb[1])) * H; y1 = (bb[1] + tb[3] * (bb[3] - bb[1])) * H
        d.rectangle((x0, y0, x1, y1), outline=col, width=4)
    rect(inset_box(card["inset"]), (0, 230, 0))
    if card.get("text_box"):
        rect(card["text_box"], (255, 220, 0))
    gap = 16; head = 120
    sheet = Image.new("RGB", (o.width + m.width + g.width + gap * 2, Hh + head), "white")
    x = 0
    for im in (o, m, g):
        sheet.paste(im, (x, head)); x += im.width + gap
    f1, f2 = ImageFont.truetype(FONT, 30), ImageFont.truetype(FONT, 24)
    ds = ImageDraw.Draw(sheet)
    ds.text((10, 6), "商品卡 %s｜%s｜真品照 %dx%d｜實心度 %.2f（要 ≥%.2f）｜物件數 %d（要 1）" % (
        card["key"], card["name"], card["size"][0], card["size"][1], card["solidity"], RULE["solidity_min"], card["n_objects"]), font=f1, fill=(200, 0, 0) if card.get("blocked") else (0, 0, 0))
    ds.text((10, 48), "左＝原圖　中＝去背後貼在洋紅底（看商品有沒有被吃掉、邊緣有沒有白邊）　右＝綠框是會貼回去的範圍、黃框是有印刷字的範圍（字幕不准壓）", font=f2, fill=(60, 60, 60))
    ds.text((10, 82), "要看：①單一商品、正面、不透明　②去背沒有吃掉商品本身　③框有框到全部的字。都對才跑 card-ok。", font=f2, fill=(60, 60, 60))
    sheet.save(outp, quality=92)


def cmd_card(a):
    d = CARDS + "/" + a.key; os.makedirs(d, exist_ok=True); cj = d + "/card.json"
    old = jload(cj) if os.path.exists(cj) else {}
    if old and old.get("name") != a.name:
        raise Stop("簡稱 %s 已經是「%s」的商品卡，不能拿來給「%s」。換一個簡稱（先 ls 素材/商品卡 看有哪些）。" % (a.key, old.get("name"), a.name))
    if not os.path.exists(a.src):
        raise Stop("找不到真品照 " + a.src)
    ref = d + "/%s_alpha.png" % a.key
    if os.path.exists(ref):
        shutil.copy2(ref, ref[:-4] + ".BEFORE-%s.png" % time.strftime("%Y%m%d-%H%M%S"))
    how = to_alpha(a.src, ref, a.white_tol)
    m = measure_alpha(ref)
    blocked = []
    if m["solidity"] < RULE["solidity_min"]:
        blocked.append("實心度 %.2f < %.2f：商品被去背吃掉（白色／透明商品），或照片裡不只一個東西。換一張照片，或先手動去背成 RGBA png 再建卡。" % (m["solidity"], RULE["solidity_min"]))
    if m["n_objects"] != 1:
        blocked.append("照片裡有 %d 個分開的東西：商品卡要單一商品正面照（組合圖、盒＋瓶、多包疊在一起的會貼壞）。" % m["n_objects"])
    card = {"key": a.key, "name": a.name, "ref": os.path.basename(ref), "src": a.src.replace("\\", "/"), "src_sha1": sha1(a.src), "ref_sha1": sha1(ref),
            "how": how, "inset": a.inset or old.get("inset") or DEF_INSET,
            "text_box": ([float(v) for v in a.text_box.split(",")] if a.text_box else old.get("text_box")),
            "lw_args": (a.lw_args.split() if a.lw_args else old.get("lw_args") or []),
            "notes": (old.get("notes") or []) + ([a.note] if a.note else []),
            "created": old.get("created") or now(), "updated": now(), "blocked": blocked, "ok": None}
    card.update(m)
    # 去背圖、貼回範圍、字區都沒變（只改備註或貼回參數）⇒ 之前看過確認圖的簽名還有效
    if old.get("ok") and not blocked and old.get("ref_sha1") == card["ref_sha1"] and old.get("inset") == card["inset"] and old.get("text_box") == card["text_box"]:
        card["ok"] = old["ok"]
    jdump(card, cj)
    sheet = d + "/%s_確認圖.jpg" % a.key
    confirm_sheet(a.src, ref, sheet, card)
    print("商品卡 %s｜%s｜%s｜真品照 %dx%d｜實心度 %.2f｜物件數 %d" % (a.key, a.name, how, m["size"][0], m["size"][1], m["solidity"], m["n_objects"]))
    print("確認圖：" + sheet)
    if blocked:
        for b in blocked:
            print("XX " + b)
        return 2
    if card["ok"]:
        print("去背圖和框都沒變，之前的簽名還有效（%s）。" % card["ok"].get("by")); return 0
    print("下一步：打開確認圖看過（商品有沒有被吃掉、是不是單一正面、框有沒有框到全部的字），再跑：")
    print('  py -3 tools/prodfilm.py card-ok %s --by <誰看的> "<看到了什麼>"' % a.key)
    return 0


def cmd_card_ok(a):
    d = CARDS + "/" + a.key; cj = d + "/card.json"
    if not os.path.exists(cj):
        raise Stop("沒有商品卡 %s，先跑 card。" % a.key)
    c = jload(cj); ref = d + "/" + c["ref"]
    if c.get("blocked"):
        raise Stop("商品卡 %s 沒過量測，不能簽：%s" % (a.key, "；".join(c["blocked"])))
    if not os.path.exists(d + "/%s_確認圖.jpg" % a.key):
        raise Stop("沒有確認圖，重跑 card。")
    if sha1(ref) != c["ref_sha1"]:
        raise Stop("去背圖在建卡之後被換過，重跑 card。")
    if len(a.note.strip()) < 12:
        raise Stop("要寫清楚看到了什麼（至少一句完整的話：是哪個商品的哪一面、去背有沒有吃掉、框有沒有框到全部的字）。")
    c["ok"] = {"time": now(), "by": a.by, "note": a.note.strip(), "ref_sha1": c["ref_sha1"]}
    jdump(c, cj)
    print("已簽：商品卡 %s（%s）｜%s｜%s" % (a.key, c["name"], a.by, a.note.strip()))
    return 0


def load_card(k):
    cj = CARDS + "/%s/card.json" % k
    if not os.path.exists(cj):
        raise Stop("沒有商品卡「%s」。先建卡：py -3 tools/prodfilm.py card %s <單一商品正面的真品照> --name <商品名>" % (k, k))
    c = jload(cj); ref = CARDS + "/%s/%s" % (k, c["ref"])
    if c.get("blocked"):
        raise Stop("商品卡「%s」沒過量測：%s" % (k, "；".join(c["blocked"])))
    if not c.get("ok"):
        raise Stop("商品卡「%s」還沒有人看過確認圖（%s/%s_確認圖.jpg）。看過再跑 card-ok。" % (k, CARDS + "/" + k, k))
    if not os.path.exists(ref) or sha1(ref) != c["ref_sha1"] or c["ok"].get("ref_sha1") != c["ref_sha1"]:
        raise Stop("商品卡「%s」的去背圖在簽名之後被換過，重跑 card＋card-ok。" % k)
    c["_ref"] = ref
    return c


# ───────────────────────── 貼回 ─────────────────────────
def scene_base(cdir, cf):
    base = cf.get("img_dir", "../首幀/_候選/")
    return base if os.path.isabs(base) else os.path.normpath(os.path.join(cdir, base))


def judge(cert, card, z0, z1):
    """一張貼回圖過不過。回傳沒過的原因清單（空＝過）。"""
    mode = replacement_mode(card)
    if replacement_mode(cert) != mode:
        return ["商品卡 replace_mode 已改，重跑 lw。"]
    if mode == "whole":
        return judge_whole(cert, card, z0, z1)
    if not cert.get("warp_ok"):
        return ["貼不回去（%s）：這張場景裡的商品跟真品照對不上——商品沒什麼印刷字、角度太側、或畫得跟真品差太多。換一張場景圖。" % cert.get("warp_msg", "")[:60]]
    m = cert["metrics"]; f = []
    if "s_up" not in m:
        return ["憑證是舊格式（沒有真品照倍率），重跑 lw。"]
    if m["lowfreq_mean"] > RULE["lowfreq_max"]:
        f.append("低頻差 %.1f > %.1f：貼片把整塊顏色或輪廓換掉了（真品照跟場景裡畫的商品不是同一個樣子，或瓶肩／邊緣疊影）。調 inset 只貼有字那一塊，或換場景圖。" % (m["lowfreq_mean"], RULE["lowfreq_max"]))
    if m["ref_solidity"] < RULE["solidity_min"]:
        f.append("真品照實心度 %.2f < %.2f" % (m["ref_solidity"], RULE["solidity_min"]))
    if m["angle_dev"] > RULE["angle_max"]:
        f.append("貼片四角偏 %.1f 度 > %.1f：貼歪了。" % (m["angle_dev"], RULE["angle_max"]))
    if m["side_ratio"] > RULE["side_ratio_max"]:
        f.append("貼片對邊比 %.2f > %.2f：貼歪了。" % (m["side_ratio"], RULE["side_ratio_max"]))
    fs = final_scale(cert, z0, z1)
    if fs > RULE["final_scale_max"]:
        f.append("真品照太小：成片上被放大 %.2f 倍 > %.2f，貼回去的字會軟。換更大的真品照重建商品卡（或把這一鏡的縮放調小）。" % (fs, RULE["final_scale_max"]))
    return f


def final_scale(cert, z0, z1):
    m = cert["metrics"]
    if replacement_mode(cert) == "whole":
        return m["scale"] * OUT_W / float(m["scene_size"][0]) * max(z0, z1)
    return m["s_up"] * max(m["scale_x"], m["scale_y"]) * OUT_W / float(m["scene_size"][0]) * max(z0, z1)


def cmd_lw(a):
    cfgp = SMP + "/sample_%s.json" % a.key
    if not os.path.exists(cfgp):
        raise Stop("沒有設定檔 " + cfgp)
    cf = jload(cfgp); ck = a.card or cf.get("card")
    if not ck:
        raise Stop("設定檔沒寫用哪張商品卡：加 --card <商品卡簡稱>（先 ls 素材/商品卡）。")
    card = load_card(ck); ref = card["_ref"]
    base = scene_base(SMP, cf)
    if replacement_mode(card) == "whole":
        return cmd_lw_whole(a, cfgp, cf, ck, card, base)
    outdir = LWDIR + "/" + ck; tmp = LWDIR + "/_tmp"
    os.makedirs(outdir, exist_ok=True); os.makedirs(tmp, exist_ok=True)
    rows = []; new_names = {}
    for i, s in enumerate(cf["scenes"], 1):
        name = s[0]
        if name == "CARD":
            continue
        sway = name.endswith("#sway"); nm = name[:-5] if sway else name
        if nm.lower().endswith(".mp4"):
            rows.append((i, nm, None, ["影片鏡頭：商品片只用靜態圖＋程式縮放（影片裡的商品是逐格重畫的，還沒有逐格貼回的憑證）。"])); continue
        p = os.path.normpath(os.path.join(base, nm))
        src = jload(p + ".lw.json")["src"] if os.path.exists(p + ".lw.json") else p
        if not os.path.exists(src):
            rows.append((i, nm, None, ["找不到場景圖 " + src])); continue
        out = outdir + "/" + os.path.splitext(os.path.basename(src))[0] + "_lw2x.png"
        certp = out + ".lw.json"
        if a.only and i not in a.only and os.path.exists(certp):
            cert = jload(certp)
        else:
            im = Image.open(src).convert("RGB"); x2 = tmp + "/x2.png"
            im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save(x2)
            jf = tmp + "/lw.json"
            if os.path.exists(jf):
                os.replace(jf, jf + ".old")
            ins = (cf.get("lw_insets") or {}).get(str(i)) or card.get("inset") or DEF_INSET
            cmd = ["py", "-3", LW, x2, out, "--ref", ref, "--inset", ins, "--json", jf] + (["--keep-skin"] if sway else []) + list(card.get("lw_args") or [])
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            line = (r.stdout.strip().splitlines() or [r.stderr.strip()[-160:]])[-1]
            ok = r.returncode == 0 and os.path.exists(out) and os.path.exists(jf)
            cert = {"tool": "prodfilm.py lw", "time": now(), "card": ck, "ref_sha1": card["ref_sha1"], "src": src.replace("\\", "/"), "src_sha1": sha1(src),
                    "inset": ins, "lw_args": list(card.get("lw_args") or []), "keep_skin": sway, "warp_ok": ok, "warp_msg": line.split("、對照圖")[0]}
            if ok:
                cert["out_sha1"] = sha1(out); cert["metrics"] = jload(jf)
            cert["replace_mode"] = "label"
            jdump(cert, certp)
        fails = judge(cert, card, s[1], s[2])
        rows.append((i, os.path.basename(src), cert, fails))
        if not fails:
            new_names[i] = os.path.relpath(out, base).replace("\\", "/") + ("#sway" if sway else "")
    # 總表圖：每鏡一列（左＝模型畫的、中＝貼回後（綠框＝貼片位置）、右＝真品照），上面印數字與判定
    f1 = ImageFont.truetype(FONT, 26); strips = []
    for i, nm, cert, fails in rows:
        cmp_ = (LWDIR + "/" + ck + "/" + os.path.splitext(nm)[0] + "_lw2x_對照.jpg") if cert and cert.get("warp_ok") else None
        if cmp_ and os.path.exists(cmp_):
            im = Image.open(cmp_).convert("RGB"); im = im.resize((int(im.width * 620 / im.height), 620), Image.LANCZOS)
        else:
            im = Image.new("RGB", (900, 120), (235, 235, 235))
        st = Image.new("RGB", (max(im.width, 1500), im.height + 40), "white"); st.paste(im, (0, 40))
        if cert and cert.get("warp_ok"):
            m = cert["metrics"]
            txt = "鏡%d %s｜%s｜低頻差 %.1f 四角偏 %.1f 對邊比 %.2f 成片放大 %.2f 倍" % (i, "過" if not fails else "沒過", nm[:34], m["lowfreq_mean"], m["angle_dev"], m["side_ratio"], final_scale(cert, cf["scenes"][i - 1][1], cf["scenes"][i - 1][2]))
        else:
            txt = "鏡%d 沒過｜%s｜%s" % (i, nm[:34], (fails or [""])[0][:60])
        ImageDraw.Draw(st).text((6, 4), txt, font=f1, fill=(0, 120, 0) if not fails else (200, 0, 0))
        strips.append(st)
    if strips:
        W = max(s_.width for s_ in strips); sheet = Image.new("RGB", (W, sum(s_.height for s_ in strips)), "white"); y = 0
        for s_ in strips:
            sheet.paste(s_, (0, y)); y += s_.height
        sp = outdir + "/%s_貼回總表.jpg" % a.key; sheet.save(sp, quality=90)
    print("== %s（%s）用商品卡 %s｜真品照 %dx%d" % (a.key, cf.get("name", ""), ck, card["size"][0], card["size"][1]))
    bad = 0
    for i, nm, cert, fails in rows:
        if fails:
            bad += 1
            print("  鏡%d XX %s" % (i, nm))
            for f in fails:
                print("       - " + f)
        else:
            m = cert["metrics"]
            print("  鏡%d 過 %s｜低頻差 %.1f、四角偏 %.1f 度、對邊比 %.2f、成片放大 %.2f 倍" % (i, nm, m["lowfreq_mean"], m["angle_dev"], m["side_ratio"], final_scale(cert, cf["scenes"][i - 1][1], cf["scenes"][i - 1][2])))
    if strips:
        print("總表圖（量測過了不等於對，人要原尺寸看每一鏡的字）：" + sp)
        print("每鏡原尺寸對照：%s/<場景檔名>_lw2x_對照.jpg" % outdir)
    if bad:
        print("XX %d 鏡沒過，設定檔沒有改。修法：調這一鏡的 inset（設定檔 lw_insets: {\"鏡號\": \"左右,上,下\"}）、換場景圖、或換更大的真品照。" % bad)
        return 2
    bak = cfgp + ".BEFORE-lw-" + time.strftime("%Y%m%d-%H%M%S"); shutil.copy2(cfgp, bak)
    for i, n in new_names.items():
        cf["scenes"][i - 1][0] = n
    cf["card"] = ck; cf["real"] = ref
    jdump(cf, cfgp)
    print("全部鏡頭都過：設定檔已改成用貼回版＋片尾卡用商品卡的去背照（舊的備份 %s）。" % os.path.basename(bak))
    return 0


# ───────────────────────── 組片前擋門 ─────────────────────────
def text_w(s, fs):
    return sum(fs if ord(c) > 0x2E7F else fs * 0.56 for c in s)


def sub_parts(txt):
    """跟 build_ph9_sample.py 的 mid 樣式同一套切法。"""
    parts = txt.split("，")
    if len(parts) == 1 and len(txt) > 8:
        parts = [txt.split("、")[0], txt.split("、", 1)[1]] if "、" in txt else [txt[:len(txt) // 2], txt[len(txt) // 2:]]
    return parts


def sub_band(txt, y, mid_fs):
    best = None
    for p in sub_parts(txt):
        s = min(mid_fs, int(960 / (max(len(p), 1) * 120) * 100)); fs = 120 * s / 100.0; w = text_w(p, fs)
        r = (540 - w / 2 - 13, y - fs / 2 - 13, 540 + w / 2 + 13, y + fs / 2 + 13)
        if best is None or (r[2] - r[0]) > (best[2] - best[0]):
            best = r
    return best


def title_band(title):
    fs = min(100, int(1250 / max(len(title), 1))); w = text_w(title, fs) + fs * 0.12   # 斜體往右多一點
    return (540 - w / 2 - 11, 195 - fs / 2 - 11, 540 + w / 2 + 11, 195 + fs / 2 + 11)


def overlap(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]) > 4 and min(a[3], b[3]) - max(a[1], b[1]) > 4


def label_rects(cert, card, z0, z1, cx, cy):
    """商品上有印刷字的那一塊，在成片（1080×1920）上的位置；鏡頭縮放的起點、終點各一個。"""
    m = cert["metrics"]; W0, H0 = m["scene_size"]
    Hq = cv2.getPerspectiveTransform(np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), np.float32(m["quad"]))
    bb = card["bbox_n"]; tb = card.get("text_box") or inset_box(cert.get("inset") or card.get("inset") or DEF_INSET)
    if replacement_mode(cert) == "whole":
        # Whole engine quad encloses the alpha crop, not the original padded image.
        rb = m["ref_box"]; rw, rh = m["ref_size"]
        bb = [(bb[0]*rw-rb[0])/(rb[2]-rb[0]), (bb[1]*rh-rb[1])/(rb[3]-rb[1]),
              (bb[2]*rw-rb[0])/(rb[2]-rb[0]), (bb[3]*rh-rb[1])/(rb[3]-rb[1])]
    u0, u1 = bb[0] + tb[0] * (bb[2] - bb[0]), bb[0] + tb[2] * (bb[2] - bb[0])
    v0, v1 = bb[1] + tb[1] * (bb[3] - bb[1]), bb[1] + tb[3] * (bb[3] - bb[1])
    pts = cv2.perspectiveTransform(np.float32([[u0, v0], [u1, v0], [u1, v1], [u0, v1]]).reshape(-1, 1, 2), Hq).reshape(-1, 2)
    pts = pts / np.float32([W0, H0]); out = []
    for z in (z0, z1):
        x0n = min(max(cx - 0.5 / z, 0.0), 1 - 1.0 / z); y0n = min(max(cy - 0.5 / z, 0.0), 1 - 1.0 / z)
        X = (pts[:, 0] - x0n) * z * OUT_W; Y = (pts[:, 1] - y0n) * z * OUT_H
        out.append((float(X.min()), float(Y.min()), float(X.max()), float(Y.max())))
    return out


def label_rect_at(cert, card, z, cx, cy):
    return label_rects(cert, card, z, z, cx, cy)[0]


def cmd_gate(a):
    cfgp = os.path.abspath(a.cfg); cdir = os.path.dirname(cfgp)
    cf = jload(cfgp); F = []; N = []
    scenes = cf.get("scenes", [])
    try:
        lines = [l.strip() for l in io.open(os.path.join(cdir, cf["lines"]), encoding="utf-8") if l.strip()]
    except Exception as e:
        lines = []; F.append("讀不到台詞檔：%s" % e)
    if lines and len(lines) != len(scenes):
        F.append("台詞 %d 句、場景 %d 個，數量對不上。" % (len(lines), len(scenes)))
    # 一、定版樣式
    title = cf.get("title", "")
    if not title:
        F.append("沒有 title：商品片上方要有品名標題（定版樣式）。")
    if cf.get("sub_style") != "mid":
        F.append("sub_style 不是 mid：舊樣式的兩行大字（y 420／560）會撞左上浮水印、壓到商品字，商品片一律用定版樣式（標題 y=195＋講話那行 y≥430）。")
    mid_y = cf.get("mid_y", 1100); ys = cf.get("sub_ys", []); mid_fs = cf.get("mid_fs", 100)
    for y in [mid_y] + list(ys):
        if y < RULE["mid_y_min"]:
            F.append("字幕 y=%s < %d：往上會撞「特別蝦」浮水印。" % (y, RULE["mid_y_min"]))
    if mid_fs > RULE["mid_fs_max"]:
        F.append("mid_fs=%s > %d：講話那行要小字（定版 60）。" % (mid_fs, RULE["mid_fs_max"]))
    if title:
        tbnd = title_band(title)
        if tbnd[0] < 10 or tbnd[2] > OUT_W - 10:
            F.append("標題「%s」太長，會出框（估計寬 %d）。" % (title, tbnd[2] - tbnd[0]))
        if overlap(tbnd, WM):
            F.append("標題會撞到左上浮水印。")
    # 二、商品卡
    card = None
    if not cf.get("card"):
        F.append("設定檔沒有 card：這個商品還沒建商品卡／場景圖還沒貼回。先跑 py -3 tools/prodfilm.py card …、card-ok …、lw <簡稱> --card <商品卡簡稱>。")
    else:
        try:
            card = load_card(cf["card"])
        except Stop as e:
            F.append(str(e))
    # 三、片尾卡
    if scenes and scenes[-1][0] == "CARD" and card:
        real = cf.get("real", "")
        if not same(real, card["_ref"]):
            F.append("片尾卡的真品照（real）不是商品卡的去背照：片尾卡一律用商品卡那張（舊做法對白底圖用去白色鍵，會把商品裡的白一起去掉）。")
        else:
            w, h = card["size"]; cs = min(cf.get("card_w", 900) / float(w), 1000.0 / h)
            if cs > RULE["card_scale_max"]:
                F.append("片尾卡的真品照太小：會被放大 %.2f 倍 > %.2f。換更大的真品照重建商品卡，或把 card_w 調小。" % (cs, RULE["card_scale_max"]))
            else:
                N.append("片尾卡：商品卡去背照，放大 %.2f 倍" % cs)
    # 四、每一鏡
    base = scene_base(cdir, cf)
    for i, s in enumerate(scenes, 1):
        name = s[0]
        if name == "CARD":
            continue
        if name.endswith("#sway"):
            F.append("鏡%d 是手拿擺動鏡頭：第二版（手拿搖動）的擋門還沒寫好，先把純商品版做穩（三版順序，CLAUDE #132）。" % i); continue
        if name.lower().endswith(".mp4"):
            F.append("鏡%d 是影片鏡頭：商品片只用靜態圖＋程式縮放（影片裡的商品是逐格重畫的）。" % i); continue
        p = os.path.normpath(os.path.join(base, name)); certp = p + ".lw.json"
        if not os.path.exists(p):
            F.append("鏡%d 找不到圖 %s" % (i, p)); continue
        if not os.path.exists(certp):
            F.append("鏡%d 沒有貼回憑證（%s）：場景圖裡的商品是模型畫的，還沒把真品貼回去。先跑 py -3 tools/prodfilm.py lw <簡稱>。" % (i, os.path.basename(name))); continue
        cert = jload(certp)
        if not cert.get("warp_ok") or cert.get("out_sha1") != sha1(p):
            F.append("鏡%d 的圖跟憑證對不上（貼回之後被改過，或貼回失敗）：重跑 lw。" % i); continue
        if card and (cert.get("card") != cf.get("card") or cert.get("ref_sha1") != card["ref_sha1"] or list(cert.get("lw_args") or []) != list(card.get("lw_args") or []) or replacement_mode(cert) != replacement_mode(card)):
            F.append("鏡%d 是用別張／舊的真品照或舊的貼回參數貼的：商品卡改過就要重跑 lw。" % i); continue
        if not card:
            continue
        if replacement_mode(card) == "whole" and cert.get("metrics", {}).get("output_sha256") != file_sha256(p):
            F.append("鏡%d 整支替換引擎憑證與主 PNG 不符，重跑 lw。" % i); continue
        fl = judge(cert, card, s[1], s[2])
        for f in fl:
            F.append("鏡%d %s" % (i, f))
        rects = label_rects(cert, card, s[1], s[2], s[3], s[4])
        # 整支商品的外框（含沒有字的瓶蓋、壓頭）：10/6 NIVEA 第一次組出來，字幕蓋到壓頭（沒壓到字，但看起來就是字幕壓在商品上）⇒ 一樣擋
        prects = label_rects(cert, dict(card, text_box=[0.0, 0.0, 1.0, 1.0]), s[1], s[2], s[3], s[4])
        if title:
            if any(overlap(tbnd, r) for r in rects):
                F.append("鏡%d 標題壓到商品上的字（標題 y %d–%d、商品字區 y %d–%d）。把這一鏡的畫面往下對（調 cy）或換場景圖。" % (i, tbnd[1], tbnd[3], min(r[1] for r in rects), max(r[3] for r in rects)))
            elif any(overlap(tbnd, r) for r in prects):
                F.append("鏡%d 標題蓋到商品（商品上緣 y %d）。把這一鏡的 cy 調小，或換一張商品站低一點的場景圖。" % (i, min(r[1] for r in prects)))
        if i <= len(lines) and i < len(scenes):
            y = ys[i - 1] if i - 1 < len(ys) else mid_y
            sb = sub_band(lines[i - 1], y, mid_fs)
            if overlap(sb, WM):
                F.append("鏡%d 字幕撞到左上浮水印（字幕 x %d–%d y %d–%d）。" % (i, sb[0], sb[2], sb[1], sb[3]))
            if any(overlap(sb, r) for r in rects):
                r = [r for r in rects if overlap(sb, r)][0]
                F.append("鏡%d 字幕壓到商品上的字（字幕 y %d–%d、商品字區 x %d–%d y %d–%d）。設定檔 sub_ys 給這一鏡換一個不壓字的 y（≥%d），或調鏡頭位置。" % (i, sb[1], sb[3], r[0], r[2], r[1], r[3], RULE["mid_y_min"]))
            elif any(overlap(sb, r) for r in prects):
                F.append("鏡%d 字幕蓋到商品（字幕 y %d–%d；商品上緣：鏡頭起點 y %d、終點 y %d）。把這一鏡的 cy 調小（鏡頭推近時畫面上緣不動、商品往下走），或換一張商品站低一點的場景圖。" % (i, sb[1], sb[3], prects[0][1], prects[1][1]))
        if not fl:
            if replacement_mode(card) == "whole":
                N.append("鏡%d 過：whole 規則全過；貼字三項 n/a、成片放大 %.2f 倍、商品字區 y %d–%d" % (i, final_scale(cert, s[1], s[2]), min(r[1] for r in rects), max(r[3] for r in rects)))
            else:
                N.append("鏡%d 過：低頻差 %.1f、成片放大 %.2f 倍、商品字區 y %d–%d" % (i, cert["metrics"]["lowfreq_mean"], final_scale(cert, s[1], s[2]), min(r[1] for r in rects), max(r[3] for r in rects)))
    print("== 商品片擋門｜%s（%s）" % (os.path.basename(cfgp), cf.get("name", "")))
    for n in N:
        print("  ○ " + n)
    if F:
        for f in F:
            print("  ⛔ " + f)
        print("⛔ 沒過 %d 條，不能組片。（沒有跳過參數；量測過了也不等於對，組完還是要原尺寸看每一鏡的字。）" % len(F))
        return 2
    print("○ 擋門全過。組完片之後還是要原尺寸看每一鏡商品上的字，再交到待驗資料夾。")
    return 0


# ───────────────────────── 組完片：原尺寸驗片圖＋人看過的簽名 ─────────────────────────
def film_paths(key, vo):
    cfgp = SMP + "/sample_%s.json" % key
    if not os.path.exists(cfgp):
        raise Stop("沒有設定檔 " + cfgp)
    cf = jload(cfgp); mp4 = SMP + "/%s商品片樣品_%s.mp4" % (cf["name"], vo); bj = mp4 + ".built.json"
    if not os.path.exists(mp4) or not os.path.exists(bj):
        raise Stop("沒有過了擋門組出來的成片（%s 或它的 .built.json 不在）。先組片：cd 樣品 && py -3 build_ph9_sample.py --vo %s --cfg sample_%s.json" % (os.path.basename(mp4), vo, key))
    b = jload(bj)
    if b.get("out_sha1") != sha1(mp4):
        raise Stop("成片在組完之後被改過（指紋對不上），重新組片。")
    return cfgp, cf, mp4, b


def run_py(args):
    return subprocess.run(["py", "-3"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")


def motion_gate_hard(mp4, cf, b, od):
    """工單 #5-C①：動態閃爍硬擋。量 30fps 母片（不是 24fps 浮水印版：brand-stamp fps=24 丟格會讓新舊片都 0.3 以上）的商品框。
    推近鏡頭（片尾卡之前）有一段 FAIL ⇒ Stop（exit 2），不出驗片圖。片尾卡從彈跳結束後另外量，只警示（原因待查，見工單5報告 A）。
    結果不管過不過都寫 od/motion-gate.json：film-ok 讀它，不是 PASS 就拒簽。**沒有跳過參數。**"""
    for p in (MG,):
        if not os.path.exists(p):
            raise Stop("沒有 %s：把雲端 tools/ 的 motion-gate.py、ghost-text-gate.py、label-box-map.py、gatelib.py 複製進來" % p)
    starts = b["starts"]; has_card = cf["scenes"][-1][0] == "CARD"
    box = cf.get("gate_box", GATE_BOX); sj = od + "/motion-gate.json"
    if os.path.exists(sj):
        os.remove(sj)   # 舊結果作廢：這次沒跑完就沒有結果檔，film-ok 會拒簽
    js = od + "/_motion_scenes.json"
    args = [MG, mp4, "--box", box, "--json", js] + (["--end", "%.3f" % starts[-1]] if has_card else [])
    r = run_py(args)
    if r.returncode not in (0, 1) or not os.path.exists(js):
        raise Stop("動態閃爍擋門跑不起來（motion-gate exit %d）：%s" % (r.returncode, (r.stdout + r.stderr)[-400:]))
    res = {"out_sha1": b["out_sha1"], "time": now(), "tool": "tools/motion-gate.py", "box": box, "scenes": jload(js)}
    res["verdict"] = res["scenes"]["verdict"]
    if has_card:
        jc = od + "/_motion_card.json"
        rc = run_py([MG, mp4, "--box", box, "--json", jc, "--start", "%.3f" % (starts[-1] + CARD_SETTLE)])
        res["card"] = jload(jc) if os.path.exists(jc) else {"verdict": "ERROR", "log": (rc.stdout + rc.stderr)[-400:]}
    jdump(res, sj)
    if res["verdict"] != "PASS":
        bad = ["格%d–%d（%.1f–%.1f 秒）比 %.2f：%s" % (s["start"], s["end"], s["t0"], s["t1"], s["ratio"], s["reason"])
               for s in res["scenes"]["segments"] if s["verdict"] == "FAIL"]
        raise Stop("動態閃爍擋門 FAIL（商品框 %s，門檻 %.2f）：%s。不出驗片圖。推近要走 kb-render（不要設 KB_OLD=1）重組再跑 sheet。"
                   % (box, res["scenes"]["threshold"], "；".join(bad)))
    print("○ 動態閃爍擋門 PASS（推近鏡頭 %d 段，比值最大 %.2f／門檻 %.2f）" % (
        len(res["scenes"]["segments"]), max([s["ratio"] for s in res["scenes"]["segments"] if s["verdict"] != "SKIP"] or [0]), res["scenes"]["threshold"]))
    if has_card and res["card"].get("verdict") != "PASS":
        print("⚠️ 片尾卡（彈跳之後）動態 %s：%s——先只警示，打開成片看片尾卡有沒有東西在動" % (
            res["card"].get("verdict"), "；".join(s.get("reason", "") for s in res["card"].get("segments", []) if s.get("verdict") == "FAIL")))
    return res


def ghost_marks(mp4, cf, b, od, base):
    """工單 #5-C②：每鏡用貼回憑證換算的 label 框（tools/label-box-map.py，照 kb-render 算法）跑 tools/ghost-text-gate.py，
    拼成一張「<商品名>-假字標記.jpg」放在驗片圖旁。先只警示、不擋（B 的筆畫對比門檻 60 邊際窄，等樣本多再改擋）。"""
    starts, d = b["starts"], b["d"]; tiles, rows = [], []
    for k, s in enumerate(cf["scenes"]):
        if s[0] == "CARD":
            continue
        lwp = os.path.normpath(os.path.join(base, s[0])) + ".lw.json"
        n = int(round((d[k] + (XFADE if k < len(cf["scenes"]) - 1 else 0)) * FILM_FPS))
        t = starts[k] + d[k] * 0.85; i = max(0, min(n - 1, int(round((t - starts[k]) * FILM_FPS))))
        fp = od + "/鏡%d_假字檢查.png" % (k + 1); bj = od + "/鏡%d_label.json" % (k + 1); mk = od + "/鏡%d_假字標記.jpg" % (k + 1)
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "%.3f" % t, "-i", mp4, "-frames:v", "1", fp])
        r = run_py([LBM, "--lw", lwp, "--zoom", str(s[1]), str(s[2]), str(s[3]), str(s[4]), "--n", str(n), "--fps", str(FILM_FPS),
                    "--frames", str(i), "--name", "鏡%d" % (k + 1), "--out", bj])
        if r.returncode != 0 or not os.path.exists(bj) or not os.path.exists(fp):
            rows.append("鏡%d：label 框或格抓不到（%s）" % (k + 1, (r.stdout + r.stderr)[-200:].strip())); continue
        box = jload(bj)["鏡%d@%d" % (k + 1, i)]
        g = run_py([GHOST, "--after", fp, "--label-box", ",".join(str(v) for v in box), "--out", mk])
        verdict = {0: "PASS", 1: "FAIL"}.get(g.returncode, "ERROR")
        rows.append("鏡%d（%.2f 秒、第 %d 格、label 框 %s）：%s" % (k + 1, t, i, box, verdict))
        if os.path.exists(mk):
            im = Image.open(mk).convert("RGB"); im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
            ImageDraw.Draw(im).text((8, im.height - 40), "鏡%d %s" % (k + 1, verdict), font=ImageFont.truetype(FONT, 30),
                                    fill=(220, 0, 0) if verdict != "PASS" else (0, 150, 0))
            tiles.append(im)
    gp = None
    if tiles:
        sheet = Image.new("RGB", (sum(t.width for t in tiles), max(t.height for t in tiles)), "white"); x = 0
        for t in tiles:
            sheet.paste(t, (x, 0)); x += t.width
        gp = od + "/%s-假字標記.jpg" % cf["name"]; sheet.save(gp, quality=90)
    if any(not r.endswith("PASS") for r in rows):
        print("⚠️ label 框外可能有假字（先只警示、不擋）：")
    for r in rows:
        print("  " + r)
    return gp, rows


def cmd_sheet(a):
    """驗片圖：先加上蝦皮版浮水印（觀眾看到的樣子），每鏡抓前、後兩格；每鏡再出一張「成片原尺寸的商品字區｜真品同一塊」並排。"""
    cfgp, cf, mp4, b = film_paths(a.key, a.vo)
    starts, d = b["starts"], b["d"]
    od = SMP + "/_驗片_%s" % a.key; os.makedirs(od, exist_ok=True)
    if os.path.exists(od + "/sheet.json"):
        os.remove(od + "/sheet.json")   # 工單 #5：這次 sheet 沒跑完（例如擋門 FAIL）就不留舊的出圖紀錄
    mg = motion_gate_hard(mp4, cf, b, od)   # 工單 #5-C①：FAIL ⇒ Stop（exit 2），下面不出圖
    stamped = od + "/蝦皮版.mp4"
    r = subprocess.run(["py", "-3", ROOT + "/tools/brand-stamp.py", "--in", mp4, "--out", stamped, "--no-card"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(stamped) or os.path.getmtime(stamped) < os.path.getmtime(mp4):
        raise Stop("浮水印版做不出來：%s %s" % (r.stdout[-200:], r.stderr[-200:]))
    card = load_card(cf["card"]); base = scene_base(SMP, cf)
    refim = Image.open(card["_ref"]).convert("RGBA"); bg = Image.new("RGBA", refim.size, (128, 128, 128, 255)); bg.alpha_composite(refim); refim = bg.convert("RGB")
    bb = card["bbox_n"]; f1 = ImageFont.truetype(FONT, 26); thumbs = []; outs = []
    for k, s in enumerate(cf["scenes"]):
        fr = {}
        for frac, tag in ((0.35, "前"), (0.85, "後")):
            fp = od + "/鏡%d_%s.png" % (k + 1, tag)
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "%.3f" % (starts[k] + d[k] * frac), "-i", stamped, "-frames:v", "1", fp])
            fr[tag] = Image.open(fp).convert("RGB"); thumbs.append(("鏡%d%s" % (k + 1, tag), fr[tag]))
        if s[0] == "CARD":
            continue
        cert = jload(os.path.normpath(os.path.join(base, s[0])) + ".lw.json")
        tb = card.get("text_box") or inset_box(cert.get("inset") or card.get("inset") or DEF_INSET)
        rx0, rx1 = (bb[0] + tb[0] * (bb[2] - bb[0])) * refim.width, (bb[0] + tb[2] * (bb[2] - bb[0])) * refim.width
        ry0, ry1 = (bb[1] + tb[1] * (bb[3] - bb[1])) * refim.height, (bb[1] + tb[3] * (bb[3] - bb[1])) * refim.height
        refc = refim.crop((int(rx0), int(ry0), int(rx1), int(ry1)))
        nfr = max(int(round((d[k] + 0.30) * 30)) - 1, 1)
        z = s[1] + (s[2] - s[1]) * min(1.0, (0.85 * d[k] * 30) / nfr)
        x0, y0, x1, y1 = label_rect_at(cert, card, z, s[3], s[4])
        px, py = 0.10 * (x1 - x0), 0.08 * (y1 - y0)
        box = (max(0, int(x0 - px)), max(0, int(y0 - py)), min(OUT_W, int(x1 + px)), min(OUT_H, int(y1 + py)))
        crop = fr["後"].crop(box)                                  # 成片原尺寸，不縮放
        refs = refc.resize((max(1, int(refc.width * crop.height / refc.height)), crop.height), Image.LANCZOS)
        row = Image.new("RGB", (crop.width + refs.width + 20, crop.height + 44), "white")
        row.paste(crop, (0, 44)); row.paste(refs, (crop.width + 20, 44))
        ImageDraw.Draw(row).text((6, 6), "鏡%d｜左＝成片原尺寸（%dx%d，沒有縮放）　右＝真品同一塊（縮到同高）" % (k + 1, crop.width, crop.height), font=f1, fill=(0, 0, 0))
        op = od + "/鏡%d_原尺寸對真品.jpg" % (k + 1); row.save(op, quality=95); outs.append(op)
    tw, th = 270, 480
    sheet = Image.new("RGB", (tw * len(thumbs), th + 34), "white"); ds = ImageDraw.Draw(sheet)
    for i, (lab, im) in enumerate(thumbs):
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (i * tw, 34)); ds.text((i * tw + 6, 2), lab, font=f1, fill=(200, 0, 0))
    sp = od + "/總覽.jpg"; sheet.save(sp, quality=90)
    gp, grows = ghost_marks(mp4, cf, b, od, base)   # 工單 #5-C②：只警示
    jdump({"out_sha1": b["out_sha1"], "time": now(), "files": [os.path.basename(x) for x in outs] + ["總覽.jpg"] + ([os.path.basename(gp)] if gp else []),
           "motion_gate": mg["verdict"], "ghost": grows}, od + "/sheet.json")
    print("驗片圖（都要打開看，看完才跑 film-ok）：")
    print("  總覽（標題／字幕／浮水印有沒有互撞、有沒有壓到商品）：" + sp)
    for o in outs:
        print("  " + o)
    if gp:
        print("  假字標記（綠＝貼回的 label 框、紅＝框外像字的東西；只警示）：" + gp)
    print("每鏡整張原尺寸：%s/鏡N_前.png、鏡N_後.png｜浮水印版影片：%s" % (od, stamped))
    print('看完：py -3 tools/prodfilm.py film-ok %s --by <誰看的> "<每一鏡看到了什麼>"' % a.key)
    return 0


def cmd_film_ok(a):
    cfgp, cf, mp4, b = film_paths(a.key, a.vo)
    sj = SMP + "/_驗片_%s/sheet.json" % a.key
    if not os.path.exists(sj) or jload(sj).get("out_sha1") != b["out_sha1"]:
        raise Stop("這支成片還沒出驗片圖（或出圖之後又重組過）。先跑：py -3 tools/prodfilm.py sheet %s" % a.key)
    mj = SMP + "/_驗片_%s/motion-gate.json" % a.key   # 工單 #5-C③：sheet 寫的動態閃爍結果
    if not os.path.exists(mj):
        raise Stop("沒有動態閃爍擋門的結果（%s）。重跑：py -3 tools/prodfilm.py sheet %s" % (mj, a.key))
    m = jload(mj)
    if m.get("out_sha1") != b["out_sha1"]:
        raise Stop("動態閃爍擋門量的是別的成片（指紋對不上），重跑 sheet。")
    if m.get("verdict") != "PASS":
        raise Stop("動態閃爍擋門沒過（%s），不准簽。重組（kb-render）後重跑 sheet。" % m.get("verdict"))
    if len(a.note.strip()) < 30:
        raise Stop("要寫清楚每一鏡看到了什麼（商品上的字有沒有全對、外形跟真品一不一樣、字幕有沒有壓到字），至少 30 個字。")
    jdump({"out_sha1": b["out_sha1"], "time": now(), "by": a.by, "note": a.note.strip()}, mp4 + ".eye.json")
    print("已簽：%s｜%s｜%s" % (os.path.basename(mp4), a.by, a.note.strip()))
    print("下一步交到待驗資料夾（PowerShell）：$env:OUTDAY='<批次日期>'; py -3 產出/_1002交商品片2.py %s" % a.key)
    return 0


def replacement_mode(obj):
    mode = obj.get('replace_mode', 'label')
    if mode not in ('label', 'whole'):
        raise Stop('不支援 replace_mode=%r；只接受 label 或 whole。' % mode)
    return mode


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def whole_rules():
    # Read the exact installed engine rules without maintaining another dictionary.
    import ast
    with open(WHOLE, encoding='utf-8-sig') as stream:
        tree = ast.parse(stream.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'RULES' for t in node.targets):
            return ast.literal_eval(node.value)
    raise Stop('prod-replace.py 沒有可讀的 RULES，停止 whole 路徑。')


def judge_whole(cert, card, z0, z1):
    m = cert.get('metrics') or {}; errors = []
    if not cert.get('warp_ok') or m.get('status') != 'VERIFIED_COMPLETE':
        return ['整支換真品未通過：' + ('；'.join(m.get('reasons') or []) or cert.get('warp_msg', '無完整結果'))]
    rules = whole_rules()
    if m.get('rules') != rules or m.get('tool_sha256') != file_sha256(WHOLE):
        errors.append('整支替換引擎或 RULES 已變更，重跑 lw。')
    if m.get('reasons') or m.get('geometry_failures'):
        errors.append('整支替換仍有失敗項，不能組片。')
    import math
    try:
        fields = ('iou', 'white_keep', 'ref_solidity', 'edge_support', 'appearance_correlation',
                  'bottom_gap_px', 'scene_product_height_px', 'remnant_max_width_px',
                  'scene_product_width_px', 'remnant_px', 'rot_deg', 'scale', 'angle_dev', 'side_ratio')
        if any(not isinstance(m.get(k), (int, float)) or not math.isfinite(m[k]) for k in fields):
            raise ValueError('缺少有限量測')
        checks = (
            (m['iou'] >= rules['iou_min'], '輪廓 IoU'),
            (m['white_keep'] >= rules['white_keep_min'], '白字亮度'),
            (m['ref_solidity'] >= rules['ref_solidity_min'] and m.get('ref_objects') == 1, '真品完整性'),
            (m['edge_support'] >= rules['boundary_edge_min'], '邊界支持'),
            (m['appearance_correlation'] >= rules['appearance_correlation_min'], '外觀支持'),
            (m['bottom_gap_px'] <= m['scene_product_height_px'] * rules['bottom_gap_fraction'], '底邊差距'),
            (m['remnant_max_width_px'] <= m['scene_product_width_px'] * rules['remnant_width_fraction'], '殘邊寬度'),
            (m['remnant_px'] <= m['thresholds']['remnant_area_px'], '殘邊面積'),
            (abs(m['rot_deg']) <= rules['rotation_degrees'] + .000001, '旋轉'),
            (m['angle_dev'] <= rules['angle_deviation_max'] and m['side_ratio'] <= rules['opposite_side_ratio_max'], '引擎形變'),
            (m.get('shadow_below_unchanged') is True and m.get('reference_alpha_preserved') is True, '陰影與完整 alpha'),
        )
        errors.extend('prod-replace 規則未過：' + title for passed, title in checks if not passed)
        fs = final_scale(cert, z0, z1)
        if not math.isfinite(fs) or fs <= 0:
            errors.append('整支替換成片倍率不可量測，停止。')
        elif fs > RULE['final_scale_max']:
            errors.append('真品照太小：成片上被放大 %.2f 倍 > %.2f，重跑 lw。' % (fs, RULE['final_scale_max']))
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        errors.append('整支替換憑證缺量測／格式錯誤，重跑 lw。')
    # label-only colour/homography heuristics are explicitly n/a. Engine rules still apply.
    return errors


def retire_whole(paths):
    import uuid
    root = os.path.abspath(LWDIR)
    existing = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not existing:
        return
    if any(os.path.commonpath([root, p]) != root or not os.path.isfile(p) for p in existing):
        raise Stop('whole 舊輸出不在 LWDIR 或不是一般檔案，停止。')
    target = os.path.join(root, '_作廢', time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    os.makedirs(target, exist_ok=False)
    for p in existing:
        os.rename(p, os.path.join(target, os.path.basename(p)))


def cmd_lw_whole(a, cfgp, cf, ck, card, base):
    outdir = os.path.join(LWDIR, ck); diagdir = os.path.join(LWDIR, '_diag', ck)
    os.makedirs(outdir, exist_ok=True); os.makedirs(diagdir, exist_ok=True)
    rows = []; new_names = {}
    for i, scene in enumerate(cf['scenes'], 1):
        name = scene[0]
        if name == 'CARD':
            continue
        if name.endswith('#sway') or name.lower().endswith('.mp4'):
            rows.append((i, name, None, ['whole 只支援靜態商品場景，不接受手持擺動或影片。']))
            continue
        p = os.path.normpath(os.path.join(base, name))
        src = jload(p + '.lw.json')['src'] if os.path.exists(p + '.lw.json') else p
        if not os.path.exists(src):
            rows.append((i, name, None, ['找不到場景圖 ' + src])); continue
        stem = os.path.splitext(os.path.basename(src))[0] + '_lw2x'
        out = os.path.join(outdir, stem + '.png'); certp = out + '.lw.json'
        jf = os.path.join(diagdir, stem + '.prod-replace.json')
        ins = (cf.get('lw_insets') or {}).get(str(i)) or card.get('inset') or DEF_INSET
        if a.only and i not in a.only and os.path.exists(certp):
            cert = jload(certp)
            if (replacement_mode(cert) != 'whole' or cert.get('src_sha1') != sha1(src)
                    or cert.get('ref_sha1') != card['ref_sha1'] or cert.get('card') != ck
                    or not os.path.exists(out) or cert.get('out_sha1') != sha1(out)):
                rows.append((i, os.path.basename(src), cert, ['舊 whole 憑證與模式／來源／成品不符，重跑此鏡。'])); continue
        else:
            cmp_ = os.path.join(outdir, stem + '_對照.jpg')
            retire_whole([out, certp, cmp_, jf, os.path.join(diagdir, stem + '_定位.jpg'),
                          os.path.join(diagdir, stem + '_模型輪廓.png')])
            # prod-replace itself creates the required 2x canvas. Supplying x2 here would create 4x.
            command = ['py', '-3', WHOLE, src, out, '--ref', card['_ref'], '--json', jf, '--diagnostics', diagdir]
            r = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
            message = (r.stdout.strip().splitlines() or [r.stderr.strip()[-160:]])[-1]
            metrics = jload(jf) if os.path.exists(jf) else {}
            ok = r.returncode == 0 and os.path.exists(out) and metrics.get('status') == 'VERIFIED_COMPLETE'
            if ok:
                size = Image.open(src).size
                ok = (Image.open(out).size == (size[0] * 2, size[1] * 2)
                      and metrics.get('output_sha256') == file_sha256(out)
                      and metrics.get('ref_sha256') == file_sha256(card['_ref'])
                      and metrics.get('scene_sha256') == file_sha256(src))
                if not ok:
                    message = '整支替換的輸出尺寸或指紋讀回不符'
                    retire_whole([out, cmp_])
            cert = {'tool': 'prodfilm.py lw(whole)', 'time': now(), 'card': ck,
                    'replace_mode': 'whole', 'ref_sha1': card['ref_sha1'], 'src': src.replace(os.sep, '/'),
                    'src_sha1': sha1(src), 'inset': ins, 'lw_args': list(card.get('lw_args') or []),
                    'keep_skin': False, 'warp_ok': bool(ok), 'warp_msg': message,
                    'metrics': metrics, 'prod_replace_json': jf,
                    'label_metrics': {'lowfreq_mean': 'n/a: whole replacement',
                                      'angle_dev': 'n/a: label homography not used',
                                      'side_ratio': 'n/a: label homography not used'},
                    'canvas_contract': 'prod-replace internally produces 2x; no duplicate upscale'}
            if ok:
                cert['out_sha1'] = sha1(out)
            jdump(cert, certp)
        fails = judge(cert, card, scene[1], scene[2])
        rows.append((i, os.path.basename(src), cert, fails))
        if not fails:
            new_names[i] = os.path.relpath(out, base).replace(os.sep, '/')
    font = ImageFont.truetype(FONT, 26); strips = []
    for i, name, cert, fails in rows:
        cmp_ = os.path.join(outdir, os.path.splitext(name)[0] + '_lw2x_對照.jpg') if cert else ''
        if cert and cert.get('warp_ok') and os.path.exists(cmp_):
            im = Image.open(cmp_).convert('RGB'); im = im.resize((int(im.width * 620 / im.height), 620), Image.LANCZOS)
        else:
            im = Image.new('RGB', (1500, 120), (235, 235, 235))
        strip = Image.new('RGB', (max(1800, im.width), im.height + 76), 'white'); strip.paste(im, (0, 76))
        text = '鏡%d %s %s｜whole｜低頻差／貼字四角／對邊比 n/a' % (i, '沒過' if fails else '過', name[:36])
        if cert and cert.get('warp_ok'):
            text += '｜成片放大 %.3f' % final_scale(cert, *cf['scenes'][i-1][1:3])
        draw = ImageDraw.Draw(strip); colour = (200, 0, 0) if fails else (0, 120, 0)
        draw.text((6, 4), text, font=font, fill=colour)
        draw.text((6, 40), (fails or ['prod-replace 全規則通過；外觀仍待驗'])[0][:108], font=font, fill=colour)
        strips.append(strip)
        print('鏡%d %s %s：%s' % (i, 'XX' if fails else '過', name, '；'.join(fails) if fails else 'whole 全規則＋成片倍率通過'))
    if strips:
        sheet = Image.new('RGB', (max(x.width for x in strips), sum(x.height for x in strips)), 'white'); y = 0
        for strip in strips:
            sheet.paste(strip, (0, y)); y += strip.height
        target = os.path.join(outdir, a.key + '_貼回總表.jpg')
        retire_whole([target]); sheet.save(target, quality=90)
        jdump({'replace_mode': 'whole', 'rows': [{'i':i,'name':n,'pass':not f,'reasons':f} for i,n,c,f in rows]}, target + '.rows.json')
        print('總表圖：' + target)
    bad = sum(bool(f) for i,n,c,f in rows)
    if bad or not rows:
        print('XX %d 鏡未過；設定檔未改。' % bad); return 2
    # Whole integration has no authority to modify sample configs.
    # Emit a plan alongside output; the owner can adopt it in a separately authorized step.
    jdump({'config': cfgp, 'config_sha1': sha1(cfgp), 'replace_mode': 'whole',
           'card': ck, 'real': card['_ref'], 'scene_outputs': new_names,
           'status': 'PENDING_CONFIG_ADOPTION', 'config_modified': False},
          os.path.join(outdir, a.key + '_whole-adoption-plan.json'))
    print('whole 全部鏡頭通過；採用清單已寫，原 sample 設定未改。仍須接入後跑 gate／sheet。')
    return 0


def main():
    ap = argparse.ArgumentParser(description="純商品片的源頭擋門：商品卡＋真品貼回＋組片前檢查")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("card"); p.add_argument("key"); p.add_argument("src"); p.add_argument("--name", required=True)
    p.add_argument("--text-box", default=""); p.add_argument("--inset", default=""); p.add_argument("--note", default="")
    p.add_argument("--white-tol", type=int, default=14, help="白底去背時跟純白差多少以內算背景（預設 14）；白瓶身被吃掉時用 2")
    p.add_argument("--lw-args", default="", help='這個商品貼回時固定要帶的 label-warp 參數，例：--lw-args="--hi 99.5"（深色瓶白字，不加字會變灰）')
    p = sub.add_parser("card-ok"); p.add_argument("key"); p.add_argument("note"); p.add_argument("--by", required=True)
    p = sub.add_parser("lw"); p.add_argument("key"); p.add_argument("--card", default=""); p.add_argument("--only", nargs="*", type=int, default=[])
    p = sub.add_parser("gate"); p.add_argument("cfg")
    p = sub.add_parser("sheet"); p.add_argument("key"); p.add_argument("--vo", default="H")
    p = sub.add_parser("film-ok"); p.add_argument("key"); p.add_argument("note"); p.add_argument("--by", required=True); p.add_argument("--vo", default="H")
    a = ap.parse_args()
    try:
        return {"card": cmd_card, "card-ok": cmd_card_ok, "lw": cmd_lw, "gate": cmd_gate, "sheet": cmd_sheet, "film-ok": cmd_film_ok}[a.cmd](a)
    except Stop as e:
        print("⛔ " + str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
