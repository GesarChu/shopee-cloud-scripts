# -*- coding: utf-8 -*-
"""2026-09-28 05:5x 第 30 棒：兩個新品的第二支（王 05:1x「那用不同角色多做幾支嗎?」→ 換人物＋換切入點，CLAUDE #53②）
  - 摩洛哥優油 v2＝人物 B5（大波浪棕髮）｜切入點：早上整理頭髮很花時間（v1 是洗完頭吹很久）
  - 統一 PH9.0 v2＝人物 B4｜切入點：上班一忙就忘記喝水（v1 是超商扛水很重）
沿用 _gen_new0928b.py 的 shot2()／five2()（身材保持句在最前、官方 <d>、台灣口音寫在講話者）
場景／服裝／口白都不跟第一支重複；結尾句跟第一支錯開
用法：py -3 _gen_new0928c.py
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
_b = open(os.path.join(HERE, "_gen_new0928b.py"), encoding="utf-8").read()
exec(_b[:_b.index("# ───────────── 摩洛哥優油 100ml")])
_b2 = _b[_b.index("# ───────────── 摩洛哥優油 100ml"):]
for name in ("MO_Q, MO_H", "PH_Q, PH_H"):
    i = _b2.index(name + " = hold(")
    j = _b2.index(")\n", _b2.index("\n", _b2.index('"', _b2.index("\n", i)))) + 2
    exec(_b2[i:j])
B4_Q = "the same long straight black hair past her shoulders with soft see-through bangs"
B4_H = "long straight black hair past her shoulders with soft see-through bangs, light natural makeup"
B5_Q = "the same long wavy dark brown hair with a side part"
B5_H = "long wavy dark brown hair with a side part, light natural makeup"

MO2 = "腳本備妥-摩洛哥優油-v2整理"
five2(MO2, "mv", B5_Q, B5_H, [
    ("She stands in front of a tall mirror in her bedroom on a busy weekday morning, an open wardrobe and a made bed behind her.",
     "A bedroom on a weekday morning with an open wardrobe and a made bed behind her", "wardrobe and the bed"),
    ("She stands at a bright bathroom sink in the morning, a round mirror and a small plant on the shelf behind her.",
     "A bright bathroom sink area in the morning with a round mirror and a small plant on the shelf behind her", "round mirror and the plant"),
    ("She sits by the window in a quiet café in the late morning, a cup of latte on the table and blurred street outside; no signs are readable.",
     "A quiet café by the window in the late morning with a latte on the table and a blurred street outside; no signs are readable", "window and the latte"),
    ("She stands in a bright modern office in the afternoon, desks, plants and large windows behind her; no screen text is readable.",
     "A bright modern office in the afternoon with desks, plants and large windows behind her; no screen text is readable", "desks and the windows"),
    ("She sits on her bed in a warm bedroom at night, a bedside lamp and soft pillows behind her.",
     "A warm bedroom at night; she sits on the bed with a bedside lamp and soft pillows behind her", "bedside lamp and the pillows"),
], MO_Q, MO_H, "bottle",
    [("早上整理頭髮", "都要花好多時間"), ("我的化妝台上都放這瓶", "摩洛哥優油"), ("洗完頭或出門前都能用", "摸起來不黏膩"),
     ("抹完看起來有光澤", "也比較好整理"), ("早上想省時間的", "下面點進去就買得到")],
    ["a plain white blouse", "a plain light grey knit top", "a plain beige trench coat over a white top, no logo",
     "a plain navy blazer over a white top", "a plain soft lilac loungewear top"])

PH2 = "腳本備妥-統一PH9離子水-v2上班"
five2(PH2, "pv", B4_Q, B4_H, [
    ("She stands in a small office meeting room in the early evening, a whiteboard with no readable writing and a window with city lights behind her.",
     "A small office meeting room in the early evening with a blank whiteboard and a window with city lights behind her", "whiteboard and the window"),
    ("She sits at her desk in a bright open office in the morning, a monitor with no readable text and a small plant behind her.",
     "A bright open office in the morning; she sits at her desk with a monitor and a small plant behind her; no screen text is readable", "monitor and the plant"),
    ("She sits at a long table in a co-working space by a big window in the afternoon, a laptop closed on the table beside her.",
     "A co-working space by a big window in the afternoon; she sits at a long table with a closed laptop beside her", "big window and the table"),
    ("She stands on a riverside running path in the early morning, green trees and the river behind her, wearing sportswear.",
     "A riverside running path in the early morning with green trees and the river behind her", "trees and the river"),
    ("She sits at a small desk in her bedroom at night, a warm desk lamp and a bookshelf behind her.",
     "A bedroom desk at night; she sits with a warm desk lamp and a bookshelf behind her", "desk lamp and the bookshelf"),
], PH_Q, PH_H, "bottle",
    [("上班一忙就忘記喝水", "下班才發現好渴"), ("現在我桌上都放這瓶", "統一的鹼性離子水"), ("一大瓶放在桌上", "一整天慢慢喝"),
     ("運動完也帶一瓶", "裡面有天然礦物質"), ("常常忘記喝水的", "點下面就買得到")],
    ["a plain white shirt", "a plain light blue shirt", "a plain oatmeal knit sweater",
     "a plain black sports jacket over a grey sports top, no logo", "a plain soft grey hoodie"])
