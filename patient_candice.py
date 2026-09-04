#!/usr/bin/env python3
# patient_candice.py — 用 Candice 人设跑同一条 pipeline（复用 patient_jordan.py，零重复）。
#
# 用法：  python patient_candice.py -t daily
#   等价于  PATIENT=candice python patient_jordan.py -t daily
#
# Candice = 抑郁 + 情绪失调 + 慢性自杀意念,戏剧化/泛滥/求助型（persona-only，
# 不套 Jordan 的 guardedness 状态机）。是用来测试的第二个病人。
import os
import sys

os.environ["PATIENT"] = "candice"

# 脸：data/CANDICE_v3/00141.jpg —— 正脸(1.000) + 神情平淡/悲伤（临床上贴合抑郁）+
#   嘴开度 0.0665（候选里最小）。
#   ⚠️ 表情优先于"嘴闭合"：这段素材里"嘴完全闭合"的帧只出现在 59s 前后的停顿，
#   而那几帧带着微笑（01795 等），对抑郁患者是错的。嘴的问题交给 AF_ANCHOR_PICK=mouth
#   （锚从生成的首块里挑嘴最闭的帧），不必牺牲参考照片的表情。
#   ⚠️ 素材首尾是黑底标题卡(1-140)和烧录字幕(2188+)，被官方预处理的"全片平均 bbox"
#   一并裁成了人脸帧，选到会把字幕印进每一帧生成画面。
# 参考帧：data/candice_hq.png —— 1254x1254 高清修复版（锐度 121 vs 原生裁剪的 47）。
#   源视频里她的脸只有 ~211px，到 512 要放大 2.43x（三个病人里最糟），所以原来最糊；
#   高清版脸宽 710px → 裁剪框到 512 是【缩小】，方向从"补像素"变成"丢冗余"。
#   这张嘴是闭合的、表情平淡，临床上贴合抑郁，不需要额外补救。
#   ⚠️ 素材首尾是黑底标题卡(1-139)和烧录字幕(2188+)；原帧取自第 141 帧（标题卡刚结束）。
os.environ.setdefault("AF_FACE", "data/candice_hq.png")

# 锚点采样预算：默认 6s 在"刚开机的机器"上不够——face_alignment 首次调用要把模型
# 载进 GPU，光第一帧就 8~9s，预算当场用完 → 只采到 1 帧 → 退化成"用首块第 0 帧当锚"。
# 实测：预算 6s 时锚的嘴开度 0.0599（听你说话时嘴微张，正是要避免的）；
#      预算 30s + stride 3 时采到 17 帧，锚为 0.0000。多花的几秒只在启动时付一次。
os.environ.setdefault("AF_ANCHOR_BUDGET_S", "30")
os.environ.setdefault("AF_ANCHOR_STRIDE", "3")

_here = os.path.dirname(os.path.abspath(__file__))
# 直接以 Candice 环境重跑 patient_jordan.py（同一条 pipeline，参数透传，如 -t daily）
os.execvp(sys.executable, [sys.executable, os.path.join(_here, "patient_jordan.py"), *sys.argv[1:]])
