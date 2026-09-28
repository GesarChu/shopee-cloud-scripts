# -*- coding: utf-8 -*-
"""genlib — 蝦皮分潤短影音「一支片 5 鏡」的提示詞產生器（工單 #1，取代 legacy/ 那串互相載入的 _gen_*.py）。

每鏡寫三個檔（shot_id＝規格檔的 shot_prefix＋鏡號，例：tt1）：
  _qwen指令/q_<shot_id>.txt   給 Qwen-Image 的首幀指令（image 1＝人物照、image 2＝商品照）
  prompt_<shot_id>D.txt       給 MiniMax H3 的影片提示詞（台詞用官方 <d>[Chinese] …</d>）
  口白腳本_<shot_id>D.txt      兩個半句各一行，驗片比對用

檔案結構：
  1. 文字模板 —— 所有會進到輸出檔的英文句子都在這一段，要改措辭只改這裡
  2. 五鏡結構 —— 每鏡的機位、表情、哪隻手拿商品（等同 legacy five2() 寫死的部分）
  3. 規格檔讀取與檢查
  4. 組字串（純函式，不碰檔案）
  5. 寫檔（輸出資料夾由呼叫端給）

規格檔格式見 spec/README.md。
"""
import json
import os

# ════════════════════════════════════════════════════════════════════════════
# 1. 文字模板（全部集中在這裡）
#    ⚠️ 這些句子＝golden/ 的內容，一個字元都不要動；改了 test_golden.py 會紅。
#    模板用 str.format 帶入欄位；規格檔的文字只當「值」帶進去，不會再被 format，所以文字裡有 { } 也安全。
# ════════════════════════════════════════════════════════════════════════════

# ── Qwen 首幀指令 ─────────────────────────────────────────────────────────────
# 身材保持句放最前面（CLAUDE #101）
QWEN_BODY = ("her whole body stays exactly as in image 1 — the same body shape and build, the same shoulder width, the same bust, waist and "
             "hips, the same arm and leg thickness, the same height and proportions — ")
QWEN_PLACE_RULE = (" The background is clearly recognisable as the place it is; there are no brand marks, no logos and no readable text anywhere "
                   "in the background.")
QWEN_HANDS_RULE = " Each visible hand has five fingers of normal length; the hands are clearly separate."
QWEN = ("Edit this photo. Keep the young woman from image 1 exactly as she is: {body}and the same face, the same eye shape and eye size, the same "
        "eyelids, the same nose, mouth and jawline, {person}, the same makeup. Only her clothes, her pose, the place and the camera change, and the "
        "clothes follow her own body shape from image 1. Change these things. First, the place: {scene}{place_rule} Second, the camera: {framing}"
        " Third, her clothes: she now wears {outfit}. Fourth, her hair: {hair} Fifth, her hands: {hands}{hands_rule}"
        " Sixth, her expression: {expression} Natural skin tones, clean realistic photography, sharp focus on her face; no text or logos added to "
        "the picture.")

# 拿商品（Qwen 要寫哪隻手：圖片模型需要明確指示）
QWEN_HOLD = ("She holds the {look}. She holds it upright in her {side} hand in front of her upper chest just below her collarbone, {grip}, "
             "the front facing the camera, the whole thing inside the frame. It is its real size: {size}.")
DEFAULT_GRIP = "four fingers wrapped around it and the thumb on the near side facing the camera"
# 叫人買那鏡：沒拿商品的那隻手食指朝下
QWEN_POINT = (" Her {side} hand is in front of her lower chest with the index finger pointing straight down and the other fingers curled, palm "
              "facing her body; there is nothing under that hand.")
# 痛點鏡不拿商品
QWEN_NO_HANDS = " Both her hands are down by her sides below the bottom edge of the picture, out of the frame."

