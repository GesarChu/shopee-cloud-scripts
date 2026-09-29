# 商品規格檔 `spec/<商品>.json`

一個商品（一支 5 鏡的片）一個 JSON 檔。`make.py` 讀它，用 `genlib.py` 寫出 15 個檔：

```
python make.py spec/<商品>.json --out out/<包名>
python tools/script-lint.py out/<包名>/口白腳本_*D.txt
```

| 產出 | 給誰 |
|---|---|
| `_qwen指令/q_<鏡>.txt` | Qwen-Image 首幀（image 1＝人物照、image 2＝商品照） |
| `prompt_<鏡>D.txt` | MiniMax H3 影片提示詞 |
| `口白腳本_<鏡>D.txt` | 兩個半句各一行，驗片比對用 |

`<鏡>`＝`shot_prefix`＋鏡號，例如 `tt1`…`tt5`。

範例：[`TTL花雕雞麵.json`](TTL花雕雞麵.json)、[`歐萊德咖啡因洗髮精.json`](歐萊德咖啡因洗髮精.json)。

---

## 規格檔只寫「這個商品不一樣的地方」

下面這些**每支片都一樣**，寫在 `genlib.py` 的 `SHOT_PLAN`／文字模板裡，規格檔改不到：

| 鏡 | 任務 | 機位 | 表情（Qwen／H3） | Qwen 首幀的手 | H3 提示詞的手 |
|---|---|---|---|---|---|
| 1 | 痛點 | F1 胸口高度、半側身（往她的左） | 有點不舒服、不笑 | 兩手垂在畫面外 | 手垂在身側不動 |
| 2 | 揭曉商品 | F2 正面、腰上、坐姿 | 滿意的淺笑 | 右手拿商品 | `in one hand` |
| 3 | 特點 | F3 眼睛高度近景、上胸以上 | 滿意的淺笑 | 左手拿商品 | `in one hand` |
| 4 | 用起來的感受 | F4 遠一點、腰上、半側身（往她的右） | 燦笑 | 右手拿商品 | `in one hand` |
| 5 | 叫人買 | F5 略低於眼睛、腰上、坐姿 | 燦笑／H3 寫 warmly | 左手拿商品（`cta: "point"` 才加右手食指朝下） | `in one hand`（`cta: "point"` 才加 `her other hand` 食指朝下） |

**4 鏡結構**（`"structure": "4"`，**2026-09-29 起 API 那半用這個**）：1 痛點（F1 空手）→ 2 揭曉＋特點（F2 右手拿、第二半句蓋在段板上）→ 3 用起來的感受（F3 左手拿）→ 4 叫人買（F4 右手拿）。每鏡口白**最多 17 字**、全片**至少 60 字**（程式會擋；叫人買那鏡短一點沒關係）、H3 照舊 124 格（5.1 秒）、講話段 `[0.0s-4.2s]`。4 鏡 × 16 字 ≈ 64 字 ≈ 15.5 秒。

**3 鏡結構**（`"structure": "3"`，2026-09-29 起測試；王：「如果劇情順暢應該 3 鏡就可以，因為才 15 秒」）：

| 鏡 | 任務 | 機位 | 表情 | Qwen 首幀的手 |
|---|---|---|---|---|
| 1 | 痛點 | F1 半側身（往她的左） | 有點不舒服、不笑 | 兩手垂在畫面外 |
| 2 | 揭曉商品＋特點（第二半句蓋在段板上） | F3 眼睛高度近景 | 滿意的淺笑 | 右手拿商品 |
| 3 | 用起來的感受＋叫人買 | F4 遠一點、半側身（往她的右） | 燦笑／H3 寫 warmly | 左手拿商品 |

- 每鏡口白**最多 22 字**、全片**至少 60 字**（兩個半句加起來；程式會擋）＝每鏡講約 5 秒；H3 提示詞時間碼是 `[0.0s-5.6s]` 講、`[5.6s-6.5s]` 安靜。
- ⚠️ **H3 要生 156 格（6.5 秒）**：`py -3 tools/rh-batch.py <清單> --length 156`（不加＝124 格 5.1 秒，講不完）。
- 🔬 9/29 12:2x 實測 1 支（NIVEA nvt2API1，19 字）：6.5 秒一支 67 幣；4.5 秒就講完、後面多講 4 個聽不懂的字（字數關 FAIL）；不推近、不燒字 ⇒ **改用 4 鏡**，3 鏡留著不當主力。
- 為什麼不能 3 鏡 × 5 秒：一支片要 ≥15 秒、聲音從頭講到尾（段板蓋聲音），實測約每秒 4 字 ⇒ 全片要約 60 字，3 鏡就是每鏡約 20 字。

