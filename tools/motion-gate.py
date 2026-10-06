#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""motion-gate.py — 純商品片「字會閃」擋門：量每格之間的動態，抓規律擺盪與靜止段的週期跳格（工單 #4-A）。

為什麼：舊做法（2× 放大＋ffmpeg zoompan）裁切框只能整數像素移動，每 4–5 格跳一次 ⇒ 商品字在閃。
  本機改用 kb-render（PIL 浮點 box 逐格 LANCZOS）後平滑。這支把「平不平滑」量成數字，寫死擋門。

用法：
  python tools/motion-gate.py <mp4> [--box x,y,w,h] [--csv out.csv] [--json 結果.json] [--start 秒] [--end 秒]
    --start／--end：只量這段時間（例：prodfilm sheet 只量片尾卡之前的推近鏡頭、片尾卡從彈跳結束後另外量）
  python tools/motion-gate.py --selftest
回傳：0＝全部 PASS、1＝有 FAIL、2＝讀檔錯誤／selftest 缺樣本（驗收沒跑）。

量法：每格灰階，d[t]＝第 t 格跟前一格的平均絕對差（0–255 灰階）。
  d 超過 CUT_ABS 的地方當轉場切開；每段（≥ MIN_SEG 格）判：
  ① 規律擺盪：相鄰差平均 ÷ 段平均 > OSC_RATIO，或去趨勢後 2–8 格週期的自相關 > AC_MIN（擺幅夠大才算）→ FAIL
  ② 靜止段（d 中位數 < STATIC_MED）出現週期性尖峰（≥ SPIKE_MIN_COUNT 次、間隔幾乎固定）→ FAIL
  ③ 其餘 PASS
