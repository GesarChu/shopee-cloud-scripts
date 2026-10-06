# -*- coding: utf-8 -*-
"""CPU whole-product replacement. No generative model, no network, no overwrites.
py -3 tools/prod-replace.py scene.png out.png --ref cutout.png --json metrics.json
A reference must be a single complete opaque product, front view, real RGBA cutout.
Reference-review JSON is optional; a rejection is binding and SHA-bound.
All transforms are similarities, even when SIFT seeds the localization.
Thresholds are fixed, not CLI-tunable. See RULES and the ticket test report.
"""
import argparse, hashlib, io, json, math, os, sys, time, uuid
from pathlib import Path
import numpy as np
import cv2
from PIL import Image

RULES = {
    "bottom_gap_fraction": .015,       # ticket: 1.5% of observed product height
    "remnant_width_fraction": .06,     # ticket: 6% of observed product width
    "rotation_degrees": 8.,            # ticket: contour similarity only
    "white_keep_min": .92,             # ticket: brightest source 1% retention
    "angle_deviation_max": 5.,         # existing prodfilm RULE / ticket
    "opposite_side_ratio_max": 1.10,   # existing prodfilm RULE / ticket
    "ref_solidity_min": .88,           # existing prodfilm RULE, not relaxed
    "iou_min": .88,                    # engineering safety gate, not learned fit
    "remnant_area_fraction": .12,      # at most two narrow 6% side strips
    "boundary_edge_min": .45,          # reject textureless pseudo-segmentation
    "candidate_margin_min": .025,      # near-tied distant objects => ambiguous
    "appearance_correlation_min": .20, # independent image evidence, rejects flat decoys
}
KEYS=("method iou bottom_gap_px remnant_px remnant_max_width_px scale rot_deg "
      "ref_solidity paste_box quad scene_size white_keep").split()

class Reject(Exception): pass

def fingerprint(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1048576),b""): h.update(b)
    return h.hexdigest()

def box(mask):
    ys,xs=np.where(mask)
    if not len(xs): raise Reject("找不到完整商品輪廓")
    return np.array([xs.min(),ys.min(),xs.max()+1,ys.max()+1],int)

def largest(mask,seed=None):
    n,lab,st,c=cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
    if n<2: raise Reject("場景分割沒有商品")
    scores=st[1:,cv2.CC_STAT_AREA].astype(float)
    if seed is not None:
        for i in range(1,n): scores[i-1]=np.sum(seed & (lab==i))
    idx=int(np.argmax(scores))+1
    if scores[idx-1]<30: raise Reject("商品分割沒有可靠的前景種子")
    return lab==idx

def solidity(mask):
    xy=np.argwhere(mask)[:,::-1].astype(np.int32)
    if len(xy)<100: raise Reject("真品去背後面積太小")
    return min(1.,float(len(xy)/max(cv2.contourArea(cv2.convexHull(xy)),1)))

def load_reference(path,met,review=None):
    met["ref_sha256"]=fingerprint(path)
    if review:
        rec=json.loads(Path(review).read_text(encoding="utf-8-sig"))
        if rec.get("ref_sha256")!=met["ref_sha256"]:
            raise Reject("真品照前檢指紋不符，請重新確認照片")
        met["reference_review"]=rec
        if rec.get("accepted") is not True:
            raise Reject(rec.get("reason","真品照不合用"))
    with Image.open(path) as im:
        if im.mode!="RGBA": raise Reject("真品照不合用：需單一正面、已去背RGBA PNG")
        rgba=np.array(im)
    mask=rgba[...,3]>128
    if (rgba[...,3]<16).mean()<.03: raise Reject("真品照沒有有效透明背景")
    if ((rgba[...,3]>16)&(rgba[...,3]<240)).mean()>.15:
        raise Reject("真品照半透明區域過大，不能可靠地替換")
    n,lab,st,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
    count=sum(a>=.03*mask.sum() for a in st[1:,cv2.CC_STAT_AREA])
    met["ref_solidity"]=solidity(mask);met["ref_objects"]=int(count)
    if count!=1: raise Reject("真品照不合用：含多個分離物件")
    if met["ref_solidity"]<RULES["ref_solidity_min"]:
        raise Reject("真品照實心度低於0.88：去背缺損、透明或多物件")
    bb=box(mask);x0,y0,x1,y1=bb
    if min(x0,y0,rgba.shape[1]-x1,rgba.shape[0]-y1)<1:
        raise Reject("真品照商品碰到圖片邊界，無法確認完整輪廓")
    met["ref_size"]=[int(rgba.shape[1]),int(rgba.shape[0])]
    met["ref_box"]=bb.tolist()
    return rgba[y0:y1,x0:x1].copy()

