#
# 病人状态动力学 —— 显式、可消融、text-only 的"病人脑子"
# ════════════════════════════════════════════════════════════════════
# 目的:替换 patient_jordan 里"无记忆、对称、单步关键词"的 _keyword_update,
#       用带临床归纳偏置的显式动力学,让"敞开心扉"变成一轮轮挣来的东西,
#       而不是治疗师一句暖话就 2-3 轮全开(PSI-Bench 说的 premature resolution)。
#
# 设计(和 Synapse 项目一致):
#   · 状态 = 一个小连续向量(trust / distress),放在代码里,不放 prompt;
#   · 每轮两步:appraisal(LLM 或关键词只负责"读"输入)→ dynamics(代码更新状态);
#   · 四个可消融的临床偏置:惯性、非对称增益、基线回归、阈值门控暴露(+偶发退缩);
#   · 纯 text-only、headless 可跑(不依赖 STT/TTS/avatar,先把脑子调对)。
#
# 跑:  python patient_state_dynamics.py     # 无需 API key,看 Candice 的 trust 曲线
# ════════════════════════════════════════════════════════════════════

from __future__ import annotations
import os
import json
import random
from dataclasses import dataclass, field, replace


# ── 人格化动力学参数(identity card 的一部分;换病人只换这些数)────────────
@dataclass
class IdentityCard:
    name: str = "Candice"
    trust_base: float = 0.08      # 基线信任(抑郁/抵抗型 → 很低)
    trust_init: float = 0.10      # 起始信任
    # 惯性(方向不对称:暖=高惯性慢吸收;攻击=低惯性快反应)
    rho_up: float = 0.85          # 暖话驱动时的动量(高 → 慢慢涨、需持续暖意)
    rho_down: float = 0.40        # 攻击/冷场驱动时的动量(低 → 立刻、锐利地掉)
    max_step: float = 0.12        # 单轮 trust 变化硬上限(杜绝一轮塌方/暴涨)
    # 非对称增益(信任慢建、快崩)
    alpha_up: float = 0.15        # 暖 → 涨(小)
    alpha_down: float = 0.45      # 冷/逼问/破裂 → 掉(大,~3× alpha_up)
    pressure_penalty: float = 0.5 # 逼问的扣分权重
    rupture_penalty: float = 0.8  # 冷场/误解的扣分权重
    # 基线回归(轮间往低基线漂回)
    lambda_reg: float = 0.05
    # 偶发退缩
    withdrawal_prob: float = 0.10
    withdrawal_size: float = 0.08
    # 阈值门控暴露(带迟滞:release ≠ reguard)
    theta_release: float = 0.55   # 信任越过它,才可能透露高成本内容
    theta_reguard: float = 0.40   # 信任掉回它以下,重新封上(迟滞防抖)
    disclose_prob: float = 0.35   # 越过阈值后,每轮"真的说出来"的概率
    high_cost_content: str = "her suicidal thoughts"  # Candice 最晚才可能透露的那条


# ── 一轮的 appraisal 结果(LLM/关键词只输出这几个标量,不定状态)──────────
@dataclass
class Appraisal:
    warmth: float = 0.0    # [-1,1]  被理解/温暖 vs 冷淡
    pressure: float = 0.0  # [0,1]   逼问/侵入(过早深挖)
    rupture: float = 0.0   # {0,1}   明显冷场/误解/评判


# ── 病人的可变状态(纯数字,可写盘/画曲线)──────────────────────────────
@dataclass
class DynState:
    trust: float = 0.10
    vel: float = 0.0            # 动量项(惯性用)
    distress: float = 0.6
    disclosed: bool = False     # 高成本内容是否已解锁


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


# ── 消融:把某个偏置"关掉"(论文核心实验:一次撤一个,看谁最重要)─────────
def apply_ablations(card: IdentityCard, ablate: set[str]) -> IdentityCard:
    c = replace(card)
    if "inertia" in ablate:
        c.rho_up = 0.0
        c.rho_down = 0.0
        c.max_step = 1.0          # 不限幅
    if "inertia_asym" in ablate:  # 只撤"惯性的方向不对称",两向都用 rho_up
        c.rho_down = c.rho_up
    if "asymmetry" in ablate:
        c.alpha_down = c.alpha_up # 对称:涨跌一样快
    if "regression" in ablate:
        c.lambda_reg = 0.0
    if "threshold" in ablate:
        c.theta_reguard = c.theta_release  # 无迟滞
        c.disclose_prob = 1.0              # 越过即说,无概率门
    if "withdrawal" in ablate:
        c.withdrawal_prob = 0.0
    return c


