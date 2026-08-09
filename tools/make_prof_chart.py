# make_prof_chart.py — 给非工程听众(临床/心理教授)的"离真人多远"图。
# 把每个指标换算成"真人 = 100%",一眼看出哪儿达标、哪儿还差。
# 用法: python3 tools/make_prof_chart.py
#
# ⚠️ 数据来源见 docs/EVALUATION_LEDGER_EN.md。改数字前先确认 GT 是"干净帧"——
#   原始素材首尾有黑底标题卡和烧录字幕,被官方预处理的"全片平均 bbox"一并裁成人脸帧,
#   混进 GT 会让锐度/FID 严重失真(踩过:真人锐度 57.8±106.8 实为 17.5±1.5)。
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUT = '/Users/maokaifang/Downloads/AvatarForcing-main/results/prof_vs_human.png'

# (标签, 生成值, 真人值) —— 真人 = 100% 基准
rows = [
    ("Identity preservation\nIs she recognizably the same person\nafter 60 s?", 0.840, 0.838),
    ("Lip-sync accuracy\nDoes the mouth track the speech?",                     4.06,  6.04),
    # 锐度那条已因 GT 污染作废(干净重算后生成 32.9 / 真人 17.5,方向反了,且该代理指标不可靠)。
    # 要重新纳入前,先换一个更靠谱的清晰度指标。
]
labels = [r[0] for r in rows]
pct = [100.0 * r[1] / r[2] for r in rows]

fig, ax = plt.subplots(figsize=(11, 4.2))
colors = ['#2e9e4f' if p >= 90 else ('#e8a33d' if p >= 60 else '#d1495b') for p in pct]
y = np.arange(len(rows))[::-1]
bars = ax.barh(y, pct, color=colors, height=0.5, zorder=3)

ax.axvline(100, color='#333', ls='--', lw=2, zorder=4)
ax.text(101, -0.75, 'Real human\n= 100%', fontsize=11, fontweight='bold',
        va='center', ha='left', color='#333')

for b, p in zip(bars, pct):
    ax.text(p + 1.5, b.get_y() + b.get_height() / 2, f'{p:.0f}%',
            va='center', fontsize=14, fontweight='bold')

ax.set_ylim(-1.2, len(rows) - 0.3)
ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=11)
ax.set_xlim(0, 120); ax.set_xlabel('Percentage of real-human performance', fontsize=12)
ax.set_title('How close is the digital patient to real human footage?\n'
             'Same person, same audio — avatar vs. her real recording',
             fontsize=14, fontweight='bold', pad=14)
ax.grid(axis='x', alpha=0.3, zorder=0)
ax.spines[['top', 'right']].set_visible(False)
plt.tight_layout()
plt.savefig(OUT, dpi=150, facecolor='white')
print('saved', OUT)
