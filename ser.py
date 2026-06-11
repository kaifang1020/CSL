"""
本地 SER(语音情绪识别)—— 让 Jordan 能感知治疗师"怎么说"。

工作方式:
  · 缓冲治疗师每一段话的原始音频(UserStartedSpeaking → UserStoppedSpeaking)
  · 这段话结束后,异步跑 wav2vec2 情绪分类
  · 算出 warmth ∈ [0,1](暖/冷),写进共享的 PatientState.therapist_warmth
  · PatientBrain 下一轮读它,和"关键词"一起决定状态变化

注意:
  · 这是 opt-in 模块,.env 里 SER=true 才会被加载
  · 首次用前请【先预下载模型】(见下方命令),别让它在 live session 里现下:
      python -c "from transformers import AutoFeatureExtractor, AutoModelForAudioClassification as M; \
        AutoFeatureExtractor.from_pretrained('superb/wav2vec2-base-superb-er'); \
        M.from_pretrained('superb/wav2vec2-base-superb-er'); print('SER model ready')"
  · 依赖:pip install transformers torch torchaudio
"""

import asyncio

import numpy as np
from loguru import logger

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)

# 同时认两种边界帧:专用 VADProcessor 发 VADUser*,其它来源发 User*
_START_FRAMES = (UserStartedSpeakingFrame, VADUserStartedSpeakingFrame)
_STOP_FRAMES = (UserStoppedSpeakingFrame, VADUserStoppedSpeakingFrame)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

SER_MODEL = "superb/wav2vec2-base-superb-er"  # ~360MB,4 类:neu/hap/ang/sad


class ToneAnalyzer(FrameProcessor):
    """缓冲治疗师语音 → 跑 SER → 写 state.therapist_warmth。"""

    def __init__(self, state, min_secs: float = 0.4):
        super().__init__()
        self.state = state
        self._buf = bytearray()
        self._sr = 16000
        self._collecting = False
        self._min_bytes = int(min_secs * 16000 * 2)  # int16 = 2 bytes/sample
        self._model = None
        self._lazy_load()  # 启动时一次性加载(主线程),避免多个分析线程并发 import 的竞争报错

    def _lazy_load(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForAudioClassification, Wav2Vec2FeatureExtractor

        # 限制 torch 占用的 CPU 核数,给 Simli 实时流留出 CPU(否则会被饿死掉线)
        torch.set_num_threads(2)
        logger.info(f"[SER] 加载模型 {SER_MODEL}(torch 限 2 线程)...")
        self._fe = Wav2Vec2FeatureExtractor.from_pretrained(SER_MODEL)
        self._model = AutoModelForAudioClassification.from_pretrained(SER_MODEL).eval()
        self._torch = torch
        self._id2label = {i: l.lower() for i, l in self._model.config.id2label.items()}
        logger.info(f"[SER] 就绪,labels={self._id2label}")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, _START_FRAMES):
            self._buf = bytearray()
            self._collecting = True
            logger.debug("[SER] 治疗师开始说话 → 开始缓冲")
        elif isinstance(frame, InputAudioRawFrame):
            if self._collecting:
                self._buf.extend(frame.audio)
                self._sr = frame.sample_rate
        elif isinstance(frame, _STOP_FRAMES):
            self._collecting = False
            data, sr = bytes(self._buf), self._sr
            logger.debug(f"[SER] 治疗师说完 → 收到 {len(data)} 字节 @ {sr}Hz")
            if len(data) >= self._min_bytes:
                asyncio.create_task(self._run(data, sr))

        await self.push_frame(frame, direction)

    async def _run(self, data: bytes, sr: int):
        try:
            warmth = await asyncio.get_event_loop().run_in_executor(
                None, self._infer, data, sr
            )
            self.state.therapist_warmth = warmth
            logger.info(f"[SER] therapist_warmth = {warmth:.2f}")
        except Exception as e:
            logger.warning(f"[SER] 分析失败,跳过:{e}")

    def _infer(self, data: bytes, sr: int) -> float:
        self._lazy_load()
        torch = self._torch
        wav = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if sr != 16000:
            import torchaudio

            wav = torchaudio.functional.resample(
                torch.from_numpy(wav), sr, 16000
            ).numpy()
        x = self._fe(wav, sampling_rate=16000, return_tensors="pt")
        with torch.no_grad():
            probs = torch.softmax(self._model(**x).logits, dim=-1)[0]
        p = {self._id2label[i]: float(probs[i]) for i in range(len(probs))}
        # 映射成 warmth:hap 最暖,neu 中性,sad 偏低,ang 最冷
        warmth = (
            p.get("hap", 0) * 1.0
            + p.get("neu", 0) * 0.55
            + p.get("sad", 0) * 0.40
            + p.get("ang", 0) * 0.0
        )
        # 打印每类概率,方便校准映射
        logger.info(
            f"[SER] probs neu={p.get('neu',0):.2f} hap={p.get('hap',0):.2f} "
            f"ang={p.get('ang',0):.2f} sad={p.get('sad',0):.2f} → warmth={warmth:.2f}"
        )
        return max(0.0, min(1.0, warmth))
