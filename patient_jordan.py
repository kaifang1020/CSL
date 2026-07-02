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
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    Frame,
    LLMRunFrame,
    MetricsFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.metrics.metrics import TTFBMetricsData
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
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
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


def _write_live_state(state):
    try:
        with open(_LIVE_STATE_FILE, "w") as f:
            json.dump(
                {
                    "guardedness": round(state.guardedness, 3),
                    "grief_access": round(state.grief_access, 3),
                    "alliance": round(state.alliance, 3),
                    "therapist_warmth": round(state.therapist_warmth, 3),
                    "therapist_attentiveness": round(state.therapist_attentiveness, 3),
                    "therapist_text": state.last_therapist_text,
                    "latency_total": round(state.last_latency, 2),
                    "latency_think": round(state.last_think, 2),
                    "latency_speak": round(state.last_speak, 2),
                    "component_ttfb": state.component_ttfb,
                },
                f,
            )
    except Exception:
        pass


def _friendly(proc: str) -> str:
    """把 processor 名(OpenAILLMService#0 等)映射成友好名。"""
    p = proc.lower()
    if "stt" in p or "deepgram" in p or "whisper" in p:
        return "STT"
    if "llm" in p:
        return "LLM"
    if "tts" in p:
        return "TTS"
    if "simli" in p or "tavus" in p or "video" in p:
        return "Avatar"
    return ""


class LatencyTracker(FrameProcessor):
    """测"治疗师说完 → Jordan 第一段音频"的总延迟(拆 think/speak),
    并顺手收集各组件 TTFB(STT/LLM/TTS/Avatar),写进 state + 日志 + UI。"""

    def __init__(self, state):
        super().__init__()
        self.state = state

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        # 各组件 TTFB:从流经的 MetricsFrame 里收集
        if isinstance(frame, MetricsFrame):
            for d in frame.data:
                if isinstance(d, TTFBMetricsData) and d.value:
                    name = _friendly(d.processor)
                    if name:
                        self.state.component_ttfb[name] = round(d.value, 2)
        if isinstance(frame, TTSAudioRawFrame) and self.state.turn_start > 0:
            now = time.monotonic()
            total = now - self.state.turn_start
            llm_first = self.state.llm_first or now
            think = max(0.0, llm_first - self.state.turn_start)  # STT尾 + LLM首字
            speak = max(0.0, now - llm_first)                    # LLM首字 → 第一段音频(TTS)
            self.state.last_latency, self.state.last_think, self.state.last_speak = total, think, speak
            self.state.turn_start = 0.0  # 本轮已测,后续音频块不再重复计
            logger.info(f"⏱ 延迟:总 {total:.2f}s(想 {think:.2f}s + 说 {speak:.2f}s)")
            _write_live_state(self.state)
        await self.push_frame(frame, direction)


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
    # —— 延迟测量(运行时用,不进 CSV)——
    turn_start: float = 0.0          # 治疗师这轮被判定说完的时刻
    llm_first: float = 0.0           # LLM 吐第一个字的时刻
    last_latency: float = 0.0        # 上轮"说完→Jordan开口"总延迟(秒)
    last_think: float = 0.0          # 其中"想"(STT尾+LLM首字)耗时
    last_speak: float = 0.0          # 其中"说"(LLM首字→第一段音频)耗时
    last_therapist_text: str = ""    # 上轮治疗师说的话(给 UI 显示)
    component_ttfb: dict = field(default_factory=dict)  # 各组件本轮 TTFB {STT/LLM/TTS/Avatar: 秒}

    def instruction(self) -> str:
        """状态 → 给 Talker(LLM)的导演指示"""
        if self.guardedness > 0.6:
            return ("[STATE: very guarded] Keep your answer very short (under 8 words). "
                    "Deflect. Do NOT bring up your deepest or most painful topic.")
        elif self.guardedness > 0.35:
            return ("[STATE: cautious] The therapist is starting to feel safer. "
                    "Answer in 1-2 sentences. You may hint at your feelings.")
        return ("[STATE: opening up] You feel safer. Speak in 2-3 sentences "
                "and you may begin to touch your deeper pain if it feels relevant.")

    def voice_tone(self) -> str:
        """状态 → 给 OpenAI TTS 的自然语言语气描述"""
        if self.guardedness > 0.6:
            return "flat, guarded and clipped, a little cold, withholding"
        elif self.guardedness > 0.35:
            return "quiet and hesitant, careful, slightly tense, with small pauses"
        return "soft and slow, vulnerable, voice a little unsteady, close to tears"

    def voice_cartesia(self):
        """状态 → 给 Cartesia 的 (emotion, speed)"""
        if self.guardedness > 0.6:
            return ("neutral", 1.0)   # 防御:平直、不慢
        elif self.guardedness > 0.35:
            return ("neutral", 0.9)   # 谨慎:稍慢
        return ("sad", 0.8)           # 敞开:脆弱、更慢


