# -*- coding: utf-8 -*-
# 2026-09-27 第 30 棒：兩個新品（歐萊德枸杞豐盈洗髮精、可口可樂易開罐 24 入）的 Qwen 首幀指令＋H3 提示詞＋口白腳本
# 跟 9/25 _gen_v2_prompts.py 的差別（王 9/27 退 FINO v3「看起來都太像了」、CLAUDE #60／#97）：
#   ① 每一鏡寫自己的機位（坐辦公桌腰上／半側身站／坐化妝台近景／戶外腰上遠一點／坐床邊），不再全部「胸口高度正面」
#   ② H3 鏡頭句用正面描述（第 29 棒騎樓 A/B：否定列舉推近 29/17/16% → 正面描述 4/5/4%，未達定論門檻，照樣量）
#   ③ 口白照賣場原文、數字不進口白、不用「後來改用＋商品」句型（9/26 觀察：這句型連燒 27 種子）
import os
HERE = os.path.dirname(os.path.abspath(__file__))

EYE = ("Her eyes are the single most important feature and must match image 1 exactly: large, round, wide-open eyes with a clear double-eyelid crease, "
       "large bright brown irises that catch the light, long separated lashes, and an alert lively gaze straight at the camera. Her bangs are thin and see-through "
       "and do not cover her eyebrows or her eyes. Keep the exact same young woman as in image 1: the same face, the same long straight black hair past her shoulders "
       "with soft see-through bangs, the same light natural makeup, the same eyes, nose, mouth and jawline. ")
EYE_SHORT = ("Her eyes stay exactly as in image 1: large, round, wide-open eyes with a clear double-eyelid crease and large bright brown irises; her thin "
             "see-through bangs do not cover her eyebrows or her eyes. ")
PHOTO = (" Natural skin tones with visible skin texture, realistic photography, natural daylight, sharp focus on her face, subtle film grain; no plastic skin, "
         "no airbrushing, no CGI.")
BGQ = " The background is clearly recognisable as the place it is; there are no brand marks, no logos and no readable text anywhere in the background."
HANDS = " Each visible hand has five fingers of normal length; the hands are clearly separate."
SOUND = ("overall_soundscape: Her clear female voice in the foreground, close and conversational: a light, bright, mid-pitched voice of a young Taiwanese woman in her mid "
         "twenties, natural Taiwanese Mandarin accent, relaxed and unhurried, the same voice and the same distance to the microphone in every clip; quiet ambience, very faint; "
         "after her last sentence there is only that quiet ambience.\nnon_diegetic_music: none. No background music.\n")
POINT_Q = (" Her right hand is in front of her lower chest with the index finger pointing straight down and the other fingers curled, palm facing her body; "
           "there is nothing under that hand.")
POINT_H = " Her right index finger keeps pointing straight down in front of her lower chest for the whole clip, and that hand stays still."
NOHAND_Q = " Both her hands are down by her sides below the bottom edge of the picture, out of the frame."
NOHAND_H = (" Her arms hang relaxed at her sides and her hands stay completely still at the bottom of the picture for the whole clip, exactly as in the first frame; "
            "her hands never rise toward her face or her body.")  # 9/27：Qwen 沒照「手在畫面外」畫（K1、T1 手垂在身側入鏡）⇒ 提示詞改成跟首幀一致


