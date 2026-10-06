# -*- coding: utf-8 -*-
"""test_prodfilm_sheet.py — 工單 #5-C：套用 prodfilm.patch 之後，sheet／film-ok 的新擋門能不能跑（用 fixtures/ts 模擬）。

用法（repo 根目錄）：
  python out/工單5/test_prodfilm_sheet.py                                  # 測 out/工單5/prodfilm.py（已套 patch 的副本）
  python out/工單5/test_prodfilm_sheet.py --prodfilm <本機 tools/prodfilm.py> # 本機套完 patch 之後測本機那支
需要：numpy、opencv、Pillow、ffmpeg（PATH 或 FFMPEG_BIN）。全部在暫存資料夾裡做，不碰本機任何路徑。

模擬的東西：
  - 本機目錄結構（ROOT/素材/商品卡/ts、ROOT/產出/…/樣品、…/首幀/_貼回/ts/*.lw.json）＝fixtures 的真檔；
  - 母片＝ts 五鏡的成片格放大成 1536×2688 當場景，照 kb-render 算法推近（新）或用真的 ffmpeg zoompan（舊），
    每鏡 3 秒＋片尾卡 2.5 秒，30fps CRF 10（同 build_ph9_sample.py）；鏡與鏡之間直接切（不做 xfade）；
  - brand-stamp.py 換成替身（只做 fps=24，沒有浮水印圖檔）；`py -3` 換成目前的 python。
驗：① kb 母片 sheet 過、出「<商品名>-假字標記.jpg」、film-ok 簽得下去 ② zoompan 母片 sheet 回 2、不出 sheet.json、film-ok 拒簽
    ③ 簽名後重組（指紋改變）film-ok 拒簽 ④ patch 後的 prodfilm 沒有任何跳過參數
    ⑤ 舊 sheet.json 還在但動態閃爍 FAIL／沒有結果檔 ⇒ film-ok 拒簽。
"""
import argparse
import argparse as _ap
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIX = os.path.join(REPO, "jobs", "wo5-擋門整合-1006", "fixtures", "ts")
LOCAL = os.path.join(REPO, "jobs", "wo5-擋門整合-1006", "local-tools")
SHOTS = ["prod1006_ts%d_s%s_lw2x.png" % (k, s) for k, s in ((1, "900331"), (2, "900197"), (3, "900197"), (4, "900331"), (5, "900197"))]
FRAMES = ["ts_shot1_t0.10.jpg", "ts_shot2_t3.40.jpg", "ts_shot3_t7.90.jpg", "ts_shot4_t10.80.jpg", "ts_shot5_t13.90.jpg"]
D, CARD_D, FPS, X = 3.0, 2.5, 30, 0.30
STAMP_STUB = '''import argparse, subprocess, sys
ap = argparse.ArgumentParser(); ap.add_argument("--in", dest="src"); ap.add_argument("--out", dest="dst"); ap.add_argument("--no-card", action="store_true")
a = ap.parse_args()
sys.exit(subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.src, "-vf", "fps=24,format=yuv420p", "-c:v", "libx264", "-crf", "10", a.dst]).returncode)
'''


def ffmpeg():
    ff = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    if not ff:
        sys.exit("⚠️ 找不到 ffmpeg（PATH 或 FFMPEG_BIN）")
    return ff


def build_mother(ff, out, sample, old):
    """五鏡推近（kb 或 zoompan）＋片尾卡 → 30fps CRF 10。回傳 (starts, d)。"""
    enc = ["-c:v", "libx264", "-crf", "10", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    parts, starts, t = [], [], 0.0
    tmp = os.path.dirname(out)
    for k, fr in enumerate(FRAMES):
        _, z0, z1, cx, cy = sample["scenes"][k]
        scene = Image.open(os.path.join(FIX, fr)).convert("RGB").resize((1536, 2688), Image.LANCZOS)
        n = int(round((D + X) * FPS)); keep = int(round(D * FPS))
        clip = os.path.join(tmp, "shot%d.mp4" % k)
        if old:
            sp = os.path.join(tmp, "scene%d.png" % k); scene.save(sp)
            vf = ("scale=2160:3840:flags=lanczos,zoompan=z='%.4f+(%.4f)*on/%d':x='iw*%.3f-(iw/zoom/2)':y='ih*%.3f-(ih/zoom/2)':d=%d:s=1080x1920:fps=%d,"
                  "setsar=1,format=yuv420p,trim=end_frame=%d" % (z0, z1 - z0, n - 1, cx, cy, n, FPS, keep))
            subprocess.run([ff, "-y", "-loglevel", "error", "-loop", "1", "-i", sp, "-vf", vf, "-frames:v", str(keep)] + enc + [clip], check=True)
        else:
            W, H = 1536, round(1536 * 1920 / 1080); im = scene.resize((W, H), Image.LANCZOS)
            p = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920", "-r", str(FPS), "-i", "-"] + enc + [clip],
                                 stdin=subprocess.PIPE)
            for i in range(keep):
                z = max(1.0, z0 + (z1 - z0) * i / (n - 1)); w, h = W / z, H / z
                x0, y0 = min(max(cx * W - w / 2, 0.0), W - w), min(max(cy * H - h / 2, 0.0), H - h)
                p.stdin.write(im.resize((1080, 1920), Image.LANCZOS, box=(x0, y0, x0 + w, y0 + h)).tobytes())
            p.stdin.close(); p.wait()
        parts.append(clip); starts.append(round(t, 3)); t += D
    card = os.path.join(tmp, "card.mp4")
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0xEAF4FB:s=1080x1920:r=%d:d=%.3f" % (FPS, CARD_D), "-i", os.path.join(FIX, "ts_alpha.png"),
                    "-filter_complex", "[1:v]scale=900:1000:force_original_aspect_ratio=decrease,format=rgba[p];[0:v][p]overlay=x='(W-w)/2':y='1290-h',format=yuv420p",
                    "-frames:v", str(int(CARD_D * FPS))] + enc + [card], check=True)
    parts.append(card); starts.append(round(t, 3))
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p_ in parts:
            f.write("file '%s'\n" % p_.replace("'", "'\\''"))
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], check=True)
    return starts, [D] * len(FRAMES) + [CARD_D]


