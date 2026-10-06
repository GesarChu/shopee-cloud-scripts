#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工單 #5-D：build_ph9_sample.patch 套用後真的組一支片，量片尾卡真品照離浮水印。

做法：暫存資料夾模擬本機 ROOT（樣品/、tools/、首幀/_貼回/ts/），把 builder（原版／patch 版）複製進 樣品/，
  只把 builder 第 12 行的 ROOT 換成暫存資料夾（其他本機路徑——kb-render、prodfilm gate、音效——在 subprocess 那層照檔名對到暫存檔）；
  場景圖＝fixtures/ts 成片格放大成 1536×2688，旁白＝1.8 秒正弦波，真品照＝fixtures/ts/ts_alpha.png。
  builder 照原樣從頭跑到尾（ffmpeg 組片、字幕、xfade、片尾卡彈跳都是真的）；只有 `prodfilm.py gate` 當作通過（那是貼回擋門，不是這裡要測的）。
檢查：
  ① 原版 builder：片尾卡（彈跳鎖死後）真品照壓進浮水印框 ⇒ card-gap check FAIL
  ② patch 版：先往下移、再縮 1% ⇒ 組完 builder 自己量 PASS、有 .built.json、有 _格_…片尾卡離浮水印.jpg；彈跳期（含 xfade）每格 ≥ 20
  ③ 細長瓶（原位置就夠）：原版、patch 版成片逐位元組相同
  ④ patch 版＋成片量 FAIL（把 check 換成固定 FAIL 的替身）⇒ builder 停、舊 .built.json 刪掉
  ⑤ patch 版＋tools/ 沒有 card-gap.py ⇒ builder 停（不能跳過）、沒有 .built.json
  ⑥ patch 版＋整張透明的真品照（layout 量不了）⇒ builder 停
  ⑦ 蝦皮版模擬（brand-stamp 的 fps=24＋浮水印框裡畫東西）：原版 FAIL、patch 版 PASS（浮水印框內遮掉不算，交付檔也能量）
用法：python out/工單5/test_card_gap_builder.py [--orig 原版] [--patched patch 版] [--keep 資料夾]   （要 ffmpeg：FFMPEG_BIN 或 PATH）
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WO5 = os.path.join(REPO, "jobs", "wo5-擋門整合-1006")
TS = os.path.join(WO5, "fixtures", "ts")
LOCAL = os.path.join(WO5, "local-tools")
sys.path.insert(0, os.path.join(REPO, "tools"))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("card_gap", os.path.join(REPO, "tools", "card-gap.py"))
cg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cg)

ROOT_RE = re.compile(r'(?m)^ROOT = r"[^"\r\n]*"')   # builder 第 12 行 ROOT = r"<本機根目錄>"（只認格式，不寫本機路徑）
LINES = ["臉又油又黏，洗完還是不清爽", "上山採藥洗顏乳", "洗完很清新，不緊繃", "深層淨化", "男生專用款", "下面點進去就買得到"]
FF = None
REAL_RUN = subprocess.run
KB_CACHE = {}