def shot(pkg, sid, scene_q, scene_h, framing_q, framing_h, anchors, expr_q, hands_q, outfit, hair_q, hair_h, hands_h, expr_h, line,
         prop_word="", end_smile=True):
    d = os.path.join(HERE, pkg)
    # 9/27 09:5x 第一版（描述句）Qwen 當修圖處理：背景、衣服、構圖全沿用底圖 ⇒ 改用 9/26 驗證過的「Edit this photo … Change …」句型，逐項寫要改什麼
    q = ("Edit this photo. Keep the young woman exactly as she is: the same face, the same eyes, the same nose, mouth and jawline, the same long straight black hair "
         "past her shoulders with soft see-through bangs, the same light natural makeup. " + EYE_SHORT +
         "Change these things. First, the place: " + scene_q + BGQ + " Second, the camera: " + framing_q + " Third, her clothes: she now wears " + outfit + ". "
         "Fourth, her hair: " + hair_q + " Fifth, her hands: " + hands_q.strip() + HANDS + " Sixth, her expression: " + expr_q +
         " Natural skin tones, clean realistic photography, sharp focus on her face; no text or logos added to the picture.")
    open(os.path.join(d, "_qwen指令", f"q_{sid}.txt"), "w", encoding="utf-8", newline="\n").write(q)
    end = "her mouth closes in a soft smile, everything else unchanged." if end_smile else "her mouth closes, her face calm, everything else unchanged."
    hold = ("she holds still with a soft closed-mouth smile, blinks once slowly and stays quiet until the end." if end_smile
            else "she holds still with her mouth closed and a calm face, blinks once slowly and stays quiet until the end.")
    keep = "her face" + (" and the " + prop_word if prop_word else "")
    cam = (" " + framing_h + ", exactly the framing of the first frame; a static locked-off tripod shot: the frame edges stay on the same " + anchors +
           " for the whole clip, " + keep + " keep exactly the same size and the same position in the frame as in the first frame, her whole head stays inside the "
           "frame with the same clear band of background above her hair, and she stays at the same distance from the camera the whole time. Natural skin tones, the "
           "background clearly recognisable as the place it is. Her hands never touch her face or her hair. Her lips move naturally and match every word she says.")
    h = ("integrated_multimodal_description:\n" + scene_h + ", continuing exactly from the first frame; no brand marks and no readable signs anywhere in the background. "
         "The background stays exactly as it is in the first frame for the whole clip. The same young woman as the first frame: long straight black hair past her shoulders "
         "with soft see-through bangs, light natural makeup, " + outfit + " that stays exactly as it is for the whole clip; " + hair_h + " " + hands_h + cam + " " + expr_h +
         "\n\n[0.0s-4.0s] Start: exactly the first frame. Action: keeping her hands perfectly still she says in Mandarin Chinese, as one continuous sentence in a single breath "
         "with no pause in the middle, once only: \"" + line[0] + "，" + line[1] + "\". End: " + end +
         "\n[4.0s-5.1s] Start: as before. Action: " + hold + " End: unchanged, the final frame.\n\n" + SOUND)
    open(os.path.join(d, f"prompt_{sid}.txt"), "w", encoding="utf-8", newline="\n").write(h)
    open(os.path.join(d, f"口白腳本_{sid}.txt"), "w", encoding="utf-8", newline="\n").write(line[0] + "\n" + line[1] + "\n")
    # 9/27 第 30 棒 A/B：MiniMax 官方 h3-prompt-writing（references/base-en.txt 4.4／4.5）＝台詞寫成 (S1) says: <d>[語言] …</d>，
    #   而「英文雙引號裡的字＝畫面上看得到的字（招牌、標籤、字幕）」⇒ 我們一直把台詞放雙引號，懷疑是燒字幕來源。D 版只換這一處。
    old_q = "she says in Mandarin Chinese, as one continuous sentence in a single breath with no pause in the middle, once only: \"" + line[0] + "，" + line[1] + "\""
    # 9/27 晚（王抓到中國口音）：官方 4.4＝口音寫在講話者那句，不是只寫在 soundscape
    new_q = ("the young woman with a light, bright voice and a natural Taiwanese Mandarin accent (S1) says in Mandarin Chinese, as one continuous sentence "
             "in a single breath with no pause in the middle, once only: <d>[Chinese] " + line[0] + "，" + line[1] + "</d>")
    # 9/27 晚王抓到的（CLAUDE #98／#99）：結尾「連結」會唸成連接、「漬」唸成墜；fed up 會變翻眼側瞄
    #   9/27 以前的六個品（og／kk／ty／nv／sk／lr）已生成、修正版另存 *E.txt，不在這裡擋；新品一律擋
    if not sid[:2] in ("og", "kk", "ty", "nv", "sk", "lr"):
        for w in ("連結", "漬", "髮質", "每次", "罐", "凍"):
            assert w not in line[0] + line[1], "口白有會唸歪的字「%s」（CLAUDE #98）" % w
        assert "fed up" not in expr_h and "annoyed" not in expr_h, "表情別寫 fed up／annoyed，會翻眼（CLAUDE #99）"
    assert old_q in h
    open(os.path.join(d, f"prompt_{sid}D.txt"), "w", encoding="utf-8", newline="\n").write(h.replace(old_q, new_q))
    open(os.path.join(d, f"口白腳本_{sid}D.txt"), "w", encoding="utf-8", newline="\n").write(line[0] + "\n" + line[1] + "\n")
    print(pkg, sid, "｜".join(line))


# ───────────── 歐萊德 枸杞豐盈洗髮精（賣場：適合細軟、扁塌髮質／平衡潔淨頭皮油脂／使秀髮呈現豐盈蓬鬆感）
O = "腳本備妥-歐萊德枸杞洗髮精-多鏡頭"
OO = "a plain oatmeal-coloured cotton crew-neck sweatshirt with no print"
FLAT_Q = ("Her fine, thin hair lies flat and limp against the top of her head, with no lift at the roots and a flat centre parting, looking a bit greasy at the "
          "roots; it clearly looks flat.")
FLAT_H = "her fine hair lies flat against the top of her head exactly as in the first frame and stays that way."
FULL_Q = ("Her hair has just been blow-dried and now has clearly visible volume: the hair on top of her head is lifted and airy at the roots instead of lying flat, "
          "the lengths look soft, full and bouncy with a gentle inward curl at the ends, noticeably fuller than flat straight hair; her bangs stay thin and see-through.")
FULL_H = "her hair looks soft and full with lift at the roots exactly as in the first frame and stays that way, not moving."
BOTTLE_Q = ("She holds the shampoo bottle from image 2, exactly its look: a slim, tall, matte white bottle shaped like a wine bottle with a light natural wood-coloured "
            "round cap on top, small thin grey printed words on the front and a short thin pink line under them, and a small green-and-grey logo near the bottom. "
            "She holds it upright in her {side} hand in front of her chest near the middle of the picture, four fingers wrapped around the body of the bottle and the "
            "thumb on the near side facing the camera, the cap on top and closed, the front of the bottle facing the camera, the whole bottle inside the frame. "
            "The bottle is its real size: about as tall as her forearm from wrist to elbow and only a little wider than her fingers.")
BOTTLE_H = ("She holds the slim matte white shampoo bottle with the light wood-coloured cap upright in her {side} hand in front of her chest exactly as in the first frame; "
            "the cap stays closed, the bottle keeps exactly this slim shape, this size, its white colour and its small printing for the whole clip, and her hand holds "
            "it perfectly still, never opening, tilting or turning it.")
PAIN_Q = "Her expression: she looks a little troubled, lips pressed together, eyebrows relaxed; she is NOT smiling."
PAIN_H = "She looks a little troubled, speaking in a calm, slightly flat voice; she does not frown."
SMILE_Q, SMILE_H = "She is pleased with an easy smile.", "She is pleased with an easy smile for the whole clip."

shot(O, "ogO1",
     "She sits at her desk in a bright open-plan office in the afternoon, a laptop and a mug on the desk in front of her, office windows and shelves behind her.",
     "A bright open-plan office in the afternoon with windows and shelves behind her; she sits at her desk with a laptop in front of her",
     "Medium shot from a slightly higher angle, showing her from the waist up as she sits at the desk, the top edge of the laptop visible at the bottom of the picture; "
     "her head takes about one fifth of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from a slightly higher angle showing her from the waist up at the desk", "office windows, shelves and the laptop edge",
     PAIN_Q, "Both her hands rest on the desk in front of her, next to the laptop, relaxed and still.", OO, FLAT_Q, FLAT_H,
     "Both her hands rest still on the desk for the whole clip.", PAIN_H, ("頭髮又細又軟", "下午就扁到貼著頭皮"), end_smile=False)

