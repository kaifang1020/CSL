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

import patient_jordan
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from loguru import logger

# 在任何改写发生前,先抓住原始的 Jordan 提示,作为"没传病人时"的兜底。
_DEFAULT_PROMPT = patient_jordan.JORDAN_PROMPT


def build_prompt(body) -> str:
    """根据 /start 请求体构造系统提示。

    body 形如 {"patient": {"name": ..., "briefing": ..., "opening_script": ...}}。
    带了 patient 就用它的 briefing 当人设、opening_script 当开场白,并套上一层通用的
    "怎么扮演"行为脚手架(从 JORDAN_PROMPT 抽象出来、不含具体人物);否则退回 Jordan。
    """
    patient = body.get("patient") if isinstance(body, dict) else None
    if not patient or not isinstance(patient, dict):
        return _DEFAULT_PROMPT

    name = (patient.get("name") or "the patient").strip()
    briefing = (patient.get("briefing") or "").strip()
    opening = (patient.get("opening_script") or "").strip()

    if not briefing:
        # 没有人设文本就别硬演,退回 Jordan,避免空提示让模型乱编。
        logger.warning("patient_clinical: 收到 patient 但 briefing 为空,退回 Jordan")
        return _DEFAULT_PROMPT

    opening_block = (
        f'To start, say ONLY this one line and nothing more:\n"{opening}"'
        if opening
        else "To start, greet the clinician briefly and naturally in ONE short line, "
        "then stop and wait."
    )

    return f"""You are roleplaying a patient named {name} in a clinical training session.

{briefing}

HOW TO ACT (always):
- Speak like a real person: hesitant, natural, occasional dry humor. Show hesitation
  with WORDS like "um", "I mean", "I guess", "yeah" — do NOT use "..." or trailing
  ellipses, and never end a reply on just punctuation. Every sentence ends on a real word.
- Never use clinical jargon about your own experience.
- The line beginning with [STATE: ...] tells you how safe/open you currently feel —
  ALWAYS obey it for HOW MUCH you say (guarded -> very short and clipped; cautious ->
  1-2 sentences; opening up -> a bit more, maybe a short detail — but never a speech).
- Never say the state numbers out loud. Stay in character. Do not acknowledge being an AI.
- Answer only what was asked; don't dump your whole story at once; then stop and wait,
  hesitant like a real first session.

{opening_block}
"""


async def bot(runner_args: RunnerArguments):
    """Runner 入口。注入按 /start 请求拼出的提示,然后委托给原版 run_bot。"""
    body = getattr(runner_args, "body", None)
    prompt = build_prompt(body)

    # 关键:run_bot 在运行时从模块全局读取 JORDAN_PROMPT,所以这里改写它即可让原版
    # 逻辑用上我们的提示——不改原文件一行。
    patient_jordan.JORDAN_PROMPT = prompt
    who = "Jordan(默认)" if prompt is _DEFAULT_PROMPT else "传入的病人设定"
    logger.info(f"patient_clinical: 本次 session 扮演 → {who}")

    transport = await create_transport(runner_args, patient_jordan.transport_params)
    await patient_jordan.run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
