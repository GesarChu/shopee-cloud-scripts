# -*- coding: utf-8 -*-
# ⚠️ 9/27 晚生成後有手修 prompt_*D.txt（左右手改 one hand／other hand、hp4 濕紙巾、lt4 馬克杯、ot3 雙手）⇒ ⛔ 直接重跑本檔，會把手修蓋掉
"""2026-09-27 晚 第 30 棒：下一批 7 個新品（王：「一批大概能做到10支」）的 Qwen 首幀指令＋H3 提示詞＋口白腳本。
沿用 _gen_new0927.py 的 shot()（官方 <d> 台詞、講話者那句寫台灣口音、會唸歪的字與 fed up 會被擋）。
這批額外照 9/27 晚王退件學到的：
  - 結尾 ⛔「連結」（唸成連接）→「點下面就買得到」「下面點進去就買得到」輪用
  - 口白用台灣用語（⛔ 蛋白粉這類大陸說法）、數字不進口白
  - 表情正面寫：一直看鏡頭（⛔ fed up／annoyed）
  - 商品拿高一點（鎖骨下方），少壓字幕帶
  - 一支五鏡五個機位：站姿半側身／坐姿腰上／近景／戶外遠一點／坐姿比下
用法：py -3 _gen_batch0928.py
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
_src = open(os.path.join(HERE, "_gen_new0927.py"), encoding="utf-8").read()
exec(_src[:_src.index("# ───────────── 歐萊德")])

UNEASY_Q = "Her expression: she looks a little uncomfortable, lips pressed together, eyebrows relaxed; she is NOT smiling."
UNEASY_H = ("She keeps looking straight into the camera lens the whole time, her eyes steady on the lens, with a slightly uncomfortable look, speaking in a "
            "calm, slightly flat voice; her forehead stays smooth.")
PLEASED_Q = "She is pleased with an easy smile, looking straight at the camera."
PLEASED_H = "She keeps looking straight into the camera lens with an easy, pleased smile for the whole clip."
BRIGHT_Q = "She smiles brightly at the camera."
BRIGHT_H = "She keeps looking straight into the camera lens and smiles brightly for the whole clip."
WARM_H = "She keeps looking straight into the camera lens and smiles warmly for the whole clip."
HAIR_Q = "Her hair looks neat and natural."
HAIR_H = "her hair stays exactly as in the first frame."

F1_Q = ("Medium close shot from chest height; her body is turned about thirty degrees to her left while her face turns back toward the camera; her head "
        "takes about one quarter of the picture height, with a clear band of background above her hair about one sixth of the picture.")
F1_H = "Medium close shot from chest height, her body turned slightly to one side and her face toward the camera"
F2_Q = ("Medium shot from chest height facing her straight on, showing her from the waist up as she sits; her head takes about one fifth of the picture "
        "height, with a clear band of background above her hair about one sixth of the picture.")
F2_H = "Medium shot from chest height showing her from the waist up as she sits"
F3_Q = ("Close-up from eye level facing her straight on, showing her from the upper chest up; her head takes about one third of the picture height, with a "
        "clear band of background above her hair about one sixth of the picture.")
F3_H = "Close-up from eye level showing her from the upper chest up"
F4_Q = ("Medium shot from chest height, a little farther away, showing her from the waist up; her body is turned about thirty degrees to her right while "
        "her face turns back toward the camera; her head takes about one fifth of the picture height, with a clear band of background above her hair about "
        "one sixth of the picture.")
F4_H = "Medium shot from chest height showing her from the waist up, her body turned slightly to one side and her face toward the camera"
F5_Q = ("Medium shot from slightly below her eye level facing her straight on, showing her from the waist up as she sits; her head takes about one fifth "
        "of the picture height, with a clear band of background above her hair about one sixth of the picture.")
F5_H = "Medium shot from slightly below eye level showing her from the waist up as she sits"


def five(pkg, pre, scenes, prod_q, prod_h, prop_word, lines, outfits, one_hand=True):
    """scenes：5 組 (scene_q, scene_h, anchors)；lines：5 組兩句；第 1 鏡痛點不拿商品、第 4 鏡可給 alt=(q,h) 換成別的道具。"""
    F = [(F1_Q, F1_H), (F2_Q, F2_H), (F3_Q, F3_H), (F4_Q, F4_H), (F5_Q, F5_H)]
    sides = [None, "right", "left", "right", "left"]
    for i in range(5):
        sq, sh, anc = scenes[i]
        fq, fh = F[i]
        sid = "%s%d" % (pre, i + 1)
        if i == 0:
            shot(pkg, sid, sq, sh, fq, fh, anc, UNEASY_Q, NOHAND_Q, outfits[i], HAIR_Q, HAIR_H, NOHAND_H, UNEASY_H, lines[i], end_smile=False)
            continue
        pq = prod_q[i] if isinstance(prod_q, dict) and i in prod_q else prod_q["default"] if isinstance(prod_q, dict) else prod_q
        ph = prod_h[i] if isinstance(prod_h, dict) and i in prod_h else prod_h["default"] if isinstance(prod_h, dict) else prod_h
        side = sides[i] if one_hand else sides[i]
        hq, hh = pq.format(side=side), ph.format(side=side)
        eq, eh = (PLEASED_Q, PLEASED_H) if i in (1, 2) else (BRIGHT_Q, BRIGHT_H if i == 3 else WARM_H)
        if i == 4:
            hq, hh = hq + POINT_Q, hh + POINT_H
        pw = prop_word if not (isinstance(prod_q, dict) and i in prod_q) else (prop_q_word.get(i, prop_word) if isinstance(prop_q_word := (prod_q.get("words") or {}), dict) else prop_word)
        shot(pkg, sid, sq, sh, fq, fh, anc, eq, hq, outfits[i], HAIR_Q, HAIR_H, hh, eh, lines[i], prop_word=pw)   # 9/27 晚：hp4 濕紙巾／lt4 馬克杯原本寫成 pack／bag（畫面沒有），已手修


def hold(desc_q, size, desc_h, grip="four fingers wrapped around it and the thumb on the near side facing the camera"):
    q = ("She holds the " + desc_q + ". She holds it upright in her {side} hand in front of her upper chest just below her collarbone, " + grip +
         ", the front facing the camera, the whole thing inside the frame. It is its real size: " + size + ".")
    h = ("She holds the " + desc_h + " upright in her {side} hand in front of her upper chest exactly as in the first frame; it keeps exactly this shape, "
         "this size, its colours and its printing for the whole clip, and her hand holds it perfectly still, never shaking, squeezing, tilting or turning it.")
    return q, h


# ───────────── 1. ANESSA 金鑽高效防曬露 60ml（賣場：SPF50+・PA++++／遇濕氣汗水熱 UV 防禦膜更強不讓防曬品脫落／耐摩擦＋防水／清爽柔滑乳狀質地，好推開不黏膩，臉、身體通用）
AN = "腳本備妥-ANESSA金鑽防曬-多鏡頭"
AN_Q, AN_H = hold("sunscreen bottle from image 2, exactly its look: a small gold metallic bottle with rounded shoulders and a slanted cap whose top is light "
                  "blue, the word ANESSA and a blue sun emblem printed on the front, small blue words below", "a little shorter than her hand is long",
                  "small gold sunscreen bottle with the light blue slanted cap")
five(AN, "an", [
    ("She stands on a sunny riverside cycling path at noon in summer, bright sunlight, green trees and a river behind her.",
     "A sunny riverside cycling path at noon with green trees and a river behind her", "trees and the river"),
    ("She sits on a bench by the front door of her apartment in the morning, a shoe cabinet and a hat hanging on a hook behind her.",
     "An apartment entrance in the morning with a shoe cabinet and a hat on a hook behind her; she sits on a small bench", "shoe cabinet and the hat on the hook"),
    ("She stands in a bright bathroom in the morning, a round mirror and white tiles behind her.",
     "A bright bathroom in the morning with a round mirror and white tiles behind her", "round mirror and the white tiles"),
    ("She stands on a sunny Taiwan beach in the afternoon, soft waves and blue sky behind her; no signs are readable.",
     "A sunny Taiwan beach in the afternoon with soft waves and a blue sky behind her", "waves and the horizon"),
    ("She sits on a sofa in a bright living room in the late afternoon, a straw beach bag and a sun hat on the sofa beside her.",
     "A bright living room in the late afternoon; she sits on a sofa with a straw beach bag and a sun hat beside her", "straw bag and the sun hat"),
], AN_Q, AN_H, "bottle",
    [("外面太陽好大", "一流汗防曬就糊掉了"), ("出門前我擦這瓶", "安耐曬金鑽"), ("乳狀質地很清爽", "好推開不黏膩"),
     ("臉跟身體都可以擦", "出門帶這一瓶就好"), ("常在戶外跑的", "點下面就買得到")],
    ["a plain white short-sleeved T-shirt",
     "a plain light blue linen shirt", "a plain white cotton T-shirt", "a plain navy sleeveless summer dress", "a plain light blue linen shirt"])

# ───────────── 2. hetras 香氛護手霜 50ml（賣場：芒果籽黃油、乳木果油、摩洛哥堅果油／乾燥時可隨時塗抹，留下質感香水等級餘韻／水潤霜狀絲綢質地能夠快速吸收不黏膩）
HT = "腳本備妥-hetras香氛護手霜-多鏡頭"
HT_Q, HT_H = hold("hand cream tube from image 2, exactly its look: a slim soft squeeze tube in a pale cream colour with a flat crimped end at the top and a "
                  "small cream screw cap at the bottom, thin light grey printed words running along it", "about as long as her hand",
                  "slim pale cream hand cream tube with the cap at the bottom",
                  grip="the cap at the bottom, her fingers wrapped around the lower half of the tube and the thumb on the near side facing the camera")
five(HT, "ht", [
    ("She stands in a cool air-conditioned open-plan office in the evening, desks, monitors and a window with city lights behind her; no screen text is readable.",
     "A cool open-plan office in the evening with desks, monitors and a window with city lights behind her", "desks and the window"),
    ("She sits at a café table by a window on a cloudy winter afternoon, a cup of coffee and an open tote bag on the table beside her.",
     "A café by a window on a cloudy winter afternoon; she sits at a table with a cup of coffee and an open tote bag beside her", "window and the coffee cup"),
    ("She sits at her desk at home in the evening, a warm desk lamp and a bookshelf behind her.",
     "A home desk in the evening with a warm desk lamp and a bookshelf behind her", "desk lamp and the bookshelf"),
    ("She stands on a Taipei street in cold winter dusk, warm shop lights and passing people blurred behind her; no shop signs are readable.",
     "A Taipei street at winter dusk with warm lights and passing people behind her; no shop signs are readable", "street lights and the buildings"),
    ("She sits on her bed in a cosy bedroom at night, a warm bedside lamp and a knitted blanket behind her.",
     "A cosy bedroom at night with a warm bedside lamp and a knitted blanket behind her; she sits on the bed", "bedside lamp and the knitted blanket"),
], HT_Q, HT_H, "tube",
    [("冷氣房待一整天", "手乾到粗粗的"), ("包包裡都放這條", "芒果籽的護手霜"), ("擦開很快就吸收", "手不會黏黏的"),
     ("香味有好多種可以選", "這條是無香款"), ("冬天手常常乾的", "下面點進去就買得到")],
    ["a plain white blouse under a plain grey cardigan", "a plain oatmeal knit sweater", "a plain soft beige hoodie",
     "a plain dark green wool coat over a cream sweater, no logo", "a plain soft beige hoodie"])

# ───────────── 3. Hoppi 純水濕紙巾 加蓋款 80抽（賣場：99%純EDI水，無香料，無酒精／比一般嬰兒濕巾更厚、更柔軟／大型濕擦拭－一次擦拭乾淨／柔韌抗拉扯，不易破／加蓋款）
HP = "腳本備妥-Hoppi純水濕紙巾-多鏡頭"
HP_Q = {"default": ("She holds the wet wipes pack from image 2, exactly its look: a soft rectangular light blue plastic pack printed with small white doodles, "
                    "a white plastic flip lid on the front with the blue word hoppi on it. She holds it upright in her {side} hand in front of her upper chest "
                    "just below her collarbone, her fingers under the bottom edge and the thumb on the near side facing the camera, the lid facing the camera "
                    "and closed, the whole pack inside the frame. It is its real size: about twice as wide as her hand.")}
HP_H = {"default": ("She holds the light blue wet wipes pack with the white lid upright in her {side} hand in front of her upper chest exactly as in the first "
                    "frame; the pack keeps exactly this shape, size and colours for the whole clip, the lid stays closed, and her hand holds it perfectly still.")}
HP_Q[3] = ("She holds one plain soft white wet wipe, loosely folded in half, in her {side} hand in front of her upper chest just below her collarbone, the "
           "wipe hanging a little over her fingers; there is no pack in the picture.")
HP_H[3] = ("She holds the loosely folded plain white wet wipe in her {side} hand in front of her upper chest exactly as in the first frame; the wipe keeps "
           "exactly this shape for the whole clip, and her hand holds it perfectly still.")
five(HP, "hp", [
    ("She sits at an outdoor night-market style food table in the evening, warm string lights and blurred food stalls behind her; no signs are readable.",
     "An outdoor food table in the evening with warm string lights and blurred food stalls behind her; no signs are readable", "string lights and the stalls"),
    ("She sits in the passenger seat of a parked car in the daytime, the car window and trees outside behind her.",
     "Inside a parked car in the daytime; she sits in the passenger seat with the window and trees outside behind her", "car window and the trees outside"),
    ("She stands in a bright kitchen in the morning, white cabinets and a window with plants behind her.",
     "A bright kitchen in the morning with white cabinets and a window with plants behind her", "white cabinets and the window"),
    ("She sits at a wooden dining table in a bright living room in the afternoon, a glass of iced tea on the table beside her.",
     "A bright living room in the afternoon; she sits at a wooden dining table with a glass of iced tea beside her", "dining table and the window"),
    ("She sits on a sofa in a tidy living room in the evening, a floor lamp and a green plant behind her.",
     "A tidy living room in the evening with a floor lamp and a green plant behind her; she sits on a sofa", "floor lamp and the green plant"),
], HP_Q, HP_H, "pack",
    [("出門吃東西手黏黏的", "又找不到地方洗手"), ("家裡跟車上都放一包", "純水的濕紙巾"), ("布很厚又很大張", "擦起來不容易破"),
     ("桌上灑到飲料的時候", "抽一張就擦乾淨"), ("家裡常用濕紙巾的", "點下面就買得到")],
    ["a plain white short-sleeved T-shirt", "a plain light grey sweatshirt", "a plain white cotton shirt", "a plain light yellow T-shirt", "a plain light grey sweatshirt"])

# ───────────── 4. ARIEL BOLD 4D 洗衣膠球 補充包（賣場：只需一顆／遇水自動溶解，不須剪開包裝／不需剪開或拆開外膜／每回一至兩顆／減少起泡…不殘留／香氛配方量增加）
A4 = "腳本備妥-ARIEL-4D洗衣膠球-多鏡頭"
A4_Q, A4_H = hold("laundry pod refill pouch from image 2, exactly its look: a stand-up plastic pouch in white and deep blue, a big yellow number and "
                  "Japanese writing at the top, a round white badge with a blue star-shaped logo in the middle, and blue-and-green gel pods pictured at the "
                  "bottom right", "about as tall as her forearm from wrist to elbow", "white and deep blue laundry pod refill pouch",
                  grip="her fingers holding its bottom half from the side and the thumb on the near side facing the camera")
five(A4, "a4", [
    ("She stands in a small laundry corner in the evening, a white front-loading washing machine and a shelf with folded towels behind her.",
     "A small laundry corner in the evening with a white front-loading washing machine and a shelf with folded towels behind her", "washing machine and the towel shelf"),
    ("She sits on a grey sofa in a living room in the morning, a basket of folded clothes beside her and a window behind her.",
     "A living room in the morning; she sits on a grey sofa with a basket of folded clothes beside her and a window behind her", "window and the clothes basket"),
    ("She stands in front of an open white top-loading washing machine in a bright bathroom in the daytime, white tiles behind her.",
     "A bright bathroom in the daytime with a white top-loading washing machine and white tiles behind her", "washing machine and the white tiles"),
    ("She stands on a quiet Taipei lane on a sunny morning, low buildings, potted plants and scooters parked in the distance behind her; no signs are readable.",
     "A quiet Taipei lane on a sunny morning with low buildings and potted plants behind her; no signs are readable", "low buildings and the potted plants"),
    ("She sits on the edge of her bed in a bright bedroom in the late afternoon, neatly folded clean clothes on the bed beside her and a window behind her.",
     "A bright bedroom in the late afternoon; she sits on the edge of the bed with neatly folded clean clothes beside her", "window and the folded clothes"),
], A4_Q, A4_H, "pouch",
    [("倒洗衣精老是倒太多", "瓶口還黏黏的"), ("現在洗衣服用這包", "日本的洗衣膠球"), ("不用剪開外膜", "遇水自己會溶解"),
     ("衣服少的時候一顆就夠", "洗完還香香的"), ("懶得量洗衣精的", "下面點進去就買得到")],
    ["a plain grey T-shirt", "a plain white hoodie", "a plain grey T-shirt", "a plain light blue cotton shirt", "a plain white hoodie"])

# ───────────── 5. 舒跑 運動飲料 250ml 鋁箔包（賣場：五大電解質，可迅速補充流失的水分與電解質／不加果糖，清爽／輕鬆解渴／維他命C添加）
SP = "腳本備妥-舒跑運動飲料24入-多鏡頭"
SP_Q, SP_H = hold("drink carton from image 2, exactly its look: a small rectangular paper drink carton, sky blue with a big green curved stripe, large white "
                  "Chinese brand letters and a small white running-woman figure on the front", "about as tall as her palm",
                  "small sky blue and green drink carton")
five(SP, "sp", [
    ("She stands in a half-cleaned apartment on a hot afternoon, cardboard boxes, a mop and a bucket behind her, sunlight through the window.",
     "A half-cleaned apartment on a hot afternoon with cardboard boxes, a mop and a bucket behind her", "cardboard boxes and the mop"),
    ("She sits on the floor of a bright living room leaning against the sofa on a hot afternoon, an electric fan behind her.",
     "A bright living room on a hot afternoon; she sits on the floor leaning against the sofa with an electric fan behind her", "sofa and the electric fan"),
    ("She stands on a shaded apartment balcony on a sunny afternoon, potted plants and the neighbourhood rooftops behind her.",
     "A shaded apartment balcony on a sunny afternoon with potted plants and neighbourhood rooftops behind her", "potted plants and the rooftops"),
    ("She stands on a forest hiking trail in Taiwan on a sunny day, green trees and wooden steps behind her; no signs are readable.",
     "A forest hiking trail in Taiwan on a sunny day with green trees and wooden steps behind her", "trees and the wooden steps"),
    ("She sits on a wooden bench at a mountain viewpoint in the late afternoon, green hills and blue sky behind her.",
     "A mountain viewpoint in the late afternoon; she sits on a wooden bench with green hills and blue sky behind her", "hills and the sky"),
], SP_Q, SP_H, "carton",
    [("大掃除流了一身汗", "整個人好渴"), ("流汗完我會喝舒跑", "補充水分跟電解質"), ("喝起來清爽解渴", "沒有加果糖"),
     ("爬山走到一半", "停下來喝一口"), ("常常流汗的", "點下面就買得到")],
    ["a plain grey cotton T-shirt", "a plain grey cotton T-shirt", "a plain white cotton T-shirt",
     "a plain light green sports jacket over a white T-shirt, no logo", "a plain light green sports jacket over a white T-shirt, no logo"])

# ───────────── 6. 立頓 奶茶量販包 香濃原味（賣場：紐西蘭進口奶源／隨時沖泡 隨時享用／七種口味）
LT = "腳本備妥-立頓奶茶量販包-多鏡頭"
LT_Q = {"default": ("She holds the milk tea powder bag from image 2, exactly its look: a bright yellow stand-up bag with the red Lipton logo at the top left, "
                    "large dark brown Chinese title letters and a picture of a glass of milk tea at the bottom. She holds it upright in her {side} hand in front "
                    "of her upper chest just below her collarbone, her fingers holding its lower half from the side and the thumb on the near side facing the "
                    "camera, the front facing the camera, the whole bag inside the frame. It is its real size: about as tall as her forearm from wrist to elbow.")}
LT_H = {"default": ("She holds the bright yellow milk tea powder bag upright in her {side} hand in front of her upper chest exactly as in the first frame; "
                    "the bag keeps exactly this shape, size, colours and printing for the whole clip, and her hand holds it perfectly still.")}
LT_Q[3] = ("She holds a plain white ceramic mug filled with light brown milk tea in her {side} hand in front of her upper chest, her fingers through the "
           "handle and the thumb on top of the handle; there is no steam and no bag in the picture.")
LT_H[3] = ("She holds the plain white mug of light brown milk tea in her {side} hand in front of her upper chest exactly as in the first frame; the mug "
           "stays level and still for the whole clip, she does not drink, and the milk tea keeps exactly this colour.")
five(LT, "lt", [
    ("She stands by a rain-streaked window in an office on a cold rainy afternoon, grey sky and wet city buildings outside.",
     "An office on a cold rainy afternoon with a rain-streaked window, grey sky and wet city buildings behind her", "rainy window and the buildings"),
    ("She sits at a small kitchen counter at home in the morning, a kettle and a shelf of cups behind her.",
     "A small home kitchen in the morning; she sits at the counter with a kettle and a shelf of cups behind her", "kettle and the cup shelf"),
    ("She sits at her office desk in the afternoon, a monitor and a window with daylight behind her; no screen text is readable.",
     "An office desk in the afternoon with a monitor and a window behind her; no screen text is readable", "monitor and the window"),
    ("She sits by a window on a rainy evening at home, a cosy armchair and a warm lamp behind her.",
     "A cosy corner at home on a rainy evening with an armchair and a warm lamp behind her", "armchair and the lamp"),
    ("She sits on a sofa under a knitted blanket in a warm living room at night, a floor lamp behind her.",
     "A warm living room at night; she sits on a sofa with a knitted blanket and a floor lamp behind her", "floor lamp and the knitted blanket"),
], LT_Q, LT_H, "bag",
    [("下雨天冷冷的", "好想喝杯奶茶"), ("家裡都備這一大包", "立頓奶茶量販包"), ("紐西蘭進口奶源", "隨時沖隨時喝"),
     ("口味有好多種", "我最常喝香濃原味"), ("天冷想喝奶茶的", "下面點進去就買得到")],
    ["a plain camel knit cardigan over a white blouse", "a plain cream knit sweater", "a plain camel knit cardigan over a white blouse",
     "a plain soft pink knit sweater", "a plain soft pink knit sweater"])

# ───────────── 7. 不倒翁 金拉麵 5 入（賣場：原味／辣味、120g×5 入、韓國、境內版；賣場沒寫味道 ⇒ 口白只講那一刻）
OT = "腳本備妥-不倒翁金拉麵-多鏡頭"
OT_Q, OT_H = hold("instant noodle multipack bag from image 2, exactly its look: a soft plastic bag in royal blue with a red and yellow burst, big white Korean "
                  "letters in the middle, a picture of a bowl of noodles with an egg at the bottom and a small orange badge at the top right",
                  "about as wide as her forearm from wrist to elbow", "royal blue instant noodle multipack bag",
                  grip="her fingers holding its bottom edge from the side and the thumb on the near side facing the camera")
five(OT, "ot", [
    ("She sits at her desk at home late at night, only a desk lamp on, a dark window behind her.",
     "A home desk late at night lit only by a desk lamp, with a dark window behind her", "desk lamp and the dark window"),
    ("She stands in front of an open kitchen pantry cabinet at home in the evening, shelves with jars behind her; no labels are readable.",
     "A home kitchen in the evening with an open pantry cabinet and shelves of jars behind her; no labels are readable", "pantry shelves"),
    ("She sits at a small dining table in a cosy apartment in the evening, a pendant lamp and a window behind her.",
     "A cosy apartment in the evening; she sits at a small dining table under a pendant lamp with a window behind her", "pendant lamp and the window"),
    ("She stands by a window on a rainy weekend afternoon at home, raindrops on the glass and grey sky outside.",
     "Home on a rainy weekend afternoon, standing by a window with raindrops on the glass and a grey sky behind her", "rainy window"),
    ("She sits on a sofa in a living room at night, a TV cabinet and a warm lamp behind her; the TV screen is dark.",
     "A living room at night; she sits on a sofa with a TV cabinet and a warm lamp behind her; the TV screen is dark", "TV cabinet and the lamp"),
], OT_Q, OT_H, "bag",
    [("半夜肚子好餓", "外送又要等好久"), ("我家都會放這一袋", "不倒翁金拉麵"), ("原味跟辣味都有", "韓國境內版"),
     ("下雨天不想出門", "煮一碗就很滿足"), ("宵夜常常想吃麵的", "點下面就買得到")],
    ["a plain oversized grey hoodie", "a plain oversized grey hoodie", "a plain navy T-shirt", "a plain navy T-shirt", "a plain oversized grey hoodie"])