shot(O, "ogO2",
     "She stands in a bright bathroom in the morning with white tiles, a round mirror and a green towel on a rail behind her.",
     "A bright bathroom in the morning with white tiles, a round mirror and a green towel on a rail behind her",
     "Medium close shot from chest height; her body is turned about thirty degrees to her left while her face turns back toward the camera; her head takes about "
     "one quarter of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium close shot from chest height, her body turned slightly to one side and her face toward the camera", "white tiles, the round mirror and the green towel",
     SMILE_Q, BOTTLE_Q.format(side="right"), OO, FLAT_Q.replace("looking a bit greasy at the roots; it clearly looks flat.", "not yet washed."),
     "her fine hair lies close to her head exactly as in the first frame and stays that way.", BOTTLE_H.format(side="right"), SMILE_H,
     ("現在洗頭用這瓶枸杞的", "專門給細軟扁塌的髮質"), prop_word="bottle")

shot(O, "ogO3",
     "She sits at a white dressing table in her bedroom in the evening, a warm table lamp and a small plant behind her.",
     "A bedroom dressing table in the evening with a warm table lamp and a small plant behind her",
     "Close-up from eye level, facing her straight on, showing her from the upper chest up; her head takes about one third of the picture height, with a clear band of "
     "background above her hair about one sixth of the picture.",
     "Close-up from eye level showing her from the upper chest up", "table lamp and the small plant",
     SMILE_Q, BOTTLE_Q.format(side="left"), OO, FULL_Q, FULL_H, BOTTLE_H.format(side="left"), SMILE_H,
     ("頭皮洗得很舒服", "頭髮吹完蓬蓬的"), prop_word="bottle")

shot(O, "ogO4",
     "She stands on a quiet tree-lined street in Taipei on a sunny afternoon, with low shop houses, green street trees and parked scooters behind her; no shop signs are readable.",
     "A quiet tree-lined street in Taipei on a sunny afternoon with low shop houses, green street trees and parked scooters behind her; no shop signs are readable",
     "Medium shot from chest height, a little farther away, showing her from the waist up; her body is turned about thirty degrees to her right while her face turns "
     "back toward the camera; her head takes about one fifth of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from chest height showing her from the waist up, her body turned slightly to one side and her face toward the camera",
     "street trees, shop houses and parked scooters",
     "She smiles brightly at the camera.", NOHAND_Q, OO, FULL_Q, FULL_H, NOHAND_H, "She smiles brightly at the camera for the whole clip.",
     ("頭頂看起來有份量", "出門心情也變好"))

shot(O, "ogO5",
     "She sits on the edge of her bed in a cosy bedroom at night, a warm bedside lamp and a light grey headboard behind her.",
     "A cosy bedroom at night with a warm bedside lamp and a light grey headboard behind her; she sits on the edge of the bed",
     "Medium shot from a slightly lower angle than her eyes, facing her straight on, showing her from the waist up as she sits; her head takes about one fifth of the "
     "picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from slightly below eye level showing her from the waist up as she sits on the bed", "bedside lamp and the headboard",
     "She smiles warmly at the camera.", BOTTLE_Q.format(side="left") + POINT_Q, OO, FULL_Q, FULL_H, BOTTLE_H.format(side="left") + POINT_H,
     "She smiles warmly at the camera for the whole clip.", ("髮質細軟容易扁的", "連結我放下面"), prop_word="bottle")

# ───────────── 可口可樂 易開罐 250ml 24 入（賣場：經典易開罐，勁享休閒時刻／擋不住的暢快口感／勁享美食，就要Coke）
K = "腳本備妥-可口可樂易開罐24入-多鏡頭"
KO = "a plain pale yellow cotton T-shirt with no print"
KHAIR_Q = "Her hair looks neat and natural."
KHAIR_H = "her hair stays exactly as in the first frame."
CAN_Q = ("She holds one unopened red Coca-Cola can from image 2, exactly its look: a short squat red aluminium can with the white flowing Coca-Cola script, the white "
         "wave line and the words ORIGINAL TASTE, a silver top with the ring pull closed, tiny cold water droplets on it. She holds it upright in her {side} hand in front "
         "of her chest near the middle of the picture, four fingers wrapped around the can and the thumb on the near side facing the camera, the logo facing the camera, "
         "the whole can inside the frame. The can is its real size: a small can about as tall as her palm is long.")
CAN_H = ("She holds the small unopened red Coca-Cola can upright in her {side} hand in front of her chest exactly as in the first frame; the ring pull stays closed, the "
         "can keeps exactly this shape, this size, its red colour and its white script for the whole clip, and her hand holds it perfectly still, never opening, tilting, "
         "lifting it to her mouth or turning it.")
CASE_Q = ("She holds the flat cardboard tray of red Coca-Cola cans from image 3 in both arms in front of her waist: a low beige cardboard tray with a small dark "
          "Coca-Cola script on its front side, holding many short red Coca-Cola cans standing upright in rows, wrapped in clear plastic film. Both forearms are under the "
          "tray and both hands hold its two short sides, the front of the tray facing the camera, the whole tray inside the frame and below her chin.")
CASE_H = ("She holds the beige cardboard tray full of red Coca-Cola cans in both arms in front of her waist exactly as in the first frame; the tray, the cans and the plastic "
          "film keep exactly this shape, size and colour for the whole clip, no can moves, and her arms hold it perfectly still.")

