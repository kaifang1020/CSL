# smoke_bridge.py — 隔离测试 AvatarForcingVideoService 的核心数据通路
# 不走 Pipecat 异步框架，直接喂假帧/填缓冲，验证：转换助手 + 块组装 + push + 出帧
# 放在 AvatarForcing 目录跑（要能 import streaming / inference / avatarforcing_service）
import numpy as np
import torch
from omegaconf import OmegaConf
from inference import InferenceAgent, seed_everything
from pipecat.frames.frames import (
    InputImageRawFrame,
    OutputImageRawFrame,
    TTSAudioRawFrame,
)
from avatarforcing_service import AvatarForcingVideoService, SR, SPF, NB

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
avatar_ref = agent.data_processor.preprocess(
    avatar_ref_path="data/simli.png", avatar_audio_path="data/bethany.mp3",
    user_audio_path="data/user.wav", user_video_path="data/user/")["avatar_ref"]

# ---- 建桥（不进 pipeline，直接测核心逻辑）----
svc = AvatarForcingVideoService(agent=agent, avatar_ref=avatar_ref)
svc._engine.begin_live(avatar_ref)        # start() 里做的事
print("✓ 桥已创建 + 引擎 begin_live")

# ---- 1) 转换助手单测 ----
tts = TTSAudioRawFrame(
    audio=(np.random.randn(int(0.4 * 24000)) * 2000).astype(np.int16).tobytes(),
    sample_rate=24000, num_channels=1)
b16 = svc._to_16k_mono(tts)
print(f"✓ _to_16k_mono: 24k 0.4s → {len(b16)} bytes (期望 {int(0.4 * SR) * 2})")

img = InputImageRawFrame(
    image=(np.random.rand(480, 640, 3) * 255).astype(np.uint8).tobytes(),
    size=(640, 480), format="RGB")
t = svc._to_engine_frame(img)
print(f"✓ _to_engine_frame: 640x480 → {tuple(t.shape)} (期望 (1,3,512,512))")

# ---- 2) 填缓冲（80 帧 ≈ 3.2s，够首块 50 + 前瞻）----
N = 80
svc._avatar_pcm += (np.random.randn(N * SPF) * 2000).astype(np.int16).tobytes()   # 假"说话"
svc._user_pcm += (np.random.randn(N * SPF) * 1000).astype(np.int16).tobytes()
for _ in range(N):
    svc._user_frames.append(svc._to_engine_frame(img))
print(f"✓ 填入 {N} 帧三路数据")

# ---- 3) 跑块时钟（同步版，模拟 _generate_loop）----
emitted = []
while len(svc._user_frames) >= NB:
    block = svc._take_block()
    if block is None:
        break
    result = svc._engine_push(*block)
    for blk in result:
        for i in range(blk.shape[0]):
            emitted.append(svc._to_output_frame(blk[i]))
print(f"✓ 块时钟跑完，共吐出 {len(emitted)} 个 OutputImageRawFrame")

# ---- 4) 检查输出帧合法 ----
if emitted:
    f = emitted[0]
    ok = (isinstance(f, OutputImageRawFrame) and f.size == (512, 512)
          and f.format == "RGB" and len(f.image) == 512 * 512 * 3)
    print(f"{'✓' if ok else '✗'} 首帧: type={type(f).__name__} size={f.size} "
          f"format={f.format} bytes={len(f.image)} (期望 {512 * 512 * 3})")
    print("\n🟢 桥冒烟测试通过：假帧进 → 视频帧出" if ok else "\n✗ 输出帧格式不对")
else:
    print("\n✗ 没吐出任何帧 —— push 没攒够或有 bug")
