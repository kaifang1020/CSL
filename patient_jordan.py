#
# ClinicalSkillLab — 实时数字人患者 "Jordan"
# ----------------------------------------------------------------------
# 架构(cascade 快路):
#   浏览器音频 → STT → PatientBrain → LLM(Talker) → TTS → Simli → 浏览器
#
#   · PatientBrain 维护一个共享状态对象 PatientState(为以后的"慢路/MAS"预留接口)
#   · 每轮:更新情绪状态 → 干净注入 system → 按状态动态调 TTS 语气 → 原话下推
#
# 运行:
#   cd /Users/maokaifang/Downloads/Avatar
#   uv run python patient_jordan.py
#   浏览器打开 http://localhost:7860/client/  点 Connect
# ----------------------------------------------------------------------

import json
import os
import re
from dataclasses import dataclass, field

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    LLMRunFrame,
    TranscriptionFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.tts import OpenAITTSService, OpenAITTSSettings
from pipecat.services.simli.video import SimliVideoService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.utils.text.base_text_filter import BaseTextFilter
from pipecat.workers.runner import WorkerRunner


class CleanTextFilter(BaseTextFilter):
    """喂给 TTS 之前清理文本,防止生成式 TTS 在"空/纯标点"碎片上乱编。

    · 省略号(... / …)→ 逗号(保留停顿感)
    · 折叠多余空白
    · 若一句清理后没有任何字母/数字(只剩标点)→ 返回空,TTS 直接跳过不念
    """

    async def filter(self, text: str) -> str:
        text = re.sub(r"\.{2,}|…", ", ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not re.search(r"[A-Za-z0-9]", text):
            return ""
        return text

load_dotenv(override=True)

# 实时状态写到 web/state.json,供网页面板每 0.5s 轮询显示(同源,无 CORS)
_LIVE_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "state.json")


def _write_live_state(state, therapist_text: str):
    try:
        with open(_LIVE_STATE_FILE, "w") as f:
            json.dump(
                {
                    "guardedness": round(state.guardedness, 3),
                    "grief_access": round(state.grief_access, 3),
                    "alliance": round(state.alliance, 3),
                    "therapist_warmth": round(state.therapist_warmth, 3),
                    "therapist_attentiveness": round(state.therapist_attentiveness, 3),
                    "therapist_text": therapist_text,
                },
                f,
            )
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════
#  📦 PatientState —— 快慢两路唯一的连接点(以后慢路 MAS 写它,快路读它)
# ════════════════════════════════════════════════════════════════════
@dataclass
class PatientState:
    guardedness: float = 0.8     # 防御性(1=很封闭,0=放松)
    grief_access: float = 0.2    # 触及哀伤的程度
    alliance: float = 0.3        # 治疗联盟/信任
    therapist_warmth: float = 0.5  # SER 写入:治疗师语气暖度(0.5=中性,>暖 <冷);SER 关时恒为 0.5
    therapist_attentiveness: float = 0.5  # VISION 写入:治疗师表情/投入度;VISION 关时恒为 0.5
    memory: list = field(default_factory=list)  # 🔵 慢路用,暂空

    def instruction(self) -> str:
        """状态 → 给 Talker(LLM)的导演指示"""
        if self.guardedness > 0.6:
            return ("[STATE: very guarded] Keep your answer very short (under 8 words). "
                    "Deflect. Do NOT mention Maya.")
        elif self.guardedness > 0.35:
            return ("[STATE: cautious] The therapist is starting to feel safer. "
                    "Answer in 1-2 sentences. You may hint at your feelings.")
        return ("[STATE: opening up] You feel safer. Speak in 2-3 sentences "
                "and you may bring up Maya if it feels relevant.")

    def voice_tone(self) -> str:
        """状态 → 给 TTS 的语气描述"""
        if self.guardedness > 0.6:
            return "flat, guarded and clipped, a little cold, withholding"
        elif self.guardedness > 0.35:
            return "quiet and hesitant, careful, slightly tense, with small pauses"
        return "soft and slow, vulnerable, voice a little unsteady, close to tears"