def edge_support(rgb,mask):
    grey=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    edge=cv2.Canny(cv2.GaussianBlur(grey,(3,3),0),35,100)>0
    nearby=cv2.dilate(edge.astype(np.uint8),np.ones((7,7),np.uint8))>0
    boundary=(cv2.dilate(mask.astype(np.uint8),np.ones((3,3),np.uint8))-
              cv2.erode(mask.astype(np.uint8),np.ones((3,3),np.uint8)))>0
    return float(nearby[boundary].mean()) if boundary.any() else 0.

def sane_bbox(bb,shape,aspect):
    x0,y0,x1,y1=map(int,bb);h,w=shape[:2];bw=x1-x0;bh=y1-y0
    return (bw>=25 and bh>=90 and bh<h*.82 and bw<w*.75
            and .62<=(bw/max(bh,1))/aspect<=1.55
            and x0>2 and y0>2 and x1<w-2 and y1<h-2)

def sift_seed(scene,ref):
    a=ref[...,3]/255.
    comp=(ref[...,:3]*a[...,None]+128*(1-a[...,None])).astype(np.uint8)
    sf=min(1.,850/max(comp.shape[:2]))
    r=cv2.resize(comp,None,fx=sf,fy=sf,interpolation=cv2.INTER_AREA)
    alpha=cv2.resize(ref[...,3],(r.shape[1],r.shape[0]))
    sift=cv2.SIFT_create(nfeatures=5000)
    k1,d1=sift.detectAndCompute(cv2.cvtColor(r,cv2.COLOR_RGB2GRAY),(alpha>200).astype(np.uint8)*255)
    k2,d2=sift.detectAndCompute(cv2.cvtColor(scene,cv2.COLOR_RGB2GRAY),None)
    if d1 is None or d2 is None:return None
    matches=cv2.BFMatcher().knnMatch(d1,d2,k=2)
    good=[p[0] for p in matches if len(p)==2 and p[0].distance<.72*p[1].distance]
    if len(good)<12:return None
    src=np.float32([k1[m.queryIdx].pt for m in good])/sf
    dst=np.float32([k2[m.trainIdx].pt for m in good])
    M,inl=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,
        ransacReprojThreshold=2.5,maxIters=3000,confidence=.995,refineIters=10)
    if M is None or inl is None:return None
    good_src=src[inl.ravel()>0];ni=len(good_src)
    if ni<12 or ni/len(good)<.45:return None
    if np.ptp(good_src[:,1])<.22*ref.shape[0] or np.ptp(good_src[:,0])<.22*ref.shape[1]:return None
    rot=math.degrees(math.atan2(M[1,0],M[0,0]))
    if abs(rot)>RULES["rotation_degrees"]:return None
    warped=cv2.warpAffine(ref[...,3],M,(scene.shape[1],scene.shape[0]))>128
    if not warped.any():return None
    return {"box":box(warped),"prior":warped,"method":"sift","sift_inliers":ni,"seed_matrix":M}

