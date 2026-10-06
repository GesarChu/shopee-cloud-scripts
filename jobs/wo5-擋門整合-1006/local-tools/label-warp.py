# -*- coding: utf-8 -*-
"""label-warp.py — 場景圖裡 Qwen 畫的商品，用 SIFT 特徵對位把「真品去背照」整片貼回去（2026-10-05 第 33 棒）
為什麼：Qwen 會把包裝字畫錯（MILBON 200g→210g、小字變亂碼），蝦皮把圖內文字錯誤算「品質不佳的虛擬內容」（CLAUDE #111）；
        label-replace.py 要一張一張量框，這支自動找位置：真品照 ↔ 場景圖特徵點配對 → RANSAC 單應矩陣 → 透視貼上。
用法：py -3 tools/label-warp.py <場景.png> <輸出.png> --ref <真品去背 RGBA png> [--erode 3] [--keep-skin] [--min-inliers 25] [--region x0,y0,x1,y1]
  --keep-skin：手拿圖用，貼片範圍內的膚色像素保留原圖（手指壓在商品上不會被蓋掉）
  --region：只在這個範圍找商品（場景裡有兩個商品或配對亂跳時用）
輸出：<輸出.png>＋<輸出>_對照.jpg（左原圖、中貼完、右真品；綠框＝貼片位置）；配對點不夠或形狀怪就不寫輸出、印 XX、回傳 2
⚠️ 只適合正面、平的或微弧的包裝（瓶身、軟管、盒子正面）；側面／大角度轉的會對不上，就別用這張場景
"""
import argparse, sys
import numpy as np, cv2
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
def _tone_ssim(before, after, mask):
    # RGB SSIM on actual 1:1 label pixels, 11x11 Gaussian window.
    b=before.astype(np.float32);a=after.astype(np.float32)
    filt=lambda x:cv2.GaussianBlur(x,(11,11),1.5)
    mb=filt(b);ma=filt(a)
    vb=filt(b*b)-mb*mb;va=filt(a*a)-ma*ma;cov=filt(a*b)-ma*mb
    score=((2*ma*mb+6.5025)*(2*cov+58.5225))/((ma*ma+mb*mb+6.5025)*(va+vb+58.5225))
    return float(np.clip(score[mask],-1,1).mean())


