# -*- coding: utf-8 -*-
"""2026-09-28 05:2x 第 30 棒：兩個新品（王 05:0x「開始做新的商品」「優先占滿免費的那五支」）
  - 摩洛哥優油 100ml（蝦皮直營 50662979/28423358401，前台 ≥6 家）＝人物 B4
  - 統一 PH9.0 鹼性離子水 800ml×20（蝦皮直營 50662979/44553797186，前台 ≥6 家）＝人物 D1
跟 _gen_batch0928.py 的差別：
  ① 人物不是 C1 ⇒ 身份句換成各人物自己的頭髮／眼型（C1 的 EYE_SHORT 不能套別人）
  ② 身材保持句放 Qwen 指令最前面（CLAUDE #101；9/28 job27 實測 B4／B5／D1 換場景換衣服身材都保住）
  ③ H3 提示詞直接寫官方 <d> 版（*D.txt），台灣口音寫在講話者那句
  ④ 這批先送 RunningHub 無限畫布免費 H3（RH Enhanced，首帧模式），本機顯卡只畫 Qwen 首幀
口白規矩：照賣場原文、⛔ 功效宣稱（PH9.0 賣場的「平衡體質／代謝力」不進口白）、數字不進口白、⛔ 連結／漬／髮質／每次／罐／凍
用法：py -3 _gen_new0928b.py
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
_a = open(os.path.join(HERE, "_gen_batch0928.py"), encoding="utf-8").read()
exec(_a[:_a.index("# ───────────── 1. ANESSA")])

BODY = ("her whole body stays exactly as in image 1 — the same body shape and build, the same shoulder width, the same bust, waist and hips, the same "
        "arm and leg thickness, the same height and proportions — ")


def shot2(pkg, sid, who_q, who_h, scene_q, scene_h, framing_q, framing_h, anchors, expr_q, hands_q, outfit, hair_q, hair_h, hands_h, expr_h, line,
          prop_word="", end_smile=True):
    d = os.path.join(HERE, pkg)
    q = ("Edit this photo. Keep the young woman from image 1 exactly as she is: " + BODY + "and the same face, the same eye shape and eye size, the same "
         "eyelids, the same nose, mouth and jawline, " + who_q + ", the same makeup. Only her clothes, her pose, the place and the camera change, and the "
         "clothes follow her own body shape from image 1. Change these things. First, the place: " + scene_q + BGQ + " Second, the camera: " + framing_q +
         " Third, her clothes: she now wears " + outfit + ". Fourth, her hair: " + hair_q + " Fifth, her hands: " + hands_q.strip() + HANDS +
         " Sixth, her expression: " + expr_q + " Natural skin tones, clean realistic photography, sharp focus on her face; no text or logos added to the picture.")
    open(os.path.join(d, "_qwen指令", f"q_{sid}.txt"), "w", encoding="utf-8", newline="\n").write(q)
    end = "her mouth closes in a soft smile, everything else unchanged." if end_smile else "her mouth closes, her face calm, everything else unchanged."
    hold_ = ("she holds still with a soft closed-mouth smile, blinks once slowly and stays quiet until the end." if end_smile
             else "she holds still with her mouth closed and a calm face, blinks once slowly and stays quiet until the end.")
    keep = "her face" + (" and the " + prop_word if prop_word else "")
    cam = (" " + framing_h + ", exactly the framing of the first frame; a static locked-off tripod shot: the frame edges stay on the same " + anchors +
           " for the whole clip, " + keep + " keep exactly the same size and the same position in the frame as in the first frame, her whole head stays inside the "
           "frame with the same clear band of background above her hair, and she stays at the same distance from the camera the whole time. Natural skin tones, the "
           "background clearly recognisable as the place it is. Her hands never touch her face or her hair. Her lips move naturally and match every word she says.")
    for w in ("連結", "漬", "髮質", "每次", "罐", "凍"):
        assert w not in line[0] + line[1], "口白有會唸歪的字「%s」（CLAUDE #98）" % w
    assert "fed up" not in expr_h and "annoyed" not in expr_h
    h = ("integrated_multimodal_description:\n" + scene_h + ", continuing exactly from the first frame; no brand marks and no readable signs anywhere in the background. "
         "The background stays exactly as it is in the first frame for the whole clip. The same young woman as the first frame: " + who_h + ", " + outfit +
         " that stays exactly as it is for the whole clip; " + hair_h + " " + hands_h + cam + " " + expr_h +
         "\n\n[0.0s-4.0s] Start: exactly the first frame. Action: keeping her hands perfectly still the young woman with a light, bright voice and a natural "
         "Taiwanese Mandarin accent (S1) says in Mandarin Chinese, as one continuous sentence in a single breath with no pause in the middle, once only: "
         "<d>[Chinese] " + line[0] + "，" + line[1] + "</d>. End: " + end +
         "\n[4.0s-5.1s] Start: as before. Action: " + hold_ + " End: unchanged, the final frame.\n\n" + SOUND)
    open(os.path.join(d, f"prompt_{sid}D.txt"), "w", encoding="utf-8", newline="\n").write(h)
    open(os.path.join(d, f"口白腳本_{sid}D.txt"), "w", encoding="utf-8", newline="\n").write(line[0] + "\n" + line[1] + "\n")
    print(pkg, sid, "｜".join(line))


def five2(pkg, pre, who_q, who_h, scenes, prod_q, prod_h, prop_word, lines, outfits, hair1_q=None):
    F = [(F1_Q, F1_H), (F2_Q, F2_H), (F3_Q, F3_H), (F4_Q, F4_H), (F5_Q, F5_H)]
    sides = [None, "right", "left", "right", "left"]
    for i in range(5):
        sq, sh, anc = scenes[i]
        fq, fh = F[i]
        sid = "%s%d" % (pre, i + 1)
        if i == 0:
            shot2(pkg, sid, who_q, who_h, sq, sh, fq, fh, anc, UNEASY_Q, NOHAND_Q, outfits[i], hair1_q or HAIR_Q, HAIR_H, NOHAND_H, UNEASY_H,
                  lines[i], end_smile=False)
            continue
        hq, hh = prod_q.format(side=sides[i]), prod_h.format(side=sides[i])
        eq, eh = (PLEASED_Q, PLEASED_H) if i in (1, 2) else (BRIGHT_Q, BRIGHT_H if i == 3 else WARM_H)
        if i == 4:
            hq, hh = hq + POINT_Q, hh + POINT_H
        shot2(pkg, sid, who_q, who_h, sq, sh, fq, fh, anc, eq, hq, outfits[i], HAIR_Q, HAIR_H, hh, eh, lines[i], prop_word=prop_word)


# ───────────── 摩洛哥優油 100ml（賣場原文：快速吸收，獨家堅果油配方／清爽不黏膩，乾濕髮皆適用／所有髮質適用／可讓秀髮變得柔順好梳，吹髮前使用可變得比較快乾，
#               能增加秀髮光澤感，讓秀髮潤澤好整理／產地以色列・公司貨）＝人物 B4（長直黑髮、透瀏海）
MO = "腳本備妥-摩洛哥優油-多鏡頭"
B4_Q = "the same long straight black hair past her shoulders with soft see-through bangs"
B4_H = "long straight black hair past her shoulders with soft see-through bangs, light natural makeup"
MO_Q, MO_H = hold("hair oil bottle from image 2, exactly its look: a flat amber-brown glass bottle with a black pump top, a tall turquoise label on the front "
                  "with a large copper-orange letter M and the white word MOROCCANOIL printed sideways along the label", "a little longer than her hand",
                  "amber-brown hair oil bottle with the black pump and the turquoise label")
five2(MO, "mo", B4_Q, B4_H, [
    ("She stands in front of a bathroom mirror in the evening after a shower, white tiles and a towel rail with a towel behind her.",
     "A bathroom in the evening with white tiles and a towel rail with a towel behind her", "white tiles and the towel rail"),
    ("She sits at a small vanity table in her bedroom in the evening, a round mirror and a hair dryer resting on the table behind her.",
     "A bedroom vanity in the evening; she sits with a round mirror and a hair dryer resting on the table behind her", "round mirror and the hair dryer"),
    ("She stands in a bright walk-in closet in the morning, clothes hanging neatly on rails behind her.",
     "A bright walk-in closet in the morning with clothes hanging neatly on rails behind her", "clothes rails"),
    ("She stands in a breezy riverside park on a sunny afternoon, green trees and the river behind her, her long hair smooth and glossy.",
     "A breezy riverside park on a sunny afternoon with green trees and the river behind her", "trees and the river"),
    ("She sits on a light grey sofa in a bright living room in the evening, a floor lamp and a bookshelf behind her.",
     "A bright living room in the evening; she sits on a light grey sofa with a floor lamp and a bookshelf behind her", "floor lamp and the bookshelf"),
], MO_Q, MO_H, "bottle",
    [("洗完頭最怕吹頭髮", "要吹好久好久"), ("洗完頭我會先抹這瓶", "摩洛哥優油"), ("吸收很快", "摸起來清爽不黏膩"),
     ("吹的時候比較快", "梳起來很順"), ("吹頭髮很花時間的", "點下面就買得到")],
    ["a plain white cotton bathrobe", "a plain soft pink cardigan over a white top", "a plain cream knit sweater",
     "a plain light blue linen shirt", "a plain soft pink cardigan over a white top"],
    hair1_q="Her hair is a little frizzy and puffy at the ends with a few flyaway strands, as if just blow-dried without any hair oil.")

# ───────────── 統一 PH9.0 鹼性離子水 800ml×20（賣場：PH9.0 鹼性離子水／適度補充天然礦物質與微量元素／800ml×20 入／產地台灣；
#               賣場的「平衡體質少負擔／啟動代謝力」＝功效宣稱，⛔ 進口白）＝人物 D1（長直黑髮、厚齊瀏海）
PH = "腳本備妥-統一PH9離子水-多鏡頭"
D1_Q = "the same long straight black hair past her shoulders with thick straight-cut bangs, the same winged eyeliner"
D1_H = "long straight black hair past her shoulders with thick straight-cut bangs, light makeup with thin winged eyeliner"
PH_Q, PH_H = hold("water bottle from image 2, exactly its look: a clear plastic bottle of water with a light blue screw cap and a ridged shoulder, a dark "
                  "navy label around the middle with large white letters PH 9.0", "about as tall as her forearm from wrist to elbow",
                  "clear plastic water bottle with the light blue cap and the dark navy label")
five2(PH, "ph", D1_Q, D1_H, [
    ("She stands outside a convenience store at the street corner on a hot afternoon, the glass shop front blurred behind her; no signs are readable.",
     "A street corner outside a convenience store on a hot afternoon with the glass shop front blurred behind her; no signs are readable", "glass shop front"),
    ("She sits at a wooden dining table in a bright kitchen in the morning, a window and a green plant behind her.",
     "A bright kitchen in the morning; she sits at a wooden dining table with a window and a green plant behind her", "window and the green plant"),
    ("She stands at her apartment door in the daytime, a shoe cabinet and a coat rack behind her.",
     "An apartment entrance in the daytime with a shoe cabinet and a coat rack behind her", "shoe cabinet and the coat rack"),
    ("She stands on a sunny Taipei sidewalk in the morning, street trees and low buildings behind her; no signs are readable.",
     "A sunny Taipei sidewalk in the morning with street trees and low buildings behind her; no signs are readable", "street trees and the buildings"),
    ("She sits on a sofa in a tidy living room in the evening, a floor lamp and a plant behind her.",
     "A tidy living room in the evening; she sits on a sofa with a floor lamp and a plant behind her", "floor lamp and the plant"),
], PH_Q, PH_H, "bottle",
    [("去超商買水還要自己扛", "重到手好痠"), ("我家現在都買這箱", "統一的鹼性離子水"), ("一大箱直接送到家", "不用自己提上樓"),
     ("出門帶一瓶在包包", "口渴隨時喝得到"), ("家裡常常沒水喝的", "下面點進去就買得到")],
    ["a plain white T-shirt", "a plain light grey sweatshirt", "a plain white cotton shirt", "a plain light green cardigan over a white top",
     "a plain light grey sweatshirt"])
