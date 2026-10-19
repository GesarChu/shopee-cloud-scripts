#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s-prefilter.py — S 階段選品預篩：分潤後台「商品推廣」存下來的 CSV → 候選表（工單 #6）。

只讀本機存好的 CSV（後台一頁存一份），⛔ 連任何網站。門檻、字典、排序全部讀 --rules（規則.json），
欄名對照讀 --columns（欄位對照.json）；兩個 json 裡底線開頭的鍵是說明，程式略過。只用 Python 標準庫。

用法：
  python tools/s-prefilter.py --offers 第1頁.csv 第2頁.csv … --done 做過清單.txt --rules 規則.json \\
      --columns 欄位對照.json [--today YYYY-MM-DD] --out 資料夾
  --today 沒給＝今天（台灣時間 UTC+8）。

流程：讀 CSV（UTF-8／UTF-8 BOM／cp950）→ 欄名對照（對不到 ⇒ exit 2）→ 數字解析（讀不懂 ⇒ 標「讀不到」、留原字、⛔ 當 0）
  → 同款分組 → 品類 → 篩選（每條規則一個理由代碼）→ 排序 → 輸出 候選.md／候選.csv／排除.csv／分組.json＋畫面摘要。

同款分組（Fable 42 10/11：新舊包裝、容量、入數不同＝同一組；口味不同＝不同組）：
  品名先 NFKC，拿掉 promo_words、capacity_pattern、拿空了的括號、括號符號 ⇒ 顯示名；
  品牌＝顯示名第一個詞（沒空格的品名：用其他列／做過清單出現過的品牌當前綴比）；
  口味＝flavor_words 裡「單獨成詞」的字；沒有單獨成詞的，才在品名裡找「不是品類字」的口味字（「海苔」在「脆烤海苔」裡是品名主體）；
  系列＝品牌之後、拿掉口味的部分（去空白）。(品牌, 系列, 口味) 完全一樣＝同組。
  比不準的配對 ⇒ 分組待人判（⛔ 硬併）：品牌一樣、組不一樣、口味沒有「兩邊都有而且不同」，而且
  系列對到同一個品類字（規則檔的字典）或一邊的系列包含另一邊。

退出碼：0 跑完／2 讀不了（編碼、欄名對不到、規則檔缺鍵、參數錯）。exit 2 時不產候選表，--out 裡舊的四個輸出檔會刪掉。
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OUT_FILES = ("候選.md", "候選.csv", "排除.csv", "分組.json")
FIELDS = ("title", "shop_id", "item_id", "url", "shop_name", "shop_type", "price", "total_sold", "monthly_sales",
          "commission_rate", "bonus", "offer_end", "sv_rate", "sv_bonus", "front_stores", "category")
RULE_KEYS = ("stage", "categories", "later_stage_categories", "min_monthly_sales", "trap_commission_min", "same_product_min_stores",
             "same_flavor_max_reject", "done_policy", "require_bonus", "offer_end_policy", "sort", "promo_words", "flavor_words",
             "capacity_pattern")
BRACKETS = "【】[]()（）「」『』〔〕<>《》〈〉"
TW = dt.timezone(dt.timedelta(hours=8))


class Fatal(Exception):
    """讀不了 ⇒ exit 2。"""


# ── 數字解析 ──────────────────────────────────────────────────────────────────
class Num:
    """解析結果：value（Decimal 或 None）、plus（有沒有「+」）、raw（原字）、ok（讀得懂；空白也算 ok、value=None）。"""

    def __init__(self, raw, value=None, plus=False, ok=True):
        self.raw, self.value, self.plus, self.ok = raw, value, plus, ok

    @property
    def blank(self):
        return self.ok and self.value is None

    @property
    def unreadable(self):
        return not self.ok

    def show(self):
        if self.unreadable:
            return "讀不到（「%s」）" % self.raw
        if self.value is None:
            return ""
        return fmt(self.value) + ("+" if self.plus else "")

    def __repr__(self):
        return "Num(%r, %r, plus=%r, ok=%r)" % (self.raw, self.value, self.plus, self.ok)


def fmt(d):
    """Decimal → 字串，整數不帶小數點。"""
    if d is None:
        return ""
    d = Decimal(d)
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


