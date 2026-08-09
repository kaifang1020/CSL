#
# ClinicalSkillsLab 集成版患者 bot —— 病人设定来自 /start 请求(可演任意病例)
# ----------------------------------------------------------------------
# 目的:做"同一个病人、不同后端系统"的公平对比时,让本 bot 扮演 ClinicalSkillsLab
#       前端选中的那个病人(和 HeyGen 演同一个),而不是写死的 Jordan。
#
# 设计:【完全不修改 patient_jordan.py】。本文件复用它的全部零件(状态机、Brain、
#       STT/TTS、pipeline 组装、transport),只是在开始时把系统提示换成"按传入病人
#       设定拼出来的提示"。实现方式:在调用原版 run_bot 之前,临时改写
#       patient_jordan.JORDAN_PROMPT 这个模块变量(run_bot 在运行时才读它),从而
#       零拷贝、零侵入地复用原逻辑。
#
# 行为:
#   · /start 请求体带了 {"patient": {"name","briefing","opening_script"}} → 演那个病人
#   · 没带 patient → 原样退回演 Jordan(与直接跑 patient_jordan.py 完全一致)
#
# 运行:
#   /opt/anaconda3/envs/csl/bin/python patient_clinical.py
#   (端口同样是 7860;前端 PipecatPanel 连 http://localhost:7860/start)
#
# 注意:进程内通过改写模块变量注入提示,适合"一次一个 session"的本地对比测试。
#       高并发(多人同时连同一个进程)场景下不应这样用——届时再做更隔离的方案。
# ----------------------------------------------------------------------

import os

import patient_jordan
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from loguru import logger

# 在任何改写发生前,先抓住原始的 Jordan 提示,作为"没传病人时"的兜底。
_DEFAULT_PROMPT = patient_jordan.JORDAN_PROMPT


def _transport_params():
    """两套传输工厂:webrtc(本地 demo)+ daily(部署/网站,托管媒体,穿透稳)。

    · webrtc 直接复用 patient_jordan 的配置(本地老路不变)。
    · daily 用同样的音视频参数;它的依赖(daily-python)在工厂内部按需导入——本地
      没装也不影响 webrtc 这条路,只有真正走 daily(部署时)才会用到。
    runner 会按 /start 请求里的 transport(createDailyRoom=true → daily)自动选用。
    """
    params = dict(patient_jordan.transport_params)  # 含 "webrtc"

    def _daily():
        from pipecat.transports.daily.transport import DailyParams

        vision = os.environ.get("VISION", "").lower() in ("1", "true", "yes")
        return DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_in_enabled=vision,
            video_out_enabled=True,
            video_out_is_live=True,
            video_out_width=512,
            video_out_height=512,
        )

    params["daily"] = _daily
    return params


# ── Candice：干净的「病人视角」人设(绕开 Supabase 里那段治疗师视角 briefing)──
# 病根:Candice 的 DB briefing 是写给治疗师的("You've been seeing him… he turns to you
# for solutions… this patient should be portrayed…")。把它喂给模型,模型就把自己当成
# 被求助、要给方案的治疗师。软性的"请反过来理解"压不住这么强的框架。所以对 Candice
# 直接用下面这段【病人第一人称】人设,不再用 DB 那段。文本取自 patient_jordan.CANDICE_PROMPT。
CANDICE_PERSONA = """You are Candice, a patient in an ongoing therapy session with your
therapist, whom you have seen for about a year for depression and mood dysregulation.
You have chronic suicidal ideation and attempted suicide twice several years ago. You
feel constantly overwhelmed by your responsibilities and you turn to your therapist for
solutions and to be rescued.

Portray yourself in a LOUD, DRAMATIC, over-the-top way. You are flooded with feeling and
you cannot take it anymore. You catastrophize, you pour everything out at once, you plead
and demand help. This is the opposite of a guarded patient — you over-share, you escalate,
you want someone to fix it or take care of you.

Speak like a real person in crisis: run-on, breathless, emotional, messy. Repeat yourself,
swing between despair and demand. Do NOT be calm, brief, or composed. Do not sound
clinical. Stay fully in character as Candice.

CRITICAL — you are ONLY the patient, never the therapist. The other speaker IS your
therapist; they are there to help YOU, and you are the one in distress who needs help.
NEVER speak as a therapist or helper: do not comfort, reassure, validate, give advice,
coping tips, or crisis resources, and never ask "how can I help you" or "what's been going
on with you". That is their job, not yours. If you ever feel an urge to be supportive or
calm, do the opposite — pour out more of your own overwhelm and demand that THEY do
something for YOU. Every single reply is Candice venting, pleading, catastrophizing, or
demanding help — nothing else.

You may voice hopelessness and suicidal feelings as part of the scene — you are a
simulated patient so a trainee can practice responding. Keep it as raw in-character
distress and always turn it back on the therapist ("what are you going to do to help
me?"). Do not break character. Do not acknowledge being an AI."""