# ── H3 影片提示詞 ─────────────────────────────────────────────────────────────
# ⛔ 影片提示詞不寫左右手，只寫 one hand／her other hand（2026-09-27 起：圖片模型常把左右手畫反，寫左右會跟首幀打架）
VIDEO_HOLD = ("She holds the {look} upright in one hand in front of her upper chest exactly as in the first frame; it keeps exactly this "
              "shape, this size, its colours and its printing for the whole clip, and her hand holds it perfectly still, never shaking, squeezing, "
              "tilting or turning it.")
VIDEO_POINT = (" The index finger of her other hand keeps pointing straight down in front of her lower chest for the whole clip, and that hand "
               "stays still.")
# 9/27：Qwen 沒照「手在畫面外」畫（手垂在身側入鏡）⇒ 提示詞寫成跟首幀一致
VIDEO_NO_HANDS = (" Her arms hang relaxed at her sides and her hands stay completely still at the bottom of the picture for the whole clip, "
                  "exactly as in the first frame; her hands never rise toward her face or her body.")
# 鏡頭鎖定句：{keep}＝「her face」或「her face and the <商品詞>」
VIDEO_CAMERA = (" {framing}, exactly the framing of the first frame; a static locked-off tripod shot: the frame edges stay on the same {anchors}"
                " for the whole clip, {keep} keep exactly the same size and the same position in the frame as in the first frame, her whole head "
                "stays inside the frame with the same clear band of background above her hair, and she stays at the same distance from the "
                "camera the whole time. Natural skin tones, the background clearly recognisable as the place it is. Her hands never touch her "
                "face or her hair. Her lips move naturally and match every word she says.")
VIDEO_KEEP = "her face"
VIDEO_KEEP_WITH_PROP = "her face and the {prop}"
# 台詞：MiniMax 官方 <d> 標籤、台灣口音寫在講話者那句
VIDEO_LINE = "<d>[Chinese] {first}，{second}</d>"
VIDEO_END_SMILE = "her mouth closes in a soft smile, everything else unchanged."
VIDEO_END_CALM = "her mouth closes, her face calm, everything else unchanged."
VIDEO_TAIL_SMILE = "she holds still with a soft closed-mouth smile, blinks once slowly and stays quiet until the end."
VIDEO_TAIL_CALM = "she holds still with her mouth closed and a calm face, blinks once slowly and stays quiet until the end."
VIDEO_SOUND = ("overall_soundscape: Her clear female voice in the foreground, close and conversational: a light, bright, mid-pitched voice of a "
               "young Taiwanese woman in her mid twenties, natural Taiwanese Mandarin accent, relaxed and unhurried, the same voice and the same "
               "distance to the microphone in every clip; quiet ambience, very faint; after her last sentence there is only that quiet ambience.\n"
               "non_diegetic_music: none. No background music.\n")
# 注意：{hair} 與 {hands} 之間固定一個空格；痛點鏡的 VIDEO_NO_HANDS 本身開頭也有空格，所以該鏡會出現兩個空格——golden 就是這樣，照留。
VIDEO = ("integrated_multimodal_description:\n"
         "{scene}, continuing exactly from the first frame; no brand marks and no readable signs anywhere in the background. The background "
         "stays exactly as it is in the first frame for the whole clip. The same young woman as the first frame: {person}, {outfit} that stays "
         "exactly as it is for the whole clip; {hair} {hands}{camera} {expression}\n"
         "\n"
         "[0.0s-4.0s] Start: exactly the first frame. Action: keeping her hands perfectly still the young woman with a light, bright voice and a "
         "natural Taiwanese Mandarin accent (S1) says in Mandarin Chinese, as one continuous sentence in a single breath with no pause in the "
         "middle, once only: {line}. End: {end}\n"
         "[4.0s-5.1s] Start: as before. Action: {tail} End: unchanged, the final frame.\n"
         "\n"
         "{sound}")

# ── 口白腳本 ─────────────────────────────────────────────────────────────────
VOICEOVER = "{first}\n{second}\n"

# ── 頭髮 ─────────────────────────────────────────────────────────────────────
QWEN_HAIR = "Her hair looks neat and natural."
VIDEO_HAIR = "her hair stays exactly as in the first frame."

