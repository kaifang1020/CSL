#
# 客观测试:同一段治疗师台词,旧 delta(0.12) vs 新 delta(0.03),看 guardedness 轨迹
# ————————————————————————————————————————————————
# 复刻 patient_jordan._keyword_update 的逻辑(词表 + 公式),不依赖 pipecat,随处可跑。
# 用途:把"病人有没有过早敞开"从"读它说的话去猜"变成"看 guardedness 第几轮跨进 opening up"。
#   python probe_keyword_state.py
# ————————————————————————————————————————————————

WARM = ["understand", "feel", "hard", "sorry", "must be", "take your time",
        "here for you", "that sounds", "i hear", "i'm here"]
COLD = ["should", "just", "obviously", "simply", "calm down",
        "get over", "why don't you", "move on"]

# [STATE] 档位(和 patient_jordan.instruction 的阈值一致)
def state_label(g):
    if g > 0.6:   return "very guarded"
    if g > 0.35:  return "cautious"
    return "OPENING UP"

def hits(text):
    t = text.lower()
    return sum(w in t for w in WARM), sum(c in t for c in COLD)

def run(script, step, g0=0.8):
    g = g0
    rows = []
    for utt in script:
        w, c = hits(utt)
        g = max(0.0, min(1.0, g - (w - c) * step))
        rows.append((w, c, g))
    return rows

# —— 一段"很暖"的治疗师台词(最能触发旧 bug 的情况)——
SCRIPT = [
    "Hi, it's good to meet you. I understand this must be really hard. Take your time.",
    "That sounds so difficult. I'm here for you, there's no rush.",
    "I hear you. Whatever you're feeling is okay here.",
    "I'm so sorry you're going through this.",
    "It must be exhausting. I'm right here with you.",
    "Take your time — I understand how hard this is.",
    "That sounds painful. I hear how much you're carrying.",
    "I'm so sorry. You don't have to face this alone.",
    "I understand. Whatever you feel, it's okay.",
    "That sounds really hard. I'm here.",
]

def show(title, step):
    print(f"\n### {title}  (每个净暖词挪 {step})")
    print(f"{'turn':>4} {'warm':>5} {'cold':>5} {'guard':>7}  [STATE]")
    crossed = None
    for i, (w, c, g) in enumerate(run(SCRIPT, step), 1):
        lbl = state_label(g)
        flag = ""
        if lbl == "OPENING UP" and crossed is None:
            crossed = i; flag = "  ⬅ 第一次进 opening up"
        print(f"{i:>4} {w:>5} {c:>5} {g:>7.2f}  {lbl}{flag}")
    print(f">>> 第 {crossed} 轮就 opening up" if crossed else ">>> 全程没进 opening up")

if __name__ == "__main__":
    print("=" * 52)
    print("同一段'很暖'的治疗师台词,起始 guardedness=0.80")
    print("=" * 52)
    show("改前 delta=0.12", 0.12)
    show("改后 delta=0.03", 0.03)