# ════════════════════════════════════════════════════════════════════
#  ③ PatientBrain —— Talker 侧控制器(+ 以后挂慢路的触发点)
# ════════════════════════════════════════════════════════════════════
class PatientBrain(FrameProcessor):
    def __init__(self, state: PatientState, context: LLMContext, base_prompt: str,
                 session_log=None, tts_kind: str = "openai"):
        super().__init__()
        self.state = state
        self.context = context
        self.base_prompt = base_prompt
        self.session_log = session_log
        self.tts_kind = tts_kind  # "openai" 或 "cartesia",决定语气设置怎么构造
        # SER / VISION 对患者状态的【驱动权重】:默认 0 = 只测量/显示,不影响患者回应
        # (患者只按 transcript + 人设反应);在 .env 设 SER_WEIGHT / VISION_WEIGHT >0 即可让它们重新驱动。
        self.w_tone = float(os.environ.get("SER_WEIGHT", "0"))
        self.w_vision = float(os.environ.get("VISION_WEIGHT", "0"))

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

            # —— 🟢 按状态动态调 TTS 语气(按当前 TTS 类型构造对应设置)——
            if self.tts_kind == "cartesia":
                from pipecat.services.cartesia.tts import (
                    CartesiaTTSSettings,
                    GenerationConfig,
                )

                emotion, speed = self.state.voice_cartesia()
                tts_delta = CartesiaTTSSettings(
                    generation_config=GenerationConfig(emotion=emotion, speed=speed)
                )
            else:
                tts_delta = OpenAITTSSettings(
                    instructions=f"Speak in a {self.state.voice_tone()} tone. "
                    f"You are a grieving man in a therapy session."
                )
            await self.push_frame(
                TTSUpdateSettingsFrame(delta=tts_delta), FrameDirection.DOWNSTREAM
            )

            logger.info(
                f"[STATE] guard={self.state.guardedness:.2f} "
                f"grief={self.state.grief_access:.2f} alli={self.state.alliance:.2f} "
                f"| 治疗师: {frame.text}"
            )

            # 记录这一轮(状态已更新);Jordan 回复结束时由 AssistantCapture 补全并写盘
            if self.session_log:
                self.session_log.start_turn(frame.text)

            # 延迟测量:标记这轮开始
            self.state.last_therapist_text = frame.text
            self.state.turn_start = time.monotonic()
            self.state.llm_first = 0.0
            self.state.component_ttfb = {}  # 清空,重新收集本轮各组件 TTFB

            # 写实时状态给网页面板
            _write_live_state(self.state)

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
        kw_delta = (warm_hits - cold_hits) * 0.03          # 信号①:说了什么(词 / transcript)——始终驱动
        # 注:每个暖词只挪 0.03(原为 0.12)。放慢是为了别让一两句共情就把 guardedness 打穿、
        #     2-3 轮就 opening up。这是"半步"权宜之计;真正的解法是带惯性/非对称/阈值的
        #     状态动力学(见 patient_state_dynamics.py),会整体替换本函数。
        # 信号②/③:SER 语气 + VISION 表情。默认权重 0 → 只测量、不驱动患者(模式 B)。
        # SER/VISION 仍照常运行、写入 state、显示在面板;只是不影响患者状态,除非把权重设 >0。
        tone_delta = (self.state.therapist_warmth - 0.5) * 0.4 * self.w_tone
        vis_delta = (self.state.therapist_attentiveness - 0.5) * 0.2 * self.w_vision
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
_AF = os.environ.get("AVATAR", "").lower() == "avatarforcing"  # 自建引擎要摄像头驱动反应
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True, audio_out_enabled=True,
        video_in_enabled=_VISION or _AF,
        video_out_enabled=True, video_out_is_live=True,
        video_out_width=512, video_out_height=512,
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True, audio_out_enabled=True,
        video_in_enabled=_VISION or _AF,
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


