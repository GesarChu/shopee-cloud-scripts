# 工單 #4 樣本說明（fixtures/）

全部來自 2026-10-06 純商品片批次（1080×1920、30fps）。沒有任何憑證或個資。

## motion/（鏡頭縮放閃爍）
- `kw_old_zoompan_crop.mp4`：舊做法（2× 放大＋ffmpeg zoompan，整數像素跳格）成片的商品區裁切（crop=500:900:290:500，前 6 秒）。王看到「字會略帶閃爍」。
- `kw_new_kbrender_crop.mp4`：同一支改 `kb-render`（PIL 浮點 box 逐格 LANCZOS）後的同一塊。王看過「可以了」。
- 本機量法（numpy）：每格轉灰階、相鄰格平均絕對差。舊：`1.7 1.4 1.4 1.8 0.9 1.4 1.4 1.8 …`（0.9↔1.8 規律擺盪、週期 4–5 格；靜止段每 5 格跳 4.6）；新：`1.1 1.1 1.1 1.0 1.0 …`（平、相鄰差平均 0.02）。

## ghost/（盒子別面長假字）
- `ww_shot4_fail.jpg`：味王咖哩牛肉調理包第 4 鏡成片格（貼回正面標籤之後）。**盒頂有模型畫的、倒過來的假字**（王：「11 秒的時候上方的字變雙重的」）→ 要判 FAIL。
- `ww_shot4_before_paste.jpg`：同一格貼回之前。`後 − 前` 有差異的區域＝貼回的標籤框（label 框）。
- `kw_shot1_pass.jpg`／`kw_shot1_before_paste.jpg`：花王洗髮精（瓶）→ PASS。
- `ax_shot2_pass.jpg`／`ax_shot2_before_paste.jpg`：一匙靈補充包（立袋）→ PASS（袋子上方有真品原本就有的小字「請倒入瓶裝使用」與虛線，那是貼回的真品標籤的一部分，不算假字）。

## whole/（整支換真品看起來假＋浮）
- `tn_shot1_scene_before_paste.jpg`：東尼玉米片第 1 鏡，模型畫的場景（盒子是模型畫的、字錯）。
- `tn_alpha.png`：真品去背照（正面偏 3/4 角，四周留透明邊）。
- `tn_shot1_current_paste_fake.jpg`：現行 whole 引擎把真品貼上去的結果。王：「商品太假跟浮空」——透視跟桌面對不上、沒有接觸陰影、照片比場景銳利、色溫不同。