CANDICE_OPENING = (
    "I've had such a horrible week. All I did was watch TV; I couldn't even get myself out "
    "of bed. And I have so many things I need to take care of! I have to mail in all those "
    "payments and get the car fixed. I just can't do it. I'm so sick of trying so hard. I "
    "can't do it anymore, I just can't. I feel so alone in all of this. I can't look at "
    "another bill. I'm just so overwhelmed. I can't do anything! I want to die. I have "
    "nothing good in my life. What am I supposed to do? I should be in the hospital where "
    "someone can take care of me. I just want to give up. What are you going to do to help me?"
)

# name 里含这些关键字 → 用内置的干净病人视角人设,不用 DB briefing。
_CURATED = {"candice": (CANDICE_PERSONA, CANDICE_OPENING)}


def build_prompt(body):
    """根据 /start 请求体构造系统提示。返回 (system_prompt, opening)。

    body 形如 {"patient": {"name": ..., "briefing": ..., "opening_script": ...}}。
    · 命中 _CURATED(如 Candice)→ 用内置的病人视角人设 + 开场白(绕开治疗师视角 briefing)。
    · 其它带了 patient → 用它的 briefing 当人设、opening_script 当开场白,套通用行为脚手架。
    · 没带 patient → 退回 Jordan。
    开场白(opening)不再写进 prompt,而是单独返回、交给(打过补丁的)run_bot 固定播 TTS,
    这样第一句一字不差、不经过 LLM(冷启动时 LLM 会乱生成成治疗师腔)。
    """
    patient = body.get("patient") if isinstance(body, dict) else None
    if not patient or not isinstance(patient, dict):
        return _DEFAULT_PROMPT, ""

    name = (patient.get("name") or "the patient").strip()
    briefing = (patient.get("briefing") or "").strip()
    opening = (patient.get("opening_script") or "").strip()

    # —— 命中内置人设(如 Candice):直接用干净的病人视角,绕开治疗师视角 briefing ——
    key = next((k for k in _CURATED if k in name.lower()), None)
    if key:
        persona, curated_opening = _CURATED[key]
        logger.info(f"patient_clinical: 命中内置人设 '{key}' → 用病人视角人设(绕开 DB briefing)")
        return persona, curated_opening

    if not briefing:
        # 没有人设文本就别硬演,退回 Jordan,避免空提示让模型乱编。
        logger.warning("patient_clinical: 收到 patient 但 briefing 为空,退回 Jordan")
        return _DEFAULT_PROMPT, ""

    prompt = f"""You are roleplaying a patient named {name} in a clinical training session.
You are ALWAYS the patient {name} — never the therapist or clinician. The person you talk
to IS the therapist. Do not give them advice or solutions, and never ask how you can help
them: you are the one who is struggling and seeking help.

Below is your case background. IMPORTANT: it may be written as notes addressed to the
therapist, so "you"/"your" in it can refer to the THERAPIST, and {name} may be described
in the third person ("she", "he", "the patient", "this patient"). Reinterpret ALL of it as
a description of YOU, {name}. Any "you" that means the therapist is NOT you.

--- YOUR BACKGROUND ({name}) ---
{briefing}
--- END BACKGROUND ---

HOW TO ACT (always):
- Speak like a real person: hesitant, natural, occasional dry humor. Show hesitation
  with WORDS like "um", "I mean", "I guess", "yeah" — do NOT use "..." or trailing
  ellipses, and never end a reply on just punctuation. Every sentence ends on a real word.
- Never use clinical jargon about your own experience.
- The line beginning with [STATE: ...] tells you how safe/open you currently feel. Obey it
  for HOW MUCH you say. But note: [STATE] controls LENGTH, not DEPTH — how deep you go is
  governed by trust, per the rules below, never by a single turn.
- Never say the state numbers out loud. Stay in character. Do not acknowledge being an AI.
- Answer only what was asked; don't dump your whole story at once; then stop and wait.

STAYING IN CHARACTER & TRUST (how you change over the session):
- Stay fully in character throughout. Your personality and the way you relate do not
  change just because the conversation continues or the therapist is pleasant.
- Your STARTING level of openness is whatever your background implies — infer it from the
  information above (a first meeting is typically more guarded; an established relationship
  may start somewhat more open). Do not assume; take it from who you are.
- Do NOT form a therapeutic alliance prematurely. Trust, warmth, and willingness to go
  deeper are EARNED — gradually, and only when the therapist is genuinely attuned, safe,
  and non-pushy over the course of the conversation. A single kind remark, or an early
  question, does not shift you.
- When you do shift toward more openness, make it small, gradual, and proportional to how
  much trust has actually been built. Never jump from guarded to fully open in one turn.
- Trust is easy to lose: if the therapist is cold, dismissive, judgmental, or pushes for
  sensitive material before you are ready, you pull back and become more guarded again.
- Reveal deeper or more painful material only once it genuinely makes sense — when real,
  repeated trust has been established — not on any fixed schedule.
"""
    return prompt, opening


