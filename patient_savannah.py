#!/usr/bin/env python3
# patient_savannah.py — 用 Savannah 人设跑同一条 pipeline（复用 patient_jordan.py，零重复）。
#
# 用法：  python patient_savannah.py -t daily
#   等价于  PATIENT=savannah python patient_jordan.py -t daily
#
# Savannah = 第三次会谈的"照顾者"型病人：她是所有人的军师，却救不了自己。
#   核心动力是矛盾（persona-only，不套 Jordan 的状态机）：她真心想被接住，
#   但治疗师一旦真的靠近，她会挡回去甚至发火，然后又重新伸手。
#   无自杀风险（与 Candice 不同）。
#
# 脸：data/savannah_hq.png（1254x1254 高清修复版）。细节见下方 AF_FACE 处的注释。
import os
import sys

os.environ["PATIENT"] = "savannah"
# 参考帧：data/savannah_hq.png —— 1254x1254 高清修复版（锐度 98 vs 原 512 帧的 25，约 4 倍）。
#   原来用的是官方预处理出的 512 裁剪帧 data/savannah/01316.jpg，源视频里她的脸只有 ~356px，
#   要放大 1.44 倍才够 512，所以发糊；换帧救不了（全片脸宽标准差仅 7px）。
#   ⚠️ 这张高清图嘴是微张的。静息嘴型交给 AF_ANCHOR_PICK=mouth（锚从生成首块里挑嘴最闭的帧），
#      启动时务必带上，否则静息状态会留着微张的嘴。参见 patient_candice.py 的同款说明。
#   ⚠️ 素材首尾有黑底标题卡和烧录字幕("Now it is your turn to talk")；pick_ref.py 的前 6 名
#      全落在污染区(2338-2416)，选中会把字幕印进每一帧（见 results/sav_stress.mp4 实证）。
os.environ.setdefault("AF_FACE", "data/savannah_hq.png")

# 锚点采样预算：默认 6s 在刚开机的机器上不够（face_alignment 首次调用要把模型载进 GPU，
# 第一帧就 8~9s，预算用完只采到 1 帧 → 锚退化）。见 patient_candice.py 的实测数据。
os.environ.setdefault("AF_ANCHOR_BUDGET_S", "30")
os.environ.setdefault("AF_ANCHOR_STRIDE", "3")

_here = os.path.dirname(os.path.abspath(__file__))
# 直接以 Savannah 环境重跑 patient_jordan.py（同一条 pipeline，参数透传，如 -t daily）
os.execvp(sys.executable, [sys.executable, os.path.join(_here, "patient_jordan.py"), *sys.argv[1:]])
