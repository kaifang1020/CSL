# pick_ref.py — 从预处理好的人脸帧里,自动挑"最适合当参考脸"的候选。
# 打分维度(都用 face_alignment 68 点,GPU):
#   ① 正脸度  鼻尖到左右脸缘距离要对称(偏头则不对称)
#   ② 睁眼    EAR(眼纵横比)要高
#   ③ 闭嘴    内唇间距要小(张嘴的帧不适合当中性锚)
#   ④ 清晰    Laplacian 方差(运动模糊的帧要排除)
#   ⑤ 平视    眼睛中心与鼻尖的垂直关系(低头的帧扣分)
# 输出:分数最高的 N 帧 + 一张联系表(contact sheet)供人眼确认。
import argparse, glob, os, numpy as np, cv2

p = argparse.ArgumentParser()
p.add_argument('--frames', required=True)          # 预处理后的帧目录
p.add_argument('--out', default='results/ref_candidates.jpg')
p.add_argument('--topn', type=int, default=6)
p.add_argument('--stride', type=int, default=3)    # 每隔几帧评一次(省时间)
# ★帧范围:很多素材首尾有标题卡/烧录字幕(savannah 末尾 78s+ 有 "Now it is your turn"),
#   字幕压在嘴部会被误判成"完全闭嘴"并选中 → 参考脸带字 → 每一帧生成画面都带字。
p.add_argument('--start', type=int, default=0)     # 只考虑序号 >= start 的帧
p.add_argument('--end', type=int, default=10**9)   # 只考虑序号 <= end 的帧
args = p.parse_args()

import face_alignment
try: LT = face_alignment.LandmarksType.TWO_D
except AttributeError: LT = face_alignment.LandmarksType._2D
fa = face_alignment.FaceAlignment(LT, flip_input=False, device='cuda')

def ear(pts):                                       # eye aspect ratio
    a = np.linalg.norm(pts[1] - pts[5]); b = np.linalg.norm(pts[2] - pts[4])
    c = np.linalg.norm(pts[0] - pts[3]) + 1e-6
    return (a + b) / (2 * c)

def fnum(p):
    try: return int(''.join(ch for ch in os.path.basename(p) if ch.isdigit()) or -1)
    except ValueError: return -1
files = [f for f in sorted(glob.glob(os.path.join(args.frames, '*.jpg')))
         if args.start <= fnum(f) <= args.end][::args.stride]
print(f"评估 {len(files)} 帧(每 {args.stride} 帧取一)…")
rows = []
for f in files:
    img = cv2.imread(f)
    if img is None: continue
    out = fa.get_landmarks(img[:, :, ::-1])
    if not out: continue
    k = out[0].astype(np.float32)
    iod = np.linalg.norm(k[36:42].mean(0) - k[42:48].mean(0)) + 1e-6
    # ① 正脸:鼻尖(30)到左脸缘(0)/右脸缘(16)的水平距离比
    dl = abs(k[30, 0] - k[0, 0]); dr = abs(k[16, 0] - k[30, 0])
    frontal = min(dl, dr) / (max(dl, dr) + 1e-6)                  # 1=完全对称
    # ② 睁眼
    eyes = (ear(k[36:42]) + ear(k[42:48])) / 2
    # ③ 闭嘴(越小越好 → 取负)
    mouth = np.linalg.norm(k[62] - k[66]) / iod
    # ④ 清晰
    sharp = cv2.Laplacian(img, cv2.CV_64F).var()
    # ⑤ 平视:眼中心与鼻尖垂直距离/iod,低头时脸被压缩会偏小
    eye_c = (k[36:42].mean(0) + k[42:48].mean(0)) / 2
    vert = (k[30, 1] - eye_c[1]) / iod
    rows.append(dict(f=f, frontal=frontal, eyes=eyes, mouth=mouth, sharp=sharp, vert=vert))

if not rows: raise SystemExit("没检到任何人脸")
A = {k: np.array([r[k] for r in rows]) for k in ('frontal','eyes','mouth','sharp','vert')}
def nz(x): return (x - x.mean()) / (x.std() + 1e-9)
score = (2.0*nz(A['frontal']) + 1.0*nz(A['eyes']) - 1.5*nz(A['mouth'])
         + 1.0*nz(A['sharp']) + 0.8*nz(A['vert']))
order = np.argsort(-score)[:args.topn]

print(f"\n{'rank':5s}{'frame':28s}{'正脸':>7s}{'睁眼':>7s}{'张嘴':>7s}{'锐度':>8s}{'总分':>7s}")
picks = []
for i, idx in enumerate(order, 1):
    r = rows[idx]; picks.append(r['f'])
    print(f"{i:<5d}{os.path.basename(r['f']):28s}{r['frontal']:7.3f}{r['eyes']:7.3f}"
          f"{r['mouth']:7.3f}{r['sharp']:8.1f}{score[idx]:7.2f}")

# 联系表:一行 topn 张,底部标 rank + 文件名
tiles = []
for i, f in enumerate(picks, 1):
    im = cv2.resize(cv2.imread(f), (256, 256))
    im = cv2.copyMakeBorder(im, 0, 26, 0, 0, cv2.BORDER_CONSTANT, value=(20,20,20))
    cv2.putText(im, f"#{i} {os.path.basename(f)}", (6, 275),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255,255,255), 1, cv2.LINE_AA)
    tiles.append(im)
os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
cv2.imwrite(args.out, np.hstack(tiles))
print("\nsaved", args.out)
print("最佳:", picks[0])