def setup_root(root, pf_path, font):
    """模擬本機目錄；回傳載入（並改好路徑）的 prodfilm 模組。"""
    tools = os.path.join(root, "tools"); os.makedirs(tools)
    for t in ("motion-gate.py", "ghost-text-gate.py", "label-box-map.py", "gatelib.py"):
        shutil.copy(os.path.join(REPO, "tools", t), tools)
    open(os.path.join(tools, "brand-stamp.py"), "w", encoding="utf-8").write(STAMP_STUB)
    cards = os.path.join(root, "素材", "商品卡", "ts"); os.makedirs(cards)
    shutil.copy(os.path.join(FIX, "card.json"), cards); shutil.copy(os.path.join(FIX, "ts_alpha.png"), cards)
    pkg = os.path.join(root, "產出", "腳本備妥-商品片樣品-20261002"); smp = os.path.join(pkg, "樣品"); os.makedirs(smp)
    lwd = os.path.join(pkg, "首幀", "_貼回", "ts"); os.makedirs(lwd)
    for s in SHOTS:
        shutil.copy(os.path.join(FIX, s + ".lw.json"), lwd)
    shutil.copy(os.path.join(LOCAL, "sample_ts.json"), smp)
    spec = importlib.util.spec_from_file_location("prodfilm_under_test", pf_path)
    pf = importlib.util.module_from_spec(spec)
    real_run = subprocess.run

    def run(args, *a, **kw):   # 本機用 py -3；這裡換成目前的 python
        if isinstance(args, list) and args[:2] == ["py", "-3"]:
            args = [sys.executable] + args[2:]
        return real_run(args, *a, **kw)
    spec.loader.exec_module(pf)
    pf.subprocess = type(sys)("subprocess_shim"); pf.subprocess.run = run
    R = root.replace(os.sep, "/")
    pf.ROOT, pf.PKG, pf.SMP, pf.CARDS = R, R + "/產出/腳本備妥-商品片樣品-20261002", R + "/產出/腳本備妥-商品片樣品-20261002/樣品", R + "/素材/商品卡"
    pf.LWDIR = pf.PKG + "/首幀/_貼回"; pf.MG, pf.GHOST, pf.LBM = R + "/tools/motion-gate.py", R + "/tools/ghost-text-gate.py", R + "/tools/label-box-map.py"
    if font:
        pf.FONT = font
    return pf, smp


def place_mother(pf, ff, smp, old):
    sample = json.load(open(os.path.join(smp, "sample_ts.json"), encoding="utf-8"))
    mp4 = os.path.join(smp, "%s商品片樣品_H.mp4" % sample["name"])
    work = tempfile.mkdtemp(dir=os.path.dirname(smp))
    starts, d = build_mother(ff, mp4, sample, old)
    shutil.rmtree(work, ignore_errors=True)
    json.dump({"tool": "test", "out_sha1": pf.sha1(mp4), "starts": starts, "d": d, "total": starts[-1] + d[-1]},
              open(mp4 + ".built.json", "w", encoding="utf-8"), ensure_ascii=False)
    return mp4


