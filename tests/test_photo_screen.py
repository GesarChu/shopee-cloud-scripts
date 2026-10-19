# -*- coding: utf-8 -*-
"""工單 #7 驗收：tools/photo-screen.py。合成圖都在這裡用 numpy／Pillow 現畫（⛔ 放真圖）。
合成驗收表 12 條一條一個測試（預期是 Kai程式專線定的，⛔ 改預期來配合程式），另外加幾條邊界測試。

跑法：python -m pytest tests/test_photo_screen.py   或   python tests/test_photo_screen.py
產出示範：python tests/test_photo_screen.py --demo out/工單7    （合成圖＋json／md／sheet）
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "tools", "photo-screen.py")
REF = os.path.join(REPO, "jobs", "wo7-真品照初篩-1019", "參考-建卡量法.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ps = _load("photo_screen", TOOL)

WHITE = (255, 255, 255)
BOX = (40, 90, 160)


def font(size):
    return ImageFont.load_default(size=size)


def box_with_text(d, x0, y0, x1, y1, color=BOX, text_color=(245, 245, 245), lines=("TSAIO MINT", "FACE WASH", "100 g")):
    d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=color)
    h = y1 - y0
    for k, t in enumerate(lines):
        d.text((x0 + (x1 - x0) * 0.12, y0 + h * (0.18 + 0.12 * k)), t, fill=text_color, font=font(int(max(18, h * 0.06))))


# ── 合成驗收表 ────────────────────────────────────────────────────────────────
def c01():   # 1400×1400 白底，中間 900×1200 有色盒（盒上畫幾行字），不碰邊
    im = Image.new("RGB", (1400, 1400), WHITE)
    box_with_text(ImageDraw.Draw(im), 250, 100, 1150, 1300)
    return im


def c02():   # 1000×1000 白底，盒 662×500
    im = Image.new("RGB", (1000, 1000), WHITE)
    box_with_text(ImageDraw.Draw(im), 169, 250, 831, 750)
    return im


def c03():   # 1024×1024 白底，盒 850×640
    im = Image.new("RGB", (1024, 1024), WHITE)
    box_with_text(ImageDraw.Draw(im), 87, 192, 937, 832)
    return im


def c04():   # 1400×1400 白底，兩個分開的盒
    im = Image.new("RGB", (1400, 1400), WHITE)
    d = ImageDraw.Draw(im)
    box_with_text(d, 100, 250, 600, 1150)
    box_with_text(d, 800, 250, 1300, 1150, color=(160, 60, 40))
    return im


def c05():   # #1＋白底黑字橫條，橫跨商品左右輪廓、兩端伸出商品外
    im = c01()
    d = ImageDraw.Draw(im)
    d.rectangle([150, 640, 1249, 719], fill=WHITE)
    d.text((165, 655), "TEA TREE OIL | SUPER COOL | BUY 2 GET 1", fill=(0, 0, 0), font=font(46))
    return im


def c06():   # #1＋右上角圓形標章，跟商品間隔 ≥ 4 px
    im = c01()
    d = ImageDraw.Draw(im)
    d.ellipse([1180, 40, 1360, 220], fill=(220, 30, 30))
    d.text((1222, 110), "NEW", fill=WHITE, font=font(40))
    return im


def c07():   # 斜角盒：正面＋上方平行四邊形頂面（占商品高 16%）＋右側平行四邊形側面（占寬 30%），三面亮度不同
    im = Image.new("RGB", (1400, 1400), WHITE)
    d = ImageDraw.Draw(im)
    x0, y0, W, H = 250, 100, 900, 1200
    ws, ht = int(W * 0.30), int(H * 0.16)
    fx1, fy0 = x0 + W - ws, y0 + ht
    d.polygon([(x0, fy0), (fx1, fy0), (x0 + W, y0), (x0 + ws, y0)], fill=(215, 185, 135))           # 頂面（亮）
    d.polygon([(fx1, fy0), (x0 + W, y0), (x0 + W, y0 + H - ht), (fx1, y0 + H)], fill=(95, 70, 40))   # 側面（暗）
    box_with_text(d, x0, fy0, fx1, y0 + H, color=(150, 110, 60))                                      # 正面
    return im


def c08():   # 白底上的白瓶（瓶身 RGB ≥ 235，只有淡灰輪廓）
    im = Image.new("RGB", (1400, 1400), WHITE)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([450, 330, 950, 1300], radius=60, fill=(245, 245, 245), outline=(200, 200, 200), width=3)
    d.rectangle([620, 150, 780, 332], fill=(240, 240, 240), outline=(200, 200, 200), width=3)
    d.text((540, 700), "PURE", fill=(236, 236, 236), font=font(60))
    return im


def c09():   # #1＋整張斜排、半透明（alpha 0.2）重複字樣浮水印
    im = c01().convert("RGBA")
    layer = Image.new("RGBA", (2000, 2000), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for yy in range(0, 2000, 160):
        for xx in range(-200, 2000, 420):
            d.text((xx + (yy // 160) % 2 * 210, yy), "SAMPLE SHOP", fill=(0, 0, 0, 51), font=font(44))
    layer = layer.rotate(30, resample=Image.BICUBIC).crop((300, 300, 1700, 1700))
    return Image.alpha_composite(im, layer).convert("RGB")


def c10():   # #1 存成 RGBA 去背 png
    a = np.zeros((1400, 1400), np.uint8)
    a[100:1300, 250:1150] = 255
    rgb = np.asarray(c01())
    return Image.fromarray(np.dstack([rgb, a]), "RGBA")


def c11():   # #1 但商品底邊貼齊圖片下緣
    im = Image.new("RGB", (1400, 1400), WHITE)
    box_with_text(ImageDraw.Draw(im), 250, 200, 1150, 1400)
    return im


def repeat_boxes(n, bw, bh, canvas):
    im = Image.new("RGB", canvas, WHITE)
    d = ImageDraw.Draw(im)
    x0 = (canvas[0] - n * bw) // 2
    y0 = (canvas[1] - bh) // 2
    for k in range(n):   # 互相相連（中間沒有縫）
        x = x0 + k * bw
        d.rectangle([x, y0, x + bw - 1, y0 + bh - 1], fill=(200, 60, 60))
        d.rectangle([x + bw * 0.1, y0 + bh * 0.15, x + bw * 0.9, y0 + bh * 0.45], fill=(250, 230, 120))
        d.ellipse([x + bw * 0.25, y0 + bh * 0.55, x + bw * 0.75, y0 + bh * 0.55 + bw * 0.5], fill=(40, 40, 40))
        d.line([x + bw - 3, y0, x + bw - 3, y0 + bh - 1], fill=(120, 30, 30), width=4)
    return im


def c12():   # 同一個盒子（120×200）橫排 5 個、互相相連
    return repeat_boxes(5, 120, 200, (1000, 1000))


CASES = {   # 編號: (畫法, 副檔名, 允許的結論, 原因裡要有的代碼（任一）)
    1: (c01, "png", {"收"}, None),
    2: (c02, "png", {"不收"}, "long<700"),
    3: (c03, "png", {"要人眼"}, "long700-999"),
    4: (c04, "png", {"不收"}, "n_obj"),
    5: (c05, "png", {"不收"}, "cross-text"),
    6: (c06, "png", {"收"}, None),
    7: (c07, "png", {"要人眼", "不收"}, "slant|judge:front_view"),
    8: (c08, "png", {"要人眼", "不收"}, "white|solid|nofg"),
    9: (c09, "png", {"要人眼", "不收"}, "wm"),
    10: (c10, "png", {"收"}, None),
    11: (c11, "png", {"收"}, None),
    12: (c12, "png", {"要人眼", "不收"}, "repeat"),
}


def write_cases(d):
    paths = {}
    for k, (fn, ext, _, _) in CASES.items():
        p = os.path.join(d, "合成%02d.%s" % (k, ext))
        fn().save(p)
        paths[k] = p
    return paths


def codes(r):
    return {x["code"] for x in r.reasons}


class Acceptance(unittest.TestCase):
    """合成驗收表 #1–#12。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="wo7_")
        cls.paths = write_cases(cls.tmp)
        cls.res = {k: ps.apply_judge(ps.screen(p), ps.NullJudge()) for k, p in cls.paths.items()}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def check(self, k):
        _, _, want, code = CASES[k]
        r = self.res[k]
        self.assertIn(r.verdict, want, "#%d 判 %s：%s" % (k, r.verdict, [x["text"] for x in r.reasons]))
        if code:
            self.assertTrue(codes(r) & set(code.split("|")), "#%d 原因代碼 %s 不含 %s" % (k, codes(r), code))
        return r

    def test_01_front_box(self):
        r = self.check(1)
        self.assertEqual(r.m["product_box"], [250, 100, 1150, 1300])
        self.assertEqual((r.m["long_side"], r.m["height"], r.m["n_objects"]), (1200, 1200, 1))
        self.assertGreaterEqual(r.m["solidity"], 0.88)
        self.assertEqual(r.m["touches_edge"], [])

    def test_02_small(self):
        self.check(2)

    def test_03_mid(self):
        self.check(3)

    def test_04_two_objects(self):
        self.assertEqual(self.check(4).m["n_objects"], 2)

    def test_05_cross_text(self):
        self.check(5)

    def test_06_badge_paint(self):
        r = self.check(6)
        paint = [p for p in r.m["paint"] if p["kind"] == "標章"]
        self.assertEqual(len(paint), 1, r.m["paint"])
        p = paint[0]
        self.assertGreaterEqual(p["gap"], 4)
        b = p["box"]
        self.assertLessEqual(b[0], 1180)
        self.assertGreaterEqual(b[2], 1361)
        self.assertGreaterEqual(b[0], 1150)   # ⛔ 碰到商品像素（商品右緣 x=1150）
        self.assertTrue(any("塗背景色" in s for s in r.suggest))
        self.assertEqual(r.m["product_box"], [250, 100, 1150, 1300])

    def test_07_oblique(self):
        r = self.check(7)
        self.assertTrue(any("斜" in x["text"] or "正面" in x["text"] for x in r.reasons))

    def test_08_white_bottle(self):
        self.check(8)

    def test_09_watermark(self):
        r = self.check(9)
        self.assertTrue(any("浮水印" in x["text"] for x in r.reasons))

    def test_10_rgba_matches_card(self):
        r = self.check(10)
        ref = _load("card_ref", REF).measure_alpha(self.paths[10])
        for k in ("solidity", "n_objects", "fg_ratio"):
            self.assertEqual(r.m["card_raw"][k], ref[k], k)
            self.assertEqual(r.m[k], ref[k], k)
        self.assertEqual(r.m["source"], "alpha")

    def test_11_touch_edge(self):
        r = self.check(11)
        self.assertEqual(r.m["touches_edge"], ["下"])
        self.assertTrue(any(x["level"] == "備註" and "碰" in x["text"] for x in r.reasons))

    def test_12_repeat(self):
        r = self.check(12)
        self.assertGreaterEqual(r.m["repeat"]["score"], ps.REPEAT_MIN)