def proposals(scene,ref):
    h,w=scene.shape[:2];aspect=ref.shape[1]/ref.shape[0]
    lab=cv2.cvtColor(scene,cv2.COLOR_RGB2LAB).astype(np.float32)
    ref_lab=cv2.cvtColor(ref[...,:3],cv2.COLOR_RGB2LAB).astype(np.float32)
    pix=ref_lab[ref[...,3]>240]
    if len(pix)>18000:pix=pix[::max(1,len(pix)//18000)]
    cv2.setRNGSeed(1206)
    _,_,centers=cv2.kmeans(pix,3,None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,30,.15),3,cv2.KMEANS_PP_CENTERS)
    # Color is a proposal only; independent GrabCut + edge evidence decide.
    distances=[]
    for c in centers:
        distances.append(np.sqrt(.10*(lab[...,0]-c[0])**2+
                                 (lab[...,1]-c[1])**2+(lab[...,2]-c[2])**2))
    dist=np.min(distances,axis=0)
    masks=[]
    for threshold in (8,13,20):
        m=(dist<threshold).astype(np.uint8)
        m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        masks.append(m)
    gray=cv2.cvtColor(scene,cv2.COLOR_RGB2GRAY)
    e=cv2.Canny(cv2.GaussianBlur(gray,(3,3),0),35,100)
    masks.append(cv2.morphologyEx(e,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8)))
    candidates=[]
    for im in masks:
        contours,_=cv2.findContours(im,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area=cv2.contourArea(c)
            if not .005*h*w<area<.5*h*w:continue
            x,y,bw,bh=cv2.boundingRect(c);bb=np.array([x,y,x+bw,y+bh])
            if not sane_bbox(bb,scene.shape,aspect):continue
            if any(np.max(np.abs(bb-p["box"]))<15 for p in candidates):continue
            fill=np.zeros((h,w),np.uint8);cv2.drawContours(fill,[c],-1,1,-1)
            extent=area/(bw*bh)
            if extent<.45:continue
            shape_error=abs(math.log((bw/bh)/aspect))
            candidates.append({"box":bb,"prior":fill>0,"method":"contour","rank":shape_error+.5*(1-extent)})
    candidates.sort(key=lambda p:p["rank"])
    return candidates[:16]

def template_proposals(scene,ref):
    """Low-frequency RGB matching only proposes locations, never supplies masks."""
    sf=.4;h,w=scene.shape[:2]
    small=cv2.resize(scene,None,fx=sf,fy=sf,interpolation=cv2.INTER_AREA)
    small=cv2.GaussianBlur(small,(5,5),0)
    rh,rw=ref.shape[:2];out=[]
    a=ref[...,3]/255.;mean=np.mean(ref[...,:3][a>.9],axis=0)
    comp=(ref[...,:3]*a[...,None]+mean*(1-a[...,None])).astype(np.uint8)
    for height in np.linspace(h*.16,h*.68,16):
        hh=int(height*sf);ww=int(hh*rw/rh)
        if ww<12 or ww>=small.shape[1]-3 or hh>=small.shape[0]-3:continue
        tpl=cv2.resize(comp,(ww,hh),interpolation=cv2.INTER_AREA)
        tpl=cv2.GaussianBlur(tpl,(5,5),0)
        mask=cv2.resize(ref[...,3],(ww,hh),interpolation=cv2.INTER_AREA)
        score=cv2.matchTemplate(small,tpl,cv2.TM_CCOEFF_NORMED,mask=mask)
        score=np.nan_to_num(score,nan=-1,posinf=-1,neginf=-1)
        _,val,_,loc=cv2.minMaxLoc(score)
        if val<.40:continue
        x,y=loc;bb=np.array([x/sf,y/sf,(x+ww)/sf,(y+hh)/sf]).round().astype(int)
        prior=np.zeros((h,w),np.uint8)
        x0,y0,x1,y1=bb
        tpl_mask=cv2.resize((ref[...,3]>128).astype(np.uint8),(x1-x0,y1-y0))
        # Rounded small-image coordinates may exceed the source canvas by 1px.
        # Clip destination AND the corresponding source offsets, without stretching.
        xa,ya,xb,yb=max(0,x0),max(0,y0),min(w,x1),min(h,y1)
        if xa>=xb or ya>=yb:continue
        prior[ya:yb,xa:xb]=tpl_mask[ya-y0:yb-y0,xa-x0:xb-x0]
        bb=np.array([xa,ya,xb,yb])
        if not any(np.max(np.abs(bb-p["box"]))<20 for p in out):
            out.append({"box":bb,"prior":prior>0,"method":"contour","rank":1-float(val)})
    out.sort(key=lambda p:p["rank"])
    return out[:6]

def segment(scene,p,ref):
    x0,y0,x1,y1=map(int,p["box"]);bh=y1-y0;bw=x1-x0;h,w=scene.shape[:2]
    mx=max(12,int(bw*.18));my=max(12,int(bh*.08))
    xa=max(0,x0-mx);ya=max(0,y0-my);xb=min(w,x1+mx);yb=min(h,y1+my)
    crop=scene[ya:yb,xa:xb].copy()
    prior=p["prior"][ya:yb,xa:xb].astype(np.uint8)
    gc=np.full(prior.shape,cv2.GC_PR_BGD,np.uint8)
    gc[prior>0]=cv2.GC_PR_FGD
    sure=cv2.erode(prior,np.ones((9,9),np.uint8))
    # Hard FG only central core, no template-enforced outline.
    sure[:int(prior.shape[0]*.2)]=0;sure[int(prior.shape[0]*.9):]=0
    if sure.sum()<40:raise Reject("商品定位缺少可靠核心")
    gc[sure>0]=cv2.GC_FGD
    # Real alpha holes supply tiny BG seeds, not a forced final silhouette.
    ra=(ref[...,3]>128).astype(np.uint8)
    n,holes,hs,hc=cv2.connectedComponentsWithStats(1-ra,8)
    for i in range(1,n):
        hx,hy,hw,hh,area=hs[i]
        if hx<=0 or hy<=0 or hx+hw>=ra.shape[1] or hy+hh>=ra.shape[0] or area<16:continue
        cx,cy=hc[i]
        xx=round(x0+cx/ra.shape[1]*bw-xa);yy=round(y0+cy/ra.shape[0]*bh-ya)
        if 3<xx<gc.shape[1]-3 and 3<yy<gc.shape[0]-3:gc[yy-2:yy+3,xx-2:xx+3]=cv2.GC_BGD
    gc[:3]=0;gc[-3:]=0;gc[:,:3]=0;gc[:,-3:]=0
    bg=np.zeros((1,65),np.float64);fg=np.zeros((1,65),np.float64)
    cv2.grabCut(cv2.cvtColor(crop,cv2.COLOR_RGB2BGR),gc,None,bg,fg,4,cv2.GC_INIT_WITH_MASK)
    m=(gc==1)|(gc==3);m=largest(m,sure>0)
    # Fill small interior print holes; preserve upper handle openings.
    inv=(~m).astype(np.uint8);n,l,st,_=cv2.connectedComponentsWithStats(inv,8)
    for i in range(1,n):
        x,y,ww,hh,area=st[i]
        if x>0 and y>0 and x+ww<inv.shape[1] and y+hh<inv.shape[0] and y>m.shape[0]*.25 and area<m.sum()*.04:m[l==i]=1
    out=np.zeros(scene.shape[:2],bool);out[ya:yb,xa:xb]=m
    bb=box(out)
    if np.any(bb[:2]<=0) or bb[2]>=w-1 or bb[3]>=h-1:raise Reject("商品輪廓接觸畫面邊界")
    return out

def similarity_fit(ref_mask,target):
    bb=box(target);x0,y0,x1,y1=map(int,bb);bw=x1-x0;bh=y1-y0
    # Work in a local ROI, not repeated full-frame warps.
    pad=max(18,int(bw*.2));xa=max(0,x0-pad);ya=max(0,y0-pad)
    xb=min(target.shape[1],x1+pad);yb=min(target.shape[0],y1+pad)
    local=target[ya:yb,xa:xb]
    rh,rw=ref_mask.shape;center=(rw/2,rh/2)
    best=None
    for deg in np.arange(-8.,8.1,2.):
        base=cv2.getRotationMatrix2D(center,float(deg),1.)
        corners=np.float64([[0,0,1],[rw,0,1],[rw,rh,1],[0,rh,1]])@base.T
        span=np.ptp(corners,axis=0)
        scale0=bh/span[1]
        for sf in (.92,.96,1.,1.04,1.08):
            scale=scale0*sf;rot=cv2.getRotationMatrix2D(center,float(deg),scale)
            q=np.float64([[0,0,1],[rw,0,1],[rw,rh,1],[0,rh,1]])@rot.T
            for dx in (-.025,0.,.025):
                for dy in (-.01,0.,.01):
                    M=rot.copy()
                    M[0,2]+=(x0+x1)/2-q[:,0].mean()+dx*bw-xa
                    M[1,2]+=y1-q[:,1].max()+dy*bh-ya
                    wm=cv2.warpAffine(ref_mask.astype(np.uint8),M,(xb-xa,yb-ya),flags=cv2.INTER_NEAREST)>0
                    un=np.count_nonzero(wm|local)
                    iou=np.count_nonzero(wm&local)/max(1,un)
                    if best is None or iou>best[0]:
                        Mg=M.copy();Mg[:,2]+=[xa,ya];best=(iou,Mg,float(deg),float(scale))
    return best

def image_bytes(arr,fmt="PNG"):
    b=io.BytesIO()
    Image.fromarray(arr).save(b,format=fmt,**({"quality":95} if fmt=="JPEG" else {}))
    return b.getvalue()

def json_bytes(obj):
    return (json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")

def exclusive(path,data):
    created=False
    try:
        with open(path,"xb") as f:
            created=True;f.write(data);f.flush();os.fsync(f.fileno())
    except Exception:
        if created:quarantine([Path(path)])
        raise

def quarantine(paths):
    if not paths:return
    dest=paths[0].parent/"_作廢"/(time.strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8])
    dest.mkdir(parents=True,exist_ok=False)
    for p in paths:
        if p.exists():p.rename(dest/p.name)

def comparison(scene,out,ref,mask):
    bb=box(mask);x0,y0,x1,y1=bb
    x0=max(0,x0-40);y0=max(0,y0-40);x1=min(scene.shape[1],x1+40);y1=min(scene.shape[0],y1+40)
    left=scene[y0:y1,x0:x1];middle=out[y0:y1,x0:x1];height=left.shape[0]
    a=ref[...,3:4]/255.
    comp=(ref[...,:3]*a+235*(1-a)).astype(np.uint8)
    width=max(1,round(ref.shape[1]*height/ref.shape[0]))
    right=np.asarray(Image.fromarray(comp).resize((width,height),Image.Resampling.LANCZOS))
    return np.concatenate([left,middle,right],axis=1)

def bottom_anchor(alpha0,M,size,obs,met):
    """Repair a rejected bottom alignment by translating the WHOLE reference.
    The observed mask and all gates stay unchanged. Use actual raster support,
    not the enclosing rectangle's bottom corner (wrong for rounded/rotated cans).
    No alpha clipping or reference cropping is permitted here.
    """
    alpha=cv2.warpAffine(alpha0,M,size,flags=cv2.INTER_LINEAR)
    sb=box(obs);pb=box(alpha>.5);support=box(alpha>0)
    ph=int(sb[3]-sb[1]);signed=int(pb[3]-sb[3])
    spill=float(alpha[sb[3]:].max(initial=0))
    before_mass=float(alpha.sum(dtype=np.float64))
    before_support=int(np.count_nonzero(alpha>0))
    repair=spill>.10 or abs(signed)>ph*RULES["bottom_gap_fraction"]
    dy=int(sb[3]-support[3]) if repair else 0
    original=M.copy()
    if dy:
        M=M.copy();M[1,2]+=dy
        alpha=cv2.warpAffine(alpha0,M,size,flags=cv2.INTER_LINEAR)
    after_support=box(alpha>0)
    mass=float(alpha.sum(dtype=np.float64))
    retained=(int(np.count_nonzero(alpha>0))==before_support and
              abs(mass-before_mass)<=max(1e-5,before_mass*1e-7))
    met.update(bottom_anchor_applied=bool(dy),bottom_anchor_shift_y_px=float(dy),
        bottom_anchor_reason=("shadow-spill" if spill>.10 else "bottom-gap") if repair else "not-needed",
        bottom_gap_before_anchor_px=float(abs(signed)),
        bottom_signed_gap_before_anchor_px=float(signed),
        paste_bottom_before_anchor_px=int(pb[3]),
        support_bottom_before_anchor_px=int(support[3]),
        support_bottom_after_anchor_px=int(after_support[3]),
        observed_bottom_anchor_px=int(sb[3]),
        shadow_alpha_before_anchor=spill,
        shadow_alpha_after_anchor=float(alpha[sb[3]:].max(initial=0)),
        transform_before_anchor=original.tolist(),
        reference_alpha_mass_before=before_mass,reference_alpha_mass_after=mass,
        reference_support_pixels_before=before_support,
        reference_support_pixels_after=int(np.count_nonzero(alpha>0)),
        reference_alpha_preserved=bool(retained))
    if not retained:raise Reject("底邊微調裁到真品，停止輸出")
    return M,alpha

def old_bottom_rim(obs,allfg):
    """Old bottom exposed below the new footprint, per shared image column.
    Entire unmatched side columns are handled by the existing remnant gate.
    This is measured BEFORE inpainting, not claimed visual removal success.
    """
    has=obs.any(axis=0)&allfg.any(axis=0)
    ob=obs.shape[0]-1-np.argmax(obs[::-1],axis=0)
    nb=allfg.shape[0]-1-np.argmax(allfg[::-1],axis=0)
    heights=np.where(has,np.maximum(ob-nb,0),0)
    rim=obs&has[None,:]&(np.arange(obs.shape[0])[:,None]>nb[None,:])
    return rim,int(heights.max(initial=0))

def replace(scene,ref,candidate,met):
    H,W=scene.shape[:2]
    sc=np.asarray(Image.fromarray(scene).resize((W*2,H*2),Image.Resampling.LANCZOS))
    mh,mw=sc.shape[:2]
    M=candidate["M"]*2
    alpha0=ref[...,3].astype(np.float32)/255.
    obs=cv2.resize(candidate["mask"].astype(np.uint8),(mw,mh),interpolation=cv2.INTER_NEAREST)>0
    M,alpha=bottom_anchor(alpha0,M,(mw,mh),obs,met)
    # Premultiplied RGB avoids white/black matte bleeding at alpha boundaries.
    premul=ref[...,:3].astype(np.float32)*alpha0[...,None]
    pr=cv2.warpAffine(premul,M,(mw,mh),flags=cv2.INTER_LANCZOS4)
    rgb=np.clip(pr/np.maximum(alpha[...,None],1e-6),0,255)
    fg=alpha>.5
    sb=box(obs);pb=box(fg);ph=int(sb[3]-sb[1]);pw=int(sb[2]-sb[0])
    allfg=alpha>.01
    iou=np.count_nonzero(obs&fg)/max(1,np.count_nonzero(obs|fg))
    residual=obs & ~allfg
    distance=cv2.distanceTransform((~fg).astype(np.uint8),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
    width=float(distance[residual].max()) if residual.any() else 0.
    bottom_gap=abs(int(pb[3])-int(sb[3]))
    rh,rw=ref.shape[:2]
    quad=np.float64([[0,0,1],[rw,0,1],[rw,rh,1],[0,rh,1]])@M.T
    edges=np.roll(quad,-1,axis=0)-quad;length=np.linalg.norm(edges,axis=1)
    ang=[]
    for i in range(4):
        u=-edges[i-1];v=edges[i]
        ang.append(math.degrees(math.acos(np.clip(np.dot(u,v)/(np.linalg.norm(u)*np.linalg.norm(v)),-1,1))))
    ratio=max(length[0]/length[2],length[2]/length[0],length[1]/length[3],length[3]/length[1])
    # Clean under antialias edges too; leaving the old object there makes a halo.
    # 2 source-pixel antialias halo becomes 4px on the required 2x canvas.
    erase=(cv2.dilate(obs.astype(np.uint8),np.ones((9,9),np.uint8))>0)&(alpha<.999)
    # Never inpaint the ground/contact shadow below the observed lowest product row.
    erase[sb[3]:]=False
    # Width is the actual erased region, including the antialias safety ring.
    width=float(distance[erase].max()) if erase.any() else 0.
    rim,rim_height=old_bottom_rim(obs,allfg)
    met.update(old_bottom_rim_height_px=rim_height,
        old_bottom_opaque_strip_height_px=max(0,int(sb[3]-pb[3])),
        old_bottom_support_strip_height_px=max(0,int(sb[3]-box(allfg)[3])),
        bottom_signed_gap_after_anchor_px=float(int(pb[3]-sb[3])),
        old_bottom_rim_pixels_before_cleanup=int(rim.sum()),
        old_bottom_rim_unhandled_pixels=int((rim&~erase).sum()),
        old_bottom_rim_measurement="貼回對齊後、清除前：共同欄位中，舊商品底端低於新貼片alpha>0.01底端的最大高度；完整側邊殘留仍由原殘邊門檻判定")
    met.update(method=candidate["method"],iou=float(iou),bottom_gap_px=float(bottom_gap),
        remnant_px=int(erase.sum()),remnant_raw_px=int(residual.sum()),
        remnant_max_width_px=width,scale=float(np.hypot(M[0,0],M[1,0])),
        rot_deg=float(candidate["rot"]),paste_box=pb.tolist(),quad=quad.tolist(),
        scene_size=[mw,mh],scene_product_box=sb.tolist(),scene_product_height_px=ph,
        scene_product_width_px=pw,edge_support=candidate["edge_support"],
        sift_inliers=candidate["sift_inliers"],appearance_correlation=candidate["appearance_correlation"],
        angle_dev=float(max(abs(np.array(ang)-90))),
        side_ratio=float(ratio),transform=M.tolist(),
        estimated_1080_scale=float(np.hypot(M[0,0],M[1,0])*1080/mw),
        source_resolution_warning=bool(np.hypot(M[0,0],M[1,0])*1080/mw>1.30),
        thresholds={"bottom_gap_px":ph*.015,"remnant_max_width_px":pw*.06,
                    "remnant_area_px":int(obs.sum()*.12),**RULES})
    failures=[]
    if iou<RULES["iou_min"]:failures.append("轮廓IoU %.3f < 0.88"%iou)
    if bottom_gap>ph*.015:failures.append("底邊差距 %.1f > %.1fpx"%(bottom_gap,ph*.015))
    if width>pw*.06:failures.append("殘邊最寬 %.1f > %.1fpx"%(width,pw*.06))
    if erase.sum()>obs.sum()*.12:failures.append("要補掉的殘邊面積超過商品面積12%")
    if abs(candidate["rot"])>8.000001:failures.append("旋轉超過8度")
    if met["angle_dev"]>5 or ratio>1.10:failures.append("商品四角或對邊形變")
    if min(pb[0],pb[1])<2 or pb[2]>mw-2 or pb[3]>mh-2:failures.append("貼片超出畫面")
    # Ground preservation includes antialias tails. Reject rather than clip product.
    if alpha[sb[3]:].max(initial=0)>.10:
        failures.append("貼片透明邊緣伸入原接觸陰影下方")
    met["geometry_failures"]=failures
    if failures:raise Reject("；".join(failures).replace("轮","輪"))
    clean=cv2.inpaint(sc,erase.astype(np.uint8)*255,3,cv2.INPAINT_TELEA) if erase.any() else sc.copy()
    # One broad scalar, shared across RGB. No local text-sensitive/per-channel tint.
    core=(alpha>.99)&obs
    lum=np.array([.2126,.7152,.0722])
    wr=rgb@lum;sr=sc.astype(np.float32)@lum
    sigma=max(30.,pw*.20)
    weighted=core.astype(np.float32)
    den=cv2.GaussianBlur(weighted,(0,0),sigma)
    ls=cv2.GaussianBlur(sr*weighted,(0,0),sigma)/np.maximum(den,1e-6)
    lr=cv2.GaussianBlur(wr*weighted,(0,0),sigma)/np.maximum(den,1e-6)
    gain=float(np.clip(np.median(ls[core]/np.maximum(lr[core],1)),.98,1.02))
    shaded=np.clip(rgb*gain,0,255)
    rendered=np.rint(clean*(1-alpha[...,None])+shaded*alpha[...,None]).clip(0,255).astype(np.uint8)
    source_lum=ref[...,:3].astype(np.float32)@lum;opaque=alpha0>.99
    threshold=np.percentile(source_lum[opaque],99)
    bright=(opaque&(source_lum>=threshold)).astype(np.float32)
    mapped=cv2.warpAffine(bright,M,(mw,mh),flags=cv2.INTER_LINEAR)
    valid=(mapped>.01)&(alpha>.99)
    if valid.sum()<8:raise Reject("真品最亮1%投影後不足8像素，無法可靠驗證白字")
    weights=mapped[valid]
    before=float(source_lum[bright>0].mean())
    after=float(np.average((rendered.astype(np.float32)@lum)[valid],weights=weights))
    keep=after/max(before,1)
    met.update(white_keep=keep,white_before=before,white_after=after,
        white_source_count=int(bright.sum()),white_output_count=int(valid.sum()),
        brightness_gain=gain,light_sigma_px=sigma,
        white_measurement="真品opaque像素最亮1%，仿射投影權重加權輸出亮度／原始最亮1%平均亮度（包含重採樣損失）",
        shadow_below_unchanged=bool(np.array_equal(rendered[sb[3]:],sc[sb[3]:])))
    if keep<RULES["white_keep_min"]:raise Reject("白字亮度保留 %.4f < 0.92"%keep)
    if not met["shadow_below_unchanged"]:raise Reject("原接觸陰影下方像素被修改")
    return rendered,comparison(sc,rendered,ref,obs|allfg)

def diagnostics(directory,stem,scene,candidate):
    d=Path(directory);d.mkdir(parents=True,exist_ok=True)
    mask=candidate["mask"].astype(np.uint8)*255
    overlay=scene.copy()
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay,contours,-1,(255,0,255),2)
    exclusive(d/(stem+"_定位.jpg"),image_bytes(overlay,"JPEG"))
    exclusive(d/(stem+"_模型輪廓.png"),image_bytes(mask))

def main(argv=None):
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    if hasattr(sys.stderr,"reconfigure"):sys.stderr.reconfigure(encoding="utf-8",errors="replace")
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scene");ap.add_argument("out");ap.add_argument("--ref",required=True)
    ap.add_argument("--json",required=True,help="量測JSON，失敗也寫，未量得欄位為null")
    ap.add_argument("--ref-review",help="可選人工真品照前檢JSON（ref_sha256,accepted,reason）；不能繞過自檢")
    ap.add_argument("--diagnostics",help="可選定位與輪廓診斷資料夾，不是通過的成品圖")
    args=ap.parse_args(argv)
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    cv2.setNumThreads(2);cv2.ocl.setUseOpenCL(False);cv2.setRNGSeed(1206)
    out=Path(args.out);jp=Path(args.json)
    cmp=out.with_name(out.stem+"_對照.jpg")
    met={k:None for k in KEYS}
    met.update(status="FAILED",reasons=[],version="1.3",tool_sha256=fingerprint(__file__),
               rules=RULES,quality_acceptance="PENDING_HUMAN_QA")
    started=time.monotonic();committed=[]
    targets=[out,cmp,jp];inputs=[Path(args.scene),Path(args.ref)]
    if args.ref_review:inputs.append(Path(args.ref_review))
    try:
        norm=lambda p:os.path.normcase(str(p.resolve()))
        if len(set(map(norm,targets)))!=len(targets) or set(map(norm,targets))&set(map(norm,inputs)):
            raise Reject("輸出路徑重複或指向輸入原件")
        if any(p.exists() for p in targets):raise Reject("輸出已存在，不覆寫；請使用新檔名")
        if out.suffix.lower()!=".png":raise Reject("輸出圖副檔名必須是.png")
        if not all(p.parent.is_dir() for p in targets):raise Reject("輸出資料夾不存在")
        with Image.open(args.scene) as im:scene=np.array(im.convert("RGB"))
        met["input_scene_size"]=[int(scene.shape[1]),int(scene.shape[0])]
        met["scene_size"]=[int(scene.shape[1]*2),int(scene.shape[0]*2)]
        met["scene_sha256"]=fingerprint(args.scene)
        ref=load_reference(args.ref,met,args.ref_review)
        candidate=find_product(scene,ref,met)
        if args.diagnostics:diagnostics(args.diagnostics,out.stem,scene,candidate)
        rendered,comparison_image=replace(scene,ref,candidate,met)
        met.update(status="VERIFIED_COMPLETE",reasons=[],seconds=round(time.monotonic()-started,3),
                   output=str(out),comparison=str(cmp))
        for p,data in ((out,image_bytes(rendered)),(cmp,image_bytes(comparison_image,"JPEG"))):
            exclusive(p,data);committed.append(p)
        met["output_sha256"]=fingerprint(out);met["comparison_sha256"]=fingerprint(cmp)
        exclusive(jp,json_bytes(met));committed.append(jp)
        print("OK %s IoU=%.3f 底差=%.1fpx 殘邊=%.1fpx 白字=%.3f 倍率=%.3f 旋轉=%.2f"%
            (met["method"],met["iou"],met["bottom_gap_px"],met["remnant_max_width_px"],
             met["white_keep"],met["scale"],met["rot_deg"]))
        return 0
    except (Reject,OSError,ValueError,cv2.error) as exc:
        if committed:quarantine(committed)
        reason=(str(exc) if isinstance(exc,Reject) else "處理失敗："+str(exc)).replace("\r"," ").replace("\n"," ")
        met.update(status="FAILED",reasons=[reason],seconds=round(time.monotonic()-started,3))
        # Never overwrite an input, prior certificate, or colliding image on error.
        safe=(jp.parent.is_dir() and not jp.exists() and
              os.path.normcase(str(jp.resolve())) not in {os.path.normcase(str(p.resolve())) for p in inputs}
              and jp not in (out,cmp))
        if safe:
            try:exclusive(jp,json_bytes(met))
            except (OSError,ValueError):pass
        print("XX "+reason)
        return 2

def find_product(scene,ref,met):
    seed=sift_seed(scene,ref)
    props=([seed] if seed is not None else [])+template_proposals(scene,ref)+proposals(scene,ref)
    viable=[]
    for p in props:
        try:
            m=segment(scene,p,ref)
            if not sane_bbox(box(m),scene.shape,ref.shape[1]/ref.shape[0]):continue
            support=edge_support(scene,m)
            if support<RULES["boundary_edge_min"]:continue
            fit=similarity_fit(ref[...,3]>128,m)
            iou,M,rot,scale=fit
            rg=cv2.cvtColor(ref[...,:3],cv2.COLOR_RGB2GRAY).astype(np.float32)
            warped=cv2.warpAffine(rg,M,(scene.shape[1],scene.shape[0]))
            footprint=cv2.warpAffine(ref[...,3],M,(scene.shape[1],scene.shape[0]))>245
            region=cv2.erode((footprint&m).astype(np.uint8),np.ones((7,7),np.uint8))>0
            sg=cv2.cvtColor(scene,cv2.COLOR_RGB2GRAY).astype(np.float32)
            aa=cv2.GaussianBlur(warped,(0,0),3)[region]
            bb=cv2.GaussianBlur(sg,(0,0),3)[region]
            if len(aa)<60 or min(aa.std(),bb.std())<1.:continue
            corr=float(np.corrcoef(aa,bb)[0,1])
            if not np.isfinite(corr) or corr<RULES["appearance_correlation_min"]:continue
            candidate={"iou":iou,"M":M,"rot":rot,"scale":scale,"mask":m,
                       "method":p["method"],"edge_support":support,
                       "appearance_correlation":corr,
                       "sift_inliers":p.get("sift_inliers",0)}
            viable.append(candidate)
            if p["method"]=="sift" and iou>=RULES["iou_min"]:return candidate
        except (Reject,cv2.error):continue
    if not viable:raise Reject("無法可靠分割／定位商品；請換更清楚、角度一致的場景")
    viable.sort(key=lambda c:c["iou"],reverse=True);best=viable[0]
    met["best_candidate_iou"]=best["iou"]
    # Return poor fits too, so the fixed final gate can report all geometry metrics.
    b0=box(best["mask"]);c0=(b0[:2]+b0[2:])/2
    for other in viable[1:]:
        b1=box(other["mask"]);c1=(b1[:2]+b1[2:])/2
        if np.linalg.norm(c1-c0)>.25*(b0[3]-b0[1]) and best["iou"]-other["iou"]<RULES["candidate_margin_min"]:
            raise Reject("有兩個相近匹配商品，定位不唯一")
    return best

if __name__=="__main__":sys.exit(main())
