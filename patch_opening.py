#!/usr/bin/env python3
# 外科手术式补丁:把 run_bot 里 on_client_connected 的开场触发
#   await worker.queue_frames([LLMRunFrame()])   # LLM 现场生成第一句(冷启动会飘成治疗师腔)
# 改成:有 CLINICAL_OPENING 环境变量 → 固定台词直接播 TTS(一字不差、不走 LLM);
#      没有 → 维持原样(LLMRunFrame)。
# 只改这一处,不引入 smart-turn 等新依赖,不碰内存。幂等:已打过就跳过。
import sys

P = "/app/patient_jordan.py"
src = open(P, encoding="utf-8").read()

if "CLINICAL_OPENING" in src:
    print("ALREADY patched — 跳过")
    sys.exit(0)

lines = src.split("\n")
out, patched = [], False
for l in lines:
    if (not patched) and ("queue_frames([LLMRunFrame()])" in l):
        indent = l[: len(l) - len(l.lstrip())]  # 保持原缩进
        out += [
            f'{indent}import os as _os',
            f'{indent}_op = _os.environ.get("CLINICAL_OPENING", "")',
            f'{indent}if _op:',
            f'{indent}    from pipecat.frames.frames import TTSSpeakFrame as _TSF',
            f'{indent}    try:',
            f'{indent}        context.messages.append({{"role": "assistant", "content": _op}})',
            f'{indent}    except Exception:',
            f'{indent}        pass',
            f'{indent}    await worker.queue_frames([_TSF(_op)])',
            f'{indent}else:',
            f'{indent}    {l.strip()}',
        ]
        patched = True
    else:
        out.append(l)

if not patched:
    print("NO MATCH — 没找到 LLMRunFrame 开场行,未改动"); sys.exit(1)

open(P, "w", encoding="utf-8").write("\n".join(out))
# 语法自检
import py_compile
try:
    py_compile.compile(P, doraise=True)
    print("PATCHED + 语法 OK")
except py_compile.PyCompileError as e:
    print("PATCHED 但语法出错!请回滚:", e); sys.exit(2)