def _align_label_lowfreq(W, S, alpha, mask):
    # Fixed preprocessing, no CLI opt-out. Over-limit regions keep the old rendering.
    info={'enabled':True,'method':'masked-gaussian-additive-r1','sigma_px':12.0,
          'rgb_shift_limit':25.0,'soft_reject_from':20.0,'lowfreq_gain':[1.0,1.0,1.0],
          'ssim_floor':0.98,'applied':False,'reason':'insufficient_support'}
    if np.count_nonzero(mask)<500:return W,info
    ys,xs=np.where(mask);h,w=mask.shape
    y0,y1=max(0,int(ys.min())-64),min(h,int(ys.max())+65)
    x0,x1=max(0,int(xs.min())-64),min(w,int(xs.max())+65)
    region=np.s_[y0:y1,x0:x1]
    Wr=W[region];Sr=S[region];ar=alpha[region];mr=mask[region]
    weight=(ar>.98).astype(np.float32)
    blur=lambda x:cv2.GaussianBlur(x,(0,0),12.0)
    den=blur(weight)
    if np.count_nonzero(weight)<200:return W,info
    low_w=blur(Wr*weight[...,None])/np.maximum(den[...,None],1e-6)
    low_s=blur(Sr*weight[...,None])/np.maximum(den[...,None],1e-6)
    requested=low_s-low_w
    magnitude=np.max(np.abs(requested),axis=2)
    t=np.clip((magnitude-20.0)/5.0,0.0,1.0)
    confidence=np.where(magnitude<=20.0,1.0,np.where(magnitude<25.0,.5*(1.0+np.cos(np.pi*t)),0.0)).astype(np.float32)
    confidence[den<1e-5]=0
    delta=requested*confidence[...,None]
    # H=Wr-low_w is retained; only its low-frequency component gets an additive shift.
    candidate=np.clip(Wr+delta,0,255).astype(np.float32)
    old=(Sr*(1-ar[...,None])+Wr*ar[...,None]).astype(np.uint8)
    new=(Sr*(1-ar[...,None])+candidate*ar[...,None]).astype(np.uint8)
    score=_tone_ssim(old,new,mr)
    lb0=cv2.GaussianBlur(Sr.astype(np.uint8),(0,0),10).astype(np.float32)
    old_lf=float(np.abs(cv2.GaussianBlur(old,(0,0),10).astype(np.float32)-lb0).mean(2)[mr].mean())
    new_lf=float(np.abs(cv2.GaussianBlur(new,(0,0),10).astype(np.float32)-lb0).mean(2)[mr].mean())
    info.update(requested_shift_min=[float(x) for x in requested[mr].min(0)],
                requested_shift_max=[float(x) for x in requested[mr].max(0)],
                over_limit_fraction=float((magnitude[mr]>=25).mean()),
                candidate_delta_abs_max=float(np.abs(delta[mr]).max()),
                ssim_rgb_1to1=score,lowfreq_before=old_lf,lowfreq_candidate=new_lf,
                applied_delta_abs_max=0.0)
    if score<.98:
        info['reason']='text_ssim_below_0.98';return W,info
    if new_lf>=old_lf:
        info['reason']='no_lowfreq_improvement';return W,info
    result=W.copy();result[region]=candidate
    info.update(applied=True,reason='within_limits_and_text_preserved',
                applied_delta_abs_max=float(np.abs(delta[mr]).max()))
    return result,info

ap = argparse.ArgumentParser()
ap.add_argument("scene"); ap.add_argument("out"); ap.add_argument("--ref", required=True)
ap.add_argument("--erode", type=int, default=3); ap.add_argument("--keep-skin", action="store_true")
ap.add_argument("--min-inliers", type=int, default=25); ap.add_argument("--region", default="")
ap.add_argument("--inset", default="0.10,0.06,0.06", help="只貼真品照中間這塊：左右各、上、下 的比例（避開真品照的反光邊、封口、瓶蓋）；例 MILBON 軟管 0.12,0.07,0.15")
ap.add_argument("--feather", type=float, default=3.0)
ap.add_argument("--text-only", action="store_true", help="只換深色字（透明／漸層瓶整塊貼會出方塊時用；先補掉原圖的深色筆畫再疊真品的字）")
ap.add_argument("--hi", type=float, default=97,help="對色亮點分位；深色瓶字面積小（hetras 沐浴乳）用 99.5，不然會抓到瓶肩反光、字變灰")
ap.add_argument("--light-sigma", type=float, default=14.0, help="2026-10-06：大範圍光影的模糊半徑。放大 2 倍的場景用 14 太小，會把模型畫的字的位置也當成光影、把貼回去的白字壓成灰色；2 倍場景用 60 左右")
ap.add_argument("--json", default="", help="2026-10-06：把貼片位置與「貼壞了沒」的量測數字寫成 JSON（給商品片擋門用）")
a = ap.parse_args()