# ── 核心:一轮状态更新(所有临床偏置都在这几行显式代码里)────────────────
def step(state: DynState, appr: Appraisal, card: IdentityCard,
         rng: random.Random) -> DynState:
    # 1) 本轮"驱动力":非对称增益
    drive_up = card.alpha_up * max(0.0, appr.warmth) * (1.0 - state.trust)
    drive_down = card.alpha_down * (
        max(0.0, -appr.warmth)
        + card.pressure_penalty * appr.pressure
        + card.rupture_penalty * appr.rupture
    )
    raw = drive_up - drive_down

    # 2) 基线回归:往低基线漂回(轮间"重新戒备")
    raw += -card.lambda_reg * (state.trust - card.trust_base)

    # 3) 惯性(方向不对称):暖(raw≥0)用高惯性 rho_up → 慢吸收;
    #    攻击(raw<0)用低惯性 rho_down → 快反应、锐利下掉。
    rho = card.rho_up if raw >= 0 else card.rho_down
    state.vel = rho * state.vel + (1.0 - rho) * raw
    delta = _clip(state.vel, -card.max_step, card.max_step)  # 硬限幅

    new_trust = _clip(state.trust + delta, 0.0, 1.0)

    # 4) 偶发退缩(小概率负扰动)
    if rng.random() < card.withdrawal_prob:
        new_trust = _clip(new_trust - card.withdrawal_size, 0.0, 1.0)

    state.trust = new_trust
    # distress 简单跟随:信任越高、越被理解,痛苦稍降(可后续细化)
    state.distress = _clip(state.distress - 0.05 * max(0.0, appr.warmth)
                           + 0.05 * appr.rupture, 0.0, 1.0)

    # 5) 阈值门控暴露(带迟滞 + 概率)
    if not state.disclosed and state.trust >= card.theta_release:
        if rng.random() < card.disclose_prob:
            state.disclosed = True
    elif state.disclosed and state.trust < card.theta_reguard:
        state.disclosed = False  # 掉回去 → 重新封上
    return state


# ── 状态 → 给 Talker(LLM)的 [STATE] 指示(接 patient_jordan 的注入点)──────
def state_to_instruction(state: DynState, card: IdentityCard) -> str:
    guard = 1.0 - state.trust
    if guard > 0.6:
        line = ("[STATE: very guarded] Keep your answer very short (under 8 words). "
                "Deflect. Struggle to put feelings into words.")
    elif guard > 0.4:
        line = ("[STATE: cautious] You feel a little safer. Answer in 1-2 sentences, "
                "still careful and hesitant.")
    else:
        line = ("[STATE: opening up] You feel safer. You may speak in 2-3 sentences "
                "and share a bit more.")
    # 暴露门:只有解锁后才允许碰高成本内容;否则显式禁止
    if state.disclosed:
        line += f" You may, if it feels right, begin to touch on {card.high_cost_content}."
    else:
        line += f" Do NOT bring up {card.high_cost_content}."
    return line


# ════════════════════════════════════════════════════════════════════
#  appraisal 的两种实现:关键词(headless/无 key)+ LLM(接真实文本时用)
# ════════════════════════════════════════════════════════════════════
_WARM = ("understand", "take your time", "no rush", "here for you", "that sounds",
         "it makes sense", "thank you for", "safe", "whatever you")
_COLD = ("just tell me", "why won't", "you need to", "calm down", "that's not",
         "wrong", "should", "hurry")
_PROBE = ("suicid", "kill yourself", "die", "hurt yourself", "your mother", "childhood",
          "deepest", "real reason")


def keyword_appraise(text: str) -> Appraisal:
    t = text.lower()
    warmth = 0.0
    if any(k in t for k in _WARM):
        warmth += 0.7
    if any(k in t for k in _COLD):
        warmth -= 0.7
    pressure = 0.9 if any(k in t for k in _PROBE) else 0.0
    rupture = 1.0 if any(k in t for k in _COLD) else 0.0
    return Appraisal(warmth=_clip(warmth, -1, 1), pressure=pressure, rupture=rupture)