UNIT = {"萬": Decimal(10000), "万": Decimal(10000), "千": Decimal(1000), "k": Decimal(1000), "K": Decimal(1000)}
RE_COUNT = re.compile(r"^(?:已售|月銷)?\s*(\d[\d,]*(?:\.\d+)?)\s*(萬|万|千|k|K)?\s*(\+)?\s*(?:sold|已售|件)?$", re.I)
RE_PRICE = re.compile(r"^(?:NT\$|NT|\$)?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:元)?$", re.I)
RE_RATE = re.compile(r"^(\d+(?:\.\d+)?)\s*%$")
RE_STORES = re.compile(r"^(\d+)\s*(?:家)?$")


def _clean(text):
    return unicodedata.normalize("NFKC", text or "").strip()


def _dec(s):
    try:
        return Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None


def parse_count(text):
    """月銷／已售：「3萬+」→30000、「6,000+」→6000、「1.2萬」→12000、「50萬+ sold」→500000；記下有沒有「+」。"""
    t = _clean(text)
    if not t:
        return Num(text, None)
    m = RE_COUNT.match(t)
    if not m or _dec(m.group(1)) is None:
        return Num(text, ok=False)
    v = _dec(m.group(1)) * UNIT.get(m.group(2) or "", Decimal(1))
    return Num(text, v, plus=bool(m.group(3)))


def parse_price(text):
    """價格：「$1,299」→1299、「NT$59」→59。區間（$59 - $99）、「洽詢」⇒ 讀不到。"""
    t = _clean(text)
    if not t:
        return Num(text, None)
    m = RE_PRICE.match(t)
    if not m or _dec(m.group(1)) is None:
        return Num(text, ok=False)
    return Num(text, _dec(m.group(1)))


def parse_rate(text):
    """分潤率：「10.5%」→10.5。沒有 % 的數字分不出是 10.5% 還是 0.105 ⇒ 讀不到（⛔ 猜）。"""
    t = _clean(text)
    if not t:
        return Num(text, None)
    m = RE_RATE.match(t)
    if not m:
        return Num(text, ok=False)
    return Num(text, Decimal(m.group(1)))


def parse_stores(text):
    t = _clean(text)
    if not t:
        return Num(text, None)
    m = RE_STORES.match(t)
    return Num(text, Decimal(m.group(1))) if m else Num(text, ok=False)


def parse_date(text):
    """「2026/12/31」「2026-12-31」「2026.1.5」→ date；空白 None；讀不懂丟 ValueError。"""
    t = _clean(text)
    if not t:
        return None
    m = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$", t)
    if not m:
        raise ValueError(t)
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


RE_URL = (re.compile(r"/product/(\d+)/(\d+)"), re.compile(r"-i\.(\d+)\.(\d+)"), re.compile(r"[?&]shopid=(\d+).*?[?&]itemid=(\d+)"))


def ids_from_url(url):
    """網址拆 shop_id／item_id：/product/<shop>/<item>、-i.<shop>.<item>。拆不出 ⇒ (None, None)。"""
    for r in RE_URL:
        m = r.search(url or "")
        if m:
            return m.group(1), m.group(2)
    return None, None


# ── 讀檔 ──────────────────────────────────────────────────────────────────────
def load_json(path, what):
    try:
        with open(path, encoding="utf-8-sig") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise Fatal("讀不了%s %s：%s" % (what, path, e))
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_rules(path):
    r = load_json(path, "規則檔")
    miss = [k for k in RULE_KEYS if k not in r]
    if miss:
        raise Fatal("規則檔 %s 缺這些鍵：%s" % (path, "、".join(miss)))
    try:
        r["_cap_re"] = re.compile(r["capacity_pattern"])
    except re.error as e:
        raise Fatal("規則檔 capacity_pattern 不是合法的正規式：%s" % e)
    for k in ("same_brand_same_series", "same_brand_other_series"):
        if r["done_policy"].get(k) not in ("exclude", "demote", "mark"):
            raise Fatal("規則檔 done_policy.%s 只能是 exclude／demote／mark：%r" % (k, r["done_policy"].get(k)))
    if r["offer_end_policy"] not in ("exclude_member", "mark"):
        raise Fatal("規則檔 offer_end_policy 只能是 exclude_member／mark：%r" % r["offer_end_policy"])
    for s in r["sort"]:
        f = s.split()
        if len(f) != 2 or f[0] not in SORT_FIELDS or f[1] not in ("asc", "desc"):
            raise Fatal("規則檔 sort 看不懂：%r（欄：%s；方向 asc／desc）" % (s, "、".join(SORT_FIELDS)))
    return r


def load_columns(path):
    c = load_json(path, "欄位對照")
    alias = {}
    for field, names in c.items():
        if field not in FIELDS:
            raise Fatal("欄位對照 %s 有不認得的標準欄位：%s" % (path, field))
        for n in names:
            alias[_clean(n).casefold()] = field
    return alias