shot(K, "kkK1",
     "She stands in a home kitchen in the afternoon beside a tall white fridge whose door is open; the lit shelves inside the fridge are almost empty, only a jar and a few eggs.",
     "A home kitchen in the afternoon; she stands beside a tall white fridge with its door open and its lit shelves almost empty",
     "Medium close shot from chest height; her body is turned about thirty degrees to her right toward the open fridge while her face turns back toward the camera; "
     "her head takes about one quarter of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium close shot from chest height, her body turned slightly toward the open fridge and her face toward the camera", "open fridge door, the fridge shelves and the kitchen wall",
     "Her expression: she looks a little disappointed, lips pressed together, eyebrows relaxed; she is NOT smiling.", NOHAND_Q, KO, KHAIR_Q, KHAIR_H, NOHAND_H,
     "She looks a little disappointed, speaking in a calm, slightly flat voice; she does not frown.", ("好想喝冰可樂", "冰箱又空空的"), end_smile=False)

shot(K, "kkK2",
     "She stands in the entrance hall of her apartment just inside the open front door, a shoe cabinet and a small mirror behind her, daylight from the doorway.",
     "The entrance hall of an apartment with a shoe cabinet and a small mirror behind her, daylight from the open front door",
     "Medium shot from chest height facing her straight on, a little farther away, showing her from the thighs up; her head takes about one fifth of the picture "
     "height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from chest height showing her from the thighs up", "shoe cabinet, the small mirror and the door frame",
     "She smiles brightly, pleased.", CASE_Q, KO, KHAIR_Q, KHAIR_H, CASE_H, "She smiles brightly for the whole clip.",
     ("我就直接買一整箱", "放家裡隨時有得喝"), prop_word="tray of cans")

shot(K, "kkK3",
     "She sits at a small wooden desk by a window at home in the afternoon, a laptop and a notebook on the desk, a bookshelf behind her.",
     "A small wooden desk by a window at home in the afternoon with a bookshelf behind her",
     "Close-up from eye level facing her straight on, showing her from the upper chest up; her head takes about one third of the picture height, with a clear band of "
     "background above her hair about one sixth of the picture.",
     "Close-up from eye level showing her from the upper chest up", "window frame and the bookshelf",
     "She is pleased with an easy, refreshed smile.", CAN_Q.format(side="right"), KO, KHAIR_Q, KHAIR_H, CAN_H.format(side="right"),
     "She is pleased with an easy smile for the whole clip.", ("做事累的時候", "冰冰的喝一口很暢快"), prop_word="can")

shot(K, "kkK4",
     "She sits on a cushion on the living-room floor in the evening beside a low coffee table with an open box of fried chicken on it, a sofa and a softly glowing TV behind her.",
     "A living room in the evening; she sits on the floor beside a low coffee table with an open box of fried chicken, a sofa and a softly glowing TV behind her",
     "Medium shot from a low angle close to the floor, her body turned about thirty degrees to her left while her face turns toward the camera, showing her from the "
     "waist up; her head takes about one fifth of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from a low angle showing her from the waist up, her body turned slightly to one side and her face toward the camera",
     "sofa, the glowing TV and the coffee table edge",
     "She smiles happily at the camera.", CAN_Q.format(side="left"), KO, KHAIR_Q, KHAIR_H, CAN_H.format(side="left"),
     "She smiles happily at the camera for the whole clip.", ("配炸雞追劇的時候", "來一口剛剛好"), prop_word="can")

shot(K, "kkK5",
     "She stands on a small apartment balcony at dusk with potted plants and a railing behind her and soft city lights in the distance.",
     "A small apartment balcony at dusk with potted plants and a railing behind her and soft city lights in the distance",
     "Medium close shot from chest height facing her straight on; her head takes about one quarter of the picture height, with a clear band of background above "
     "her hair about one sixth of the picture.",
     "Medium close shot from chest height facing her", "potted plants, the railing and the distant city lights",
     "She smiles warmly at the camera.", CAN_Q.format(side="left") + POINT_Q, KO, KHAIR_Q, KHAIR_H, CAN_H.format(side="left") + POINT_H,
     "She smiles warmly at the camera for the whole clip.", ("家裡可樂常常喝完的", "連結我放下面"), prop_word="can")

# ───────────── TRYALL 無添加乳清蛋白（蝦皮直營；賣場圖：沖泡方式「想喝什麼口味，自己決定！」取用搖搖杯加入 200–300ml 的水、豆漿或牛奶→加入1份蛋白粉→混合至溶解）
T = "腳本備妥-TRYALL無添加乳清-多鏡頭"
TO_GYM = "a plain black sports tank top under an open light grey zip-up track jacket, with no print and no logo"
TO_HOME = "a plain soft white oversized cotton T-shirt with no print"
POUCH_Q = ("She holds the protein powder pouch from image 2, exactly its look: a white stand-up resealable pouch with a small green V-shaped logo and the grey word TRYALL "
           "near the top, the words INSTANT WHEY PROTEIN CONCENTRATE in grey capital letters in the middle, a thin grey line and small grey text under them. She holds "
           "it upright in her {side} hand in front of her chest near the middle of the picture, her fingers holding the side edge of the pouch and the thumb on the "
           "front edge, the front of the pouch facing the camera, the whole pouch inside the frame. The pouch is its real size: about as tall as her forearm from wrist "
           "to elbow.")
POUCH_H = ("She holds the white protein powder pouch upright in her {side} hand in front of her chest exactly as in the first frame; the pouch stays sealed, keeps "
           "exactly this shape, this size, its white colour and its printing for the whole clip, and her hand holds it perfectly still, never opening, tilting or turning it.")
SHAKER_Q = ("She holds a clear plastic shaker bottle with a plain black screw lid, with no logo and no text, filled two thirds with a smooth pale beige milky drink, "
            "upright in her {side} hand in front of her chest near the middle of the picture, four fingers wrapped around the bottle and the thumb on the near side, "
            "the whole bottle inside the frame; the lid is closed.")
SHAKER_H = ("She holds the clear shaker bottle with the black lid and the pale beige drink upright in her {side} hand in front of her chest exactly as in the first "
            "frame; the lid stays closed, the drink level stays the same, and her hand holds it perfectly still, never shaking, lifting, tilting or drinking from it.")
