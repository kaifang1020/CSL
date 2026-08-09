#!/usr/bin/env python3
"""解析 bot.log，抽出所有延迟事件，按 turn 排时间轴 + 汇总。
用法: python parse_latency.py /workspace/bot.log
"""
import re, sys, statistics
from datetime import datetime

LOG = sys.argv[1] if len(sys.argv) > 1 else "/workspace/bot.log"
TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s*\|")

# 事件类型 -> 在每行里匹配的正则（第一个命中的为准）
PATTERNS = [
    ("USER_START", re.compile(r"User started speaking")),
    ("USER_STOP",  re.compile(r"User stopped speaking")),
    ("EOT_DONE",   re.compile(r"End of Turn result: EndOfTurnState\.COMPLETE")),
    ("STOP_SECS",  re.compile(r"due to stop_secs.*?Silence in ms:\s*([\d.]+)")),
    ("STT",        re.compile(r"DeepgramSTTService\S*\s*TTFB:\s*([\d.]+)s")),
    ("THERAPIST",  re.compile(r"治疗师:\s*(.*?)\s*$")),
    ("VISION",     re.compile(r"\[VISION\]")),
    ("SER",        re.compile(r"\[SER\]\s*therapist_warmth")),
    ("LLM_CALL",   re.compile(r"Generating chat from context")),
    ("LLM_TTFB",   re.compile(r"OpenAILLMService\S*\s*TTFB:\s*([\d.]+)s")),
    ("TTS_TTFB",   re.compile(r"CartesiaTTSService\S*\s*TTFB:\s*([\d.]+)s")),
    ("FIRSTFRAME", re.compile(r"avatar(?:首帧|音频)延迟.*?([\d.]+)ms")),
    ("BLOCK",      re.compile(r"引擎块耗时\s*([\d.]+)ms.*?mode=(\w+)")),
    ("LATENCY",    re.compile(r"延迟.*?总\s*([\d.]+)s.*?想\s*([\d.]+)s.*?说\s*([\d.]+)s")),
]

def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")

events = []
for line in open(LOG, encoding="utf-8", errors="replace"):
    m = TS.match(line)
    if not m:
        continue
    t = parse_ts(m.group(1))
    for name, pat in PATTERNS:
        mm = pat.search(line)
        if mm:
            events.append((t, name, mm.groups()))
            break

if not events:
    print("没解析到事件，检查日志路径/内容:", LOG); sys.exit(0)

def nums(name, idx=0):
    out = []
    for _, n, g in events:
        if n == name and g and g[idx]:
            try: out.append(float(g[idx]))
            except: pass
    return out

def line_stat(label, name, idx=0, unit="s"):
    v = nums(name, idx)
    if not v: return f"  {label}: (无)"
    return f"  {label}: n={len(v)}  均 {statistics.mean(v):.2f}{unit}  范围[{min(v):.2f},{max(v):.2f}]{unit}"

print("=" * 64)
print("汇总")
print("=" * 64)
print(line_stat("STT TTFB", "STT"))
print(line_stat("LLM TTFB", "LLM_TTFB"))
print(line_stat("TTS TTFB", "TTS_TTFB"))
print(line_stat("avatar 首帧延迟", "FIRSTFRAME", 0, "ms"))
print(line_stat("引擎块耗时", "BLOCK", 0, "ms"))
lat = [(float(a), float(b), float(c)) for _, n, (a, b, c) in [(t, n, g) for t, n, g in events if n == "LATENCY"]]
if lat:
    tot = [x[0] for x in lat]; th = [x[1] for x in lat]; sp = [x[2] for x in lat]
    print(f"  端到端延迟: n={len(lat)}  总均 {statistics.mean(tot):.2f}s = 想 {statistics.mean(th):.2f}s + 说 {statistics.mean(sp):.2f}s")
ss = nums("STOP_SECS")
if ss:
    print(f"  ⚠️ smart_turn 退回静音兜底(stop_secs): {len(ss)} 次, 静音 {[f'{x/1000:.1f}s' for x in ss]}")
else:
    print("  smart_turn 退回静音兜底: 0 次")

print()
print("=" * 64)
print("逐 turn 时间轴（Δ = 距上一事件秒数；⬅GAP = 该步耗时>1s，延迟在这里）")
print("=" * 64)
last_latency_i = -1
for i, (t, n, g) in enumerate(events):
    if n != "LATENCY":
        continue
    seg = events[last_latency_i + 1: i + 1]
    last_latency_i = i
    seg = [e for e in seg if e[1] != "BLOCK"]  # 引擎块太多，时间轴里略去
    if not seg:
        continue
    t0 = seg[0][0]
    print(f"\n--- turn  总 {g[0]}s  想 {g[1]}s  说 {g[2]}s ---")
    prev = t0
    for (tt, nn, gg) in seg:
        d0 = (tt - t0).total_seconds()
        dp = (tt - prev).total_seconds()
        mark = "  ⬅GAP" if dp > 1.0 else ""
        extra = (" " + " ".join(str(x) for x in gg)) if gg and any(gg) else ""
        print(f"  +{d0:6.2f}s  Δ{dp:5.2f}s{mark}   {nn}{extra}")
        prev = tt