def call(pf, fn, **kw):
    try:
        return getattr(pf, fn)(_ap.Namespace(**kw)), ""
    except pf.Stop as e:
        return 2, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prodfilm", default=os.path.join(REPO, "out", "工單5", "prodfilm.py"))
    ap.add_argument("--font", help="中文字型（本機不用給；Linux 可給 wqy-zenhei.ttc）")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ff = ffmpeg()
    os.environ["PATH"] = os.path.dirname(ff) + os.pathsep + os.environ.get("PATH", "")
    src = open(a.prodfilm, encoding="utf-8").read()
    checks = []
    checks.append(("④ 沒有跳過參數（--skip／--force／--no-gate／--no-motion）", not any(k in src for k in ("--skip", "--force", "--no-gate", "--no-motion"))))
    with tempfile.TemporaryDirectory() as root:
        pf, smp = setup_root(root, a.prodfilm, a.font)
        od = os.path.join(smp, "_驗片_ts")
        # ① 新做法（kb）
        print("== ① kb 母片：sheet 要過、film-ok 要簽得下去")
        place_mother(pf, ff, smp, old=False)
        rc, msg = call(pf, "cmd_sheet", key="ts", vo="H")
        mg = json.load(open(os.path.join(od, "motion-gate.json"), encoding="utf-8")) if os.path.exists(os.path.join(od, "motion-gate.json")) else {}
        ghost = os.path.join(od, "tsaio上山採藥野薄荷淨涼洗顏乳-假字標記.jpg")
        checks.append(("① sheet 回 0", rc == 0))
        checks.append(("① motion-gate.json 是 PASS", mg.get("verdict") == "PASS"))
        checks.append(("① 有「<商品名>-假字標記.jpg」", os.path.exists(ghost)))
        if os.path.exists(ghost):
            shutil.copy(ghost, os.path.join(REPO, "out", "工單5", "test_sheet_假字標記.jpg"))
        rc2, msg2 = call(pf, "cmd_film_ok", key="ts", vo="H", by="test", note="五鏡都看過：管身字全對、外形跟真品一樣、字幕沒有壓到字、片尾卡正常")
        checks.append(("① film-ok 簽得下去", rc2 == 0))
        # ③ 重組（指紋改變）⇒ film-ok 拒簽
        print("== ③ 簽完之後重組：film-ok 要拒簽")
        place_mother(pf, ff, smp, old=False)
        mp4 = [f for f in os.listdir(smp) if f.endswith("_H.mp4")][0]
        with open(os.path.join(smp, mp4), "ab") as f:
            f.write(b"\0")   # 模擬重組：檔案指紋改變
        bj = os.path.join(smp, mp4 + ".built.json"); b = json.load(open(bj, encoding="utf-8")); b["out_sha1"] = pf.sha1(os.path.join(smp, mp4))
        json.dump(b, open(bj, "w", encoding="utf-8"))
        rc3, msg3 = call(pf, "cmd_film_ok", key="ts", vo="H", by="test", note="x" * 40)
        checks.append(("③ 重組後 film-ok 拒簽（%s）" % msg3[:40], rc3 == 2))
        # ② 舊做法（zoompan）
        print("== ② zoompan 母片：sheet 要回 2、不出圖；film-ok 要拒簽")
        place_mother(pf, ff, smp, old=True)
        rc4, msg4 = call(pf, "cmd_sheet", key="ts", vo="H")
        print("  sheet：%s" % msg4[:300])
        checks.append(("② sheet 回 2", rc4 == 2))
        checks.append(("② 沒有留下 sheet.json", not os.path.exists(os.path.join(od, "sheet.json"))))
        mg = json.load(open(os.path.join(od, "motion-gate.json"), encoding="utf-8")) if os.path.exists(os.path.join(od, "motion-gate.json")) else {}
        checks.append(("② motion-gate.json 是 FAIL", mg.get("verdict") == "FAIL"))
        rc5, msg5 = call(pf, "cmd_film_ok", key="ts", vo="H", by="test", note="x" * 40)
        checks.append(("② film-ok 拒簽（%s）" % msg5[:40], rc5 == 2))
        # ⑤ 就算留著一份指紋對得上的舊 sheet.json（例如 patch 之前出的圖），motion-gate.json 不是 PASS 也要拒簽
        print("== ⑤ 舊 sheet.json 還在、但動態閃爍 FAIL：film-ok 要因為動態閃爍拒簽")
        mp4 = [f for f in os.listdir(smp) if f.endswith("_H.mp4")][0]
        sha = json.load(open(os.path.join(smp, mp4 + ".built.json"), encoding="utf-8"))["out_sha1"]
        json.dump({"out_sha1": sha, "time": "patch 之前", "files": []}, open(os.path.join(od, "sheet.json"), "w", encoding="utf-8"))
        rc6, msg6 = call(pf, "cmd_film_ok", key="ts", vo="H", by="test", note="x" * 40)
        checks.append(("⑤ 動態閃爍 FAIL 拒簽（%s）" % msg6[:30], rc6 == 2 and "動態閃爍" in msg6))
        os.remove(os.path.join(od, "motion-gate.json"))
        rc7, msg7 = call(pf, "cmd_film_ok", key="ts", vo="H", by="test", note="x" * 40)
        checks.append(("⑤ 沒有 motion-gate.json 拒簽（%s）" % msg7[:30], rc7 == 2 and "動態閃爍" in msg7))
    print("\n== 結果")
    for name, good in checks:
        print("  %s %s" % ("✅" if good else "❌", name))
    ok = all(g for _, g in checks)
    print("全部通過" if ok else "有沒過的")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