sc = np.asarray(Image.open(a.scene).convert("RGB"))
rf = np.asarray(Image.open(a.ref).convert("RGBA"))
rgb_r, al_r = rf[..., :3], rf[..., 3]
# 真品貼在中灰底上找特徵（白底會讓白瓶邊緣沒特徵）
comp = (rgb_r * (al_r[..., None] / 255.0) + 128 * (1 - al_r[..., None] / 255.0)).astype(np.uint8)
H0, W0 = sc.shape[:2]
# 真品放大到跟場景商品差不多的尺度再找（場景商品通常 250–700px 高）
s_up = max(1.0, 900.0 / max(comp.shape[:2]))
comp_u = cv2.resize(comp, None, fx=s_up, fy=s_up, interpolation=cv2.INTER_CUBIC)
mask_r = cv2.resize(al_r, None, fx=s_up, fy=s_up, interpolation=cv2.INTER_LINEAR)
mask_full = mask_r.copy()   # 找特徵用整支；貼的時候只貼中間
ix, it, ib = [float(v) for v in a.inset.split(",")]
ys_, xs_ = np.where(mask_r > 128); bx0, bx1, by0, by1 = xs_.min(), xs_.max(), ys_.min(), ys_.max()
rect = np.zeros_like(mask_r); bw, bh = bx1 - bx0, by1 - by0
rect[int(by0 + it * bh):int(by1 - ib * bh), int(bx0 + ix * bw):int(bx1 - ix * bw)] = 255
mask_paste = np.minimum(mask_r, rect)
g1 = cv2.cvtColor(comp_u, cv2.COLOR_RGB2GRAY); g2 = cv2.cvtColor(sc, cv2.COLOR_RGB2GRAY)
m2 = None
if a.region:
    x0, y0, x1, y1 = [int(v) for v in a.region.split(",")]
    m2 = np.zeros_like(g2); m2[y0:y1, x0:x1] = 255
sift = cv2.SIFT_create(nfeatures=6000)
k1, d1 = sift.detectAndCompute(g1, (mask_full > 128).astype(np.uint8) * 255)
k2, d2 = sift.detectAndCompute(g2, m2)
if d1 is None or d2 is None or len(k1) < 10 or len(k2) < 10:
    print("XX 特徵點太少", len(k1 or []), len(k2 or [])); sys.exit(2)
mt = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
good = [m for m, n in (p for p in mt if len(p) == 2) if m.distance < 0.75 * n.distance]
if len(good) < a.min_inliers:
    print("XX 好的配對只有 %d" % len(good)); sys.exit(2)
src = np.float32([k1[m.queryIdx].pt for m in good]); dst = np.float32([k2[m.trainIdx].pt for m in good])
Hm, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
ni = int(inl.sum()) if inl is not None else 0
if Hm is None or ni < a.min_inliers:
    print("XX RANSAC 內點只有 %d（配對 %d）" % (ni, len(good))); sys.exit(2)
h1, w1 = g1.shape
quad = cv2.perspectiveTransform(np.float32([[0, 0], [w1, 0], [w1, h1], [0, h1]]).reshape(-1, 1, 2), Hm).reshape(-1, 2)
area = cv2.contourArea(quad.astype(np.float32)); convex = cv2.isContourConvex(quad.astype(np.float32))
sx = np.linalg.norm(quad[1] - quad[0]) / w1; sy = np.linalg.norm(quad[3] - quad[0]) / h1
if not convex or area < 2000 or not (0.5 < sx / sy < 2.0):
    print("XX 對位形狀怪（convex=%s area=%d 長寬比例=%.2f）" % (convex, area, sx / sy)); sys.exit(2)
warp = cv2.warpPerspective(comp_u, Hm, (W0, H0), flags=cv2.INTER_LANCZOS4)
wa = cv2.warpPerspective(mask_paste, Hm, (W0, H0), flags=cv2.INTER_LINEAR)
if a.erode: wa = cv2.erode(wa, np.ones((a.erode * 2 + 1,) * 2, np.uint8))
wa = cv2.GaussianBlur(wa, (0, 0), a.feather).astype(np.float32) / 255.0
m = wa > 0.5
if m.sum() < 500:
    print("XX 貼片範圍太小"); sys.exit(2)
