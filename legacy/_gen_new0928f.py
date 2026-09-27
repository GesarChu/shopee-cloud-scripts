# -*- coding: utf-8 -*-
"""2026-09-28 06:4x 第 30 棒：新品 歐萊德 咖啡因洗髮精 400mL＝人物 B7（高馬尾）
選品：Rough99 5561958/633406718（10 萬+、18%、$699 起）；前台 ≥5 家（484653339 2000+、6432326 2000+、O'right 官方 36448712、1326067903…）
賣場原文（咖啡因洗髮精）：適合問題頭皮、一般髮質／運用超音波萃取技術，保留天然咖啡因萃取物／活絡頭皮…使髮絲呈現健康豐盈
⛔ 功效字不進口白：問題頭皮、活絡頭皮、強健髮根、養護頭皮（官方圖 or01 也有這些字，只拿外觀）
商品參考圖＝or_bottle.png（O'right 官方店 or02 單瓶白底）
⛔「後來改用／換用」句型（9/26 觀察連燒）、⛔ 囤／整／乾／訂
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "_gen_new0928c.py"), encoding="utf-8").read().split("MO2 = ")[0])
B7_Q = "the same long dark brown hair tied up in a high ponytail with a few loose strands framing her face"
B7_H = "long dark brown hair tied up in a high ponytail with a few loose strands framing her face, light natural makeup"
OC_Q, OC_H = hold("shampoo bottle from image 2, exactly its look: a tall slim dark chocolate-brown bottle with rounded shoulders and a light beige "
                  "wooden-looking cap, the small white words Caffeine Shampoo on the upper front and a small white logo near the bottom",
                  "about as tall as her forearm from wrist to elbow", "tall slim dark brown shampoo bottle with the light beige cap")

OC = "腳本備妥-歐萊德咖啡因洗髮精-多鏡頭"
five2(OC, "oc", B7_Q, B7_H, [
    ("She stands in a bright office in the late afternoon, desks, a window and plants behind her; no screen text is readable.",
     "A bright office in the late afternoon with desks, a window and plants behind her; no screen text is readable", "desks and the window"),
    ("She stands in a clean modern bathroom in the evening, a glass shower screen and grey tiles behind her.",
     "A clean modern bathroom in the evening with a glass shower screen and grey tiles behind her", "shower screen and the grey tiles"),
    ("She sits at a white vanity table in her bedroom in the morning, a round mirror and a small vase of flowers behind her.",
     "A bedroom vanity in the morning; she sits with a round mirror and a small vase of flowers behind her", "round mirror and the flowers"),
    ("She stands in a bright yoga studio in the morning, a wooden floor, big windows and green plants behind her, wearing a sports top.",
     "A bright yoga studio in the morning with a wooden floor, big windows and green plants behind her", "big windows and the plants"),
    ("She sits on a cream sofa in a cosy living room in the evening, a floor lamp and a bookshelf behind her.",
     "A cosy living room in the evening; she sits on a cream sofa with a floor lamp and a bookshelf behind her", "floor lamp and the bookshelf"),
], OC_Q, OC_H, "bottle",
    [("綁了一整天馬尾", "髮根看起來塌塌的"), ("浴室裡放的是這瓶", "歐萊德咖啡因洗髮精"), ("有天然咖啡因萃取", "一般頭髮都能用"),
     ("洗完髮絲看起來", "豐盈又有精神"), ("頭髮容易扁塌的", "下面點進去就買得到")],
    ["a plain white blouse", "a plain light grey bathrobe", "a plain soft blue knit top",
     "a plain black sports top under a light grey zip jacket, no logo", "a plain cream knit sweater"])
