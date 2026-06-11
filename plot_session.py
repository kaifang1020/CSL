"""
把一节 session 的情绪轨迹画成图。

用法:
  python plot_session.py                      # 画 sessions/ 里最新的一节
  python plot_session.py sessions/session_xxx.csv   # 画指定的一节

输出:同名 .png,并弹窗显示。
依赖:pip install matplotlib
（标签用英文,避免 matplotlib 缺中文字体显示成方块。）
"""

import csv
import glob
import math
import os
import sys

import matplotlib.pyplot as plt


def _latest_csv() -> str:
    files = sorted(glob.glob("sessions/session_*.csv"))
    if not files:
        sys.exit("sessions/ 下没有 session_*.csv —— 先跑一节对话再来画。")
    return files[-1]


def _load(path: str):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _nums(rows, key):
    out = []
    for r in rows:
        try:
            out.append(float(r.get(key, "")))
        except (ValueError, TypeError):
            out.append(float("nan"))
    return out


def _has_signal(ys):
    # 全是 0.5(传感器没开)或全是 nan 就不画
    return any((not math.isnan(v)) and abs(v - 0.5) > 1e-9 for v in ys)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else _latest_csv()
    rows = _load(path)
    if not rows:
        sys.exit(f"{path} 是空的。")
    turns = [int(r["turn"]) for r in rows]

    fig, ax = plt.subplots(figsize=(11, 6))

    # 患者内部状态(实线)
    patient = [
        ("guardedness", "Guardedness (defensiveness)", "#d62728"),
        ("grief_access", "Grief access", "#1f77b4"),
        ("alliance", "Alliance (trust)", "#2ca02c"),
    ]
    for key, label, color in patient:
        ax.plot(turns, _nums(rows, key), marker="o", color=color, linewidth=2, label=label)

    # 治疗师信号(虚线,较淡);没开的传感器恒为 0.5 → 自动不画
    therapist = [
        ("therapist_warmth", "Therapist tone warmth (SER)", "#ff7f0e"),
        ("therapist_attentiveness", "Therapist expression (VISION)", "#9467bd"),
    ]
    for key, label, color in therapist:
        ys = _nums(rows, key)
        if _has_signal(ys):
            ax.plot(turns, ys, marker="x", linestyle="--", color=color, alpha=0.6, label=label)

    ax.set_xlabel("Turn")
    ax.set_ylabel("Value (0–1)")
    ax.set_ylim(-0.02, 1.02)
    if turns:
        ax.set_xticks(turns)
    ax.set_title(f"Emotional trajectory — {os.path.basename(path)}")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()

    out = os.path.splitext(path)[0] + ".png"
    fig.savefig(out, dpi=130)
    print(f"已保存:{out}")

    # 顺便在终端打印每轮的治疗师话(对照曲线看)
    print("\n每轮治疗师说了什么:")
    for r in rows:
        print(f"  turn {r['turn']}: {r['therapist'][:70]}")

    plt.show()


if __name__ == "__main__":
    main()