"""
import argparse
import csv
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gatelib  # noqa: E402

# ── 門檻（怎麼定的寫在旁邊；實測樣本後的校準結果見 out/工單4-報告.md）──────────────
CUT_ABS = 12.0        # 轉場：相鄰格平均差 > 12 灰階。閃爍尖峰約 4.6（README），真轉場通常 20 以上，取中間偏低
MIN_SEG = 10          # 少於 10 格（0.33 秒）的段不判，只列出來
OSC_RATIO = 0.15      # 工單 #5（全尺寸 1080×1920、--box 290,500,500,900、30fps 母片）重定：
                      #   母片 新 kb-render 8 支 39 段：最大 0.12（tsaio 段2、澎澎 段4）；舊 zoompan 5 支 20 段：最小 0.18（NIVEA密集修護乳液 段2）
                      #   ⇒ 取中間 0.15，兩邊各留 0.03。資料：jobs/wo5-擋門整合-1006/fixtures/motion-calib-1006-classes.json（selftest 會逐段核）
                      #   #4 的 0.10 是在 250×450 縮圖樣本上定的；全尺寸母片的噪底就到 0.1 左右（tsaio 0.11／0.12 會被誤擋）
                      # ⚠️ 只量 30fps 母片：蝦皮版（brand-stamp fps=24）30→24 每 5 格丟 1 格，新舊都 0.30–0.38（真的頓挫，見工單5報告 A2）
                      # ⚠️ 只適用純商品片（靜態圖＋推近）；真的在動的影片比值會更高
AC_LAGS = range(2, 9) # 2–8 格週期（工單）
AC_MIN = 0.35         # 去趨勢後自相關峰值。純雜訊在 60 格長度下約 ±0.25 以內；規律 4–5 格擺盪 > 0.5
AC_DETREND = 9        # 去趨勢用的移動平均窗（格）：拿掉縮放加減速造成的慢變化
AMP_MIN = 0.08        # 擺幅門檻：d 的標準差 ÷ 平均 < 0.08 就不看自相關（避免平滑片的壓縮雜訊被當週期）
STATIC_MED = 0.3      # 工單給的值：段中位數 < 0.3 灰階＝畫面幾乎不動
SPIKE_ABS = 1.0       # 靜止段尖峰：d > 1.0 而且 > SPIKE_REL × 中位數
SPIKE_REL = 4.0
SPIKE_MIN_COUNT = 3   # 至少 3 次尖峰才談週期
SPIKE_JITTER = 1      # 尖峰間隔跟中位數差 ≤ 1 格算「一致」
SPIKE_REGULAR = 0.75  # ≥ 75% 的間隔一致＝規律（壓縮雜訊偶爾多一根或少一根尖峰也照抓）


def frame_diffs(frames):
    return np.array([float(np.mean(np.abs(frames[i] - frames[i - 1]))) for i in range(1, len(frames))], dtype=np.float64)


def split_segments(d):
    """依轉場尖峰切段 → [(start, end)]，d 的索引、end 不含；轉場那一格本身不歸任何段。"""
    segs, start = [], 0
    for i, v in enumerate(d):
        if v > CUT_ABS:
            if i > start:
                segs.append((start, i))
            start = i + 1
    if start < len(d):
        segs.append((start, len(d)))
    return segs


def autocorr_peak(x):
    """去趨勢後，2–8 格的正規化自相關最大值與對應週期。"""
    if len(x) < max(AC_LAGS) * 2 + AC_DETREND:
        return 0.0, 0
    k = np.ones(AC_DETREND) / AC_DETREND
    trend = np.convolve(np.pad(x, AC_DETREND // 2, mode="edge"), k, mode="valid")[:len(x)]
    r = x - trend
    r = r - r.mean()
    den = float(np.dot(r, r))
    if den <= 1e-12:
        return 0.0, 0
    best, lag = 0.0, 0
    for L in AC_LAGS:
        c = float(np.dot(r[:-L], r[L:])) / den * len(r) / (len(r) - L)
        if c > best:
            best, lag = c, L
    return best, lag


def judge_segment(x):
    """一段的判定 → dict(verdict, reason, mean, adj, ratio, ac, lag, spikes, med)。"""
    mean, med = float(np.mean(x)), float(np.median(x))
    adj = float(np.mean(np.abs(np.diff(x)))) if len(x) > 1 else 0.0
    ratio = adj / mean if mean > 1e-9 else 0.0
    amp = float(np.std(x)) / mean if mean > 1e-9 else 0.0
    ac, lag = autocorr_peak(x)
    out = dict(mean=mean, med=med, adj=adj, ratio=ratio, amp=amp, ac=ac, lag=lag, spikes=[])
    if len(x) < MIN_SEG:
        return dict(out, verdict="SKIP", reason="段太短（%d 格 < %d）" % (len(x), MIN_SEG))
    if med < STATIC_MED:
        thr = max(SPIKE_ABS, SPIKE_REL * med)
        hot = [i for i, v in enumerate(x) if v > thr]
        spikes = [i for k, i in enumerate(hot) if k == 0 or i - hot[k - 1] > 1]   # 連續兩格都高＝同一次跳格
        out["spikes"] = spikes
        if len(spikes) >= SPIKE_MIN_COUNT:
            gaps = np.diff(spikes)
            mg = float(np.median(gaps))
            regular = float(np.mean(np.abs(gaps - mg) <= SPIKE_JITTER))
            if regular >= SPIKE_REGULAR:
                return dict(out, verdict="FAIL", reason="靜止段週期跳格：%d 次尖峰、約每 %.0f 格一次（%.0f%% 間隔一致）"
                            % (len(spikes), mg, regular * 100))
        return dict(out, verdict="PASS", reason="靜止段，無週期尖峰（尖峰 %d 次）" % len(spikes))
    if ratio > OSC_RATIO:
        return dict(out, verdict="FAIL", reason="規律擺盪：相鄰差/平均 %.2f > %.2f" % (ratio, OSC_RATIO))
    if amp >= AMP_MIN and ac > AC_MIN:
        return dict(out, verdict="FAIL", reason="週期擺盪：%d 格週期自相關 %.2f > %.2f" % (lag, ac, AC_MIN))
    return dict(out, verdict="PASS", reason="平滑")


def analyse(path, box=None, csv_path=None, quiet=False, start=None, end=None, json_path=None):
    frames, fps = gatelib.read_gray_frames(path, box, start, end)
    base = gatelib.read_gray_frames.first or 0   # --start 時，格號照整支片算
    if not quiet and abs(fps - 30) > 0.5:   # 只提醒，不改判定
        print("  ⚠️ 這支是 %.2f fps：門檻是用 30fps 母片定的；24fps 交付檔（brand-stamp）丟格會讓比值到 0.3 以上，請量母片" % fps)
    if len(frames) < 3:
        raise ValueError("影片格數太少（%d）：%s" % (len(frames), path))
    d = frame_diffs(frames)
    segs = split_segments(d)
    results = []
    for s, e in segs:
        r = judge_segment(d[s:e])
        r.update(start=base + s + 1, end=base + e)   # 換成影片格號：d[i] 是第 i+1 格對第 i 格
        results.append(r)
    if csv_path:
        seg_of = {}
        for k, r in enumerate(results):
            for f in range(r["start"], r["end"] + 1):
                seg_of[f] = k + 1
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["frame", "time_s", "mean_abs_diff", "segment"])
            for i, v in enumerate(d):
                w.writerow([base + i + 1, "%.3f" % ((base + i + 1) / fps), "%.4f" % v, seg_of.get(base + i + 1, "cut")])
    if not quiet:
        print("%s  %d 格 @ %.2f fps%s" % (os.path.basename(path), len(frames), fps, "  box=%s" % (box,) if box else ""))
        print("  d 前 12 格：" + " ".join("%.2f" % v for v in d[:12]))
        for k, r in enumerate(results, 1):
            print("  段%d 格%d–%d（%.1f–%.1f 秒）平均 %.3f｜相鄰差 %.3f｜比 %.2f｜自相關 %.2f@%d｜%s %s"
                  % (k, r["start"], r["end"], r["start"] / fps, r["end"] / fps, r["mean"], r["adj"], r["ratio"], r["ac"], r["lag"],
                     {"PASS": "✅ PASS", "FAIL": "🔴 FAIL", "SKIP": "⏭️ SKIP"}[r["verdict"]], r["reason"]))
    verdict = "FAIL" if any(r["verdict"] == "FAIL" for r in results) else "PASS"
    if not quiet:
        print("  ⇒ %s" % verdict)
    if json_path:
        import json
        segs = [dict(seg=k, start=r["start"], end=r["end"], t0=round(r["start"] / fps, 3), t1=round(r["end"] / fps, 3), mean=round(r["mean"], 4),
                     adj=round(r["adj"], 4), ratio=round(r["ratio"], 4), ac=round(r["ac"], 3), lag=r["lag"], verdict=r["verdict"], reason=r["reason"])
                for k, r in enumerate(results, 1)]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(dict(file=os.path.basename(path), fps=round(fps, 3), box=list(box) if box else None, start=start, end=end,
                           threshold=OSC_RATIO, verdict=verdict, segments=segs), f, ensure_ascii=False, indent=1)
    return verdict, results, d


# ── 合成資料（樣本缺時的邏輯自測；不能取代樣本驗收）──────────────────────────────
def _synthetic_videos(tmpdir):
    import cv2
    from PIL import Image
    rng = np.random.default_rng(4)
    W, H = 300, 450

    def base(seed):
        r = np.random.default_rng(seed)
        img = (r.normal(128, 18, (H * 2, W * 2))).clip(0, 255).astype(np.uint8)
        img = cv2.GaussianBlur(img, (0, 0), 2)
        for k in range(8):
            cv2.putText(img, "BRAND %d 500ml" % k, (40, 120 + k * 100), cv2.FONT_HERSHEY_SIMPLEX, 1.6, 20, 3, cv2.LINE_AA)
        return img

    def render(img, boxes, integer):
        out = []
        pil = Image.fromarray(img)
        for x0, y0, x1, y1 in boxes:
            if integer:   # 舊：整數像素裁切＋縮放（zoompan 的行為）
                xi, yi = int(x0), int(y0)
                wi, hi = int(x1 - x0), int(y1 - y0)
                crop = img[yi:yi + hi, xi:xi + wi]
                out.append(cv2.resize(crop, (W, H), interpolation=cv2.INTER_LINEAR))
            else:         # 新：浮點 box 逐格 LANCZOS（kb-render）
                out.append(np.asarray(pil.resize((W, H), Image.LANCZOS, box=(x0, y0, x1, y1))))
        return out

    def plan():
        boxes = []
        for t in range(90):   # 段 1：慢慢推近 1.00 → 1.08
            z = 1.0 + 0.08 * t / 89
            w, h = 2 * W / z, 2 * H / z
            boxes.append(((2 * W - w) / 2, (2 * H - h) / 2, (2 * W + w) / 2, (2 * H + h) / 2))
        return boxes

    def pan():
        return [(20 + 0.2 * t, 20, 20 + 0.2 * t + 2 * W - 60, 20 + 2 * H - 60) for t in range(90)]   # 段 2：每格 0.2 px 慢移

    paths = {}
    for name, integer in (("old_zoompan", True), ("new_kbrender", False)):
        frames = render(base(1), plan(), integer) + render(base(2), pan(), integer)
        p = os.path.join(tmpdir, name + ".avi")   # 無損 FFV1：只驗演算法，不混進編碼器雜訊
        vw = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*"FFV1"), 30, (W, H), isColor=False)
        for f in frames:
            vw.write(f)
        vw.release()
        paths[name] = p
    _ = rng
    return paths


CALIB_JSON = os.path.join(gatelib.ROOT, "jobs", "wo5-擋門整合-1006", "fixtures", "motion-calib-1006-classes.json")
TS_DIR = os.path.join(gatelib.ROOT, "jobs", "wo5-擋門整合-1006", "fixtures", "ts")
FULL_BOX = (290, 500, 500, 900)   # builder 的商品固定框（工單 #5 量法）


def _calib_check():
    """10/6 校準 log（母片 30fps 的動態段）逐段核：新 kb 全 ≤ 門檻、舊 zoompan 全 > 門檻。回傳 (ok, 說明)。"""
    import json
    segs = json.load(open(CALIB_JSON, encoding="utf-8"))["segments"]
    mom = [x for x in segs if x["src"] == "母片CRF0" and x["kind"] == "動"]
    new = [x for x in mom if x["cls"] == "新kb"]
    old = [x for x in mom if x["cls"] == "舊zoompan"]
    bad_new = [x for x in new if x["ratio"] > OSC_RATIO]
    bad_old = [x for x in old if x["ratio"] <= OSC_RATIO]
    print("  母片 新 kb：%d 段，比值最大 %.2f（門檻 %.2f）%s" % (len(new), max(x["ratio"] for x in new), OSC_RATIO, "" if not bad_new else "；超過：%s" % bad_new))
    print("  母片 舊 zoompan：%d 段，比值最小 %.2f %s" % (len(old), min(x["ratio"] for x in old), "" if not bad_old else "；沒超過：%s" % bad_old))
    shop = [x for x in segs if x["src"] == "蝦皮版CRF10" and x["kind"] == "動"]
    if shop:
        print("  （參考）蝦皮版 24fps：%d 段，比值 %.2f–%.2f ⇒ 交付檔分不出新舊，擋門只量母片" % (len(shop), min(x["ratio"] for x in shop), max(x["ratio"] for x in shop)))
    return not bad_new and not bad_old and len(new) > 0 and len(old) > 0


def _ffmpeg():
    import shutil
    return os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")


def _fullsize_clips(tmp, ff):
    """全尺寸樣本：ts 第 1 鏡成片格放大成 1536×2688 當場景，把真品去背照貼在 lw 憑證 quad 的位置（模擬 lw2x 銳利標籤），
    舊路＝builder 原本的 ffmpeg scale=2160:3840＋zoompan；新路＝kb-render 的浮點 box LANCZOS；都編 30fps CRF 10（同 builder 母片）。"""
    import subprocess
    from PIL import Image
    bg = Image.open(os.path.join(TS_DIR, "ts_shot1_t0.10.jpg")).convert("RGB").resize((1536, 2688), Image.LANCZOS)
    al = Image.open(os.path.join(TS_DIR, "ts_alpha.png")).convert("RGBA").resize((437, 1034), Image.LANCZOS)
    bg.paste(al, (556, 1029), al)
    scene = os.path.join(tmp, "scene.png")
    bg.save(scene)
    n, fps, enc = 99, 30, ["-c:v", "libx264", "-crf", "10", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    W, H = bg.size
    kb = os.path.join(tmp, "kb.mp4")
    p = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920", "-r", str(fps), "-i", "-"] + enc + [kb],
                         stdin=subprocess.PIPE)
    for i in range(n):
        z = 1.0 + 0.05 * i / (n - 1)
        w, h = W / z, H / z
        x0, y0 = min(max(0.5 * W - w / 2, 0.0), W - w), min(max(0.45 * H - h / 2, 0.0), H - h)
        p.stdin.write(bg.resize((1080, 1920), Image.LANCZOS, box=(x0, y0, x0 + w, y0 + h)).tobytes())
    p.stdin.close()
    p.wait()
    zp = os.path.join(tmp, "zoompan.mp4")
    vf = ("scale=2160:3840:flags=lanczos,zoompan=z='1.0+(0.05)*on/%d':x='iw*0.5-(iw/zoom/2)':y='ih*0.45-(ih/zoom/2)':d=%d:s=1080x1920:fps=%d,"
          "setsar=1,format=yuv420p" % (n - 1, n, fps))
    subprocess.run([ff, "-y", "-loglevel", "error", "-loop", "1", "-i", scene, "-vf", vf, "-frames:v", str(n)] + enc + [zp], check=True)
    return kb, zp


def selftest():
    ok = True
    cases = [(gatelib.fixture("motion", "kw_old_zoompan_crop.mp4"), "FAIL"), (gatelib.fixture("motion", "kw_new_kbrender_crop.mp4"), "PASS")]
    miss = gatelib.missing([p for p, _ in cases] + [CALIB_JSON, os.path.join(TS_DIR, "ts_shot1_t0.10.jpg"), os.path.join(TS_DIR, "ts_alpha.png")])
    print("== 樣本驗收 1（工單 #4-A：250×450 裁切樣本）")
    for p, want in cases:
        if not os.path.exists(p):
            continue
        got, _, _ = analyse(p)
        good = got == want
        ok &= good
        print("  %s %s：要 %s、得 %s\n" % ("✅" if good else "❌", os.path.basename(p), want, got))
    print("== 樣本驗收 2（工單 #5：10/6 校準 log，全尺寸 30fps 母片逐段核）")
    if os.path.exists(CALIB_JSON):
        good = _calib_check()
        ok &= good
        print("  %s 新 kb 全 PASS、舊 zoompan 全 FAIL\n" % ("✅" if good else "❌"))
    print("== 樣本驗收 3（工單 #5：全尺寸 1080×1920 樣本，ts 格＋真品標籤，真的 ffmpeg zoompan vs kb-render）")
    ff = _ffmpeg()
    if not ff:
        print("  ⚠️ 找不到 ffmpeg（PATH 或 FFMPEG_BIN），這組沒跑")
        miss.append("ffmpeg")
    elif os.path.exists(os.path.join(TS_DIR, "ts_alpha.png")):
        with tempfile.TemporaryDirectory() as tmp:
            kb, zp = _fullsize_clips(tmp, ff)
            for path, want in ((zp, "FAIL"), (kb, "PASS")):
                got, _, _ = analyse(path, FULL_BOX)
                good = got == want
                ok &= good
                print("  %s 全尺寸 %s：要 %s、得 %s\n" % ("✅" if good else "❌", os.path.basename(path), want, got))
    print("== 合成資料自測（模擬整數像素裁切 vs 浮點 LANCZOS；只驗邏輯，不能取代樣本）")
    with tempfile.TemporaryDirectory() as tmp:
        vids = _synthetic_videos(tmp)
        for name, want in (("old_zoompan", "FAIL"), ("new_kbrender", "PASS")):
            got, _, _ = analyse(vids[name])
            good = got == want
            ok &= good
            print("  %s 合成 %s：要 %s、得 %s\n" % ("✅" if good else "❌", name, want, got))
    if miss:
        print("結果：%s；有樣本沒跑（缺 %s）⇒ exit 2" % ("已跑的都通過" if ok else "有沒過的", "、".join(miss)))
        return 2
    print("結果：%s" % ("全部通過" if ok else "有沒過的"))
    return 0 if ok else 1


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="純商品片動態閃爍擋門")
    ap.add_argument("video", nargs="?", help="mp4")
    ap.add_argument("--box", help="只量這塊：x,y,w,h（例如商品區）")
    ap.add_argument("--csv", help="把每格的差值寫成 CSV")
    ap.add_argument("--json", help="把判定結果（每段數字＋總判定）寫成 JSON（prodfilm sheet 讀這個）")
    ap.add_argument("--start", type=float, help="只量這個時間（秒）之後")
    ap.add_argument("--end", type=float, help="只量這個時間（秒）之前")
    ap.add_argument("--selftest", action="store_true", help="跑樣本驗收（fixtures/motion）")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.video:
        ap.error("要給 mp4 或 --selftest")
    try:
        verdict, _, _ = analyse(a.video, gatelib.parse_box(a.box) if a.box else None, a.csv, start=a.start, end=a.end, json_path=a.json)
    except (OSError, ValueError) as e:
        print("❌ %s" % e, file=sys.stderr)
        return 2
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