- 影片提示詞**一律不寫左右手**（圖片模型常把左右畫反，寫了會跟首幀打架）；Qwen 首幀仍寫左右。
- 第 2、5 鏡的機位句寫死「as she sits」——這兩鏡的場景句（`scene_qwen`）最好也寫 `She sits…`，不然首幀指令會同時叫她站又叫她坐（現有兩份 golden 的第 2 鏡就是這樣，見 `out/工單1-報告.md`）。

---

## 欄位

所有文字欄位都是**英文句子片段**，會被原樣塞進固定的英文模板裡，所以大小寫、句尾標點要照下表寫。
`note` 在任何物件裡都可以放（備註用，不會進輸出）。欄位名打錯、多寫、少寫都會直接報錯。

### 最上層

| 欄位 | 必填 | 說明 | 例 |
|---|---|---|---|
| `package` | ✅ | 包名＝`make.py` 沒給 `--out` 時的輸出資料夾 `out/<package>`。只能是資料夾名，不能帶 `/`。 | `"腳本備妥-TTL花雕雞麵-多鏡頭"` |
| `shot_prefix` | ✅ | 鏡頭編號前綴，只能英數字。會變成檔名 `q_tt1.txt`、`prompt_tt1D.txt`。**跟以前用過的前綴不要重複**。 | `"tt"` |
| `note` | | 備註：日期、商品全名、人物代號、商品參考圖檔名、從哪裡來。 | |
| `person` | ✅ | 人物，見下。 | |
| `product` | ✅ | 商品，見下。 | |
| `shot1_hair_qwen` | | 只改**第 1 鏡 Qwen 首幀**的頭髮句（痛點鏡要頭髮亂／扁時用）。不寫＝`Her hair looks neat and natural.`。完整句、句號結尾。對應 legacy `five2(hair1_q=…)`。 | `"Her hair is a little frizzy and puffy at the ends with a few flyaway strands, as if just blow-dried without any hair oil."` |
| `structure` | | `"5"`（預設）、`"4"` 或 `"3"`。見上面。 | `"4"` |
| `cta` | | 最後一鏡叫人買要不要另一隻手食指朝下：`"hold"`（**預設**，只拿著商品微笑講）或 `"point"`。王 9/29：「是不是一定要指下面」「整體自然順暢就好」＋當天兩支片錯在指下面那隻手（中指、手指像接上去）⇒ 新片用預設。9/29 以前的規格檔都補了 `"cta": "point"`，重跑產出跟以前一樣。 | `"hold"` |
| `shots` | ✅ | **幾鏡結構就剛好幾個**，依鏡號排，見下。 | |

### `person`（人物外觀，對應 legacy `who_q`／`who_h`）

| 欄位 | 必填 | 塞進哪裡 | 怎麼寫 |
|---|---|---|---|
| `id` | | 不進輸出 | 人物代號，例 `"B6"` |
| `qwen` | ✅ | Qwen：`…the same nose, mouth and jawline, ‹qwen›, the same makeup.` | 每一項用 `the same …` 開頭、逗號分隔、**不加句號**。只寫頭髮、眼鏡這類要保住的外觀（臉、身材已經在模板裡）。 |
| `video` | ✅ | H3：`The same young woman as the first frame: ‹video›, ‹outfit› that stays…` | 同樣的外觀，**不加 the same**、最後通常補 `light natural makeup`、不加句號。 |

### `product`（商品，對應 legacy `hold(desc_q, size, desc_h, grip)` 和 `prop_word`）