def read_text(path):
    """UTF-8（有沒有 BOM）→ cp950（Excel 存的 Big5）。都讀不了 ⇒ Fatal。回傳 (文字, 編碼名)。"""
    try:
        raw = open(path, "rb").read()
    except OSError as e:
        raise Fatal("讀不了 %s：%s" % (path, e))
    for enc, name in (("utf-8-sig", "UTF-8" + ("（BOM）" if raw.startswith(b"\xef\xbb\xbf") else "")), ("cp950", "cp950")):
        try:
            return raw.decode(enc), name
        except UnicodeDecodeError:
            pass
    raise Fatal("%s 不是 UTF-8 也不是 cp950（Big5），讀不了" % path)


def load_done(path):
    """做過清單：一行「品牌｜系列」（| 也可以）；系列空白＝整個品牌；# 開頭是註解。"""
    if not path:
        return []
    text, _ = read_text(path)
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        b, _, s = ln.replace("|", "｜").partition("｜")
        out.append((_clean(b), _clean(s)))
    return out


def read_offers(paths, alias):
    rows, unknown, info = [], {}, []
    for p in paths:
        text, enc = read_text(p)
        rd = csv.reader(io.StringIO(text))
        try:
            header = next(rd)
        except StopIteration:
            raise Fatal("%s 是空的" % p)
        cols, seen = [], {}
        for h in header:
            f = alias.get(_clean(h).casefold())
            if f is None:
                unknown.setdefault(h.strip(), []).append(os.path.basename(p))
            elif f in seen:
                raise Fatal("%s 有兩欄都對到「%s」：%s、%s" % (p, f, seen[f], h))
            else:
                seen[f] = h
            cols.append(f)
        if unknown:
            continue
        n = 0
        for ln, rec in enumerate(rd, start=2):
            if not any(x.strip() for x in rec):
                continue
            if len(rec) != len(header):
                raise Fatal("%s 第 %d 行有 %d 欄，標題列是 %d 欄" % (p, ln, len(rec), len(header)))
            d = {f: "" for f in FIELDS}
            d.update({f: v.strip() for f, v in zip(cols, rec)})
            d["_file"], d["_line"] = os.path.basename(p), ln
            rows.append(d)
            n += 1
        info.append((os.path.basename(p), enc, n))
    if unknown:
        raise Fatal("欄名對不到欄位對照（⛔ 猜、⛔ 略過；在欄位對照.json 加別名）：" +
                    "、".join("「%s」（%s）" % (h, "、".join(fs)) for h, fs in unknown.items()))
    if not rows:
        raise Fatal("CSV 裡沒有資料列")
    if "title" not in {f for r in rows for f in r if r[f]}:
        raise Fatal("CSV 沒有品名欄")
    return rows, info


# ── 品名：顯示名、品牌、系列、口味、品類 ───────────────────────────────────────
def strip_title(title, rules):
    """品名 → (顯示名, 拿掉的字)。拿掉 promo_words、容量入數、括號裡的促銷字。"""
    s = unicodedata.normalize("NFKC", title)
    removed = []
    for w in sorted(rules["promo_words"], key=len, reverse=True):
        w2 = unicodedata.normalize("NFKC", w)
        if w2 in s:
            removed.append(w2)
            s = s.replace(w2, " ")
    removed += [m.group(0).strip() for m in rules["_cap_re"].finditer(s)]
    s = rules["_cap_re"].sub(" ", s)
    nb = unicodedata.normalize("NFKC", BRACKETS)
    s = re.sub(r"[%s]\s*[%s]" % (re.escape(nb[0::2]), re.escape(nb[1::2])), " ", s)   # 拿空了的括號
    s = re.sub(r"[%s]" % re.escape(nb), " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -_/｜|,，")
    return s, removed


def word_hits(text, words):
    return [w for w in words if w and w in text]