THAIR_Q = "Her hair looks neat and natural."
THAIR_H = "her hair stays exactly as in the first frame."

shot(T, "tyT1",
     "She stands in a bright modern gym in the evening with dumbbell racks and training machines behind her; there are no brand marks.",
     "A bright modern gym in the evening with dumbbell racks and training machines behind her",
     "Medium close shot from chest height; her body is turned about thirty degrees to her left while her face turns back toward the camera; her head takes about "
     "one quarter of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium close shot from chest height, her body turned slightly to one side and her face toward the camera", "dumbbell racks and training machines",
     "Her expression: she looks a little fed up, lips pressed together, eyebrows relaxed; she is NOT smiling. Her face has a light healthy glow after exercise.",
     NOHAND_Q, TO_GYM, THAIR_Q, THAIR_H, NOHAND_H, "She looks a little fed up, speaking in a calm, slightly flat voice; she does not frown.",
     ("調味蛋白粉喝久了", "甜到有點膩"), end_smile=False)

shot(T, "tyT2",
     "She stands in a bright home kitchen in the morning with a light wooden counter, a window with daylight and a kettle behind her.",
     "A bright home kitchen in the morning with a light wooden counter, a window with daylight and a kettle behind her",
     "Medium shot from chest height facing her straight on, a little farther away, showing her from the waist up; her head takes about one fifth of the picture "
     "height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from chest height showing her from the waist up", "window, the wooden counter and the kettle",
     "She is pleased with an easy smile.", POUCH_Q.format(side="right"), TO_HOME, THAIR_Q, THAIR_H, POUCH_H.format(side="right"),
     "She is pleased with an easy smile for the whole clip.", ("現在喝的是這包無添加的", "原味沒有調味"), prop_word="pouch")

shot(T, "tyT3",
     "She sits at a small round dining table at home in the morning, a glass of soy milk and a bowl of fruit on the table, a window with sheer curtains behind her.",
     "A small round dining table at home in the morning with a window and sheer curtains behind her",
     "Close-up from eye level facing her straight on, showing her from the upper chest up; her head takes about one third of the picture height, with a clear band "
     "of background above her hair about one sixth of the picture.",
     "Close-up from eye level showing her from the upper chest up", "window and the sheer curtains",
     "She is pleased with an easy smile.", SHAKER_Q.format(side="left"), TO_HOME, THAIR_Q, THAIR_H, SHAKER_H.format(side="left"),
     "She is pleased with an easy smile for the whole clip.", ("加豆漿或牛奶一起喝", "口味自己決定"), prop_word="shaker bottle")

shot(T, "tyT4",
     "She stands on a riverside running path in a green park in the early morning with trees, grass and a bridge in the distance behind her.",
     "A riverside running path in a green park in the early morning with trees, grass and a distant bridge behind her",
     "Medium shot from a slightly low angle, a little farther away, showing her from the waist up; her body is turned about thirty degrees to her right while her face "
     "turns back toward the camera; her head takes about one fifth of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from a slightly low angle showing her from the waist up, her body turned slightly to one side and her face toward the camera",
     "trees, the grass and the distant bridge",
     "She smiles brightly at the camera, fresh after a run.", SHAKER_Q.format(side="right"), TO_GYM, THAIR_Q, THAIR_H, SHAKER_H.format(side="right"),
     "She smiles brightly at the camera for the whole clip.", ("運動完來一杯", "補充蛋白質很簡單"), prop_word="shaker bottle")

shot(T, "tyT5",
     "She sits on a light grey sofa in a cosy living room in the evening, a floor lamp and a bookshelf behind her.",
     "A cosy living room in the evening with a light grey sofa, a floor lamp and a bookshelf behind her; she sits on the sofa",
     "Medium shot from slightly below her eye level facing her straight on, showing her from the waist up as she sits; her head takes about one fifth of the picture "
     "height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from slightly below eye level showing her from the waist up as she sits on the sofa", "floor lamp and the bookshelf",
     "She smiles warmly at the camera.", POUCH_Q.format(side="left") + POINT_Q, TO_HOME, THAIR_Q, THAIR_H, POUCH_H.format(side="left") + POINT_H,
     "She smiles warmly at the camera for the whole clip.", ("想喝無添加乳清的", "連結我放下面"), prop_word="pouch")

# ───────────── 挑完首幀後的對齊修正（提示詞寫的手＝首幀的手，CLAUDE #90）
def _fix(pkg, sid, old, new):
    for suf in ("", "D"):
        p = os.path.join(HERE, pkg, f"prompt_{sid}{suf}.txt")
        s = open(p, encoding="utf-8").read()
        assert old in s, (sid, old[:40])
        open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))

# kkK4 選 900331：她是雙手捧罐
_fix(K, "kkK4", "She holds the small unopened red Coca-Cola can upright in her left hand in front of her chest exactly as in the first frame;",
     "She holds the small unopened red Coca-Cola can upright with both hands in front of her chest exactly as in the first frame;")
_fix(K, "kkK4", "and her hand holds it perfectly still", "and her hands hold it perfectly still")

# ogO3 選 v3 900197（蓬鬆版重畫）：她是右手拿瓶
_fix(O, "ogO3", "shampoo bottle with the light wood-coloured cap upright in her left hand", "shampoo bottle with the light wood-coloured cap upright in her right hand")