| 欄位 | 必填 | 塞進哪裡 | 怎麼寫 |
|---|---|---|---|
| `word` | ✅ | H3 鏡頭句：`her face and the ‹word› keep exactly the same size…`（鏡 2–5） | 一個名詞：`bag`、`bottle`、`tube`、`pouch`、`carton`… 要是畫面上真的有的東西。 |
| `look_qwen` | ✅ | Qwen：`She holds the ‹look_qwen›. She holds it upright in her right hand…` | 固定開頭 `<東西> from image 2, exactly its look: ` ＋外觀（形狀、顏色、印刷字的位置）。**不加句號**（模板會加）。 |
| `look_video` | ✅ | H3：`She holds the ‹look_video› upright in one hand in front of her upper chest…` | 短版外觀，一個名詞片語，例 `dark red and orange instant noodle multipack bag`。 |
| `size` | ✅ | Qwen：`It is its real size: ‹size›.` | 用身體當尺，例 `about as tall as her forearm from wrist to elbow`、`a little longer than her hand`。不加句號。 |
| `grip` | | Qwen：`…just below her collarbone, ‹grip›, the front facing the camera…` | 手怎麼握。不寫＝`four fingers wrapped around it and the thumb on the near side facing the camera`（圓罐、小瓶用這個）。袋子、軟包裝要改，例 `her fingers holding its lower half from the side and the thumb on the near side facing the camera`。 |

### `shots[]`（每鏡一個物件，對應 legacy `scenes`／`lines`／`outfits` 同一個位置）

| 欄位 | 必填 | 塞進哪裡 | 怎麼寫 |
|---|---|---|---|
| `line` | ✅ | 口白腳本（兩行）、H3：`<d>[Chinese] ‹前半句›，‹後半句›</d>` | **兩個字串**＝前半句、後半句。不要自己加逗號（程式會加全形「，」）、不要空白。 |
| `scene_qwen` | ✅ | Qwen：`First, the place: ‹scene_qwen› The background is clearly recognisable…` | **完整句、句號結尾**，`She stands…`／`She sits…` 開頭，寫地點、時間、背後有什麼。有螢幕／招牌就補 `no screen text is readable`／`no signs are readable`。 |
| `scene_video` | ✅ | H3 第一句：`‹scene_video›, continuing exactly from the first frame; …` | 同一個地點的名詞片語版，大寫開頭、**不加句號**。 |
| `anchors` | ✅ | H3 鏡頭句：`the frame edges stay on the same ‹anchors› for the whole clip` | 背景裡兩個好認的東西，例 `white cabinets and the stove`。 |
| `outfit` | ✅ | Qwen：`she now wears ‹outfit›.`；H3：`…, ‹outfit› that stays exactly as it is for the whole clip` | 名詞片語、`a plain …` 開頭、不加句號。每鏡要不同（規則三.7）。 |

---

## 程式會擋的東西（`make.py` 會直接報錯、不寫檔）

- 少欄位、多欄位（通常是拼錯）、型別不對、字串是空的。
- `shots` 數量跟 `structure` 不合；4 鏡每鏡超過 17 字、3 鏡超過 22 字、全片不到 60 字；`structure`／`cta` 不是認得的值；`line` 不是兩個半句；半句帶全形逗號、換行、前後空白。
- 口白含 H3 會唸歪的字：`連結 漬 髮質 每次 罐 凍`（`genlib.BANNED_LINE_WORDS`）。
  ⚠️ 這份清單比 `rules/寫腳本規則.md` 二.5 短（整、乾、囤、訂、結、殼、倒、重、痠、髮尾…都沒擋），寫台詞時還是要自己對規則檔，並跑 `tools/script-lint.py`。
- `make.py` 不准把 `--out` 指到 `golden/` 裡面。

## 寫新商品的步驟

1. 複製一份範例改名 `spec/<商品>.json`，改 `package`、`shot_prefix`、`note`。
2. `person` 換成這支片的人物；`product` 照商品參考圖寫外觀、尺寸、拿法。
3. 5 個 `shots` 依「痛點 → 揭曉 → 特點 → 感受 → 叫人買」寫台詞、場景、服裝（3 鏡結構：「痛點 → 揭曉＋特點 → 感受＋叫人買」）。
4. `python make.py spec/<商品>.json --out out/<包名>` → `python tools/script-lint.py out/<包名>/口白腳本_*D.txt`。
5. 打開 `out/<包名>/` 看一遍：Qwen 指令的站／坐跟機位對不對得上、場景句有沒有漏句號。