# ── 機位（每鏡一個，F1–F5）────────────────────────────────────────────────────
FRAMING = {
    "F1": ("Medium close shot from chest height; her body is turned about thirty degrees to her left while her face turns back toward the "
           "camera; her head takes about one quarter of the picture height, with a clear band of background above her hair about one sixth of "
           "the picture.",
           "Medium close shot from chest height, her body turned slightly to one side and her face toward the camera"),
    "F2": ("Medium shot from chest height facing her straight on, showing her from the waist up as she sits; her head takes about one fifth "
           "of the picture height, with a clear band of background above her hair about one sixth of the picture.",
           "Medium shot from chest height showing her from the waist up as she sits"),
    "F3": ("Close-up from eye level facing her straight on, showing her from the upper chest up; her head takes about one third of the "
           "picture height, with a clear band of background above her hair about one sixth of the picture.",
           "Close-up from eye level showing her from the upper chest up"),
    "F4": ("Medium shot from chest height, a little farther away, showing her from the waist up; her body is turned about thirty degrees to "
           "her right while her face turns back toward the camera; her head takes about one fifth of the picture height, with a clear band of "
           "background above her hair about one sixth of the picture.",
           "Medium shot from chest height showing her from the waist up, her body turned slightly to one side and her face toward the camera"),
    "F5": ("Medium shot from slightly below her eye level facing her straight on, showing her from the waist up as she sits; her head takes "
           "about one fifth of the picture height, with a clear band of background above her hair about one sixth of the picture.",
           "Medium shot from slightly below eye level showing her from the waist up as she sits"),
}

# ── 表情（Qwen, H3）；⛔ fed up／annoyed（會翻白眼，CLAUDE #99；test_golden.py 會檢查）──
EXPRESSION = {
    "uneasy": ("Her expression: she looks a little uncomfortable, lips pressed together, eyebrows relaxed; she is NOT smiling.",
               "She keeps looking straight into the camera lens the whole time, her eyes steady on the lens, with a slightly uncomfortable "
               "look, speaking in a calm, slightly flat voice; her forehead stays smooth."),
    "pleased": ("She is pleased with an easy smile, looking straight at the camera.",
                "She keeps looking straight into the camera lens with an easy, pleased smile for the whole clip."),
    "bright": ("She smiles brightly at the camera.",
               "She keeps looking straight into the camera lens and smiles brightly for the whole clip."),
    "warm": ("She smiles brightly at the camera.",   # legacy 鏡 5 的 Qwen 表情就是 bright，只有 H3 用 warm
             "She keeps looking straight into the camera lens and smiles warmly for the whole clip."),
}
BANNED_EXPRESSION_WORDS = ("fed up", "annoyed")

# ── 口白會被 H3 唸歪、一律擋下的字（legacy shot2() 的 assert 清單，CLAUDE #98）───────
#    ⚠️ 這份比 rules/寫腳本規則.md 二.5 短；要加字請先確認不會擋掉現有規格檔（見 out/工單1-報告.md）。
BANNED_LINE_WORDS = ("連結", "漬", "髮質", "每次", "罐", "凍")


# ════════════════════════════════════════════════════════════════════════════
# 2. 五鏡結構（每支片固定：痛點 → 揭曉 → 特點 → 感受 → 叫人買）
#    hand：Qwen 首幀裡拿商品的手（None＝這鏡不拿商品）；point：另一隻手食指朝下
# ════════════════════════════════════════════════════════════════════════════
SHOT_PLAN = (
    {"framing": "F1", "expression": "uneasy",  "hand": None,    "point": False, "smile_at_end": False},   # 1 痛點
    {"framing": "F2", "expression": "pleased", "hand": "right", "point": False, "smile_at_end": True},    # 2 揭曉商品
    {"framing": "F3", "expression": "pleased", "hand": "left",  "point": False, "smile_at_end": True},    # 3 特點
    {"framing": "F4", "expression": "bright",  "hand": "right", "point": False, "smile_at_end": True},    # 4 用起來的感受
    {"framing": "F5", "expression": "warm",    "hand": "left",  "point": True,  "smile_at_end": True},    # 5 叫人買
)
OTHER_HAND = {"left": "right", "right": "left"}


