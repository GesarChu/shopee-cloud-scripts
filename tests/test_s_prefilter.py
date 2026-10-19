# -*- coding: utf-8 -*-
"""工單 #6 驗收：tools/s-prefilter.py。預期全部照 jobs/wo6-選品預篩-1019/預期結果.md（⛔ 改預期來配合程式）。

跑法：python -m pytest tests/test_s_prefilter.py   或   python tests/test_s_prefilter.py（只用標準庫 unittest）
"""
import ast
import csv
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "tools", "s-prefilter.py")
J = os.path.join(REPO, "jobs", "wo6-選品預篩-1019")
SAMPLE = os.path.join(J, "樣本-商品推廣.csv")
UNKNOWN = os.path.join(J, "樣本-欄位不明.csv")
DONE = os.path.join(J, "做過清單-樣本.txt")
RULES = os.path.join(J, "規則.json")
COLS = os.path.join(J, "欄位對照.json")
TODAY = "2026-10-19"

_spec = importlib.util.spec_from_file_location("s_prefilter", TOOL)
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)


def run(offers, out, rules=RULES, done=DONE, cols=COLS, today=TODAY):
    r = subprocess.run([sys.executable, TOOL, "--offers"] + list(offers) + ["--done", done, "--rules", rules, "--columns", cols,
                        "--today", today, "--out", out], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def slurp(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def spit(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w", **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as f:
        f.write(data)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rows_of(cell):
    """「列 1 直營 …；列 2 …」→ [1, 2]"""
    return [int(x) for x in re.findall(r"列 (\d+)", cell)]


# ── 預期結果.md 抄成資料 ───────────────────────────────────────────────────────
EXP_GROUPS = {  # 一、分組
    "晴空 洗碗精 檸檬": [1, 2, 3], "晴空 洗碗精 綠茶": [15], "山嵐 脆烤海苔 原味": [4], "山嵐 脆烤海苔 梅子": [5],
    "晨露 抽取式衛生紙": [12, 13], "舊識牌 無加糖豆漿": [9], "舊識牌 糙米米漿": [10],
}
EXP_SINGLES = [6, 7, 8, 11, 14, 16]
EXP_CANDS = [  # 二、候選表：名次、組、月銷下限、每單約 $（金額, 列, 實／估）或 None、同款家數開頭
    (1, "山嵐 脆烤海苔 原味", "60000", ("10.40", 4, "估"), "8（前台）"),
    (2, "晨露 抽取式衛生紙", "30000", ("8.76", 13, "估"), "待數（CSV 1 家有效）"),
    (3, "晴空 洗碗精 檸檬", "30000", ("4.77", 3, "估"), "6（前台）"),
    (4, "晴空 洗碗精 綠茶", "20000", None, "待數"),
    (5, "未知品 XYZ-2000", "2000", ("44.40", 14, "估"), "待數"),
    (6, "清新 除濕盒", "1000", ("0.72", 11, "估"), "待數"),
    (7, "舊識牌 糙米米漿", "4000", ("1.10", 10, "估"), "待數"),
]
EXP_EXCL = {  # 三、排除表
    5: "同口味 ≤2 家（前台 2）",
    6: "沒有月銷＋列表分潤 20.5% ≥ 15（小店衝曝光）",
    7: "第 3 階段品類：寵物",
    8: "第 3 階段品類：美妝",
    9: "做過（舊識牌｜豆漿）",
    12: "推廣已到期（2026/10/15 早於 2026-10-19）",
    16: "流量低（月銷 500 < 1000）",
}


class SampleRun(unittest.TestCase):
    """樣本跑一次，對 預期結果.md 一、二、三、四。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="wo6_")
        cls.out = os.path.join(cls.tmp, "out")
        cls.code, cls.log = run([SAMPLE], cls.out)
        cls.cands = read_csv(os.path.join(cls.out, "候選.csv"))
        cls.excl = read_csv(os.path.join(cls.out, "排除.csv"))
        cls.groups = json.loads(slurp(os.path.join(cls.out, "分組.json")))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_exit_and_summary(self):
        self.assertEqual(self.code, 0, self.log)
        for s in ("讀 16 列", "分成 13 組", "候選 7 組", "排除 7 列"):
            self.assertIn(s, self.log)

    def test_groups(self):
        gs = {g["組名"]: g["列"] for g in self.groups["組"]}
        self.assertEqual(len(gs), 13)
        for name, rows in EXP_GROUPS.items():
            self.assertEqual(gs.get(name), rows, name)
        singles = sorted(r[0] for r in gs.values() if len(r) == 1 and r[0] not in sum(EXP_GROUPS.values(), []))
        self.assertEqual(singles, EXP_SINGLES)
        self.assertNotEqual(gs["晴空 洗碗精 檸檬"], gs["晴空 洗碗精 綠茶"])   # 口味不同 ⛔ 併
        self.assertNotIn(9, gs["舊識牌 糙米米漿"])                             # 不同系列 ⛔ 同組

    def test_flavor_vs_body(self):
        g = {x["組名"]: x for x in self.groups["組"]}
        self.assertEqual(g["山嵐 脆烤海苔 梅子"]["口味"], "梅子")   # 「海苔」是品名主體不是口味
        self.assertEqual(g["山嵐 脆烤海苔 原味"]["系列"], "脆烤海苔")

    def test_candidate_order_and_numbers(self):
        self.assertEqual(len(self.cands), len(EXP_CANDS))
        for row, (rank, name, monthly, per, stores) in zip(self.cands, EXP_CANDS):
            self.assertEqual(int(row["名次"]), rank)
            self.assertEqual(row["組名"], name)
            self.assertEqual(row["月銷"].split("｜")[0], monthly, name)
            cell = row["每單約 $（哪一家、實／估）"]
            if per is None:
                self.assertTrue(cell.startswith("算不出來"), cell)
            else:
                self.assertTrue(cell.startswith("%s（列 %d，%s）" % per), cell)
            self.assertTrue(row["同款家數（前台／CSV／待數）"].startswith(stores), row["同款家數（前台／CSV／待數）"])
            self.assertIn("開詳情看短影音那列", row["下一步"])
            if stores.startswith("待數"):
                self.assertIn("前台數家數", row["下一步"])

    def test_candidate_marks(self):
        c = {r["組名"]: r for r in self.cands}
        self.assertIn("列 12 推廣已到期，只剩列 13", c["晨露 抽取式衛生紙"]["標記"])
        self.assertEqual(rows_of(c["晨露 抽取式衛生紙"]["各家（賣場類型 shop/item）"]), [13])
        self.assertIn("列 1 短影音 0.5＋0.5＝0.59（實）", c["晴空 洗碗精 檸檬"]["每單約 $（哪一家、實／估）"])
        self.assertIn("價格讀不到（「洽詢」）", c["晴空 洗碗精 綠茶"]["標記"])
        for m in ("未分類（待人判）", "不是分潤加碼", "到期日待查"):
            self.assertIn(m, c["未知品 XYZ-2000"]["標記"])
        self.assertIn("同品牌不同系列（降級，排最後）", c["舊識牌 糙米米漿"]["標記"])
        self.assertEqual(rows_of(c["清新 除濕盒"]["各家（賣場類型 shop/item）"]), [11])   # 1,000+＝1000 留著

    def test_exclusions(self):
        ex = {int(r["列"]): r for r in self.excl}
        self.assertEqual(sorted(ex), sorted(EXP_EXCL))
        for row, reason in EXP_EXCL.items():
            self.assertIn(reason, ex[row]["理由"], row)
        self.assertIn("同組列 13 照留", ex[12]["備註"])

    def test_md_written(self):
        md = slurp(os.path.join(self.out, "候選.md"))
        self.assertIn("| 1 | 山嵐 脆烤海苔 原味 |", md)

    def test_csv_has_bom(self):
        self.assertTrue(slurp(os.path.join(self.out, "候選.csv"), "rb").startswith(b"\xef\xbb\xbf"))


class Numbers(unittest.TestCase):
    """預期結果.md 四：數字解析逐條。"""

    def test_counts(self):
        for raw, want, plus in (("3萬+", 30000, True), ("6,000+", 6000, True), ("10萬+", 100000, True), ("1.2萬", 12000, False),
                                ("50萬+ sold", 500000, True), ("1,000+", 1000, True), ("500+", 500, True)):
            n = sp.parse_count(raw)
            self.assertTrue(n.ok, raw)
            self.assertEqual(n.value, Decimal(want), raw)
            self.assertEqual(n.plus, plus, raw)

    def test_price_and_rate(self):
        self.assertEqual(sp.parse_price("$1,299").value, Decimal(1299))
        self.assertEqual(sp.parse_price("NT$59").value, Decimal(59))
        self.assertEqual(sp.parse_rate("10.5%").value, Decimal("10.5"))

    def test_unreadable_is_not_zero(self):
        for f in (sp.parse_price, sp.parse_count, sp.parse_rate):
            n = f("洽詢")
            self.assertFalse(n.ok)
            self.assertIsNone(n.value)          # ⛔ 當 0
            self.assertEqual(n.raw, "洽詢")      # 保留原字
            self.assertIn("讀不到", n.show())

    def test_blank_is_not_unreadable(self):
        n = sp.parse_count("")
        self.assertTrue(n.ok)
        self.assertIsNone(n.value)

    def test_half_up(self):
        class O:   # 99 × 10.5% = 10.395 → 10.40（float 的 round 會變 10.39）
            price, sv, sv_bonus, rate = sp.Num("$99", Decimal(99)), sp.Num(""), sp.Num(""), sp.Num("10.5%", Decimal("10.5"))
        v, kind, _ = sp.Offer.per_order(O)
        self.assertEqual(str(v), "10.40")
        self.assertEqual(kind, "估")

    def test_url_ids(self):
        self.assertEqual(sp.ids_from_url("https://shopee.tw/product/123/456?x=1"), ("123", "456"))
        self.assertEqual(sp.ids_from_url("https://shopee.tw/某商品-i.789.1011"), ("789", "1011"))
        self.assertEqual(sp.ids_from_url("https://example.invalid/none"), (None, None))


class Columns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wo6_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unknown_column_exit2(self):
        out = os.path.join(self.tmp, "out")
        os.makedirs(out)
        spit(os.path.join(out, "候選.md"), "舊的")   # 上一次留下的
        code, log = run([UNKNOWN], out)
        self.assertEqual(code, 2, log)
        self.assertIn("神秘欄", log)
        self.assertFalse(any(os.path.exists(os.path.join(out, n)) for n in sp.OUT_FILES), os.listdir(out))

    def test_sold_maps_to_monthly(self):
        p = os.path.join(self.tmp, "en.csv")
        spit(p, "title,url,price,sold,commission_rate,front_stores\n"
                                             "晴空 洗碗精 檸檬 500ml,https://shopee.tw/x-i.900001.100001,$59,50萬+ sold,1%,6\n")
        rows, _ = sp.read_offers([p], sp.load_columns(COLS))
        o = sp.Offer(1, rows[0], sp.load_rules(RULES))
        self.assertEqual(o.monthly.value, Decimal(500000))
        self.assertTrue(o.total.blank)                          # 不是總銷量
        self.assertEqual((o.shop, o.item), ("900001", "100001"))  # 沒有 shop/item 欄 ⇒ 從網址拆

    def test_bad_encoding_exit2(self):
        p = os.path.join(self.tmp, "bad.csv")
        spit(p, "品名,價格\n晴空,$59\n".encode("utf-16"))
        code, log = run([p], os.path.join(self.tmp, "out"))
        self.assertEqual(code, 2, log)


class Encodings(unittest.TestCase):
    """預期結果.md 四：cp950、UTF-8 BOM 存的同一份，結果要跟原檔一模一樣。"""

    def test_same_output(self):
        tmp = tempfile.mkdtemp(prefix="wo6_")
        try:
            text = slurp(SAMPLE)
            outs = {}
            for enc in ("orig", "utf-8-sig", "cp950"):
                d = os.path.join(tmp, enc)
                os.makedirs(d)
                p = os.path.join(d, os.path.basename(SAMPLE))
                if enc == "orig":
                    shutil.copy(SAMPLE, p)
                else:
                    with open(p, "w", encoding=enc, newline="") as f:
                        f.write(text)
                code, log = run([p], os.path.join(d, "out"))
                self.assertEqual(code, 0, enc + log)
                self.assertIn("cp950" if enc == "cp950" else "UTF-8", log)
                outs[enc] = {n: slurp(os.path.join(d, "out", n), "rb") for n in sp.OUT_FILES}
            self.assertNotEqual(slurp(os.path.join(tmp, "cp950", os.path.basename(SAMPLE)), "rb"), slurp(SAMPLE, "rb"))
            for enc in ("utf-8-sig", "cp950"):
                for n in sp.OUT_FILES:
                    self.assertEqual(outs[enc][n], outs["orig"][n], "%s %s" % (enc, n))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RulesFromFile(unittest.TestCase):
    """門檻都從規則檔讀：改 json 結果就跟著變（程式沒寫死）。"""

    def run_with(self, **changes):
        tmp = tempfile.mkdtemp(prefix="wo6_")
        self.addCleanup(shutil.rmtree, tmp, True)
        r = json.loads(slurp(RULES))
        r.update(changes)
        rp = os.path.join(tmp, "規則.json")
        spit(rp, json.dumps(r, ensure_ascii=False))
        code, log = run([SAMPLE], os.path.join(tmp, "out"), rules=rp)
        self.assertEqual(code, 0, log)
        return {int(x["列"]): x for x in read_csv(os.path.join(tmp, "out", "排除.csv"))}

    def test_min_monthly_sales(self):
        ex = self.run_with(min_monthly_sales=2000)
        self.assertIn("流量低（月銷 1000 < 2000）", ex[11]["理由"])

    def test_trap(self):
        ex = self.run_with(trap_commission_min=25)
        self.assertEqual(ex[6]["理由"], "沒有月銷")

    def test_min_stores(self):
        ex = self.run_with(same_product_min_stores=10)
        self.assertIn("同款家數 <10", ex[4]["理由"])

    def test_missing_key_exit2(self):
        tmp = tempfile.mkdtemp(prefix="wo6_")
        self.addCleanup(shutil.rmtree, tmp, True)
        r = json.loads(slurp(RULES))
        del r["min_monthly_sales"]
        rp = os.path.join(tmp, "規則.json")
        spit(rp, json.dumps(r, ensure_ascii=False))
        code, log = run([SAMPLE], os.path.join(tmp, "out"), rules=rp)
        self.assertEqual(code, 2)
        self.assertIn("min_monthly_sales", log)


class MultiPage(unittest.TestCase):
    def test_split_pages_same_result_and_duplicates(self):
        tmp = tempfile.mkdtemp(prefix="wo6_")
        self.addCleanup(shutil.rmtree, tmp, True)
        lines = slurp(SAMPLE).splitlines()
        p1, p2 = os.path.join(tmp, "p1.csv"), os.path.join(tmp, "p2.csv")
        spit(p1, "\n".join(lines[:9]) + "\n")
        spit(p2, "\n".join([lines[0]] + lines[9:]) + "\n")
        code, log = run([p1, p2], os.path.join(tmp, "split"))
        self.assertEqual(code, 0, log)
        got = [(r["組名"], r["每單約 $（哪一家、實／估）"].split("；")[0]) for r in read_csv(os.path.join(tmp, "split", "候選.csv"))]
        self.assertEqual(got, [(c[1], ("%s（列 %d，%s）" % c[3]) if c[3] else got[3][1]) for c in EXP_CANDS])
        code, log = run([SAMPLE, SAMPLE], os.path.join(tmp, "dup"))   # 同一頁存了兩次
        self.assertEqual(code, 0, log)
        ex = read_csv(os.path.join(tmp, "dup", "排除.csv"))
        self.assertEqual(sum(1 for r in ex if "重複列" in r["理由代碼"]), 16)
        self.assertEqual([r["組名"] for r in read_csv(os.path.join(tmp, "dup", "候選.csv"))], [c[1] for c in EXP_CANDS])


class GroupReview(unittest.TestCase):
    def test_uncertain_pair_not_merged(self):
        tmp = tempfile.mkdtemp(prefix="wo6_")
        self.addCleanup(shutil.rmtree, tmp, True)
        p = os.path.join(tmp, "g.csv")
        spit(p,
             "品名,賣場ID,商品ID,價格,月銷,列表分潤率,分潤加碼,加碼到期,前台同款家數\n"
             "晴空 洗碗精 檸檬 500ml,1,1,$59,3萬+,1%,是,2026/12/31,6\n"
             "晴空 濃縮洗碗精 檸檬 500ml,2,2,$59,3萬+,1%,是,2026/12/31,6\n"
             "晴空 洗碗精 綠茶 500ml,3,3,$59,3萬+,1%,是,2026/12/31,6\n")
        code, log = run([p], os.path.join(tmp, "out"))
        self.assertEqual(code, 0, log)
        g = json.loads(slurp(os.path.join(tmp, "out", "分組.json")))
        self.assertEqual(len(g["組"]), 3)                         # ⛔ 硬併
        pend = g["分組待人判"]
        # 只有「洗碗精 檸檬 × 濃縮洗碗精 檸檬」比不準；綠茶跟兩個檸檬都是口味不同＝確定不同組，不列
        self.assertEqual([tuple(x["組名"]) for x in pend], [("晴空 洗碗精 檸檬", "晴空 濃縮洗碗精 檸檬")], pend)


class StoreCount(unittest.TestCase):
    def test_csv_alone_reaches_min(self):
        """前台欄空白、CSV 同組 4 家（不同賣場）⇒ 家數 4（CSV），不是待數。"""
        tmp = tempfile.mkdtemp(prefix="wo6_")
        self.addCleanup(shutil.rmtree, tmp, True)
        p = os.path.join(tmp, "s.csv")
        body = "".join("晴空 洗碗精 檸檬 %dml,%d,%d,$59,3萬+,1%%,是,2026/12/31,\n" % (500 * (i + 1), i + 1, i + 1) for i in range(4))
        spit(p, "品名,賣場ID,商品ID,價格,月銷,列表分潤率,分潤加碼,加碼到期,前台同款家數\n" + body)
        code, log = run([p], os.path.join(tmp, "out"))
        self.assertEqual(code, 0, log)
        c = read_csv(os.path.join(tmp, "out", "候選.csv"))
        self.assertEqual(c[0]["同款家數（前台／CSV／待數）"], "4（CSV）")
        self.assertNotIn("前台數家數", c[0]["下一步"])


class Static(unittest.TestCase):
    """驗收 3、5：沒有網路 import、只用標準庫、沒有寫死本機路徑。"""

    def test_imports(self):
        tree = ast.parse(slurp(TOOL))
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or "").split(".")[0])
        bad = {"requests", "urllib", "http", "socket", "selenium", "playwright", "httpx", "aiohttp", "pandas", "numpy"}
        self.assertFalse(mods & bad, mods & bad)
        stdlib = getattr(sys, "stdlib_module_names", None)
        if stdlib:
            self.assertFalse({m for m in mods if m and m not in stdlib}, mods)

    def test_no_local_paths(self):
        src = slurp(TOOL)
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]|/Users/|/home/|Desktop", src))


if __name__ == "__main__":
    unittest.main(verbosity=2)
