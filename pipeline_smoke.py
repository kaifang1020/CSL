# pipeline_smoke.py — 在真·pipecat 异步管线里跑桥（验证 _generate_loop / push 线程池 / 帧推送）
# 喂录好的数据：bethany.mp3=Jordan音频，data/user=治疗师音视频 → 桥 → 捕获 avatar 帧 → 存 mp4
# 在 AvatarForcing 目录、GPU 节点、afp 环境跑。不需要外网。
import asyncio
import glob

import cv2
import librosa
import numpy as np
import torch
import torchvision
from omegaconf import OmegaConf
from inference import InferenceAgent, seed_everything
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InputImageRawFrame,
    OutputImageRawFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.workers.runner import WorkerRunner
from avatarforcing_service import AvatarForcingVideoService, SR

# ---- 建 agent + 参考脸 ----
opt = OmegaConf.load("configs/inference.yaml")
opt.mae_ckpt_path = "pretrained_dir/motion_autoencoder.pth"
opt.ckpt_path = "pretrained_dir/flow_transformer.pth"
opt.result_dir = "results"
opt.rank, opt.ngpus = 0, 1
import inference
inference.opt = opt
seed_everything(25)
agent = InferenceAgent(opt)
_face = agent.data_processor.preprocess_face("data/simli.png")
avatar_ref = agent.data_processor.transform(image=_face)["image"].unsqueeze(0)


# ---- 捕获 sink ----
class Capture(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.frames = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, OutputImageRawFrame):
            self.frames.append(frame.image)
        await self.push_frame(frame, direction)


svc = AvatarForcingVideoService(agent=agent, avatar_ref=avatar_ref)
cap = Capture()
pipeline = Pipeline([svc, cap])

# ---- 载入录好的数据，造输入帧 ----
SECS = 4
av = (librosa.load("data/bethany.mp3", sr=SR)[0] * 32767).astype(np.int16)
us = (librosa.load("data/user.wav", sr=SR)[0] * 32767).astype(np.int16)
av = np.resize(av, SECS * SR)
us = np.resize(us, SECS * SR)
frame_paths = sorted(glob.glob("data/user/*.jpg"))[: SECS * 25]

input_frames = []
for p in frame_paths:                       # 治疗师视频帧（块时钟）
    img = cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]
    input_frames.append(InputImageRawFrame(image=img.tobytes(), size=(w, h), format="RGB"))
input_frames.append(TTSAudioRawFrame(audio=av.tobytes(), sample_rate=SR, num_channels=1))   # Jordan
input_frames.append(InputAudioRawFrame(audio=us.tobytes(), sample_rate=SR, num_channels=1))  # 治疗师


async def main():
    worker = PipelineWorker(pipeline, params=PipelineParams(), idle_timeout_secs=300)
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    run_fut = asyncio.ensure_future(runner.run())

    await asyncio.sleep(2)                       # 让 StartFrame → svc.start() → begin_live + 块时钟
    await worker.queue_frames(input_frames)      # 喂三路
    await asyncio.sleep(SECS + 5)                # 让块时钟把缓冲跑完、吐帧
    await worker.queue_frames([EndFrame()])
    await asyncio.sleep(2)
    if not run_fut.done():
        run_fut.cancel()

    print(f"\n捕获到 {len(cap.frames)} 个 avatar 视频帧")
    if cap.frames:
        arrs = [np.frombuffer(b, dtype=np.uint8).reshape(512, 512, 3) for b in cap.frames]
        torchvision.io.write_video("results/pipeline_smoke.mp4", torch.from_numpy(np.stack(arrs)), fps=25)
        print("已写 results/pipeline_smoke.mp4")
        print("🟢 桥在真异步管线里 work：输入帧 → 管线 → avatar 视频帧")
    else:
        print("✗ 没捕获到帧 —— 桥在真管线里有问题")


asyncio.run(main())