# ───────────── NIVEA 妮維雅 密集修護乳液 400ml（蝦皮直營；賣場：「質地清爽不黏膩，容易吸收」「搭配天然葡萄籽油、酪梨油精華」「持久保濕」「給肌膚看的見的水嫩透亮」）
N = "腳本備妥-NIVEA密集修護乳液-多鏡頭"
N_SWEATER = "a plain soft light grey knit sweater with no print"
N_ROBE = "a plain white cotton bathrobe"
N_COAT = "a plain camel wool coat over a light grey knit sweater, with no print and no logo"
NIV_Q = ("She holds the body lotion bottle from image 2, exactly its look: a tall dark navy-blue plastic bottle with a navy pump on top, a round white-and-blue NIVEA "
         "logo near the top, small white printed words and a white milk-drop picture on the front. She holds it upright in her {side} hand in front of her chest near "
         "the middle of the picture, four fingers wrapped around the body of the bottle and the thumb on the near side facing the camera, the pump on top, the front "
         "of the bottle facing the camera, the whole bottle inside the frame. The bottle is its real size: about as tall as her forearm from wrist to elbow.")
NIV_H = ("She holds the tall dark navy-blue lotion bottle with the pump upright in her {side} hand in front of her chest exactly as in the first frame; the bottle "
         "keeps exactly this shape, this size, its dark blue colour and its white logo for the whole clip, her fingers never press the pump, and her hand holds it "
         "perfectly still, never tilting or turning it.")
NHAIR_Q = "Her hair looks neat and natural."
NHAIR_H = "her hair stays exactly as in the first frame."

shot(N, "nvN1",
     "She stands in a bathroom on a cold winter evening right after a shower, the mirror behind her fogged with steam, white tiles and a towel rail behind her.",
     "A bathroom on a winter evening with a steamed-up mirror, white tiles and a towel rail behind her",
     "Medium close shot from chest height; her body is turned about thirty degrees to her left while her face turns back toward the camera; her head takes about "
     "one quarter of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium close shot from chest height, her body turned slightly to one side and her face toward the camera", "fogged mirror, the white tiles and the towel rail",
     "Her expression: she looks a little uncomfortable, lips pressed together, eyebrows relaxed; she is NOT smiling.", NOHAND_Q, N_ROBE,
     "Her hair is dry and neat, tucked behind her shoulders.", NHAIR_H, NOHAND_H,
     "She looks a little uncomfortable, speaking in a calm, slightly flat voice; she does not frown.", ("天氣一冷洗完澡", "全身皮膚都緊緊的"), end_smile=False)

shot(N, "nvN2",
     "She sits at a white dressing table in her bedroom in the evening, a round mirror and a small vase of dried flowers behind her.",
     "A bedroom dressing table in the evening with a round mirror and a small vase of dried flowers behind her",
     "Medium shot from chest height facing her straight on, showing her from the waist up as she sits; her head takes about one fifth of the picture height, with a "
     "clear band of background above her hair about one sixth of the picture.",
     "Medium shot from chest height showing her from the waist up as she sits", "round mirror and the vase of dried flowers",
     "She is pleased with an easy smile.", NIV_Q.format(side="right"), N_SWEATER, NHAIR_Q, NHAIR_H, NIV_H.format(side="right"),
     "She is pleased with an easy smile for the whole clip.", ("我擦的是妮維雅密集修護", "深藍色這瓶"), prop_word="bottle")

shot(N, "nvN3",
     "She sits on a beige sofa in a warm living room in the evening, a knitted blanket and a floor lamp behind her.",
     "A warm living room in the evening with a beige sofa, a knitted blanket and a floor lamp behind her",
     "Close-up from eye level facing her straight on, showing her from the upper chest up; her head takes about one third of the picture height, with a clear band "
     "of background above her hair about one sixth of the picture.",
     "Close-up from eye level showing her from the upper chest up", "floor lamp and the knitted blanket",
     "She is pleased with an easy smile.", NIV_Q.format(side="left"), N_SWEATER, NHAIR_Q, NHAIR_H, NIV_H.format(side="left"),
     "She is pleased with an easy smile for the whole clip.", ("擦起來清爽不黏膩", "很容易吸收"), prop_word="bottle")

shot(N, "nvN4",
     "She stands on a quiet Taipei street on a cool winter afternoon with bare trees, low buildings and soft grey sky behind her; no shop signs are readable.",
     "A quiet Taipei street on a cool winter afternoon with bare trees, low buildings and a soft grey sky behind her; no shop signs are readable",
     "Medium shot from chest height, a little farther away, showing her from the waist up; her body is turned about thirty degrees to her right while her face turns "
     "back toward the camera; her head takes about one fifth of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from chest height showing her from the waist up, her body turned slightly to one side and her face toward the camera",
     "bare trees, the low buildings and the grey sky",
     "She smiles brightly at the camera.", NOHAND_Q, N_COAT, NHAIR_Q, NHAIR_H, NOHAND_H, "She smiles brightly at the camera for the whole clip.",
     ("擦完再出門", "摸起來水水嫩嫩"))

shot(N, "nvN5",
     "She sits on the edge of her bed in a cosy bedroom at night, a warm bedside lamp and a white headboard behind her.",
     "A cosy bedroom at night with a warm bedside lamp and a white headboard behind her; she sits on the edge of the bed",
     "Medium shot from slightly below her eye level facing her straight on, showing her from the waist up as she sits; her head takes about one fifth of the picture "
     "height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from slightly below eye level showing her from the waist up as she sits on the bed", "bedside lamp and the white headboard",
     "She smiles warmly at the camera.", NIV_Q.format(side="left") + POINT_Q, N_SWEATER, NHAIR_Q, NHAIR_H, NIV_H.format(side="left") + POINT_H,
     "She smiles warmly at the camera for the whole clip.", ("冬天想好好保濕的", "連結我放下面"), prop_word="bottle")