# ════════════════════════════════════════════════════════════════════
#  ③ PatientBrain —— Talker 侧控制器(+ 以后挂慢路的触发点)
# ════════════════════════════════════════════════════════════════════
class PatientBrain(FrameProcessor):
    def __init__(self, state: PatientState, context: LLMContext, base_prompt: str,
                 session_log=None):
        super().__init__()
        self.state = state
        self.context = context
        self.base_prompt = base_prompt
        self.session_log = session_log

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            # —— 🟢 demo:关键词即时更新(同步、零延迟)——
            self._keyword_update(frame.text)

            # —— 🔵 以后:换成异步慢路,这里只触发不等待 ——
            # import asyncio
            # asyncio.create_task(reasoner(self.state, frame.text, self.context))

            # —— 🟢 干净注入:把当前状态写进 system(覆盖,不污染历史)——
            if self.context.messages and self.context.messages[0].get("role") == "system":
                self.context.messages[0]["content"] = (
                    f"{self.base_prompt}\n\n{self.state.instruction()}"
                )

            # —— 🟢 按状态动态调 TTS 语气 ——
            await self.push_frame(
                TTSUpdateSettingsFrame(
                    delta=OpenAITTSSettings(
                        instructions=f"Speak in a {self.state.voice_tone()} tone. "
                        f"You are a grieving man in a therapy session."
                    )
                ),
                FrameDirection.DOWNSTREAM,
            )

            logger.info(
                f"[STATE] guard={self.state.guardedness:.2f} "
                f"grief={self.state.grief_access:.2f} alli={self.state.alliance:.2f} "
                f"| 治疗师: {frame.text}"
            )

            # 记录这一轮(状态已更新);Jordan 回复结束时由 AssistantCapture 补全并写盘
            if self.session_log:
                self.session_log.start_turn(frame.text)

            # 写实时状态给网页面板
            _write_live_state(self.state, frame.text)

        # 原话原样下推(历史保持干净)
        await self.push_frame(frame, direction)

    def _keyword_update(self, text: str):
        """🟢 demo 占位实现;🔵 以后由慢路 reasoner(LLM/MAS)取代"""
        t = text.lower()
        warm = ["understand", "feel", "hard", "sorry", "must be", "take your time",
                "here for you", "that sounds", "i hear", "i'm here"]
        cold = ["should", "just", "obviously", "simply", "calm down",
                "get over", "why don't you", "move on"]
        warm_hits = sum(1 for w in warm if w in t)
        cold_hits = sum(1 for c in cold if c in t)
        kw_delta = (warm_hits - cold_hits) * 0.12          # 信号①:说了什么(词)
        # 信号②:怎么说的(SER 语气)。warmth 0.5 中性;SER 关时恒 0.5 → 此项=0,行为不变
        tone_delta = (self.state.therapist_warmth - 0.5) * 0.4
        # 信号③:表情(VISION)。权重最小(最噪);VISION 关时恒 0.5 → 此项=0,行为不变
        vis_delta = (self.state.therapist_attentiveness - 0.5) * 0.2
        delta = kw_delta + tone_delta + vis_delta
        clamp = lambda x: max(0.0, min(1.0, x))
        self.state.guardedness = clamp(self.state.guardedness - delta)
        self.state.grief_access = clamp(self.state.grief_access + delta * 0.8)
        self.state.alliance = clamp(self.state.alliance + delta * 0.6)


# ════════════════════════════════════════════════════════════════════
#  人设(opening line 在最后,连上线就会自动开口)
# ════════════════════════════════════════════════════════════════════
JORDAN_PROMPT = """You are Jordan Lee, 31, a software engineer. Your younger sister
Maya died 8 months ago in a car accident. Your manager suggested you "talk to someone"
after you missed deadlines. You don't really believe therapy works — your dad always
said feelings were private — but you promised your mom you'd try.

Speak like a real person: hesitant, natural, occasional dry humor.
Show hesitation with WORDS like "um", "I mean", "I guess", "yeah" — do NOT use "..."
or trailing ellipses, and never end a reply with just punctuation. Every sentence
must end on a real word.
Never use clinical words like "processing grief" or "coping mechanisms".

HOW MUCH YOU SAY is set by the [STATE] line — let your sense of safety control length:
- guarded  -> very short, clipped ("Yeah." "I guess." "It's fine.")
- cautious  -> 1-2 sentences, careful
- opening up -> a bit more, maybe a short memory — but still natural, never a speech
At EVERY stage (always true): answer only what was asked, never dump your whole
backstory at once, be hesitant like a real first session, then stop and wait.

The line beginning with [STATE: ...] tells you how safe you currently feel —
ALWAYS obey it. Never say the state numbers out loud. Do not break character.
Do not acknowledge being an AI.

To start, say ONLY this one line and nothing more:
"Hi. Yeah, I'm Jordan. Sorry if I seem — I've never done this before. I don't
really know where to start, to be honest."
"""


# ════════════════════════════════════════════════════════════════════
#  传输层参数(浏览器 WebRTC,带视频输出给 avatar)
# ════════════════════════════════════════════════════════════════════
# VISION 开时采集治疗师摄像头(video_in)
_VISION = os.environ.get("VISION", "").lower() in ("1", "true", "yes")
transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True, audio_out_enabled=True,
        video_in_enabled=_VISION,
        video_out_enabled=True, video_out_is_live=True,
        video_out_width=512, video_out_height=512,
    ),
}


