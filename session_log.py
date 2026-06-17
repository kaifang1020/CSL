"""
把每一节 session 记录到文件:每轮 = 治疗师的话 + Jordan 的回复 + 当时的状态。
产出:sessions/session_YYYYmmdd_HHMMSS.csv(给画图/统计)和 .jsonl(给程序读)。

用法:
  log = SessionLogger(state)                 # 创建(自动按时间命名文件)
  PatientBrain 在每轮更新完状态后调用 log.start_turn(治疗师文本)
  AssistantCapture 在 Jordan 回复结束时调用 log.finish_turn(Jordan文本) → 写入一行
"""

import csv
import datetime
import json
import os
import time

from loguru import logger

from pipecat.frames.frames import Frame, LLMFullResponseEndFrame, LLMTextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

_COLS = [
    "turn", "time", "therapist", "jordan",
    "guardedness", "grief_access", "alliance",
    "therapist_warmth", "therapist_attentiveness",
]


class SessionLogger:
    """累计每轮记录,写 CSV + JSONL。"""

    def __init__(self, state, out_dir="sessions"):
        self.state = state
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_path = os.path.join(out_dir, f"session_{ts}.csv")
        self.jsonl_path = os.path.join(out_dir, f"session_{ts}.jsonl")
        self.turn = 0
        self._pending = None
        with open(self.csv_path, "w", newline="") as f:
            csv.writer(f).writerow(_COLS)
        logger.info(f"[LOG] 本节记录到 {self.csv_path}")

    def start_turn(self, therapist_text: str):
        """治疗师说完、状态已更新时调用:暂存这一轮(等 Jordan 回复)。"""
        self._pending = {
            "time": datetime.datetime.now().isoformat(timespec="seconds"),
            "therapist": therapist_text.strip(),
            "guardedness": round(self.state.guardedness, 3),
            "grief_access": round(self.state.grief_access, 3),
            "alliance": round(self.state.alliance, 3),
            "therapist_warmth": round(self.state.therapist_warmth, 3),
            "therapist_attentiveness": round(self.state.therapist_attentiveness, 3),
        }

    def finish_turn(self, jordan_text: str):
        """Jordan 回复结束时调用:补上回复并写入一行。"""
        if not self._pending:
            return  # 开场白没有对应的治疗师轮,跳过
        self.turn += 1
        row = {"turn": self.turn, **self._pending, "jordan": jordan_text.strip()}
        self._pending = None
        try:
            with open(self.csv_path, "a", newline="") as f:
                csv.writer(f).writerow([row[c] for c in _COLS])
            with open(self.jsonl_path, "a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            logger.info(f"[LOG] 第 {row['turn']} 轮已记录")
        except Exception as e:
            logger.warning(f"[LOG] 写入失败,跳过:{e}")


class AssistantCapture(FrameProcessor):
    """累计 Jordan 的流式回复文本,回复结束时交给 SessionLogger 写入。"""

    def __init__(self, session_log: SessionLogger, state=None):
        super().__init__()
        self.log = session_log
        self.state = state  # 用于记录 LLM 吐第一个字的时刻(延迟测量)
        self._buf = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame):
            # 记录这轮 LLM 第一个字的时刻(给延迟拆分用)
            if self.state is not None and self.state.turn_start > 0 and self.state.llm_first == 0:
                self.state.llm_first = time.monotonic()
            self._buf.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            text = "".join(self._buf).strip()
            self._buf = []
            if text:
                self.log.finish_turn(text)
        await self.push_frame(frame, direction)
