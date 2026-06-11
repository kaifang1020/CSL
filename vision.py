"""
摄像头视觉:让 Jordan 感知治疗师的表情/投入度。
· VisionProbe     —— Step1 探路,只打印收到的帧(不调 API)
· VisionAnalyzer  —— Step2 真分析:每轮抓一帧 → GPT-4o-mini 看图 → 写 state.therapist_attentiveness

云端视觉,不吃本地 CPU(不会像本地模型那样搞崩 Simli)。
依赖:pip install Pillow   (openai 已随 pipecat 安装)
opt-in:.env 里 VISION=true 才加载。
"""

import asyncio
import base64
import io
import json
import os

from loguru import logger

from pipecat.frames.frames import (
    Frame,
    InputImageRawFrame,
    UserStoppedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

_STOP_FRAMES = (UserStoppedSpeakingFrame, VADUserStoppedSpeakingFrame)

VISION_PROMPT = (
    "You see a still frame from a therapist's webcam during a therapy session. "
    "Judge their facial expression and how engaged/present they look toward the patient. "
    'Reply with JSON ONLY: {"warmth": 0.0-1.0, "attentiveness": 0.0-1.0, '
    '"expression": "2-4 word description"}. '
    "warmth=how warm/caring the face looks; attentiveness=how engaged vs distracted."
)


class VisionProbe(FrameProcessor):
    """Step1:只打印收到的视频帧(节流),验证摄像头是否真的流进来。"""

    def __init__(self, log_every: int = 30):
        super().__init__()
        self._n = 0
        self._log_every = log_every

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputImageRawFrame):
            self._n += 1
            if self._n % self._log_every == 1:
                w, h = frame.size
                logger.info(
                    f"[VISION] 收到帧 #{self._n}  {w}x{h}  {len(frame.image)} bytes  fmt={frame.format}"
                )
        await self.push_frame(frame, direction)


class VisionAnalyzer(FrameProcessor):
    """Step2:每轮(说完时)抓最新一帧 → GPT-4o-mini 看图 → 写 state.therapist_attentiveness。"""

    def __init__(self, state, model: str = "gpt-4o-mini"):
        super().__init__()
        self.state = state
        self._model = model
        self._latest = None  # (image_bytes, size, format)
        self._client = None
        self._frame_count = 0

    def _client_lazy(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        return self._client

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputImageRawFrame):
            self._latest = (frame.image, frame.size, frame.format)
            self._frame_count += 1
            if self._frame_count % 30 == 1:  # 节流:约每秒一条
                logger.info(f"[VISION] 收到视频帧 #{self._frame_count}  {frame.size}")
        elif isinstance(frame, _STOP_FRAMES):
            if self._latest is not None:
                asyncio.create_task(self._analyze(self._latest))
            else:
                logger.warning(
                    "[VISION] 治疗师说完,但至今没收到任何视频帧 —— "
                    "屏幕共享可能没把视频送到 bot(或 video_in 没生效)"
                )
        await self.push_frame(frame, direction)

    async def _analyze(self, img):
        try:
            b64 = await asyncio.get_event_loop().run_in_executor(None, self._encode, img)
            result = await self._call_vision(b64)
            warmth = float(result.get("warmth", 0.5))
            att = float(result.get("attentiveness", 0.5))
            signal = max(0.0, min(1.0, (warmth + att) / 2))
            self.state.therapist_attentiveness = signal
            logger.info(
                f"[VISION] {result.get('expression','?')}  "
                f"warmth={warmth:.2f} att={att:.2f} → signal={signal:.2f}"
            )
        except Exception as e:
            logger.warning(f"[VISION] 分析失败,跳过:{e}")

    def _encode(self, img) -> str:
        from PIL import Image

        image_bytes, size, fmt = img
        pil = Image.frombytes(fmt or "RGB", size, image_bytes)
        buf = io.BytesIO()
        pil.convert("RGB").save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()

    async def _call_vision(self, b64: str) -> dict:
        resp = await self._client_lazy().chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "low",  # 低分辨率,省钱够用
                            },
                        },
                    ],
                }
            ],
            max_tokens=60,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