def tone(path, sec, freq=440.0):
    n = int(sec * 48000)
    x = (0.3 * np.sin(2 * np.pi * freq * np.arange(n) / 48000) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(x.tobytes())


def duration(path):
    if path.lower().endswith(".wav"):
        with wave.open(path) as w:
            return w.getnframes() / float(w.getframerate())
    import cv2
    cap = cv2.VideoCapture(path)
    n, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    return n / fps


class Sim:
    """一個模擬的本機 ROOT。"""

    def __init__(self, base, builder, real, shared, tools=True):
        self.root = os.path.join(base, "shopee")
        self.smp = os.path.join(self.root, "樣品")
        self.tools = os.path.join(self.root, "tools")
        self.sfx = os.path.join(self.root, "_sfx")
        for d in (self.smp, self.tools, os.path.join(self.root, "首幀", "_候選"), self.sfx):   # 場景圖＝C（../首幀/_候選/）＋"../_貼回/ts/…"
            os.makedirs(d, exist_ok=True)
        src = open(builder, "rb").read().decode("utf-8")
        src, n = ROOT_RE.subn(lambda m: 'ROOT = r"%s"' % self.root, src)
        assert n == 1, "builder 的 ROOT = r\"…\" 那一行不是預期的樣子"
        open(os.path.join(self.smp, "build_ph9_sample.py"), "wb").write(src.encode("utf-8"))
        shutil.copytree(os.path.join(shared, "ts"), os.path.join(self.root, "首幀", "_貼回", "ts"))
        shutil.copy(os.path.join(LOCAL, "kb-render.py"), self.tools)
        if tools:
            for f in ("card-gap.py", "gatelib.py"):
                shutil.copy(os.path.join(REPO, "tools", f), self.tools)
        self.real = os.path.join(self.root, os.path.basename(real))
        shutil.copy(real, self.real)
        for sub in ("transition/whoosh-1.mp3", "accent/bubble-pop-1.mp3"):
            os.makedirs(os.path.dirname(os.path.join(self.sfx, sub)), exist_ok=True)
            tone(os.path.join(self.sfx, sub), 0.3, 880)   # 副檔名 .mp3、內容 wav：ffmpeg 看內容
        tone(os.path.join(self.sfx, "music.wav"), 20.0, 220)
        cf = json.load(open(os.path.join(LOCAL, "sample_ts.json"), encoding="utf-8"))
        cf["real"], cf["music"] = self.real, os.path.join(self.sfx, "music.wav")
        json.dump(cf, open(os.path.join(self.smp, "sample_ts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        for f in (cf["lines"], "lines_ph9.txt"):   # builder 讀 cfg 之前會先開 PH9 的預設台詞檔
            open(os.path.join(self.smp, f), "w", encoding="utf-8").write("\n".join(LINES) + "\n")
        vd = os.path.join(self.smp, "ts_voiceA")
        os.makedirs(vd)
        for i in range(len(LINES)):
            tone(os.path.join(vd, "line%02d.wav" % (i + 1)), 1.8)
        self.cf = cf
        self.out = os.path.join(self.smp, "%s商品片樣品_A.mp4" % cf["name"])

    def fake_run(self, args, *a, **k):
        if isinstance(args, (list, tuple)):
            args = list(args)
            if args[:2] == ["py", "-3"]:
                base = os.path.basename(args[2].replace("\\", "/"))
                if base == "prodfilm.py":   # 貼回擋門當作通過（不是這裡要測的）
                    return subprocess.CompletedProcess(args, 0, "" if k.get("text") else b"", "" if k.get("text") else b"")
                if base == "kb-render.py":
                    key = (os.path.basename(args[3]),) + tuple(args[5:])
                    if key in KB_CACHE:
                        shutil.copy(KB_CACHE[key], args[4])
                        return subprocess.CompletedProcess(args, 0)
                    r = REAL_RUN([sys.executable, os.path.join(self.tools, base)] + args[3:], *a, **k)
                    KB_CACHE[key] = os.path.join(CACHE_DIR, "kb_%d.mp4" % len(KB_CACHE))
                    shutil.copy(args[4], KB_CACHE[key])
                    return r
                args = [sys.executable, os.path.join(self.tools, base)] + args[3:]
            elif args[0] == "ffmpeg":
                args = [FF] + [self.map_path(x) for x in args[1:]]
            elif args[0] == "ffprobe":
                s = "%.6f\n" % duration(args[-1])
                return subprocess.CompletedProcess(args, 0, s if k.get("text") else s.encode(), "" if k.get("text") else b"")
        return REAL_RUN(args, *a, **k)

    def map_path(self, x):
        if isinstance(x, str) and "sfx-library/" in x:
            return os.path.join(self.sfx, x.split("sfx-library/", 1)[1])
        return x

    def build(self):
        """跑 builder（runpy，跟命令列一樣從頭到尾）。回傳 (exit 訊息或 None, stdout)。"""
        old_cwd, old_argv = os.getcwd(), sys.argv
        buf, code = io.StringIO(), None
        subprocess.run = self.fake_run
        try:
            sys.argv = [os.path.join(self.smp, "build_ph9_sample.py"), "--vo", "A", "--cfg", "sample_ts.json"]
            with contextlib.redirect_stdout(buf):
                runpy.run_path(sys.argv[0], run_name="__main__")
        except SystemExit as e:
            code = str(e.code)
        finally:
            subprocess.run = REAL_RUN
            sys.argv = old_argv
            os.chdir(old_cwd)
        return code, buf.getvalue()

    def built(self):
        p = self.out + ".built.json"
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def sha1(p):
    return hashlib.sha1(open(p, "rb").read()).hexdigest()


def main():
    global FF, CACHE_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", default=os.path.join(LOCAL, "build_ph9_sample.py"))
    ap.add_argument("--patched", default=os.path.join(HERE, "build_ph9_sample.py"))
    ap.add_argument("--keep", help="暫存放這裡、跑完不刪（看檔用）")
    a = ap.parse_args()
    FF = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    if not FF:
        print("✗ 找不到 ffmpeg（FFMPEG_BIN 或 PATH）")
        return 2
    os.environ["PATH"] = os.path.dirname(os.path.abspath(FF)) + os.pathsep + os.environ.get("PATH", "")   # kb-render 自己叫 ffmpeg
    base = a.keep or tempfile.mkdtemp(prefix="wo5d_")
    os.makedirs(base, exist_ok=True)
    CACHE_DIR = os.path.join(base, "_kbcache")
    os.makedirs(CACHE_DIR, exist_ok=True)
    ok_all = True

    def chk(cond, msg):
        nonlocal ok_all
        print(("  ✓ " if cond else "  ✗ ") + msg)
        ok_all = ok_all and bool(cond)

    try:
        # 共用素材：場景圖（成片格放大成 1536×2688，跟 lw2x 一樣大）、細長瓶、透明圖
        shared = os.path.join(base, "_shared")
        os.makedirs(os.path.join(shared, "ts"), exist_ok=True)
        cf0 = json.load(open(os.path.join(LOCAL, "sample_ts.json"), encoding="utf-8"))
        shots = sorted(f for f in os.listdir(TS) if f.startswith("ts_shot") and not f.startswith("ts_shot6"))
        for (img, *_), shot in zip(cf0["scenes"][:-1], shots):
            Image.open(os.path.join(TS, shot)).convert("RGB").resize((1536, 2688), Image.LANCZOS).save(os.path.join(shared, "ts", os.path.basename(img)))
        narrow = os.path.join(shared, "narrow_alpha.png")
        im = Image.new("RGBA", (240, 950), (0, 0, 0, 0))
        im.paste((40, 60, 90, 255), (60, 10, 180, 940))
        im.save(narrow)
        clear = os.path.join(shared, "clear_alpha.png")
        Image.new("RGBA", (400, 950), (0, 0, 0, 0)).save(clear)
        ts_alpha = os.path.join(TS, "ts_alpha.png")

        print("① 原版 builder＋ts 真品照")
        s1 = Sim(os.path.join(base, "1_orig"), a.orig, ts_alpha, shared)
        code, log = s1.build()
        b1 = s1.built()
        chk(code is None and b1 is not None, "原版組得出來（有 .built.json）%s" % ("" if code is None else "：" + code))
        v1, r1 = cg.check_video(s1.out, card_start=b1["starts"][-1], quiet=True)
        h1 = r1["hard"][0]
        chk(v1 == "FAIL" and h1["gap"] < 5, "片尾卡 %.2f 秒外框 %s 距離 %.1f ⇒ %s（要 FAIL）" % (h1["t"], h1.get("bbox"), h1.get("gap", -1), v1))
        cg.check_video(s1.out, card_start=b1["starts"][-1], quiet=True, out=os.path.join(HERE, "card_builder_原版.jpg"))

        print("② patch 版 builder＋ts 真品照")
        s2 = Sim(os.path.join(base, "2_patch"), a.patched, ts_alpha, shared)
        code, log = s2.build()
        b2 = s2.built()
        lay_line = [l for l in log.splitlines() if l.startswith("片尾卡真品照")]
        chk(code is None and b2 is not None, "patch 版組得出來、builder 自己量過、有 .built.json%s" % ("" if code is None else "：" + code))
        print("     builder：%s" % (lay_line[0] if lay_line else "（沒印 layout）"))
        print("     builder：%s" % " ／ ".join(l.strip() for l in log.splitlines() if "離浮水印" in l or "彈跳期" in l))
        cgimg = os.path.join(s2.smp, "_格_ts_A_片尾卡離浮水印.jpg")
        chk(os.path.exists(cgimg), "有 _格_ts_A_片尾卡離浮水印.jpg")
        if os.path.exists(cgimg):
            shutil.copy(cgimg, os.path.join(HERE, "card_builder_patch後.jpg"))
        v2, r2 = cg.check_video(s2.out, card_start=b2["starts"][-1], quiet=True) if b2 else ("ERROR", {"hard": [{}]})
        h2 = r2["hard"][0]
        chk(v2 == "PASS", "片尾卡 %.2f 秒外框 %s 距離 %.1f ⇒ %s" % (h2.get("t", -1), h2.get("bbox"), h2.get("gap", -1), v2))
        bn = [x for x in r2.get("bounce", []) if x["gap"] is not None]
        chk(bn and min(x["gap"] for x in bn) >= cg.MIN_GAP,
            "彈跳期（含 xfade）量得到的 %d 格最小 %.1f px ≥ %d（量不到的 %d 格＝轉場中底色不是片尾卡）"
            % (len(bn), min(x["gap"] for x in bn) if bn else -1, cg.MIN_GAP, len(r2.get("bounce", [])) - len(bn)))
        bo = [x for x in r1.get("bounce", []) if x["gap"] is not None]
        print("     對照原版彈跳期：量得到的 %d 格最小 %.1f px" % (len(bo), min(x["gap"] for x in bo) if bo else -1))

        print("③ 細長瓶（原位置就夠）：原版 vs patch 版逐位元組")
        s3a = Sim(os.path.join(base, "3_orig"), a.orig, narrow, shared)
        s3b = Sim(os.path.join(base, "3_patch"), a.patched, narrow, shared)
        ca, _ = s3a.build()
        cb, logb = s3b.build()
        chk(ca is None and cb is None and s3b.built() is not None, "兩版都組得出來")
        chk(os.path.exists(s3a.out) and os.path.exists(s3b.out) and sha1(s3a.out) == sha1(s3b.out),
            "成片 sha1 相同（%s）；builder：%s" % (sha1(s3b.out)[:12] if os.path.exists(s3b.out) else "-",
                                                 " ".join(l for l in logb.splitlines() if l.startswith("片尾卡真品照"))))

        print("④ patch 版＋成片量 FAIL（替身）⇒ 停、舊 .built.json 刪掉")
        s4 = Sim(os.path.join(base, "4_fail"), a.patched, ts_alpha, shared)
        real_tool = os.path.join(s4.tools, "card-gap.py")
        os.rename(real_tool, os.path.join(s4.tools, "card_gap_real.py"))
        open(real_tool, "w", encoding="utf-8").write(
            "import os, sys, subprocess\n"
            "if sys.argv[1:2] == ['check']:\n    print('✗ 替身：固定 FAIL'); sys.exit(1)\n"
            "sys.exit(subprocess.call([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'card_gap_real.py')] + sys.argv[1:]))\n")
        open(s4.out + ".built.json", "w").write('{"out_sha1": "舊的"}')
        code, log = s4.build()
        chk(code is not None and "不發 .built.json" in code and not os.path.exists(s4.out + ".built.json"),
            "builder 停：%s；.built.json %s" % ((code or "").splitlines()[0][:60], "還在 ✗" if os.path.exists(s4.out + ".built.json") else "已刪"))

        print("⑤ patch 版＋tools/ 沒有 card-gap.py ⇒ 停")
        s5 = Sim(os.path.join(base, "5_notool"), a.patched, ts_alpha, shared, tools=False)
        code, _ = s5.build()
        chk(code is not None and "card-gap.py" in code and s5.built() is None and not os.path.exists(s5.out),
            "builder 停：%s" % (code or "").splitlines()[0][:70])

        print("⑥ patch 版＋整張透明的真品照 ⇒ 停")
        s6 = Sim(os.path.join(base, "6_clear"), a.patched, clear, shared)
        code, _ = s6.build()
        chk(code is not None and "片尾卡" in code and s6.built() is None, "builder 停：%s" % (code or "").splitlines()[0][:70])

        print("⑦ 蝦皮版模擬：fps=24＋浮水印框裡畫東西（圖示、字、陰影）")
        for name, sim, bj in (("原版", s1, b1), ("patch 版", s2, b2)):
            sp = sim.out[:-4] + "_蝦皮版.mp4"
            x0, y0, x1, y1 = cg.WM_BOX
            vf = ("fps=24,drawbox=x=%d:y=%d:w=96:h=109:color=0xF07830:t=fill,drawbox=x=%d:y=%d:w=138:h=50:color=white:t=fill,"
                  "drawbox=x=%d:y=%d:w=138:h=50:color=black@0.5:t=fill,format=yuv420p" % (x0, y0, x0 + 106, y0 + 30, x0 + 109, y0 + 33))
            r = REAL_RUN([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", sim.out, "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "10",
                          "-profile:v", "high", "-an", sp], capture_output=True, text=True)
            v, rr = cg.check_video(sp, card_start=bj["starts"][-1], quiet=True) if r.returncode == 0 else ("ERROR", {"hard": [{}]})
            h = rr["hard"][0]
            want = "FAIL" if name == "原版" else "PASS"
            chk(v == want, "%s 蝦皮版：%.2f 秒外框 %s 距離 %.1f ⇒ %s（要 %s）" % (name, h.get("t", -1), h.get("bbox"), h.get("gap", -1), v, want))
            if name == "patch 版":
                cg.check_video(sp, card_start=bj["starts"][-1], quiet=True, out=os.path.join(HERE, "card_builder_patch後_蝦皮版模擬.jpg"))
    finally:
        if not a.keep:
            shutil.rmtree(base, ignore_errors=True)
    print("test_card_gap_builder %s" % ("全部通過" if ok_all else "有失敗"))
    return 0 if ok_all else 1


CACHE_DIR = None

if __name__ == "__main__":
    sys.exit(main())
