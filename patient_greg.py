#!/usr/bin/env python3
# patient_greg.py — 用 Greg 人设跑同一条 pipeline（复用 patient_jordan.py，零重复）。
#
# 用法：  python patient_greg.py -t daily
#   等价于  PATIENT=greg python patient_jordan.py -t daily
#
# Greg = 75 岁退休教师,丧偶,由子女照护;抑郁 + 衰老带来的躯体受限 + 强烈的
# 「不想成为负担」(perceived burdensomeness)。自杀呈现方式与 Candice 相反:
# 不是崩溃求救,而是平静地把「结束」讲成一个已经想通的合理结论。
import os
import sys

os.environ["PATIENT"] = "greg"

# 脸:参考帧由 pick_ref.py 在真人区间内挑选后填入。
#   ⚠️ 素材首尾是黑底卡片:0–8.04s 标题卡「Greg」、79.55–87.55s「Now it's your turn to speak.」
#   官方预处理用全片平均 bbox,会把这些黑卡一并裁成「人脸帧」。25fps 下真人区间约为
#   第 201–1988 帧,选参考帧必须限定在这个范围内。
# 高清参考图:1254x1254,脸宽 477px → 裁剪框约 953px,到 512 是【缩小 0.54x】。
# 旧的 data/GREG_v3/01920.jpg 是从视频里裁的,脸宽仅 183px → 放大 1.40x,锐度 16.1;
# 这张锐度 269.7(16.8 倍),而嘴闭合/睁眼/正脸各项不差。参考帧决定外观基线,
# 缩放方向从"补像素"变成"丢冗余"是画质提升最实在的一步。
# 参考帧：data/greg_hq_v2.png（2026-09-04 换）。
#   换的理由不是清晰度，是【临床相符】：旧的 greg_hq.png 红润饱满、眼神警觉、
#   嘴微张且嘴角略上扬，看起来像个健康的退休老人——而 GREG_PROMPT 写的是
#   "calm, articulate and resigned"、"affect is flatter than a younger patient's"。
#   参考帧决定整个外观基线，所以这是【每一帧都在犯】的错，直接违反评估框架里的
#   Frame-level B · Facial-state congruence。
#   新图：肤色偏灰、面颊削瘦、眼睑沉、嘴闭合且嘴角平——和人设相符。
#   ⚠️ 代价：锐度 175 vs 旧图 270，清晰度略降（仍远高于原始视频帧的 16）。
#   ⚠️ 旧图保留在 frozen/v1-golden/ref_frames/GREG_hq.png，想回退改回 data/greg_hq.png。
#   ⏳ 待验证：mouth/smile 关键点数值（本地无 face_alignment，要等服务器）。
#      预期新图更好——旧图嘴微张+嘴角上扬，可能正是"露齿笑 14~17% 帧"的源头之一。
os.environ.setdefault("AF_FACE", "data/greg_hq_v2.png")

# 锚点采样预算:默认 6s 在刚开机的机器上不够——face_alignment 首次调用要把模型载进
# GPU,光第一帧就 8~9s,预算当场用完 → 只采到 1 帧 → 锚退化。见 patient_candice.py。
os.environ.setdefault("AF_ANCHOR_BUDGET_S", "30")
os.environ.setdefault("AF_ANCHOR_STRIDE", "3")

_here = os.path.dirname(os.path.abspath(__file__))
os.execvp(sys.executable, [sys.executable, os.path.join(_here, "patient_jordan.py"), *sys.argv[1:]])