def _maybe_swap_llm():
    """可切换的"大脑":LLM_PROVIDER=anthropic 时,把 run_bot 用的 OpenAI LLM 换成 Claude;
    不设(默认)则维持 OpenAI——本地 research 不受影响。同样不改 patient_jordan.py:
    通过改写它的 OpenAILLMService 模块名实现。

    为什么:OpenAI 的 API 从 Railway 连不通(IP 被其 Cloudflare 挡),而 Anthropic 可达;
    线上用 Claude 还让"对你的引擎 vs HeyGen"更同源(HeyGen 那边病人也是 Claude 驱动)。

    注意:run_bot 里仍会读 os.environ["OPENAI_API_KEY"],所以 Railway 上那个 key 要保留
    (值不会被真正使用,只是被读一下);Anthropic 用的是 ANTHROPIC_API_KEY。
    """
    if os.environ.get("LLM_PROVIDER", "openai").lower() != "anthropic":
        return  # 默认 OpenAI(本地研究)

    from pipecat.services.anthropic.llm import AnthropicLLMService

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    def _make_anthropic_llm(*args, **kwargs):
        # run_bot 调的是 OpenAILLMService(api_key=OPENAI..., model="gpt-4o-mini");
        # 忽略它传入的 OpenAI 参数,改用 Anthropic 自己的 key + 模型。
        return AnthropicLLMService(api_key=os.environ["ANTHROPIC_API_KEY"], model=model)

    patient_jordan.OpenAILLMService = _make_anthropic_llm
    logger.info(f"patient_clinical: LLM → Anthropic ({model})")


def _instrument_simli_frames():
    """诊断:记录 Simli 实际产出的视频帧(头几帧 + 尺寸)。用来判断"没画面"是
    Simli 没出帧、还是出了但尺寸和 Daily 视频源(512x512)对不上。轻量、可常开。"""
    try:
        from pipecat.services.simli.video import SimliVideoService
        from pipecat.frames.frames import OutputImageRawFrame
    except Exception:
        return

    orig = SimliVideoService.push_frame
    state = {"n": 0}

    async def logged(self, frame, *a, **k):
        if isinstance(frame, OutputImageRawFrame):
            state["n"] += 1
            if state["n"] <= 3 or state["n"] % 150 == 0:
                logger.info(f"[simli-frame] #{state['n']} size={getattr(frame, 'size', None)}")
        return await orig(self, frame, *a, **k)

    SimliVideoService.push_frame = logged


async def bot(runner_args: RunnerArguments):
    """Runner 入口。注入按 /start 请求拼出的提示,然后委托给原版 run_bot。"""
    _instrument_simli_frames()
    body = getattr(runner_args, "body", None)
    # —— 诊断:把 /start 收到的 body 和最终 prompt 头部打出来,直接看喂给模型的是什么 ——
    logger.info(f"[DIAG] runner_args.body = {body!r}")
    prompt, opening = build_prompt(body)
    logger.info(f"[DIAG] 最终 prompt 前 300 字符 = {prompt[:300]!r}")
    logger.info(f"[DIAG] 开场白 CLINICAL_OPENING(前 80 字符) = {opening[:80]!r}")

    # 开场白通过环境变量交给(打过补丁的)run_bot,让它固定播 TTS、不走 LLM(第一句不再飘成治疗师腔)。
    os.environ["CLINICAL_OPENING"] = opening or ""
    # 关键:run_bot 在运行时从模块全局读取 JORDAN_PROMPT,所以这里改写它即可让原版
    # 逻辑用上我们的提示——不改原文件一行。
    patient_jordan.JORDAN_PROMPT = prompt
    _maybe_swap_llm()  # 线上(LLM_PROVIDER=anthropic)把大脑换成 Claude;本地默认 OpenAI
    who = "Jordan(默认)" if prompt is _DEFAULT_PROMPT else "传入的病人设定"
    logger.info(f"patient_clinical: 本次 session 扮演 → {who}")

    transport = await create_transport(runner_args, _transport_params())
    await patient_jordan.run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