# 顏色：兩點對齊（暗 10%／亮 97% 分位，每通道線性）；只用原圖不是膚色的像素（10/5 手拿圖膚色算進來會把字染紫；深色瓶只對白點會讓瓶身變色、字變灰）
W = warp.astype(np.float32); S = sc.astype(np.float32)
ycc0 = cv2.cvtColor(sc, cv2.COLOR_RGB2YCrCb)
skin0 = (ycc0[..., 1] > 135) & (ycc0[..., 1] < 180) & (ycc0[..., 2] > 85) & (ycc0[..., 2] < 135)
wb = m & ~skin0
if wb.sum() < 200: wb = m
bright = np.median(S[wb].mean(1)) > 170          # 白／淺色包裝：只對白點（每通道乘倍數，墨色等比例＝色相不跑；兩點對色會把 MILBON 深紫字染成紫紅）
for c in range(3):
    if bright:
        g = np.percentile(S[..., c][wb], 90) / max(np.percentile(W[..., c][wb], 90), 1.0)
        W[..., c] = W[..., c] * np.clip(g, 0.6, 1.4)
    else:                                         # 深色瓶（NARUKO 綠、hetras 琥珀）：兩點對齊
        wl, wh = np.percentile(W[..., c][wb], [10, a.hi]); sl, sh = np.percentile(S[..., c][wb], [10, a.hi])
        g = np.clip((sh - sl) / max(wh - wl, 1.0), 0.6, 1.6)
        W[..., c] = (W[..., c] - wl) * g + sl
# 大範圍光影：原圖亮度／貼片亮度的模糊比例（0.75–1.25）
ls = cv2.GaussianBlur(S.mean(2), (0, 0), a.light_sigma); lw = cv2.GaussianBlur(W.mean(2), (0, 0), a.light_sigma)
ratio = np.clip(ls / np.maximum(lw, 1), 0.75, 1.25)
W = np.clip(W * ratio[..., None], 0, 255)
alpha = wa.copy()
if a.keep_skin:
    ycc = cv2.cvtColor(sc, cv2.COLOR_RGB2YCrCb)
    skin = ((ycc[..., 1] > 135) & (ycc[..., 1] < 180) & (ycc[..., 2] > 85) & (ycc[..., 2] < 135))
    # 10/5：琥珀色瓶（hetras）整支落在膚色範圍 ⇒ 另外要求「跟貼片（對過色的真品）顏色差很多」才算手指
    skin = (skin & (np.linalg.norm(S - W, axis=2) > 45)).astype(np.uint8)
    skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    skin = cv2.dilate(skin, np.ones((3, 3), np.uint8)).astype(np.float32)   # 10/5：5×5 會在指尖周圍留一圈原圖暗邊
    skin = cv2.GaussianBlur(skin, (0, 0), 1.0)
    alpha = alpha * (1 - skin)
if a.text_only:
    # 10/5 晚：透明／漸層瓶（Lador 精華油）整塊貼會看出方塊 ⇒ 只換深色字：先把原圖貼片範圍內的深色筆畫補掉，再只疊真品的深色字
    gS = S.mean(2); gW = W.mean(2)
    dS = (cv2.GaussianBlur(gS, (0, 0), 6) - gS > 22) & m
    dS = cv2.dilate(dS.astype(np.uint8), np.ones((5, 5), np.uint8))
    Sc = cv2.inpaint(sc, dS, 4, cv2.INPAINT_TELEA).astype(np.float32)
    valid = cv2.warpPerspective(np.full(g1.shape, 255, np.uint8), Hm, (W0, H0))   # 真品照範圍外是黑的，邊緣會被當成字畫出一條黑線
    valid = cv2.erode(valid, np.ones((21, 21), np.uint8)).astype(np.float32) / 255.0
    ta = np.clip((cv2.GaussianBlur(gW, (0, 0), 6) - gW - 8) / 30.0, 0, 1) * wa * valid
    ta = cv2.GaussianBlur(ta.astype(np.float32), (0, 0), 0.6)
    if a.keep_skin: ta = ta * (1 - skin); Sc = np.where(skin[..., None] > 0.5, S, Sc)
    S = np.where(m[..., None], Sc, S); alpha = ta