class Extra(unittest.TestCase):
    """驗收表以外的邊界：尺寸過的重複多包、色條跨輪廓、寬包、間隔太近的標章、只在背景的浮水印、webp／JPEG、單一正面不誤判。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wo7_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_img(self, im, name="x.png", **kw):
        p = os.path.join(self.tmp, name)
        im.save(p, **kw)
        return ps.apply_judge(ps.screen(p), ps.NullJudge())

    def test_big_repeat_needs_eye(self):
        r = self.run_img(repeat_boxes(5, 240, 1100, (1600, 1400)))   # 尺寸過（1200×1100），靠重複圖樣抓
        self.assertGreaterEqual(r.m["long_side"], 1000)
        self.assertNotEqual(r.verdict, "收")
        self.assertIn("repeat", codes(r))

    def test_colored_strip_crossing(self):
        im = c01()
        d = ImageDraw.Draw(im)
        d.rectangle([150, 640, 1249, 719], fill=(250, 210, 40))
        d.text((165, 655), "TEA TREE OIL | SUPER COOL", fill=(0, 0, 0), font=font(46))
        r = self.run_img(im)
        self.assertNotEqual(r.verdict, "收")
        self.assertTrue(codes(r) & {"cross-bar", "cross-bar?", "cross-text"}, codes(r))

    def test_wide_pack(self):
        im = Image.new("RGB", (1600, 1000), WHITE)
        box_with_text(ImageDraw.Draw(im), 100, 250, 1500, 750)   # 1400×500：高 < 600、寬高比 2.8
        r = self.run_img(im)
        self.assertEqual(r.verdict, "要人眼")
        self.assertIn("wide", codes(r))

    def test_badge_too_close(self):
        im = c01()
        ImageDraw.Draw(im).ellipse([1152, 40, 1332, 220], fill=(220, 30, 30))   # 離商品 1 px
        r = self.run_img(im)
        self.assertNotEqual(r.verdict, "收")

    def test_watermark_only_background_paintable(self):
        layer = Image.new("RGBA", (1400, 1400), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for k in range(8):
            d.text((20 + k * 46, 1330), "W", fill=(0, 0, 0, 51), font=font(40))   # 半透明淡色字只在左下角背景（字跟字分開）
        im = Image.alpha_composite(c01().convert("RGBA"), layer).convert("RGB")
        r = self.run_img(im)
        self.assertEqual(r.verdict, "收", [x["text"] for x in r.reasons])
        self.assertTrue(any(p["kind"] == "浮水印" for p in r.m["paint"]))

    def test_faint_blob_gets_paint_suggestion(self):
        layer = Image.new("RGBA", (1400, 1400), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rectangle([30, 1320, 230, 1380], fill=(0, 0, 0, 40))   # 一塊淡灰（不到浮水印的塊數）
        r = self.run_img(Image.alpha_composite(c01().convert("RGBA"), layer).convert("RGB"))
        self.assertEqual(r.verdict, "收")
        self.assertTrue(any(p["kind"] == "背景淡色塊" for p in r.m["paint"]), r.m["paint"])

    def test_jpeg_and_webp(self):
        for name, kw in (("x.jpg", {"quality": 85}), ("x.webp", {"quality": 85})):
            r = self.run_img(c01(), name, **kw)
            self.assertEqual(r.verdict, "收", "%s：%s" % (name, [x["text"] for x in r.reasons]))
            self.assertLessEqual(abs(r.m["long_side"] - 1200), 2)

    def test_symmetric_bottle_front(self):
        im = Image.new("RGB", (1400, 1400), WHITE)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([430, 330, 970, 1320], radius=80, fill=(30, 120, 70))
        d.rectangle([620, 120, 780, 340], fill=(20, 20, 20))
        d.text((520, 700), "HERBAL", fill=WHITE, font=font(64))
        r = self.run_img(im)
        self.assertEqual(r.verdict, "收", [x["text"] for x in r.reasons])

    def test_labeled_bottle_not_rejected(self):
        """正面的瓶子：圓肩（輪廓有斜邊）＋標籤上下緣（橫向強邊）＝左右對稱 ⇒ 最多要人眼，⛔ 不收。"""
        im = Image.new("RGB", (1400, 1400), WHITE)
        d = ImageDraw.Draw(im)
        d.polygon([(560, 120), (840, 120), (840, 300), (980, 420), (980, 1320), (420, 1320), (420, 420), (560, 300)], fill=(30, 120, 70))
        d.rectangle([420, 640, 979, 1000], fill=(240, 230, 200))
        d.text((480, 760), "HERBAL TONIC", fill=(30, 30, 30), font=font(56))
        r = self.run_img(im)
        self.assertNotEqual(r.verdict, "不收", [x["text"] for x in r.reasons])

    def test_two_tone_front_not_rejected(self):
        """正面的雙色盒（上 20% 白帶）不能被當成斜角「不收」；最多要人眼（交模型／人）。"""
        im = c01()
        ImageDraw.Draw(im).rectangle([250, 100, 1149, 340], fill=(235, 235, 225))
        r = self.run_img(im)
        self.assertNotEqual(r.verdict, "不收", [x["text"] for x in r.reasons])


class FakeModel(BaseHTTPRequestHandler):
    """程式內的假 OpenAI 相容伺服器（只聽 127.0.0.1）：回固定答案，記下收到的請求。"""
    answer = {"single_product": True, "front_view": True, "added_text": False, "multi_pack": False}
    seen = []

    def do_POST(self):   # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        FakeModel.seen.append((self.path, body))
        out = {"choices": [{"message": {"role": "assistant", "content": "```json\n%s\n```" % json.dumps(FakeModel.answer)}}]}
        data = json.dumps(out).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class JudgeInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), FakeModel)
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()
        cls.url = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        cls.tmp = tempfile.mkdtemp(prefix="wo7_")
        cls.paths = write_cases(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_null_judge(self):
        self.assertEqual(ps.NullJudge().ask("x", [0, 0, 1, 1], ps.QUESTIONS), {"status": "not_connected"})

    def test_http_payload_and_stricter_only(self):
        FakeModel.seen.clear()
        FakeModel.answer = {"single_product": True, "front_view": False, "added_text": False, "multi_pack": False}
        j = ps.HttpJudge(self.url, "fake")
        r = ps.apply_judge(ps.screen(self.paths[1]), j)   # 程式判收 ⇒ 模型說不是正面 ⇒ 要人眼
        self.assertEqual(r.judge["status"], "ok")
        self.assertEqual(r.verdict, "要人眼")
        path, body = FakeModel.seen[-1]
        self.assertEqual(path, "/v1/chat/completions")
        parts = body["messages"][-1]["content"]
        self.assertTrue(any(p.get("type") == "image_url" and p["image_url"]["url"].startswith("data:image/jpeg;base64,") for p in parts))

    def test_model_cannot_relax(self):
        FakeModel.answer = {"single_product": True, "front_view": True, "added_text": False, "multi_pack": False}
        j = ps.HttpJudge(self.url, "fake")
        r = ps.apply_judge(ps.screen(self.paths[2]), j)   # 程式判不收（長邊 662）
        self.assertEqual(r.verdict, "不收")
        r = ps.apply_judge(ps.screen(self.paths[7]), j)   # 斜角：模型說正面也不能變收
        self.assertNotEqual(r.verdict, "收")
        r = ps.apply_judge(ps.screen(self.paths[3]), j)   # 要人眼（700–999）：模型說都好也還是要人眼
        self.assertEqual(r.verdict, "要人眼")

    def test_cli_judge_http(self):
        FakeModel.answer = {"single_product": True, "front_view": True, "added_text": True, "multi_pack": False}
        out = os.path.join(self.tmp, "j.json")
        r = subprocess.run([sys.executable, TOOL, self.paths[1], "--judge", "http", "--judge-url", self.url, "--judge-model", "fake",
                            "--json", out], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = json.load(open(out, encoding="utf-8"))[0]
        self.assertEqual(res["judge"]["status"], "ok")
        self.assertEqual(res["verdict"], "要人眼")   # 模型說有後加字條 ⇒ 收 變 要人眼
        self.assertTrue(any(x["code"] == "model:added_text" for x in res["reasons"]))

    def test_server_down_is_not_pass(self):
        j = ps.HttpJudge("http://127.0.0.1:9", "fake", timeout=2)
        r = ps.apply_judge(ps.screen(self.paths[7]), j)
        self.assertNotEqual(r.verdict, "收")
        if r.verdict != "不收":
            self.assertEqual(r.judge["status"], "error")


class CLI(unittest.TestCase):
    def test_folder_sort_and_outputs(self):
        tmp = tempfile.mkdtemp(prefix="wo7_")
        self.addCleanup(shutil.rmtree, tmp, True)
        d = os.path.join(tmp, "imgs")
        os.makedirs(d)
        write_cases(d)
        js, md, sh = os.path.join(tmp, "o.json"), os.path.join(tmp, "o.md"), os.path.join(tmp, "o.jpg")
        r = subprocess.run([sys.executable, TOOL, d, "--json", js, "--md", md, "--sheet", sh], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = json.load(open(js, encoding="utf-8"))
        order = [ps.ORDER[x["verdict"]] for x in res]
        self.assertEqual(order, sorted(order))
        ok = [x["measure"]["long_side"] for x in res if x["verdict"] == "收"]
        self.assertEqual(ok, sorted(ok, reverse=True))
        im = Image.open(sh)
        self.assertLessEqual(im.width, 3800)
        self.assertLessEqual(os.path.getsize(sh), 3 * 1024 * 1024)
        self.assertIn("| 1 |", open(md, encoding="utf-8").read())

    def test_sheet_limits_many_images(self):
        tmp = tempfile.mkdtemp(prefix="wo7_")
        self.addCleanup(shutil.rmtree, tmp, True)
        rng = np.random.default_rng(7)
        for k in range(40):   # 雜訊圖：最難壓的情況
            Image.fromarray(rng.integers(0, 255, (900, 900, 3), dtype=np.uint8)).save(os.path.join(tmp, "n%02d.jpg" % k), quality=95)
        sh = os.path.join(tmp, "s.jpg")
        r = subprocess.run([sys.executable, TOOL, tmp, "--sheet", sh], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLessEqual(Image.open(sh).width, 3800)
        self.assertLessEqual(os.path.getsize(sh), 3 * 1024 * 1024)

    def test_no_images_exit2(self):
        tmp = tempfile.mkdtemp(prefix="wo7_")
        self.addCleanup(shutil.rmtree, tmp, True)
        r = subprocess.run([sys.executable, TOOL, tmp], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)


class Static(unittest.TestCase):
    def test_imports_and_paths(self):
        import ast
        import re
        src = open(TOOL, encoding="utf-8").read()
        mods = set()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or "").split(".")[0])
        third = {m for m in mods if m not in getattr(sys, "stdlib_module_names", mods)}
        self.assertLessEqual(third, {"cv2", "numpy", "PIL"}, third)
        self.assertFalse(mods & {"requests", "torch", "tensorflow", "easyocr", "pytesseract", "paddleocr", "onnxruntime", "transformers"})
        self.assertIsNone(re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/|Desktop", src))


def demo(out):
    """合成圖＋json／md／sheet 放 out（out/工單7）。"""
    imgs = os.path.join(out, "合成圖")
    os.makedirs(imgs, exist_ok=True)
    write_cases(imgs)
    repeat_boxes(5, 240, 1100, (1600, 1400)).save(os.path.join(imgs, "合成13-大的重複多包.png"))
    r = subprocess.run([sys.executable, TOOL, imgs, "--json", os.path.join(out, "結果.json"), "--md", os.path.join(out, "結果.md"),
                        "--sheet", os.path.join(out, "驗圖.jpg")], capture_output=True, text=True, encoding="utf-8")
    print(r.stdout + r.stderr)
    return r.returncode


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--demo":
        sys.exit(demo(sys.argv[2]))
    unittest.main(verbosity=2)