def _build_tts():
    """TTS 选择:.env 里 TTS=cartesia → Cartesia(低延迟);否则默认 OpenAI。
    返回 (kind, service)。kind 用来告诉 PatientBrain 怎么构造语气设置。"""
    kind = os.environ.get("TTS", "openai").lower()
    if kind == "cartesia":
        from pipecat.services.cartesia.tts import CartesiaTTSService

        logger.info("TTS: Cartesia(低延迟,需 pip install 'pipecat-ai[cartesia]')")
        return "cartesia", CartesiaTTSService(
            api_key=os.environ["CARTESIA_API_KEY"],
            voice_id=os.environ.get(
                "CARTESIA_VOICE_ID", "71a7ad14-091c-4e8e-a314-022ece01c121"
            ),
            text_filters=[CleanTextFilter()],
        )
    logger.info("TTS: OpenAI gpt-4o-mini-tts")
    return "openai", OpenAITTSService(
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini-tts",
        voice="ash",
        text_filters=[CleanTextFilter()],
    )


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("启动 Jordan...")

    state = PatientState()
    stt = _build_stt()

    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    )
    tts_kind, tts = _build_tts()  # 默认 OpenAI;.env 设 TTS=cartesia 即切 Cartesia
    # 选 avatar:AVATAR=avatarforcing → 自建流式引擎;=tavus → Tavus;否则默认 Simli
    avatar_choice = os.environ.get("AVATAR", "simli").lower()
    if avatar_choice == "avatarforcing":
        from omegaconf import OmegaConf

        from avatarforcing_service import AvatarForcingVideoService
        from inference import InferenceAgent

        logger.info("Avatar: AvatarForcing(自建流式引擎,加载模型中…)")
        af_opt = OmegaConf.load("configs/inference.yaml")
        af_opt.mae_ckpt_path = "pretrained_dir/motion_autoencoder.pth"
        af_opt.ckpt_path = "pretrained_dir/flow_transformer.pth"
        af_opt.result_dir = "results"
        af_opt.rank, af_opt.ngpus = 0, 1
        import inference as _inf

        _inf.opt = af_opt
        af_agent = InferenceAgent(af_opt)
        _face = af_agent.data_processor.preprocess_face(os.environ.get("AF_FACE", "data/simli.png"))
        af_ref = af_agent.data_processor.transform(image=_face)["image"].unsqueeze(0)
        avatar = AvatarForcingVideoService(agent=af_agent, avatar_ref=af_ref)
    elif avatar_choice == "tavus":
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
        from pipecat.services.simli.video import SimliVideoService

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
    # 端点检测:smart_turn 默认静音兜底 stop_secs=3s(语义判不出"说完"时白等 3 秒,延迟大头)→ 调小。
    # 可用 AF_STOP_SECS 调(小=更跟手但易在停顿处抢话；大=更耐心)。
    from pipecat.turns.user_turn_strategies import UserTurnStrategies
    from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
    from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
    from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
    _stop_secs = float(os.environ.get("AF_STOP_SECS", "1.5"))
    _turn_strats = UserTurnStrategies(stop=[
        TurnAnalyzerUserTurnStopStrategy(
            turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams(stop_secs=_stop_secs)))])
    logger.info(f"端点检测 stop_secs={_stop_secs}s(默认 3s；语义判不出时的静音兜底)")
    user_agg, assistant_agg = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(), user_turn_strategies=_turn_strats),
    )

    from session_log import AssistantCapture, SessionLogger

    session_log = SessionLogger(state)  # 每节自动存 sessions/session_*.csv
    brain = PatientBrain(state, context, JORDAN_PROMPT, session_log=session_log, tts_kind=tts_kind)
    assistant_capture = AssistantCapture(session_log, state)
    latency_tracker = LatencyTracker(state)

    # 传感器可选:SER(语气)和 VISION(表情)都需要"说完"边界帧,所以共用一个前置 VAD
    # 研究用传感器：SER(语气→warmth)、VISION(表情→attentiveness)。两者权重默认 0(只测量、不驱动病人)，
    # AvatarForcing 模式下都暂不需要 → 默认都不挂。SER 轻(本地 wav2vec2)但占 GPU；
    # VISION 重(GPT-4o-mini)且挂在 STT 之前的临界路径上，会把"说完→调 LLM"堵几秒，更要关。要用再单独开。
    _ser_env = os.environ.get("SER", "").lower() in ("1", "true", "yes")
    _vision_env = os.environ.get("VISION", "").lower() in ("1", "true", "yes")
    ser_on = _ser_env and not _AF
    vision_on = _vision_env and not _AF
    if _AF and (_ser_env or _vision_env):
        logger.info(f"传感器已跳过(AVATAR=avatarforcing 下暂不需要): SER={_ser_env} VISION={_vision_env}")

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
            latency_tracker,     # ⑥' 测响应延迟(治疗师说完→Jordan开口)
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
        from pipecat.runner.utils import maybe_capture_participant_camera

        # ⚠️ 必须传 framerate>0：helper 默认 framerate=0，Daily 内部 `if framerate>0` 才推帧，
        # 否则订阅成功但一帧 InputImageRawFrame 都不进管线（cam_total=0 的根因）。25 匹配引擎 25fps/NB=10。
        await maybe_capture_participant_camera(transport, client, framerate=25)  # 治疗师摄像头(VISION + avatar 反应靠它)
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