# ───────────── SENKA 專科超微米潔顏乳 第二支（v2 通勤；第一支＝浴室痛點＋九份，9/26 已上蝦皮）；賣場：「5 倍細緻超濃密泡泡」「保濕導入技術更能感受肌膚水潤不緊繃」「6 入組」
S = "腳本備妥-SENKA專科潔顏乳-v2通勤"
SO = "a plain navy blue cotton T-shirt with no print"
SO_COAT = "a plain light beige trench coat over a plain white T-shirt, with no print and no logo"
TUBE_Q = ("She holds the face wash tube from image 2, exactly its look: a soft squeeze tube in a soft pink colour with the white SENKA logo near the top, the words "
          "Perfect Whip in large white letters, and a white foam-cloud badge with the words Beauty Foam in pink script below them. The tube is held upright with "
          "its flat pink flip-top cap at the bottom, in her {side} hand in front of her chest near the middle of the picture, four fingers wrapped around the tube "
          "and the thumb on the near side facing the camera, the front of the tube facing the camera, the whole tube inside the frame. The tube is its real size: "
          "about as long as her hand from wrist to fingertips.")
TUBE_H = ("She holds the soft pink face wash tube upright in her {side} hand in front of her chest exactly as in the first frame; the tube keeps exactly this shape, "
          "this size, its pink colour and its white printing for the whole clip, it is never squeezed or opened, and her hand holds it perfectly still, never tilting "
          "or turning it.")
SHAIR_Q = "Her hair looks neat and natural."
SHAIR_H = "her hair stays exactly as in the first frame."

shot(S, "skS1",
     "She stands at a city bus stop in the evening after work, warm street lights, blurred traffic lights and shop fronts behind her; no shop signs are readable.",
     "A city bus stop in the evening with warm street lights and blurred traffic behind her; no shop signs are readable",
     "Medium shot from chest height, a little farther away, showing her from the waist up; her body is turned about thirty degrees to her left while her face turns "
     "back toward the camera; her head takes about one fifth of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from chest height showing her from the waist up, her body turned slightly to one side and her face toward the camera",
     "street lights, the bus stop shelter and the blurred traffic",
     "Her expression: she looks a little tired and uncomfortable, lips pressed together, eyebrows relaxed; she is NOT smiling. Her face looks a little shiny after a long day.",
     NOHAND_Q, SO_COAT, SHAIR_Q, SHAIR_H, NOHAND_H,
     "She looks a little tired, speaking in a calm, slightly flat voice; she does not frown.", ("在外面待一整天", "臉黏黏的好不舒服"), end_smile=False)

shot(S, "skS2",
     "She stands in the entrance hall of her apartment in the evening just after coming home, a shoe cabinet, a small mirror and a coat hook behind her, warm indoor light.",
     "The entrance hall of an apartment in the evening with a shoe cabinet, a small mirror and a coat hook behind her, warm indoor light",
     "Medium close shot from chest height facing her straight on; her head takes about one quarter of the picture height, with a clear band of background above "
     "her hair about one sixth of the picture.",
     "Medium close shot from chest height facing her", "shoe cabinet, the small mirror and the coat hook",
     "She is pleased with an easy smile.", TUBE_Q.format(side="right"), SO, SHAIR_Q, SHAIR_H, TUBE_H.format(side="right"),
     "She is pleased with an easy smile for the whole clip.", ("回家第一件事就是洗臉", "我用這條粉紅色的"), prop_word="tube")

shot(S, "skS3",
     "She stands at a white bathroom sink at night with a round mirror, white tiles and a small plant behind her; her hair is held back with a plain white headband.",
     "A white bathroom at night with a round mirror, white tiles and a small plant behind her",
     "Close-up from eye level facing her straight on, showing her from the upper chest up; her head takes about one third of the picture height, with a clear band "
     "of background above her hair about one sixth of the picture.",
     "Close-up from eye level showing her from the upper chest up", "round mirror, the white tiles and the plant",
     "She is pleased with an easy smile.", TUBE_Q.format(side="left"), SO, "Her hair is held back with a plain white headband.",
     "her hair and the white headband stay exactly as in the first frame.", TUBE_H.format(side="left"),
     "She is pleased with an easy smile for the whole clip.", ("泡泡很綿密", "洗起來很舒服"), prop_word="tube")

shot(S, "skS4",
     "She sits at a bedroom dressing table at night with a warm table lamp and a small vase behind her; her face looks fresh and just washed.",
     "A bedroom dressing table at night with a warm table lamp and a small vase behind her",
     "Medium shot from slightly below her eye level, her body turned about thirty degrees to her right while her face turns toward the camera, showing her from the "
     "waist up as she sits; her head takes about one fifth of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from slightly below eye level showing her from the waist up as she sits, her body turned slightly to one side and her face toward the camera",
     "table lamp and the vase",
     "She smiles happily at the camera.", TUBE_Q.format(side="right"), SO, SHAIR_Q, SHAIR_H, TUBE_H.format(side="right"),
     "She smiles happily at the camera for the whole clip.", ("洗完臉不會緊繃", "摸起來水水的"), prop_word="tube")

shot(S, "skS5",
     "She sits on a light grey sofa in a cosy living room in the evening with a floor lamp and a bookshelf behind her.",
     "A cosy living room in the evening with a light grey sofa, a floor lamp and a bookshelf behind her; she sits on the sofa",
     "Medium shot from chest height facing her straight on, showing her from the waist up as she sits; her head takes about one fifth of the picture height, with "
     "a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from chest height showing her from the waist up as she sits on the sofa", "floor lamp and the bookshelf",
     "She smiles warmly at the camera.", TUBE_Q.format(side="left") + POINT_Q, SO, SHAIR_Q, SHAIR_H, TUBE_H.format(side="left") + POINT_H,
     "She smiles warmly at the camera for the whole clip.", ("常常覺得臉黏黏", "連結我放下面"), prop_word="tube")

