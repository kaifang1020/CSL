# import asyncio
# import os
# from pipecat.pipeline.pipeline import Pipeline
# from pipecat.pipeline.runner import PipelineRunner
# from pipecat.pipeline.task import PipelineTask, PipelineParams
# from pipecat.audio.vad.silero import SileroVADAnalyzer
# from pipecat.transports.local.audio import (
#     LocalAudioTransport,
#     LocalAudioTransportParams,
# )
# from pipecat.services.whisper.stt import WhisperSTTService
# from pipecat.services.openai.llm import OpenAILLMService
# from pipecat.services.openai.tts import OpenAITTSService
# from pipecat.processors.aggregators.llm_context import LLMContext
# from pipecat.processors.aggregators.llm_response_universal import (
#     LLMContextAggregatorPair,
#     LLMUserAggregatorParams,
# )

# # ── 患者人设 ──────────────────────────────────────
# PATIENT_PROMPT = """You are Jordan Lee, 31, a software engineer. Your younger
# sister Maya died 8 months ago in a car accident. You're in a therapy session.

# You are guarded and reserved at first. You give short answers. You don't
# volunteer information about Maya unless the therapist earns your trust through
# warmth and patience. If the therapist is cold, clinical, or rushes you, you
# become more closed off. Speak naturally, in 1-2 sentences. Never break character."""


# async def main():
#     # ① 音频输入输出
#     transport = LocalAudioTransport(
#         LocalAudioTransportParams(
#             audio_in_enabled=True,
#             audio_out_enabled=True,
#         )
#     )

#     # ② 听：语音 → 文字
#     stt = WhisperSTTService(model="small", language="en")

#     # ③ 想：文字 → 回应
#     llm = OpenAILLMService(
#         api_key=os.getenv("OPENAI_API_KEY"),
#         model="gpt-4o-mini",
#     )

#     # ④ 说：文字 → 语音
#     tts = OpenAITTSService(
#         api_key=os.getenv("OPENAI_API_KEY"),
#         voice="alloy",
#     )

#     # ⑤ 上下文
#     context = LLMContext(messages=[{"role": "system", "content": PATIENT_PROMPT}])

#     # ⑥ 聚合器：返回 user 和 assistant 两个，VAD 配在 user_params
#     user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
#         context,
#         user_params=LLMUserAggregatorParams(
#             vad_analyzer=SileroVADAnalyzer(),
#         ),
#     )

#     # ⑦ 串成 pipeline
#     pipeline = Pipeline([
#         transport.input(),
#         stt,
#         user_aggregator,
#         llm,
#         tts,
#         transport.output(),
#         assistant_aggregator,
#     ])

#     task = PipelineTask(pipeline)
#     runner = PipelineRunner()
#     await runner.run(task)


# if __name__ == "__main__":
#     asyncio.run(main())

import asyncio
import os
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame, TranscriptionFrame


# ════════════════════════════════════════════════════
#  PATIENT BRAIN
# ════════════════════════════════════════════════════
class PatientBrain(FrameProcessor):
    def __init__(self):
        super().__init__()
        # 三个状态变量
        self.guardedness = 0.8   # 防御性（1=非常防御，0=完全放松）
        self.disclosure = 0.1    # 披露意愿（1=愿意敞开，0=封闭）
        self.alliance = 0.3      # 治疗联盟（1=信任，0=不信任）

    def _update_state(self, text: str):
        t = text.lower()

        # 温暖/共情信号
        warm = ["understand", "feel", "hard", "sorry", "must be",
                "take your time", "here for you", "that sounds", "i hear"]
        # 冷漠/说教信号
        cold = ["just", "should", "obviously", "simply", "calm down",
                "get over", "why don't you", "move on"]

        warm_hits = sum(1 for w in warm if w in t)
        cold_hits = sum(1 for c in cold if c in t)

        delta = (warm_hits - cold_hits) * 0.12

        # 惯性更新：状态变化有阻力，不会瞬间跳变
        self.guardedness = max(0.0, min(1.0, self.guardedness - delta))
        self.disclosure  = max(0.0, min(1.0, self.disclosure + delta * 0.8))
        self.alliance    = max(0.0, min(1.0, self.alliance + delta * 0.6))

    def _state_instruction(self) -> str:
        # 把当前状态翻译成给 LLM 的指令
        if self.guardedness > 0.6:
            tone = ("You feel guarded and unsafe right now. Keep your answer "
                    "very short (under 8 words). Deflect. Do NOT mention Maya.")
        elif self.guardedness > 0.35:
            tone = ("You're cautious but the therapist is starting to feel safer. "
                    "Answer in 1-2 sentences. You might hint at your feelings.")
        else:
            tone = ("You feel safer and more willing to open up. You can speak "
                    "in 2-3 sentences and may bring up Maya if it feels relevant.")

        return (f"[Internal state — guardedness={self.guardedness:.2f}, "
                f"disclosure={self.disclosure:.2f}, alliance={self.alliance:.2f}] "
                f"{tone}")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # 拦截治疗师说的话
        if isinstance(frame, TranscriptionFrame):
            self._update_state(frame.text)

            # 在终端打印状态变化，方便你 demo 时展示
            print("\n" + "═" * 50)
            print(f"  治疗师: {frame.text}")
            print(f"  guardedness: {self.guardedness:.2f}  "
                  f"disclosure: {self.disclosure:.2f}  "
                  f"alliance: {self.alliance:.2f}")
            print("═" * 50 + "\n")

            # 把状态指令作为一条 system 消息插进去，再传原始话
            state_frame = TranscriptionFrame(
                text=f"{self._state_instruction()}\n\nTherapist says: {frame.text}",
                user_id=frame.user_id,
                timestamp=frame.timestamp,
            )
            await self.push_frame(state_frame, direction)
        else:
            await self.push_frame(frame, direction)


# ════════════════════════════════════════════════════
PATIENT_PROMPT = """You are Jordan Lee, 31, a software engineer. Your younger
sister Maya died 8 months ago in a car accident. You're in a therapy session.

Each therapist message is prefixed with your current internal emotional state
and an instruction for how to respond. ALWAYS obey that instruction — it reflects
how safe you feel. Never mention the state numbers out loud. Stay in character."""


async def main():
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        )
    )

    stt = WhisperSTTService(
        settings=WhisperSTTService.Settings(model="small", language="en")
    )
    patient_brain = PatientBrain()
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini")
    tts = OpenAITTSService(api_key=os.getenv("OPENAI_API_KEY"), voice="alloy")

    context = LLMContext(messages=[{"role": "system", "content": PATIENT_PROMPT}])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline([
        transport.input(),
        stt,
        patient_brain,        # ← 插在 STT 和聚合器之间
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])

    task = PipelineTask(pipeline)
    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())