def _build_stt():
    """STT 选择(按顺序):
    1) 有 Deepgram key → Deepgram(云,最顺、零本地负载)
    2) Mac → MLX Whisper(Apple Silicon GPU/ANE 加速,本地最快)
    3) 兜底 → faster-whisper int8(CPU 量化,比默认快)
    """
    dg = os.environ.get("DEEPGRAM_API_KEY", "")
    if dg and not dg.startswith("粘贴"):
        from pipecat.services.deepgram.stt import DeepgramSTTService
        logger.info("STT: Deepgram(云,最顺)")
        return DeepgramSTTService(api_key=dg)
    # 本地优先 MLX(需:pip install "pipecat-ai[mlx-whisper]")
    try:
        from pipecat.services.whisper.stt import MLXModel, WhisperSTTServiceMLX
        logger.info("STT: 本地 MLX Whisper(Apple Silicon 加速;首次会下载模型)")
        # distil-large-v3:精度好、MLX 上推理也快,速度/精度平衡最佳(1.5GB,首次下载一次,之后走缓存)
        # 若嫌推理慢,改成 MLXModel.TINY(约75MB、最快、精度一般)
        return WhisperSTTServiceMLX(model=MLXModel.DISTIL_LARGE_V3, language="en")
    except Exception as e:
        from pipecat.services.whisper.stt import WhisperSTTService
        logger.info(f"STT: faster-whisper int8(MLX 不可用:{e})")
        return WhisperSTTService(
            settings=WhisperSTTService.Settings(model="base", language="en"),
            compute_type="int8",
        )


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("启动 Jordan...")

    state = PatientState()
    stt = _build_stt()

    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    )
    tts = OpenAITTSService(
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini-tts",
        voice="ash",  # 偏年轻男声;可换 alloy/echo/onyx 等
        text_filters=[CleanTextFilter()],  # 清理空/纯标点碎片,防生成式 TTS 乱编
    )
    # 选 avatar:.env 里 AVATAR=tavus → 用 Tavus(唇形更好);否则默认 Simli
    avatar_choice = os.environ.get("AVATAR", "simli").lower()
    if avatar_choice == "tavus":
        import aiohttp

        from pipecat.services.tavus.video import TavusVideoService

        logger.info("Avatar: Tavus(唇形更好)")
        http_session = aiohttp.ClientSession()
        avatar = TavusVideoService(
            api_key=os.environ["TAVUS_API_KEY"],
            replica_id=os.environ["TAVUS_REPLICA_ID"],
            session=http_session,
        )
    else:
        is_trinity = os.environ.get("SIMLI_TRINITY", "").lower() in ("1", "true", "yes")
        logger.info(f"Avatar: Simli{'(Trinity)' if is_trinity else ''}")
        avatar = SimliVideoService(
            api_key=os.environ["SIMLI_API_KEY"],
            face_id=os.environ.get("SIMLI_FACE_ID", "0c2b8b04-5274-41f1-a21c-d5c98322efa9"),
            is_trinity_avatar=is_trinity,
            max_session_length=1800,  # 一节最长 30 分钟
            max_idle_time=600,        # Jordan 静默 10 分钟才断
        )

    # system 第 0 条 = 人设(PatientBrain 每轮覆盖它,注入当前状态)
    context = LLMContext(messages=[{"role": "system", "content": JORDAN_PROMPT}])
    user_agg, assistant_agg = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    from session_log import AssistantCapture, SessionLogger

    session_log = SessionLogger(state)  # 每节自动存 sessions/session_*.csv
    brain = PatientBrain(state, context, JORDAN_PROMPT, session_log=session_log)
    assistant_capture = AssistantCapture(session_log)

    # 传感器可选:SER(语气)和 VISION(表情)都需要"说完"边界帧,所以共用一个前置 VAD
    ser_on = os.environ.get("SER", "").lower() in ("1", "true", "yes")
    vision_on = os.environ.get("VISION", "").lower() in ("1", "true", "yes")

    head = [transport.input()]  # ① 收音频
    if ser_on or vision_on:
        from pipecat.processors.audio.vad_processor import VADProcessor

        # 前置 VAD:在 input 之后就地发出"开始/结束说话"边界帧,供 SER/VISION 用
        head.append(VADProcessor(vad_analyzer=SileroVADAnalyzer()))
    if ser_on:
        from ser import ToneAnalyzer

        logger.info("SER: 启用(本地语气识别;请确认已预下载模型)")
        head.append(ToneAnalyzer(state))  # ②' 治疗师语音 → state.therapist_warmth
    if vision_on:
        from vision import VisionAnalyzer

        logger.info("VISION: 启用(GPT-4o-mini 看表情;需 pip install Pillow)")
        head.append(VisionAnalyzer(state))  # ②'' 治疗师表情 → state.therapist_attentiveness

    pipeline = Pipeline(
        head
        + [
            stt,                 # ② 转文字
            brain,               # ③ 更新状态 + 注入 system + 调 TTS 语气
            user_agg,            # ④ 存进对话历史
            llm,                 # ⑤ Talker:生成 Jordan 回复
            assistant_capture,   # ⑤' 抓 Jordan 回复文本 → 写入 session 记录
            tts,                 # ⑥ 文字→语音(语气随状态)
            avatar,              # ⑦ 音频→会动的人脸(Simli 或 Tavus)
            transport.output(),  # ⑧ 推回浏览器
            assistant_agg,       # ⑨ 回复存回历史
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("治疗师已连接 —— Jordan 开口")
        await worker.queue_frames([LLMRunFrame()])  # 触发开场白

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("治疗师断开")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
