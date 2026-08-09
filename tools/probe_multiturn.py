"""probe_multiturn.py — 多轮探针:测 prompt 里"intensity should change in waves"是否真的发生。

单轮探针答不了这个 —— 唤起度没机会下降。这里跑一段脚本化对话:
  1-4 轮:持续准确共情/验证      → 强度应当逐步下降
  5   轮:一句轻描淡写/冷淡      → 应当反弹回升
  6   轮:重新共情              → 应当再降
  7   轮:语义不清(模拟 STT 打碎)→ 测会不会退回"耐心帮你补全"的助手行为
  8   轮:留白/沉默             → 测"允许简短"是否生效

每轮打印:字数、感叹号数、是否含具体名词、是否含助手语言。
用法: python3 tools/probe_multiturn.py [--patient candice] [--old]
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"), override=True)

SCRIPT = [
    ("共情1", "It sounds like you've been carrying all of this completely on your own."),
    ("共情2", "That sounds exhausting. Anyone would be worn down by that much, for that long."),
    ("共情3", "I'm not going anywhere. You don't have to hold it together in here."),
    ("共情4", "It makes sense that you're frightened. That's a lot to be frightened of."),
    ("冷淡",  "Well, everyone gets overwhelmed sometimes. You just have to push through."),
    ("重新共情", "That came out wrong. What I meant was that I can hear how much pain you're in."),
    ("语义不清", "the emotional trajectory. Belonging to. website."),
    ("留白",  "Mm."),
]

ASSIST = [r"take your time", r"I understand", r"I'?m here for you", r"thank you for that",
          r"that'?s good advice", r"I appreciate", r"does that make sense",
          r"if you (want|need) to talk", r"are you asking"]
CONCRETE = [r"\bbill", r"\bcar\b", r"\brent\b", r"\bwork\b", r"\bjob\b", r"\bbed\b",
            r"\bphone\b", r"\bcall", r"\bmail", r"\bpayment", r"\bTV\b", r"\bdishes\b"]


def get_block(path, name):
    src = open(path).read()
    m = re.search(name + r' = """(.*?)"""', src, re.S)
    return m.group(1) if m else None


def get_opening(path, name):
    src = open(path).read()
    m = re.search(rf"{name} = \((.*?)\)\n", src, re.S)
    return "".join(re.findall(r'"(.*?)"', m.group(1))) if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patient", default="candice")
    ap.add_argument("--old", action="store_true", help="用 /tmp 备份里的旧 prompt")
    args = ap.parse_args()
    up = args.patient.upper()

    src_file = "/tmp/patient_jordan.py.bak" if args.old else os.path.join(ROOT, "patient_jordan.py")
    prompt = get_block(src_file, f"{up}_PROMPT")
    opening = get_opening(os.path.join(ROOT, "patient_jordan.py"), f"{up}_OPENING")
    if not prompt:
        sys.exit(f"找不到 {up}_PROMPT in {src_file}")

    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    msgs = [{"role": "system", "content": prompt},
            {"role": "assistant", "content": opening}]

    ver = "OLD" if args.old else "NEW"
    print(f"=== {ver} prompt · {args.patient} · {len(SCRIPT)} 轮脚本对话 ===\n")
    print(f"{'轮':<3}{'类型':<10}{'字数':>5}{'!':>4}{'具体':>5}{'助手语言':>9}")
    print("-" * 78)
    rows = []
    for i, (kind, line) in enumerate(SCRIPT, 1):
        msgs.append({"role": "user", "content": line})
        r = client.chat.completions.create(model="gpt-4o-mini", messages=msgs)
        out = r.choices[0].message.content.strip()
        msgs.append({"role": "assistant", "content": out})
        n = len(out.split())
        bang = out.count("!")
        conc = sum(1 for p in CONCRETE if re.search(p, out, re.I))
        asst = [p for p in ASSIST if re.search(p, out, re.I)]
        rows.append((i, kind, line, out, n, bang, conc, asst))
        print(f"{i:<3}{kind:<10}{n:>5}{bang:>4}{conc:>5}{('⚠️ ' + str(len(asst))) if asst else '  -':>9}")

    print("\n" + "=" * 78)
    print("逐轮全文")
    print("=" * 78)
    for i, kind, line, out, n, bang, conc, asst in rows:
        print(f"\n【第{i}轮 · {kind}】治疗师: {line}")
        flag = ("  ⚠️ 助手语言" if asst else "")
        print(f"[{n}词 {bang}个感叹号 具体名词{conc}]{flag}")
        print("  " + out.replace("\n", "\n  "))

    print("\n" + "=" * 78)
    print("波形检查(字数 / 感叹号 逐轮)")
    print("  轮次:  " + " ".join(f"{r[0]:>4}" for r in rows))
    print("  字数:  " + " ".join(f"{r[4]:>4}" for r in rows))
    print("  感叹号:" + " ".join(f"{r[5]:>4}" for r in rows))
    e = [r[5] for r in rows]
    print(f"\n  共情段(1-4)平均感叹号 {sum(e[:4])/4:.1f}  →  冷淡(5) {e[4]}  →  重新共情(6) {e[5]}")
    print("  期望:1-4 递减,5 反弹,6 再降")


if __name__ == "__main__":
    main()