W, tone_shift = _align_label_lowfreq(W, S, alpha, m)
out = (S * (1 - alpha[..., None]) + W * alpha[..., None]).astype(np.uint8)
Image.fromarray(out).save(a.out)
# 對照圖
vis = out.copy(); cv2.polylines(vis, [quad.astype(np.int32)], True, (0, 255, 0), 2)
ys, xs = np.where(m); pad = 40
y0, y1, x0, x1 = max(0, ys.min() - pad), min(H0, ys.max() + pad), max(0, xs.min() - pad), min(W0, xs.max() + pad)
crop = lambda im: im[y0:y1, x0:x1]
refv = cv2.resize(comp, (int(comp.shape[1] * (y1 - y0) / comp.shape[0]), y1 - y0))
row = np.concatenate([crop(sc), crop(vis), refv], 1)
Image.fromarray(row).save(a.out[:-4] + "_對照.jpg", quality=90)
# 2026-10-06 第 34 棒：貼完自己量「貼壞了沒」（批次實測：程式回報成功的 12 款裡人眼看有 5 款是貼壞的——真品照不是單一商品正面、或白瓶去背被吃掉）
#   低頻差＝整塊顏色／形狀有沒有被換掉（只換字的話應該很小）；四角偏／對邊比＝貼片歪不歪。數字只量不擋，擋門在 tools/prodfilm-gate.py
_lb0 = cv2.GaussianBlur(sc, (0, 0), 10).astype(np.float32); _lb1 = cv2.GaussianBlur(out, (0, 0), 10).astype(np.float32)
_dd = np.abs(_lb1 - _lb0).mean(2)[m]
def _ang(p_, q_, r_):
    v1, v2 = p_ - q_, r_ - q_
    return float(np.degrees(np.arccos(np.clip(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9), -1, 1))))
_qd = quad.astype(np.float64)
_angs = [_ang(_qd[(i - 1) % 4], _qd[i], _qd[(i + 1) % 4]) for i in range(4)]
_e = [float(np.linalg.norm(_qd[(i + 1) % 4] - _qd[i])) for i in range(4)]
_solid = float((al_r > 128).sum()) / max(1.0, float(cv2.contourArea(cv2.convexHull(np.argwhere(al_r > 128)[:, ::-1].astype(np.int32)))))
met = {"lowfreq_mean": round(float(_dd.mean()), 2), "lowfreq_p95": round(float(np.percentile(_dd, 95)), 2), "angle_dev": round(max(abs(x - 90) for x in _angs), 1),
       "side_ratio": round(max(_e[0] / _e[2], _e[2] / _e[0], _e[1] / _e[3], _e[3] / _e[1]), 3), "scale_x": round(float(sx), 3), "scale_y": round(float(sy), 3),
       "ref_solidity": round(_solid, 3), "inliers": ni, "matches": len(good), "quad": [[round(float(v), 1) for v in p_] for p_ in _qd],
       "paste_box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())], "scene_size": [int(W0), int(H0)],
       # s_up＝真品照先放大幾倍才拿去對位；真品原始像素→場景像素的倍率＝s_up×scale（給 tools/prodfilm.py 算「成片上真品照被放大幾倍」，太大＝真品照太小、貼回去會糊）
       "s_up": round(float(s_up), 4), "ref_size": [int(rf.shape[1]), int(rf.shape[0])]}
met['tone_shift'] = tone_shift
if a.json:
    import json as _json
    open(a.json, "w", encoding="utf-8").write(_json.dumps(met, ensure_ascii=False))
print("OK 內點 %d／配對 %d、貼片 %dx%d px、對照圖 %s｜低頻差 %.1f（95%% %.1f）、四角偏 %.1f 度、對邊比 %.2f、真品實心度 %.2f" % (ni, len(good), x1 - x0, y1 - y0, a.out[:-4] + "_對照.jpg", met["lowfreq_mean"], met["lowfreq_p95"], met["angle_dev"], met["side_ratio"], met["ref_solidity"]))