class Offer:
    def __init__(self, idx, d, rules):
        self.idx, self.d = idx, d
        self.title = d["title"]
        self.name, self.removed = strip_title(self.title, rules)
        self.price = parse_price(d["price"])
        self.monthly = parse_count(d["monthly_sales"])
        self.total = parse_count(d["total_sold"])
        self.rate = parse_rate(d["commission_rate"])
        self.sv = parse_rate(d["sv_rate"])
        self.sv_bonus = parse_rate(d["sv_bonus"])
        self.front = parse_stores(d["front_stores"])
        self.shop, self.item = d["shop_id"] or None, d["item_id"] or None
        if (not self.shop or not self.item) and d["url"]:
            s, i = ids_from_url(d["url"])
            self.shop, self.item = self.shop or s, self.item or i
        self.reasons = []   # [(代碼, 說明)]
        self.marks = []
        self.end, self.end_bad = None, False
        try:
            self.end = parse_date(d["offer_end"])
        except ValueError:
            self.end_bad = True

    @property
    def excluded(self):
        return bool(self.reasons)

    def per_order(self):
        """每單約 $：價格 ×（短影音＋獎勵）%（實）；沒有短影音用列表分潤率（估）。Decimal、ROUND_HALF_UP 到 2 位。
        回傳 (金額或 None, 實／估 或 None, 說明)。"""
        if self.price.value is None:
            return None, None, "價格%s" % ("讀不到（「%s」）" % self.price.raw if self.price.unreadable else "空白")
        if self.sv.value is not None:
            b = self.sv_bonus.value if self.sv_bonus.value is not None else Decimal(0)
            v = (self.price.value * (self.sv.value + b) / Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
            return v, "實", "短影音 %s＋%s" % (fmt(self.sv.value), fmt(b))
        if self.rate.value is not None:
            v = (self.price.value * self.rate.value / Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
            return v, "估", "列表分潤 %s%%" % fmt(self.rate.value)
        return None, None, "分潤率%s" % ("讀不到（「%s」）" % self.rate.raw if self.rate.unreadable else "空白")


def analyse_names(offers, rules, done):
    """品牌、口味、系列、分組鍵。"""
    flavors = [unicodedata.normalize("NFKC", w) for w in rules["flavor_words"]]
    catwords = {unicodedata.normalize("NFKC", w) for ws in list(rules["categories"].values()) + list(rules["later_stage_categories"].values()) for w in ws}
    known = {o.name.split(" ")[0] for o in offers if " " in o.name} | {b for b, _ in done if b}
    for o in offers:
        if " " in o.name:
            o.brand = o.name.split(" ")[0]
            toks = o.name.split(" ")[1:]
            pre = sorted((k for k in known if o.brand.startswith(k) and len(k) < len(o.brand)), key=len, reverse=True)
            if pre:   # 「晴空洗碗精 檸檬」：第一個詞開頭是別列的品牌 ⇒ 拆開
                toks = [o.brand[len(pre[0]):]] + toks
                o.brand = pre[0]
        else:
            pre = sorted((b for b in known if o.name.startswith(b) and len(b) < len(o.name)), key=len, reverse=True)
            o.brand = pre[0] if pre else ""
            toks = [o.name[len(o.brand):]] if o.brand else [o.name]
        if not o.brand:
            o.marks.append("品牌待人判（品名沒有空格、也沒有對到已知品牌）")
        fl = [t for t in toks if t in flavors]   # 單獨成詞的口味字
        rest = [t for t in toks if t not in flavors]
        if not fl:   # 沒有單獨成詞的：在詞裡找不是品類字的口味字（「脆烤海苔」的海苔是品名主體）
            body = "".join(rest)
            for w in sorted(flavors, key=len, reverse=True):
                if w in body and w not in catwords:
                    fl.append(w)
                    body = body.replace(w, "")
            rest = [body]
        o.flavor = "、".join(fl)
        o.series = "".join(rest).replace(" ", "")
        o.key = (o.brand.casefold(), o.series.casefold(), "|".join(sorted(fl)))
        o.dict_words = {w for w in catwords if w in o.series}


def categorize(o, rules):
    text = o.name + " " + _clean(o.d["category"])
    now = [c for c, ws in rules["categories"].items() if word_hits(text, ws) or _clean(o.d["category"]) == c]
    later = [c for c, ws in rules["later_stage_categories"].items() if word_hits(text, ws) or _clean(o.d["category"]) == c]
    o.cat_now, o.cat_later = now, later
    if now and later:
        o.category = "品類衝突（待人判）：%s／%s" % ("、".join(now), "、".join(later))
    elif later:
        o.category = "、".join(later)
    elif now:
        o.category = "、".join(now)
    else:
        o.category = "未分類（待人判）"


# ── 分組 ──────────────────────────────────────────────────────────────────────
class Group:
    def __init__(self, gid, members):
        self.gid, self.members = gid, members
        first = sorted(members, key=lambda o: (" " not in o.name, o.idx))[0]   # 有空格的品名當組名
        self.name = first.name
        self.brand, self.series, self.flavor = first.brand, first.series, first.flavor
        self.reasons, self.marks = [], []
        self.demoted = False

    @property
    def alive(self):
        return [o for o in self.members if not o.excluded]


def make_groups(offers):
    by = {}
    for o in offers:
        by.setdefault(o.key, []).append(o)
    groups = [Group(i + 1, ms) for i, ms in enumerate(sorted(by.values(), key=lambda ms: ms[0].idx))]
    for g in groups:
        for o in g.members:
            o.group = g
    pend = []
    for i, a in enumerate(groups):
        for b in groups[i + 1:]:
            oa, ob = a.members[0], b.members[0]
            if not oa.brand or oa.brand.casefold() != ob.brand.casefold():
                continue
            if oa.flavor and ob.flavor and oa.flavor != ob.flavor:
                continue   # 口味不同＝確定不同組
            share = sorted(oa.dict_words & ob.dict_words)
            contain = oa.series and ob.series and (oa.series in ob.series or ob.series in oa.series)
            if share or contain:
                why = ("系列都有品類字「%s」" % "、".join(share)) if share else "一邊的系列包含另一邊"
                if oa.flavor != ob.flavor:
                    why += "；口味一邊有一邊沒有（%s／%s）" % (oa.flavor or "無", ob.flavor or "無")
                pend.append({"組": [a.gid, b.gid], "組名": [a.name, b.name], "列": [[o.idx for o in a.members], [o.idx for o in b.members]],
                             "原因": "品牌一樣（%s）、%s，程式沒有併" % (oa.brand, why)})
    return groups, pend


# ── 篩選 ──────────────────────────────────────────────────────────────────────
def apply_rules(offers, groups, rules, done, today):
    stage_next = int(rules["stage"]) + 1
    trap = Decimal(str(rules["trap_commission_min"]))
    min_sales = Decimal(str(rules["min_monthly_sales"]))
    seen = {}
    for o in offers:   # 一列一列的規則
        if o.shop and o.item:
            k = (o.shop, o.item)
            if k in seen:
                o.reasons.append(("重複列", "重複（同 shop/item %s/%s 已在列 %d）" % (o.shop, o.item, seen[k])))
            else:
                seen[k] = o.idx
        else:
            o.marks.append("沒有 shop/item")
        for b, s in done:
            if b and ((o.brand and o.brand.casefold() == b.casefold()) or (not o.brand and o.name.startswith(b))):
                same = (not s) or (s in o.series) or (s in o.name)
                pol = rules["done_policy"]["same_brand_same_series" if same else "same_brand_other_series"]
                label = "%s｜%s" % (b, s) if s else b
                if pol == "exclude":
                    o.reasons.append(("做過", "做過（%s）" % label))
                elif pol == "demote":
                    o.demote = "同品牌不同系列（降級，排最後）" if not same else "做過（%s）（降級，排最後）" % label
                else:
                    o.marks.append(("做過（%s）" % label) if same else "同品牌不同系列（%s）" % label)
        if o.cat_later and not o.cat_now:
            o.reasons.append(("第%d階段品類" % stage_next, "第 %d 階段品類：%s" % (stage_next, "、".join(o.cat_later))))
        if o.category.startswith("品類衝突") or o.category.startswith("未分類"):
            o.marks.append(o.category)
        if o.monthly.unreadable:
            o.marks.append("月銷讀不到（「%s」）" % o.monthly.raw)
        elif o.monthly.value is None or o.monthly.value == 0:
            if o.rate.value is not None and o.rate.value >= trap:
                o.reasons.append(("小店衝曝光", "沒有月銷＋列表分潤 %s%% ≥ %s（小店衝曝光）" % (fmt(o.rate.value), fmt(trap))))
            else:
                o.reasons.append(("沒有月銷", "沒有月銷"))
        elif o.monthly.value < min_sales:
            o.reasons.append(("流量低", "流量低（月銷 %s < %s）" % (fmt(o.monthly.value), fmt(min_sales))))
        elif o.monthly.value == min_sales:
            o.marks.append("月銷剛好 %s（「%s」）留著" % (fmt(min_sales), o.monthly.raw))
        bonus = _clean(o.d["bonus"])
        if bonus not in ("是", "有", "Y", "y", "yes", "Yes", "TRUE", "true", "1"):
            txt = "不是分潤加碼" if bonus else "分潤加碼待查"
            if rules["require_bonus"]:
                o.reasons.append(("不是分潤加碼", txt))
            else:
                o.marks.append(txt)
        if o.end_bad:
            o.marks.append("到期日讀不到（「%s」）" % o.d["offer_end"])
        elif o.end is None:
            o.marks.append("到期日待查")
        elif o.end < today:
            txt = "推廣已到期（%s 早於 %s）" % (o.d["offer_end"], today.isoformat())
            if rules["offer_end_policy"] == "exclude_member":
                o.reasons.append(("推廣已到期", txt))
            else:
                o.marks.append(txt)
        if o.price.unreadable:
            o.marks.append("價格讀不到（「%s」）" % o.price.raw)
        for f, n in (("列表分潤率", o.rate), ("短影音", o.sv), ("短影音獎勵", o.sv_bonus), ("前台同款家數", o.front)):
            if n.unreadable:
                o.marks.append("%s讀不到（「%s」）" % (f, n.raw))
    min_st = Decimal(str(rules["same_product_min_stores"]))
    max_rej = Decimal(str(rules["same_flavor_max_reject"]))
    for g in groups:   # 一組一組的規則（只算沒被一列規則排除的家）
        alive = g.alive
        fronts = [o.front.value for o in g.members if o.front.value is not None]
        g.front = max(fronts) if fronts else None
        g.csv_stores = len({o.shop or ("列%d" % o.idx) for o in alive})
        if not alive:
            continue
        if g.front is None:   # 前台欄空白：CSV 自己就湊到門檻＝家數已知；不到 ⇒ 待數（不排除）
            if g.csv_stores >= min_st:
                g.stores, g.stores_show = Decimal(g.csv_stores), "%d（CSV）" % g.csv_stores
            else:
                g.stores, g.stores_show = None, "待數（CSV %d 家有效）" % g.csv_stores
        else:
            g.stores = max(g.front, Decimal(g.csv_stores))
            g.stores_show = "%s（%s）" % (fmt(g.stores), "前台" if g.front >= g.csv_stores else "CSV")
            rs = []
            if g.stores <= max_rej:
                rs.append(("同口味≤%s家" % fmt(max_rej), "同口味 ≤%s 家（前台 %s）" % (fmt(max_rej), fmt(g.front))))
            if g.stores < min_st:
                rs.append(("同款家數<%s" % fmt(min_st), "同款家數 <%s（前台 %s、CSV %d 家）" % (fmt(min_st), fmt(g.front), g.csv_stores)))
            for o in alive:
                o.reasons.extend(rs)
        alive = g.alive
        if not alive:
            continue
        for o in g.members:
            if o.excluded and o.reasons[0][0] == "推廣已到期":
                g.marks.append("列 %d 推廣已到期，只剩列 %s" % (o.idx, "、".join(str(x.idx) for x in alive)))
        g.demoted = any(getattr(o, "demote", None) for o in alive)
        for o in alive:
            if getattr(o, "demote", None):
                g.marks.append(o.demote)
        for o in alive:
            for m in o.marks:
                m = ("列 %d %s" % (o.idx, m)) if len(alive) > 1 else m
                if m not in g.marks:
                    g.marks.append(m)


def group_metrics(g):
    alive = g.alive
    ms = [o.monthly.value for o in alive if o.monthly.value is not None]
    g.monthly = max(ms) if ms else None
    best = None
    g.per_rows = []
    for o in alive:
        v, kind, how = o.per_order()
        g.per_rows.append((o, v, kind, how))
        if v is not None and (best is None or v > best[1]):
            best = (o, v, kind, how)
    g.best = best
    g.price = max((o.price.value for o in alive if o.price.value is not None), default=None)
    g.rate = max((o.rate.value for o in alive if o.rate.value is not None), default=None)


SORT_FIELDS = {"monthly_sales": lambda g: g.monthly, "per_order": lambda g: g.best[1] if g.best else None,
               "price": lambda g: g.price, "commission_rate": lambda g: g.rate}


def sort_groups(cands, rules):
    """規則檔 sort 依序比；值是 None（讀不到／算不出來）的排在同層最後。降級的整批排在最後。"""
    def key(g):
        k = [1 if g.demoted else 0]
        for s in rules["sort"]:
            f, d = s.split()
            v = SORT_FIELDS[f](g)
            k += [1 if v is None else 0, (-v if d == "desc" else v) if v is not None else 0]
        return k + [g.members[0].idx]
    return sorted(cands, key=key)


# ── 輸出 ──────────────────────────────────────────────────────────────────────
CAND_COLS = ["名次", "組名", "品牌", "系列", "口味", "各家（賣場類型 shop/item）", "價", "月銷", "列表分潤率", "每單約 $（哪一家、實／估）",
             "同款家數（前台／CSV／待數）", "品類", "標記", "下一步"]


def cand_row(rank, g):
    alive = g.alive
    each = "；".join("列 %d %s %s/%s" % (o.idx, o.d["shop_type"] or "?", o.shop or "?", o.item or "?") for o in alive)
    price = "；".join("列 %d %s" % (o.idx, ("$" + o.price.show()) if o.price.value is not None else (o.price.show() or "空白")) for o in alive)
    monthly = "；".join("列 %d %s（%s）" % (o.idx, o.monthly.show() or "空白", o.monthly.raw) if not o.monthly.unreadable else
                       "列 %d %s" % (o.idx, o.monthly.show()) for o in alive)
    rate = "；".join("列 %d %s" % (o.idx, (fmt(o.rate.value) + "%") if o.rate.value is not None else (o.rate.show() or "空白")) for o in alive)
    if g.best:
        o, v, kind, how = g.best
        per = "%s（列 %d，%s）" % (format(v, "f"), o.idx, kind)
        others = ["列 %d %s＝%s（%s）" % (x.idx, h, format(w, "f"), k) for x, w, k, h in g.per_rows if x is not o and w is not None]
        others += ["列 %d 算不出來（%s）" % (x.idx, h) for x, w, k, h in g.per_rows if w is None]
        if others:
            per += "；" + "；".join(others)
    else:
        per = "算不出來（%s）" % "；".join("列 %d %s" % (x.idx, h) for x, w, k, h in g.per_rows)
    nxt = ["開詳情看短影音那列"]
    if g.stores is None:
        nxt.append("前台數家數")
    if any(o.price.unreadable or o.price.blank for o in alive):
        nxt.append("詳情看價格")
    if any(m.startswith("未分類") or m.startswith("品類衝突") for m in g.marks):
        nxt.append("人判品類")
    if "到期日待查" in g.marks:
        nxt.append("看加碼到期日")
    cats = []
    for o in alive:
        if o.category not in cats:
            cats.append(o.category)
    month_show = (fmt(g.monthly) if g.monthly is not None else "讀不到")
    return {"名次": rank, "組名": g.name, "品牌": g.brand, "系列": g.series, "口味": g.flavor, "各家（賣場類型 shop/item）": each,
            "價": price, "月銷": "%s｜%s" % (month_show, monthly), "列表分潤率": rate, "每單約 $（哪一家、實／估）": per,
            "同款家數（前台／CSV／待數）": g.stores_show, "品類": "、".join(cats), "標記": "；".join(g.marks), "下一步": "；".join(nxt),
            "_monthly": month_show, "_per": (format(g.best[1], "f"), g.best[0].idx, g.best[2]) if g.best else None}


def md_escape(s):
    return str(s).replace("|", "｜").replace("\n", " ")


def write_outputs(out, offers, groups, pend, cands, rules, today, info):
    os.makedirs(out, exist_ok=True)
    rows = [cand_row(i + 1, g) for i, g in enumerate(cands)]
    with open(os.path.join(out, "候選.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CAND_COLS)
        for r in rows:
            w.writerow([r[c] for c in CAND_COLS])
    lines = ["# 候選表（%s，第 %s 階段：%s）" % (today.isoformat(), rules["stage"], "、".join(rules["sort"])), "",
             "來源：" + "、".join("%s（%d 列）" % (a, c) for a, _, c in info), "",
             "列表分潤率不一定等於短影音（規則檔 list_rate_note）：每單約 $ 標「估」的是拿列表分潤率估的，只拿來排序。", "",
             "| " + " | ".join(CAND_COLS) + " |", "|" + "---|" * len(CAND_COLS)]
    for r in rows:
        lines.append("| " + " | ".join(md_escape(r[c]) for c in CAND_COLS) + " |")
    if pend:
        lines += ["", "## 分組待人判（程式沒有併）", ""] + ["- 組 %s：%s ⇒ %s" % (p["組"], " ／ ".join(p["組名"]), p["原因"]) for p in pend]
    ex = [o for o in offers if o.excluded]
    lines += ["", "## 排除 %d 列（細節見 排除.csv）" % len(ex), ""] + \
             ["- 列 %d %s：%s" % (o.idx, o.title, "；".join(t for _, t in o.reasons)) for o in ex]
    with open(os.path.join(out, "候選.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(out, "排除.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["列", "檔案", "檔案行", "品名", "組", "賣場類型", "shop_id", "item_id", "價", "月銷", "列表分潤率", "理由代碼", "理由", "備註"])
        for o in ex:
            keep = [x.idx for x in o.group.alive]
            note = ("同組列 %s 照留" % "、".join(map(str, keep))) if keep else ""
            w.writerow([o.idx, o.d["_file"], o.d["_line"], o.title, o.group.name, o.d["shop_type"], o.shop or "", o.item or "",
                        o.d["price"], o.d["monthly_sales"], o.d["commission_rate"], "、".join(c for c, _ in o.reasons),
                        "；".join(t for _, t in o.reasons), note])
    gj = {"_說明": "同組＝(品牌, 系列, 口味) 一樣；品名先拿掉 promo_words、容量入數（capacity_pattern）、拿空了的括號與括號符號。"
                    "口味不同＝不同組。分組待人判＝程式不確定、沒有併的配對。",
          "今天": today.isoformat(), "來源": [{"檔": a, "列數": c} for a, _, c in info],   # 編碼只印在畫面：UTF-8／cp950 存的同一份要產出一模一樣的檔
          "組": [{"組": g.gid, "組名": g.name, "品牌": g.brand, "系列": g.series, "口味": g.flavor, "列": [o.idx for o in g.members],
                 "候選": bool(g.alive), "怎麼判": [{"列": o.idx, "品名": o.title, "比對用": "%s｜%s｜%s" % (o.brand, o.series, o.flavor or "（無口味）"),
                                                 "拿掉": o.removed} for o in g.members]} for g in groups],
          "分組待人判": pend}
    with open(os.path.join(out, "分組.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(gj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return rows


def remove_outputs(out):
    gone = []
    for n in OUT_FILES:
        p = os.path.join(out, n)
        if os.path.exists(p):
            os.remove(p)
            gone.append(n)
    return gone


def run(a):
    alias = load_columns(a.columns)
    rules = load_rules(a.rules)
    done = load_done(a.done)
    if a.today:
        try:
            today = dt.date.fromisoformat(a.today)
        except ValueError:
            raise Fatal("--today 要 YYYY-MM-DD：%s" % a.today)
    else:
        today = dt.datetime.now(TW).date()
    raw, info = read_offers(a.offers, alias)
    offers = [Offer(i + 1, d, rules) for i, d in enumerate(raw)]
    analyse_names(offers, rules, done)
    for o in offers:
        categorize(o, rules)
    groups, pend = make_groups(offers)
    apply_rules(offers, groups, rules, done, today)
    cands = [g for g in groups if g.alive]
    for g in cands:
        group_metrics(g)
    cands = sort_groups(cands, rules)
    rows = write_outputs(a.out, offers, groups, pend, cands, rules, today, info)
    ex = [o for o in offers if o.excluded]
    cnt = {}
    for o in ex:
        for c, _ in o.reasons:
            cnt[c] = cnt.get(c, 0) + 1
    print("讀 %d 列（%s）、分成 %d 組；候選 %d 組、排除 %d 列；分組待人判 %d 對" % (
        len(offers), "、".join("%s %s %d 列" % x for x in info), len(groups), len(cands), len(ex), len(pend)))
    for c, n in sorted(cnt.items(), key=lambda x: -x[1]):
        print("  排除理由 %s：%d 列" % (c, n))
    for r in rows:
        print("  %d. %s｜月銷 %s｜每單約 %s｜家數 %s%s" % (r["名次"], r["組名"], r["_monthly"],
              ("%s（列 %d，%s）" % r["_per"]) if r["_per"] else "算不出來", r["同款家數（前台／CSV／待數）"],
              ("｜" + r["標記"]) if r["標記"] else ""))
    print("輸出：%s" % "、".join(os.path.join(a.out, n) for n in OUT_FILES))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="S 階段選品預篩：分潤後台 CSV → 候選表（只讀本機 CSV）")
    ap.add_argument("--offers", nargs="+", required=True, help="後台存的 CSV（一頁一個，可以好幾個）")
    ap.add_argument("--done", help="做過清單（品牌｜系列）")
    ap.add_argument("--rules", required=True, help="規則.json")
    ap.add_argument("--columns", required=True, help="欄位對照.json")
    ap.add_argument("--today", help="YYYY-MM-DD；沒給＝今天（台灣時間）")
    ap.add_argument("--out", required=True, help="輸出資料夾")
    a = ap.parse_args(argv)
    try:
        return run(a)
    except Fatal as e:
        gone = remove_outputs(a.out) if os.path.isdir(a.out) else []
        print("✗ %s" % e)
        print("沒有產出候選表%s。" % ("（%s 裡舊的 %s 已刪，免得誤用）" % (a.out, "、".join(gone)) if gone else ""))
        return 2


if __name__ == "__main__":
    sys.exit(main())