# ════════════════════════════════════════════════════════════════════════════
# 3. 規格檔
# ════════════════════════════════════════════════════════════════════════════
class SpecError(ValueError):
    """規格檔寫錯（缺欄位、型別不對、台詞有禁字……）。"""


# 欄位名 → (必填?, 型別)；欄位說明見 spec/README.md
_TOP_KEYS = {"package": (True, str), "shot_prefix": (True, str), "person": (True, dict), "product": (True, dict),
             "shots": (True, list), "shot1_hair_qwen": (False, str), "note": (False, str)}
_PERSON_KEYS = {"qwen": (True, str), "video": (True, str), "id": (False, str), "note": (False, str)}
_PRODUCT_KEYS = {"word": (True, str), "look_qwen": (True, str), "look_video": (True, str), "size": (True, str),
                 "grip": (False, str), "note": (False, str)}
_SHOT_KEYS = {"scene_qwen": (True, str), "scene_video": (True, str), "anchors": (True, str), "outfit": (True, str),
              "line": (True, list), "note": (False, str)}
_TYPE_NAME = {str: "字串", dict: "物件 {…}", list: "陣列 […]"}


def _check_keys(obj, allowed, where):
    if not isinstance(obj, dict):
        raise SpecError("%s 應該是物件 {…}" % where)
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise SpecError("%s 有不認得的欄位：%s（拼錯？可用的欄位：%s）" % (where, "、".join(unknown), "、".join(allowed)))
    for key, (required, typ) in allowed.items():
        if key not in obj:
            if required:
                raise SpecError("%s 缺欄位 %s" % (where, key))
            continue
        if not isinstance(obj[key], typ):
            raise SpecError("%s.%s 應該是%s" % (where, key, _TYPE_NAME[typ]))
        if typ is str and not obj[key].strip():
            raise SpecError("%s.%s 是空的（選填欄位不用就整個拿掉）" % (where, key))


def validate_spec(spec):
    """檢查規格檔結構；有問題丟 SpecError（訊息講清楚是哪個欄位）。"""
    _check_keys(spec, _TOP_KEYS, "規格檔")
    _check_keys(spec["person"], _PERSON_KEYS, "person")
    _check_keys(spec["product"], _PRODUCT_KEYS, "product")
    if any(c in spec["package"] for c in "/\\:") or spec["package"] in (".", ".."):
        raise SpecError("package 只能是資料夾名稱，不能帶路徑：%r" % spec["package"])
    if not spec["shot_prefix"].isalnum():
        raise SpecError("shot_prefix 只能用英數字（會變成檔名）：%r" % spec["shot_prefix"])
    if len(spec["shots"]) != len(SHOT_PLAN):
        raise SpecError("shots 要剛好 %d 鏡（現在 %d 鏡）" % (len(SHOT_PLAN), len(spec["shots"])))
    for i, shot in enumerate(spec["shots"], 1):
        where = "shots[%d]（第 %d 鏡）" % (i - 1, i)
        _check_keys(shot, _SHOT_KEYS, where)
        line = shot["line"]
        if not (isinstance(line, list) and len(line) == 2 and all(isinstance(s, str) and s.strip() for s in line)):
            raise SpecError("%s.line 要是兩個半句，例如 [\"加班到半夜好餓\", \"外面的店都關了\"]" % where)
        for half in line:
            if half != half.strip() or "\n" in half or "，" in half:
                raise SpecError("%s.line 的半句不要帶前後空白、換行或全形逗號（逗號由程式加）：%r" % (where, half))
        for w in BANNED_LINE_WORDS:
            if w in line[0] + line[1]:
                raise SpecError("%s 口白有會唸歪的字「%s」（CLAUDE #98）" % (where, w))


