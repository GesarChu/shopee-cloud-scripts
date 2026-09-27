# -*- coding: utf-8 -*-
"""2026-09-28 06:3x 第 30 棒：新品 TTL 台酒花雕雞麵（袋裝 3 包／袋）＝人物 B6（戴眼鏡、上班族）
選品：蝦皮直營 50662979/42805586469（全系列，20 萬+、10.5%）；前台 ≥6 家（愛買 5 萬+、牛牛小舖 1 萬+、台酒旗艦 7000+、萬家福 6000+…）
賣場原文（花雕雞袋麵）：使用台灣菸酒公司遵循古法釀製的料理花雕酒，搭配濃郁藥膳湯頭，香Q的細麵與雞肉塊料理包，讓忙碌的現代消費者，能即時享用…
商品參考圖＝ttl_pack.png（直營圖的「3包/袋」圓章用台酒旗艦店圖對齊補掉，/c/tmp/ttl/ttl_check.jpg 看過）
⛔ 囤（唸成存）、⛔ 整（唸成枕）、⛔ 功效字
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "_gen_new0928c.py"), encoding="utf-8").read().split("MO2 = ")[0])
B6_Q = "the same shoulder-length softly wavy brown hair, the same thin round gold-rimmed glasses"
B6_H = "shoulder-length softly wavy brown hair, thin round gold-rimmed glasses, light natural makeup"
TT_Q, TT_H = hold("instant noodle multipack bag from image 2, exactly its look: a tall box-shaped soft plastic bag with a peaked top, dark red and orange "
                  "with a light beige lower half, large dark red Chinese title letters and a picture of a bowl of noodle soup with chicken pieces",
                  "about as tall as her forearm from wrist to elbow", "dark red and orange instant noodle multipack bag",
                  grip="her fingers holding its lower half from the side and the thumb on the near side facing the camera")

TT = "腳本備妥-TTL花雕雞麵-多鏡頭"
five2(TT, "tt", B6_Q, B6_H, [
    ("She stands in a quiet open office late at night, empty desks and dim ceiling lights behind her; no screen text is readable.",
     "A quiet open office late at night with empty desks and dim ceiling lights behind her; no screen text is readable", "empty desks and the ceiling lights"),
    ("She stands in a small home kitchen at night, white cabinets and a stove with a pot behind her.",
     "A small home kitchen at night with white cabinets and a stove with a pot behind her", "white cabinets and the stove"),
    ("She sits at a small dining table at night, a steaming bowl of noodle soup on the table in front of her and a warm pendant lamp behind her.",
     "A small dining table at night with a steaming bowl of noodle soup on the table and a warm pendant lamp behind her", "pendant lamp and the table"),
    ("She sits on a sofa in a cosy living room at night, a floor lamp and a blanket behind her.",
     "A cosy living room at night; she sits on a sofa with a floor lamp and a blanket behind her", "floor lamp and the blanket"),
    ("She sits at a desk in her bedroom at night, a laptop closed on the desk and a bookshelf behind her.",
     "A bedroom desk at night with a closed laptop and a bookshelf behind her", "laptop and the bookshelf"),
], TT_Q, TT_H, "bag",
    [("加班到半夜好餓", "外面的店都關了"), ("家裡都會放幾包", "台酒的花雕雞麵"), ("湯頭有花雕酒", "還有雞肉塊料理包"),
     ("細麵煮起來香Q", "晚上吃很滿足"), ("常常加班肚子餓的", "點下面就買得到")],
    ["a plain white shirt under a grey cardigan", "a plain light grey hoodie", "a plain light grey hoodie",
     "a plain soft beige loungewear top", "a plain navy knit sweater"])