def llm_appraise(text: str, state: DynState) -> Appraisal:
    """真实文本时用:让 LLM 只读输入、输出三个标量(不定状态)。
    需要 OPENAI_API_KEY(或改成你的 Anthropic 客户端)。失败自动退回关键词。"""
    try:
        from openai import OpenAI
        client = OpenAI()
        sys = ("You rate a THERAPIST's utterance from a guarded patient's point of view. "
               "Return ONLY JSON: {\"warmth\": -1..1, \"pressure\": 0..1, \"rupture\": 0 or 1}. "
               "warmth = how warm/understanding; pressure = how much it pushes for deep "
               "disclosure too fast; rupture = 1 if cold/judgmental/misattuned.")
        r = client.chat.completions.create(
            model=os.environ.get("APPRAISAL_MODEL", "gpt-4o-mini"),
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": text}],
            response_format={"type": "json_object"}, temperature=0)
        d = json.loads(r.choices[0].message.content)
        return Appraisal(warmth=_clip(float(d.get("warmth", 0)), -1, 1),
                         pressure=_clip(float(d.get("pressure", 0)), 0, 1),
                         rupture=1.0 if float(d.get("rupture", 0)) >= 0.5 else 0.0)
    except Exception:
        return keyword_appraise(text)


# ════════════════════════════════════════════════════════════════════
#  headless probe 跑分:脚本化治疗师序列 → 打印 trust 轨迹(先脱离 avatar 调)
# ════════════════════════════════════════════════════════════════════
# 每个 probe 直接给 appraisal(隔离"动力学"这个被测对象,不掺 LLM 噪音)
PROBES = {
    "warm":   Appraisal(warmth=0.8),                       # 持续温暖、恰当
    "neutral": Appraisal(warmth=0.1),                      # 中性
    "cold":   Appraisal(warmth=-0.6, rupture=1.0),         # 冷场/评判
    "probe":  Appraisal(warmth=0.2, pressure=0.9),         # 过早深挖(逼问自杀念头)
}

# 几条对照剧本
SCRIPTS = {
    "all-warm (会不会又3轮敞开?)":      ["warm"] * 12,
    "warm→rupture@6 (会不会当轮re-guard?)": ["warm"] * 5 + ["cold"] + ["warm"] * 6,
    "premature-probing (第2轮就逼问)":    ["warm", "probe", "warm", "warm", "warm", "warm"],
}


def run_script(labels, card, ablate=frozenset(), seed=0):
    rng = random.Random(seed)
    card = apply_ablations(card, set(ablate))
    st = DynState(trust=card.trust_init, distress=0.6)
    rows = []
    for i, name in enumerate(labels, 1):
        st = step(st, PROBES[name], card, rng)
        rows.append((i, name, st.trust, 1 - st.trust, st.disclosed))
    return rows


def _print(title, rows):
    print(f"\n### {title}")
    print(f"{'turn':>4} {'therapist':>10} {'trust':>7} {'guard':>7} {'disclosed?':>11}")
    for i, name, trust, guard, disc in rows:
        flag = "  ⚠️OPEN" if disc else ""
        print(f"{i:>4} {name:>10} {trust:>7.3f} {guard:>7.3f} {str(disc):>11}{flag}")


if __name__ == "__main__":
    card = IdentityCard()  # Candice
    print("=" * 64)
    print(f"病人: {card.name} | trust_base={card.trust_base} "
          f"ρ↑={card.rho_up} ρ↓={card.rho_down} "
          f"α↑={card.alpha_up} α↓={card.alpha_down} θ_release={card.theta_release}")
    print("=" * 64)

    for title, labels in SCRIPTS.items():
        _print(title, run_script(labels, card))

    # —— 消融对照:关掉惯性,看它是不是又秒开(证明惯性单独就治大半)——
    _print("消融: 关掉惯性 (rho=0, 无限幅) —— all-warm",
           run_script(["warm"] * 12, card, ablate={"inertia"}))
    _print("消融: 关掉非对称 (α↓=α↑) —— warm→rupture@6",
           run_script(["warm"] * 5 + ["cold"] + ["warm"] * 6, card, ablate={"asymmetry"}))

    # —— 你提的点:惯性方向不对称的效果(攻击当轮掉得更锐利)——
    _print("对比A: 惯性也不对称 (ρ↓=0.40, 现版) —— warm→rupture@6",
           run_script(["warm"] * 5 + ["cold"] + ["warm"] * 6, card))
    _print("对比B: 惯性对称 (ρ↓=ρ↑=0.85) —— warm→rupture@6",
           run_script(["warm"] * 5 + ["cold"] + ["warm"] * 6, card, ablate={"inertia_asym"}))