def load_spec(path):
    """讀 spec/<商品>.json 並檢查。"""
    with open(path, encoding="utf-8") as f:
        try:
            spec = json.load(f)
        except json.JSONDecodeError as e:
            raise SpecError("%s 不是合法 JSON：%s" % (path, e))
    validate_spec(spec)
    return spec


# ════════════════════════════════════════════════════════════════════════════
# 4. 組字串（純函式）
# ════════════════════════════════════════════════════════════════════════════
def shot_ids(spec):
    return ["%s%d" % (spec["shot_prefix"], i) for i in range(1, len(SHOT_PLAN) + 1)]


def render_shot(spec, index):
    """第 index 鏡（0 起算）→ {"qwen": 首幀指令, "video": 影片提示詞, "voiceover": 口白腳本}。"""
    plan = SHOT_PLAN[index]
    shot = spec["shots"][index]
    person, product = spec["person"], spec["product"]
    framing_q, framing_h = FRAMING[plan["framing"]]
    expr_q, expr_h = EXPRESSION[plan["expression"]]
    side = plan["hand"]
    if side is None:
        hands_q, hands_h, keep = QWEN_NO_HANDS, VIDEO_NO_HANDS, VIDEO_KEEP
    else:
        hands_q = QWEN_HOLD.format(look=product["look_qwen"], side=side, grip=product.get("grip", DEFAULT_GRIP), size=product["size"])
        hands_h = VIDEO_HOLD.format(look=product["look_video"])
        keep = VIDEO_KEEP_WITH_PROP.format(prop=product["word"])
        if plan["point"]:
            hands_q += QWEN_POINT.format(side=OTHER_HAND[side])
            hands_h += VIDEO_POINT
    hair_q = spec["shot1_hair_qwen"] if index == 0 and "shot1_hair_qwen" in spec else QWEN_HAIR
    first, second = shot["line"]

    qwen = QWEN.format(body=QWEN_BODY, person=person["qwen"], scene=shot["scene_qwen"], place_rule=QWEN_PLACE_RULE, framing=framing_q,
                       outfit=shot["outfit"], hair=hair_q, hands=hands_q.strip(), hands_rule=QWEN_HANDS_RULE, expression=expr_q)
    camera = VIDEO_CAMERA.format(framing=framing_h, anchors=shot["anchors"], keep=keep)
    smile = plan["smile_at_end"]
    video = VIDEO.format(scene=shot["scene_video"], person=person["video"], outfit=shot["outfit"], hair=VIDEO_HAIR, hands=hands_h,
                         camera=camera, expression=expr_h, line=VIDEO_LINE.format(first=first, second=second),
                         end=VIDEO_END_SMILE if smile else VIDEO_END_CALM, tail=VIDEO_TAIL_SMILE if smile else VIDEO_TAIL_CALM,
                         sound=VIDEO_SOUND)
    return {"qwen": qwen, "video": video, "voiceover": VOICEOVER.format(first=first, second=second)}


def render_package(spec):
    """整支片 → {相對路徑: 檔案內容}（15 個檔）。"""
    files = {}
    for i, sid in enumerate(shot_ids(spec)):
        out = render_shot(spec, i)
        files["_qwen指令/q_%s.txt" % sid] = out["qwen"]
        files["prompt_%sD.txt" % sid] = out["video"]
        files["口白腳本_%sD.txt" % sid] = out["voiceover"]
    return files


# ════════════════════════════════════════════════════════════════════════════
# 5. 寫檔
# ════════════════════════════════════════════════════════════════════════════
def write_package(spec, out_dir):
    """把整支片寫進 out_dir（資料夾不存在會自己建）；UTF-8、\\n 換行、無 BOM。回傳寫出的檔案路徑。"""
    written = []
    for rel, text in render_package(spec).items():
        path = os.path.join(out_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        written.append(path)
    return written
