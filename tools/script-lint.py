#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
script-lint.py — 口白腳本自動檢查（2026-09-26 第 27 棒）

為什麼：這週重生／重做的原因，有一半在送顯卡前就看得出來——口白帶數字（十二支、230克被吞）、
  帶品牌名（拿著商品講品牌名的鏡頭燒字幕 20 幾個種子）、語助詞「欸」、絕對字、價格、情緒詞（H3 擠眉）、
  同一個實字講三次像繞口令。這些規矩散在 CLAUDE.md、文案與分鏡SOP、分鏡規格三個檔，靠人記就會漏。
  ⇒ 寫首幀指令之前先跑這支，紅字不清掉不准往下。

用法：
  py -3 tools/script-lint.py <備妥包資料夾> [plan.json]     # 讀 plan 裡每個鏡的 口白腳本_<clip>.txt
  py -3 tools/script-lint.py <口白腳本檔> [<口白腳本檔>…]     # 直接給檔
回傳值：有 🔴 就 exit 1（佇列可以拿來擋）。
"""
import glob, json, os, re, sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RULES_HARD = [
    (r"[0-9０-９]", "🔴 阿拉伯數字：H3 會吞掉（十二支、230克都沒唸出來）→ 數字放段板／說明文字"),
    (r"欸", "🔴 語助詞「欸」：王 9/12 禁（每支都用會被看出同模板）"),
    (r"(最好|最棒|最強|一定|絕對|絕不|永遠|百分百|保證|第一名|完全不)", "🔴 絕對字：只准照賣場原文，⛔ 誇大（CLAUDE #39）"),
    (r"(元|塊錢|折|免運|優惠|特價|便宜)", "🔴 價格／優惠字：口白不報價，放 FB 說明文字（SOP 一）"),
    (r"(美白|抗老|淡斑|除皺|去痘|消炎|治療|療效|瘦身|減肥|豐胸|生髮)", "🔴 功效宣稱：化粧品法規字，⛔（CLAUDE #39）"),
    (r"(FB|IG|LINE|Instagram|Facebook|抖音|TikTok)", "🔴 其他平台名：蝦皮手冊第 33 張禁"),
]
RULES_WARN = [
    (r"(髮尾)", "⚠️ 兩個三聲連讀：配音會把前字變二聲（髮尾→罰尾，王 9/27 退）→ 改寫成「頭髮」；配音用字表已把「髮」唸成「法」"),
    (r"[A-Za-z]{2,}", "⚠️ 英文／品牌名：拿著商品講品牌名的鏡頭燒字幕最兇（ARIEL／CeraVe／FINO 各 20 幾個種子）；whisper 也常聽不到 → 品牌名放段板"),
    (r"(可惜|不想|好煩|討厭|受不了|崩潰|氣死|超煩)", "⚠️ 情緒詞：H3 會演成擠眉（文案SOP 3-4a）→ 改「事實＋決定」"),
    (r"(乾|囤|凍|罐|訂|殼|倒|防曬)", "⚠️ 這幾個字 H3 唸歪過（乾→堪、囤→存、訂包廂→訂包新、殼→連殼、倒→島（王 9/28 ARIEL）、防曬→中國口音（王 9/28 ANESSA））→ 生完逐字稿要人聽"),
    (r"[二三四五六七八九十百千]+(支|包|入|片|瓶|罐|克|天|次|小時|分鐘|公斤|毫升|種|組|條|顆|粒)", "⚠️ 中文數量詞：七種、十二支這類被吞過 → 能不講就不講"),
]


def check_line(text):
    out = []
    for pat, msg in RULES_HARD:
        m = re.search(pat, text)
        if m:
            out.append("%s ← 「%s」" % (msg, m.group(0)))
    for pat, msg in RULES_WARN:
        m = re.search(pat, text)
        if m:
            out.append("%s ← 「%s」" % (msg, m.group(0)))
    n = len(re.sub(r"[，。、！？\s]", "", text))
    if n < 3:
        out.append("⚠️ 句子太短（%d 字）" % n)
    if n > 13:
        out.append("⚠️ 句子太長（%d 字）：一鏡一句一個狀態，H3 五秒講不完會加速或吞字" % n)
    return out


def load_targets(args):
    files = []
    if len(args) >= 1 and os.path.isdir(args[0]):
        d = args[0]
        plan = args[1] if len(args) > 1 else None
        if plan:
            pj = json.load(open(os.path.join(d, plan) if not os.path.isabs(plan) else plan, encoding="utf-8"))
            for s in pj["shots"]:
                files.append(os.path.join(d, "口白腳本_%s.txt" % s["clip"]))
        else:
            files = sorted(glob.glob(os.path.join(d, "口白腳本_*.txt")))
    else:
        files = args
    return files


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    files = load_targets(sys.argv[1:])
    hard = 0
    all_lines = []
    print("口白腳本檢查：%d 個檔\n" % len(files))
    for f in files:
        if not os.path.exists(f):
            print("🔴 缺檔 %s" % f)
            hard += 1
            continue
        lines = [l.strip() for l in open(f, encoding="utf-8", errors="replace").read().splitlines() if l.strip()]
        print("== %s" % os.path.basename(f))
        for l in lines:
            all_lines.append(l)
            issues = check_line(l)
            mark = "🔴" if any(i.startswith("🔴") for i in issues) else ("⚠️" if issues else "✅")
            print("  %s %s" % (mark, l))
            for i in issues:
                print("       %s" % i)
                if i.startswith("🔴"):
                    hard += 1
    # 整支：繞口令（同一個雙字實詞 ≥3 次）＋相鄰句同字結尾
    if len(files) > 1:
        grams = Counter()
        for l in all_lines:
            t = re.sub(r"[，。、！？\s]", "", l)
            for i in range(len(t) - 1):
                g = t[i:i + 2]
                if not re.search(r"(的|了|是|在|我|你|他|就|都|也|很|有|跟|和|把|會|能|可以|這|那|一)", g):
                    grams[g] += 1
        rep = [(g, n) for g, n in grams.items() if n >= 3]
        if rep:
            print("\n⚠️ 整支重複實詞（≥3 次，像繞口令；王 9/15「好多包很像在繞口令」）：" + "、".join("%s×%d" % x for x in rep))
        ends = [re.sub(r"[，。、！？\s]", "", l)[-1:] for l in all_lines]
        same = [i for i in range(1, len(ends)) if ends[i] and ends[i] == ends[i - 1]]
        if same:
            print("⚠️ 相鄰句同字結尾：第 %s 句" % "、".join(str(i + 1) for i in same))
        shots = len(files)
        est = shots * 3.6
        print("\n鏡頭數 %d，估正片約 %.0f 秒（每鏡取 3–4 秒＋段板）%s" % (shots, est, "" if est >= 15 else " 🔴 撐不到 15 秒（CLAUDE #10）→ 加鏡，⛔ 不灌水"))
        print("第一句＝「%s」→ 自問：這句是痛點嗎？（CLAUDE #16：第一句就是痛點，不是鋪陳）" % (all_lines[0] if all_lines else ""))
    print("\n%s" % ("🔴 %d 個硬傷，不准往下" % hard if hard else "✅ 沒有硬傷（⚠️ 的要自己判斷）"))
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