# ───────────── 巴黎萊雅 溫和眼唇卸妝液 第二支（v2 回家卸妝；第一支＝櫃姐版 9/19 已上架）；賣場：清爽配方、不留下油質／輕鬆卸防水眼部彩妝／用化妝棉輕抹於眼皮上，直至完全潔淨，切勿用力擦拭
L = "腳本備妥-巴黎萊雅眼唇卸妝液-v2回家卸妝"
LO = "a plain soft lavender cotton pajama top with no print"
LR_Q = ("She holds the make-up remover bottle from image 2, exactly its look: a small clear plastic bottle with a white screw cap, the liquid inside in two layers "
        "(light blue on top, clear below), and a light blue label with the white L'OREAL logo and the word GENTLE. She holds it upright in her {side} hand in front "
        "of her chest near the middle of the picture, four fingers wrapped around the bottle and the thumb on the near side facing the camera, the cap on top and "
        "closed, the label facing the camera, the whole bottle inside the frame. The bottle is small, its real size: about as tall as her palm is long.")
LR_H = ("She holds the small clear two-layer make-up remover bottle with the white cap upright in her {side} hand in front of her chest exactly as in the first "
        "frame; the cap stays closed, the bottle keeps exactly this shape, this size, its blue and clear layers and its label for the whole clip, it is never shaken, "
        "and her hand holds it perfectly still, never tilting or turning it.")
PAD_Q = (" In her other hand, held low in front of her stomach, she holds one clean round white cotton pad between her thumb and fingers; it does not touch her face.")
PAD_H = (" Her other hand keeps holding the clean round white cotton pad low in front of her stomach exactly as in the first frame; it never rises and never touches her face.")
LHAIR_Q = "Her hair looks neat and natural. Her eye make-up is still on: dark mascara and a thin eyeliner."
LHAIR_H = "her hair and her eye make-up stay exactly as in the first frame."

shot(L, "lrL1",
     "She stands in a small bathroom at night in front of a mirror cabinet with warm light, a towel rail and a few toiletries behind her.",
     "A small bathroom at night with a mirror cabinet, warm light, a towel rail and toiletries behind her",
     "Medium close shot from chest height; her body is turned about thirty degrees to her left while her face turns back toward the camera; her head takes about "
     "one quarter of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium close shot from chest height, her body turned slightly to one side and her face toward the camera", "mirror cabinet, the towel rail and the toiletries",
     "Her expression: she looks a little tired and fed up, lips pressed together, eyebrows relaxed; she is NOT smiling.", NOHAND_Q, LO, LHAIR_Q, LHAIR_H, NOHAND_H,
     "She looks a little tired, speaking in a calm, slightly flat voice; she does not frown.", ("防水睫毛膏", "每次都卸不掉"), end_smile=False)

shot(L, "lrL2",
     "She sits at a white bedroom dressing table at night with a round mirror, a small lamp and a jar of cotton pads behind her.",
     "A bedroom dressing table at night with a round mirror, a small lamp and a jar of cotton pads behind her",
     "Medium shot from chest height facing her straight on, showing her from the waist up as she sits; her head takes about one fifth of the picture height, with a "
     "clear band of background above her hair about one sixth of the picture.",
     "Medium shot from chest height showing her from the waist up as she sits", "round mirror, the small lamp and the cotton pad jar",
     "She is pleased with an easy smile.", LR_Q.format(side="right"), LO, LHAIR_Q, LHAIR_H, LR_H.format(side="right"),
     "She is pleased with an easy smile for the whole clip.", ("現在卸眼唇用這瓶", "巴黎萊雅的眼唇卸妝液"), prop_word="bottle")

shot(L, "lrL3",
     "She sits at the same kind of white dressing table at night, a warm lamp and a small plant behind her.",
     "A dressing table at night with a warm lamp and a small plant behind her",
     "Close-up from eye level facing her straight on, showing her from the upper chest up; her head takes about one third of the picture height, with a clear band "
     "of background above her hair about one sixth of the picture.",
     "Close-up from eye level showing her from the upper chest up", "warm lamp and the small plant",
     "She is pleased with a calm, gentle smile.", LR_Q.format(side="right") + PAD_Q, LO, LHAIR_Q, LHAIR_H, LR_H.format(side="right") + PAD_H,
     "She has a calm, gentle smile for the whole clip.", ("用化妝棉輕輕抹", "不用用力擦"), prop_word="bottle")

shot(L, "lrL4",
     "She sits on a beige sofa in a cosy living room at night with a floor lamp and a window with city lights behind her; her face is bare and fresh without make-up.",
     "A cosy living room at night with a beige sofa, a floor lamp and a window with city lights behind her",
     "Medium shot from slightly below her eye level, her body turned about thirty degrees to her right while her face turns toward the camera, showing her from the "
     "waist up as she sits; her head takes about one fifth of the picture height, with a clear band of background above her hair about one sixth of the picture.",
     "Medium shot from slightly below eye level showing her from the waist up as she sits, her body turned slightly to one side and her face toward the camera",
     "floor lamp and the window",
     "She smiles happily at the camera.", LR_Q.format(side="left"), LO, "Her hair looks neat and natural. Her face is clean with no make-up.",
     "her hair and her clean make-up-free face stay exactly as in the first frame.", LR_H.format(side="left"),
     "She smiles happily at the camera for the whole clip.", ("卸完清清爽爽", "摸起來不油膩"), prop_word="bottle")

shot(L, "lrL5",
     "She sits on the edge of her bed at night with a warm bedside lamp and a white headboard behind her; her face is clean with no make-up.",
     "A bedroom at night with a warm bedside lamp and a white headboard behind her; she sits on the edge of the bed",
     "Medium shot from chest height facing her straight on, showing her from the waist up as she sits; her head takes about one fifth of the picture height, with a "
     "clear band of background above her hair about one sixth of the picture.",
     "Medium shot from chest height showing her from the waist up as she sits on the bed", "bedside lamp and the headboard",
     "She smiles warmly at the camera.", LR_Q.format(side="left") + POINT_Q, LO, "Her hair looks neat and natural. Her face is clean with no make-up.",
     "her hair and her clean make-up-free face stay exactly as in the first frame.", LR_H.format(side="left") + POINT_H,
     "She smiles warmly at the camera for the whole clip.", ("常畫防水眼妝的", "連結我放下面"), prop_word="bottle")
