"""
AvatarForcingVideoService — 把 AvatarForcing 流式引擎接进 Pipecat 的桥（v2）。

放在管线里 SimliVideoService 的位置：吃 TTS 音频 + 治疗师音视频，吐 avatar 视频帧。
依赖：streaming.py(StreamingAvatarForcing) + inference.py(InferenceAgent) 要在 import 路径上。

v2 相比 v1 的两个核心改动：
  · 防漂移：沉默时不喂引擎、画面冻在上一帧（掐掉"空转累积误差"）；说完补几块静音 flush 句尾。
  · 防卡顿：生成与播放分离 —— 后台尽快生成丢进队列，另一循环严格 25fps 发帧 + 同步音频。

仍保留的 v1 简化（TODO，跑顺后再打磨）：
  · 音频重采样用线性插值（应换 av.AudioResampler / torchaudio）
  · 治疗师人脸直接 resize（应加 face_alignment 裁剪）
  · 逐块 wav2vec 归一化的细微差异
  · 长会话跨句残余漂移（如仍明显，再加"按句/定期重锚"）
"""
import asyncio
import os

import numpy as np
import torch
from loguru import logger

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InputImageRawFrame,
    OutputAudioRawFrame,
    OutputImageRawFrame,
    StartFrame,
    InterruptionFrame,
    TTSAudioRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.ai_service import AIService

from streaming import StreamingAvatarForcing

SR = 16000              # 引擎要的采样率
FPS = 25                # 输出帧率
NB = 10                 # 一块帧数（0.4s）
SPF = SR // FPS         # 每帧采样数 = 640
BYTES_PER_BLOCK = NB * SPF * 2   # 一块的 16k s16 字节数
FLUSH_BLOCKS = 2        # 说完后再补几块静音，把句尾不足前瞻的帧挤出来
# 被打断时补更多静音块：从半句中途切断，嘴正张着发音，2 块(0.8s)可能闭不回去。
FLUSH_INTERRUPT = int(os.environ.get("AF_FLUSH_INTERRUPT", "3"))   # 3 块≈1.2s

# 双模式 cfg（可调）：说话求干净对口型(弱反应)，倾听求强反应(真人脸/语音驱动)
U_SPEAK = float(os.environ.get("AF_U_SPEAK", "0.0"))
U_LISTEN = float(os.environ.get("AF_U_LISTEN", "1.0"))
# ★a_cfg 同样分模式。原先它定死在构造函数(=2.0)、全程不切，倾听时是个隐性的"别动"压制源：
#   合成式 v = v_uncond + a_cfg*(v_aud - v_uncond) + u_cfg*(v_user - v_uncond)；
#   倾听时喂给 wa 的是纯静音 → (v_aud - v_uncond) 这个方向就是"闭嘴不发声的静止感"，
#   还被 ×2 夸张化，正好和 u_cfg=1.0 推的"对治疗师有反应"对着干。调低它把这股力松开。
#   默认 2.0 = 保持原行为，不改任何东西。
A_SPEAK = float(os.environ.get("AF_A_SPEAK", "2.0"))
A_LISTEN = float(os.environ.get("AF_A_LISTEN", "2.0"))
# ★pose 正则也必须分模式。它在 step() 里没有任何模式判断，AF_POSE_REG 是全程生效的——
#   而锚点是一张"嘴闭合、姿态居中"的脸。倾听要它强(压幅度、维持抑郁基线)，
#   说话要它弱：λ 一大，激动时该有的大幅头部动作会被一起拽回中位，人就"变呆"了。
#   实测 λ 从 0.2 提到 0.4 后，说话时头部大动作明显消失。
#   两者都默认回落到 AF_POSE_REG，不设就是原来的全程同值行为。
_PR = os.environ.get("AF_POSE_REG", "0")
POSE_REG_SPEAK = float(os.environ.get("AF_POSE_REG_SPEAK", _PR))
POSE_REG_LISTEN = float(os.environ.get("AF_POSE_REG_LISTEN", _PR))
CAM_WINDOW = 0.5        # 距上次收到摄像头帧 < 这么多秒，认为摄像头在开
FACE_REDETECT = 12      # 每隔多少帧重新检测一次人脸框（其余帧复用，省算力）
RCTX = int(os.environ.get("AF_RCTX", "10"))   # 音频前瞻帧数：每块等多少帧"未来"音频。小=低延迟/口型略糙
# ★说话态跳过治疗师视觉通道。solve_cfg 里 x_cat=x_t.repeat(3,1,1) 永远算 3 路分支，
#   没有 u_cfg_scale==0 的短路；说话态 AF_U_SPEAK=0.0 → 第 3 路算完乘 0 丢弃。
#   人脸检测 27.8 + 裁剪 19.5 + 运动编码 20 ≈ 67ms/块 全白花。设 0 可关掉这个优化。
SKIP_USER_ZERO = os.environ.get("AF_SKIP_USER_ZERO", "1") not in ("0", "false", "False")
# ★输出锐化(unsharp mask)。生成帧只还原了参考图 53% 的高频细节(实测锐度 365→206)——
#   这是 motion autoencoder 解码器从 512 维运动潜码重建的固有上限,不是精度问题
#   (bf16/fp16/fp32 实测锐度完全一样)。锐化不能凭空造细节,但能把已有的边缘提回来。
#   实测:0.6 视觉上明显更清楚且自然;1.2 过锐(皱纹被刻出来、眼镜边缘起光晕)。
#   代价 0.89ms/帧 = 8.9ms/块,跑在线程池里。0=关。
SHARPEN = float(os.environ.get("AF_SHARPEN", "0"))
SHARPEN_R = float(os.environ.get("AF_SHARPEN_R", "1.6"))   # 高斯半径
MAX_Q = int(os.environ.get("AF_MAX_Q", "15"))  # 输出队列上限(帧)：超了暂停生成。防无界堆积→音视频落后十几秒。15≈0.6s缓冲
REANCHOR_S = float(os.environ.get("AF_REANCHOR_S", "12"))  # 每隔多少秒倾听生成就重锚一次清漂移(0=关)。缩短=漂移更小、过渡更顺
# ★治疗师输入缓冲上限(帧)。消费恒定 25fps(每块取 NB=10)，而摄像头实际可能更快
#   (2026-08-19 实测 ~29.3fps)→ 缓冲只涨不消:live 日志里 user_frames 125 秒从 269 涨到 862，
#   倾听时镜像的就是治疗师 ~30 秒前的样子，越聊越旧;存的还是原始摄像头图，同时也在吃内存。
#   超限就丢最旧的:反应要的是"此刻"，不是排队。干跑验证滞后 10.3s → 0.68s。
MAX_USER_FRAMES = int(os.environ.get("AF_MAX_USER_FRAMES", "30"))   # 3 块 = 1.2s
REANCHOR_FRAMES = int(REANCHOR_S * FPS)
XFADE = int(os.environ.get("AF_XFADE", "8"))   # 重锚淡入淡出帧数(~0.32s)：漂移脸→干净脸做溶解，盖住"跳变"。0=关过渡


class AvatarForcingVideoService(AIService):
    def __init__(self, *, agent, avatar_ref, a_cfg=2.0, u_cfg=0.0, **kwargs):
        super().__init__(**kwargs)
        self._agent = agent
        self._avatar_ref = avatar_ref
        self._engine = StreamingAvatarForcing(
            agent, a_cfg_scale=a_cfg, u_cfg_scale=u_cfg, nfe=10, audio_lctx=16, audio_rctx=RCTX)
        logger.info(f"AvatarForcing 引擎: audio_lctx=16 audio_rctx={RCTX} (前瞻 {RCTX/25:.2f}s)")
        # 输入缓冲
        self._avatar_pcm = bytearray()   # 16k mono s16, 病人 TTS（给引擎驱动嘴）
        self._tts_audio = bytearray()    # 原始 TTS 音频（待与视频同步发给浏览器）
        self._tts_sr = None              # 原始 TTS 采样率
        self._user_pcm = bytearray()     # 16k mono s16, 治疗师麦克风
        self._user_frames = []           # 治疗师帧（已转引擎张量 [1,3,512,512]）
        self._last_cam_ts = None         # 上次收到摄像头帧的时刻（判断摄像头是否在开）
        self._dbg_cam = 0                # 诊断：收到多少摄像头帧
        self._dbg_drop = 0               # 诊断：因超限丢弃的旧摄像头帧数
        self._dbg_tick = 0               # 诊断：生成循环计数
        self._face_box = None            # 缓存的人脸框 (mx,my,bs)，避免每帧检测
        self._face_ctr = 0               # 人脸检测计数（每 FACE_REDETECT 帧重检）
        self._utt_t0 = None              # 计时：本句 TTS 音频首次到达的时刻
        self._utt_logged = False         # 计时：本句首帧延迟是否已打印
        self._last_tts_t = None          # 计时：上次收到 TTS 音频的时刻（判新句子）
        self._utt_n = 0                  # 计时：第几句（验证"2s 首块只在开场白"）
        self._blk_n = 0                  # 计时：引擎块计数（每 25 块打一次耗时）
        self._emit_n = 0                 # 计时：播放帧计数（每 50 帧打一次队列深度）
        # 输出队列 + 播放状态
        self._out_q = asyncio.Queue()    # (OutputImageRawFrame, audio_bytes) —— 待 25fps 发出
        self._last_frame = None          # 上一帧（队列空时保持，避免卡顿/冻结成黑屏）
        self._ref_frame = None           # 干净参考脸的输出帧（重锚重建期间显示它）
        self._ref_img = None             # 干净参考脸的 np 数组 [512,512,3]（重锚过渡用）
        self._frames_since_anchor = 0    # 重锚：自上次重锚以来已生成的帧数
        self._pending_flush = 0          # 打断后强制补的静音块数（把张着的嘴 flush 回闭合）
        self._gen_task = None            # 生产者：生成
        self._emit_task = None           # 消费者：25fps 播放

    # ---------- 生命周期 ----------
    async def start(self, frame: StartFrame):
        await super().start(frame)
        self._engine.begin_live(self._avatar_ref)        # 编码 Jordan 的脸 + 建记忆
        # 开局先把"干净的参考脸"作为待显示帧，连上就有画面、沉默期也显示它
        try:
            self._ref_frame = self._to_output_frame(self._avatar_ref[0])
            self._ref_img = np.frombuffer(self._ref_frame.image, dtype=np.uint8).reshape(512, 512, 3).copy()
            self._last_frame = self._ref_frame
        except Exception:
            self._last_frame = None
        # 启动预热：把冷启动(cudnn autotune + CUDA kernel JIT)成本在此刻付掉。
        # 否则它落到真实第一句 → 首句 first_block 是"冷"的(实测 ~5s)，开头像被"吞"。
        # 此时尚无治疗师连入，阻塞几秒无副作用。
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._warmup)
        logger.info("AvatarForcing 预热完成（first_block+step 已编译）")
        self._gen_task = self.create_task(self._generate_loop())
        self._emit_task = self.create_task(self._emit_loop())
        logger.info("AvatarForcing 节点已启动（v2：沉默冻结 + 25fps 平滑）")

    async def stop(self, frame: EndFrame):
        await super().stop(frame)
        await self._teardown()

    async def cancel(self, frame: CancelFrame):
        await super().cancel(frame)
        await self._teardown()

    async def _teardown(self):
        for t in (self._gen_task, self._emit_task):
            if t:
                await self.cancel_task(t)
        self._gen_task = self._emit_task = None

    # ---------- 帧路由：把输入塞进缓冲 ----------
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # ★被打断（治疗师插话）：pipecat 会取消上游 TTS，但本服务原先完全不理这帧 →
        #   残留的旧音频/旧画面还会继续播，且嘴被切在"张着发音"的那一刻没人 flush 它闭上。
        #   这里：丢掉所有残留 + 强制补几块静音把唇形收回闭合。
        if isinstance(frame, InterruptionFrame):
            n_pcm, n_q = len(self._avatar_pcm), self._out_q.qsize()
            self._avatar_pcm.clear()                          # 丢掉没播的 TTS（驱动嘴的）
            self._tts_audio.clear()                           # 丢掉没播的 TTS（给浏览器的）
            while not self._out_q.empty():                    # 丢掉已生成但没播的画面
                try:
                    self._out_q.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._pending_flush = FLUSH_INTERRUPT             # 让生成循环补静音，把嘴闭回去
            logger.info(f"✂️ 被打断：丢弃 {n_pcm}B 音频 + {n_q} 帧，补 {FLUSH_INTERRUPT} 块静音 flush 唇形")
            return

        if isinstance(frame, TTSAudioRawFrame):
            self._avatar_pcm += self._to_16k_mono(frame)     # 16k 给引擎驱动嘴
            self._tts_audio += frame.audio                    # 原始音频缓冲，待与视频同步发出
            self._tts_sr = frame.sample_rate
            now = asyncio.get_running_loop().time()           # 计时：TTS 间隔 >0.5s 视为新句子的开头
            if self._last_tts_t is None or (now - self._last_tts_t) > 0.5:
                self._utt_t0 = now
                self._utt_logged = False
                self._utt_n += 1
            self._last_tts_t = now
            return                                            # 不立即透传 → 在播放循环里和视频帧一起发(同步)
        elif isinstance(frame, InputAudioRawFrame):
            self._user_pcm += self._to_16k_mono(frame)        # 治疗师音频 → 反应
            self._trim_user_buffers()
        elif isinstance(frame, InputImageRawFrame):
            try:
                self._user_frames.append(self._decode_raw(frame))       # 廉价解码存原图，裁脸放线程池
                self._trim_user_buffers()
                self._last_cam_ts = asyncio.get_running_loop().time()    # 标记摄像头在开
                self._dbg_cam += 1
                if self._dbg_cam <= 3 or self._dbg_cam % 50 == 0:
                    logger.info(f"📷 收到治疗师摄像头帧 x{self._dbg_cam} "
                                f"(size={frame.size}, fmt={getattr(frame, 'format', '?')})")
            except Exception as e:
                logger.error(f"摄像头帧解析失败: {e} (size={getattr(frame,'size','?')}, "
                             f"bytes={len(frame.image)}, fmt={getattr(frame,'format','?')})")

        await self.push_frame(frame, direction)

    # ---------- 生产者：说话→对口型 / 倾听→做反应 / 无摄像头沉默→冻结 ----------
    async def _generate_loop(self):
        loop = asyncio.get_running_loop()
        trailing = 0     # 句尾还要补几块静音来 flush 唇形
        while True:
            await asyncio.sleep(0.02)
            now = loop.time()
            camera_on = self._last_cam_ts is not None and (now - self._last_cam_ts) < CAM_WINDOW
            have_tts = len(self._avatar_pcm) >= BYTES_PER_BLOCK

            # 打断后:强制补静音块(process_frame 里置位),把切在张嘴那一刻的唇形 flush 回闭合
            if self._pending_flush > 0:
                trailing = max(trailing, self._pending_flush)
                self._pending_flush = 0

            # ---- 选模式 ----
            if have_tts:
                mode = "speak"; trailing = FLUSH_BLOCKS       # Jordan 说话：对口型
            elif trailing > 0:
                mode = "speak"; trailing -= 1                 # 刚说完：flush 唇形尾巴
            elif camera_on and len(self._user_frames) >= NB:
                mode = "listen"                               # 治疗师说话/Jordan 倾听：做反应
            else:
                # 诊断：为什么没生成（每 ~2s 打一次）
                self._dbg_tick += 1
                if self._dbg_tick % 100 == 0:
                    logger.info(f"⏸ 冻结中：camera_on={camera_on} "
                                f"user_frames={len(self._user_frames)} cam_total={self._dbg_cam}")
                continue                                      # 无摄像头的沉默：冻结(防漂移)

            if mode == "listen" and self._dbg_tick % 25 == 0:
                logger.info(f"🙂 倾听反应中 u_cfg={U_LISTEN} a_cfg={A_LISTEN} "
                            f"user_frames={len(self._user_frames)}")
            self._dbg_tick += 1

            # ★背压：队列已堆够就暂停生成，等消费者按 25fps 播放。否则生成快于播放、队列无界增长，
            #   Jordan 的音视频会落后十几秒（实测 14~23s）。这把 avatar 延迟钉在 ~MAX_Q/25 秒。
            if self._out_q.qsize() >= MAX_Q:
                continue

            # ★定期重锚：倾听久了累积漂移 → 趁此刻把引擎刷回干净参考脸，清零累积误差。
            #   严格门控：Jordan 必须真正静默 >1.5s（不是 TTS 流的小间隙）+ 他的画面也播完了，
            #   否则会在他说一半时重锚、把后半句打断。
            if (mode == "listen" and REANCHOR_FRAMES
                    and self._frames_since_anchor >= REANCHOR_FRAMES
                    and (self._last_tts_t is None or (now - self._last_tts_t) > 1.5)
                    and self._out_q.qsize() <= NB):
                # 过渡起点：当前(已漂移)显示帧
                from_arr = None
                if self._last_frame is not None:
                    try:
                        from_arr = np.frombuffer(self._last_frame.image, dtype=np.uint8).reshape(512, 512, 3)
                    except Exception:
                        from_arr = None
                await loop.run_in_executor(None, self._engine.begin_live, self._avatar_ref)
                self._frames_since_anchor = 0
                # 淡入淡出：漂移脸 → 干净参考脸做 XFADE 帧溶解，盖住"跳变"（缩短间隔后两端更接近，过渡更顺）
                if XFADE and from_arr is not None and self._ref_img is not None:
                    for k in range(1, XFADE + 1):
                        a = k / XFADE
                        blended = (from_arr * (1.0 - a) + self._ref_img * a).astype(np.uint8)
                        await self._out_q.put((
                            OutputImageRawFrame(image=blended.tobytes(), size=(512, 512), format="RGB"), b""))
                if self._ref_frame is not None:
                    self._last_frame = self._ref_frame   # 过渡后落在干净脸
                logger.info(f"🔄 重锚清漂移：{XFADE}帧溶解过渡→干净参考脸（每 {REANCHOR_S}s 一次）")
                continue

            # ---- 按模式配置引擎 ----
            if mode == "speak":
                self._engine.u_cfg_scale = U_SPEAK            # 干净对口型，弱反应
                self._engine.a_cfg_scale = A_SPEAK            # 音频条件：说话时要它强，口型才准
                self._engine.pose_reg = POSE_REG_SPEAK        # ★弱：别把说话时的大幅头部动作拽回中位
                a_pcm = self._pop_audio(self._avatar_pcm)     # TTS（flush 时不足补静音）
                emit_audio = True
            else:  # listen
                self._engine.u_cfg_scale = U_LISTEN           # 强反应：真实人脸/语音驱动
                self._engine.a_cfg_scale = A_LISTEN           # ★调低=松开"静音→别动"的压制，让反应冒出来
                self._engine.pose_reg = POSE_REG_LISTEN       # ★强：压幅度、防漂移、维持抑郁基线
                a_pcm = b"\x00" * BYTES_PER_BLOCK             # avatar 静音 → 嘴闭
                emit_audio = False

            try:
                u_pcm = self._pop_audio(self._user_pcm)
                u_frames = self._take_user_frames()
                _t = loop.time()                                  # 计时：引擎块耗时
                # 说话且 u_cfg=0 → 跳过整条治疗师视觉通道（那一路乘 0 丢弃，纯白算）
                skip_user = (mode == "speak" and SKIP_USER_ZERO and U_SPEAK == 0.0)
                frames = await loop.run_in_executor(
                    None, self._engine_push,
                    self._pcm_to_tensor(a_pcm), self._pcm_to_tensor(u_pcm), u_frames, skip_user)
                self._blk_n += 1
                if self._blk_n % 25 == 0:
                    logger.info(f"⏱ 引擎块耗时 {(loop.time()-_t)*1000:.0f}ms (mode={mode}, rctx={RCTX})")

                n = len(frames)
                if n == 0:
                    continue
                # 说话：取对应原始音频按帧切片同步发；倾听：无音频(Jordan 在听)
                audio = self._pop_tts_audio(n) if emit_audio else b""
                bpf = self._frame_audio_bytes()
                for idx, f in enumerate(frames):             # 帧已在线程池里转好
                    aud = audio[idx * bpf:(idx + 1) * bpf] if (emit_audio and bpf) else b""
                    await self._out_q.put((f, aud))
                self._frames_since_anchor += n           # 重锚计数
            except Exception as e:
                # 单块出错就跳过 + 记录，绝不让整个生成循环死掉（避免画面永久冻结）
                logger.exception(f"⚠️ 生成块失败(已跳过, mode={mode}): {e}")
                continue

    # ---------- 消费者：严格 25fps 平滑播放 ----------
    async def _emit_loop(self):
        loop = asyncio.get_running_loop()
        period = 1.0 / FPS                       # 40ms
        next_t = loop.time() + period
        while True:
            await asyncio.sleep(max(0, next_t - loop.time()))
            next_t += period
            self._emit_n += 1
            if self._emit_n % 50 == 0:               # 队列深度：>0=生成有余量；长期=0 可能卡顿
                logger.info(f"📊 队列深度 {self._out_q.qsize()} 帧")
            try:
                frame, aud = self._out_q.get_nowait()
                self._last_frame = frame
            except asyncio.QueueEmpty:
                frame, aud = self._last_frame, b""   # 队列空（沉默/没生成）→ 保持上一帧，不发音频
            if frame is not None:
                await self.push_frame(frame)
            if aud and self._tts_sr:
                if self._utt_t0 is not None and not self._utt_logged:   # 本句"首段同步音频发出"= 你听到Jordan
                    pos = getattr(self._engine, "position", -1)
                    logger.info(f"⏱ avatar音频延迟 第{self._utt_n}句 {(loop.time()-self._utt_t0)*1000:.0f}ms "
                                f"(TTS到桥→首段同步音频出, pos={pos})  ← 这才是'听到Jordan'的真实缓冲")
                    self._utt_logged = True
                await self.push_frame(OutputAudioRawFrame(
                    audio=aud, sample_rate=self._tts_sr, num_channels=1))

    # ---------- 小工具 ----------
    def _engine_push(self, a_aud, u_aud, u_raw, skip_user=False):
        """线程池里跑完整条重活：人脸裁剪 → 引擎 → 出图转帧。返回 OutputImageRawFrame 列表。

        ★出图转换(_to_output_frame)以前留在事件循环里做，10 帧 40ms —— 正好一个帧周期，
          直接偷 _emit_loop 的 25fps 节拍预算。搬进来后事件循环只剩排队。
        ★skip_user：说话态且 u_cfg==0 时，user 那路 CFG 分支乘 0 丢弃，
          人脸检测(27.8ms)+裁剪(19.5ms)+运动编码(20ms)全是白算，整条跳过。"""
        if skip_user:
            u_frames, n_zero = None, len(u_raw)
        else:
            u_frames, n_zero = [self._crop_to_tensor(r) for r in u_raw], 0
        with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            result = self._engine.push(a_aud, u_aud, u_frames, user_motion_zero=n_zero)
        return [self._to_output_frame(blk[i])
                for blk in result for i in range(blk.shape[0])]

    def _warmup(self):
        """启动预热：用静音音频 + 空白帧空跑 first_block(50帧)+step(10帧)，
        把冷启动的 cudnn autotune / CUDA kernel 编译在启动时付掉（实测首句省 ~5s）。
        预热后 begin_live() 重置，丢弃预热产生的状态，真实会话从干净开始。"""
        try:
            self._engine.u_cfg_scale = U_SPEAK
            a = self._pcm_to_tensor(b"\x00" * BYTES_PER_BLOCK)   # 10 帧静音
            produced = 0
            need = self._engine.NC + NB                          # first_block(50)+至少一个 step(10)
            for _ in range(16):                                  # 每次喂 10 帧；rctx 前瞻下约 7~8 次出首块
                res = self._engine_push(a, a, [None] * NB)
                produced += len(res)
                if produced >= need:
                    break
        except Exception as e:
            logger.warning(f"预热跳过(不致命): {e}")
        finally:
            self._engine.begin_live(self._avatar_ref)            # 重置，丢弃预热状态

    def _trim_user_buffers(self):
        """治疗师画面/声音只保留最近 MAX_USER_FRAMES 帧，超出的丢最旧的。
        画面和声音按同一个时长窗口裁，避免两路错开(嘴对的是 A 时刻的声、脸是 B 时刻的)。"""
        n_over = len(self._user_frames) - MAX_USER_FRAMES
        if n_over > 0:
            del self._user_frames[:n_over]
            self._dbg_drop += n_over
            if self._dbg_drop == n_over or self._dbg_drop % 250 < n_over:
                logger.info(f"🗑 治疗师画面缓冲超限，已累计丢弃 {self._dbg_drop} 帧旧画面 "
                            f"(上限 {MAX_USER_FRAMES} 帧≈{MAX_USER_FRAMES/FPS:.1f}s，"
                            f"摄像头比 25fps 快时正常)")
        max_bytes = MAX_USER_FRAMES * SPF * 2
        if len(self._user_pcm) > max_bytes:
            del self._user_pcm[:len(self._user_pcm) - max_bytes]

    def _take_user_frames(self):
        """取 NB 帧治疗师原始画面（np RGB）；不够补 None（裁剪时→空白帧）。"""
        u = self._user_frames[:NB]
        self._user_frames = self._user_frames[NB:]
        while len(u) < NB:
            u.append(None)
        return u

    def _frame_audio_bytes(self):
        """每帧（1/25 秒）对应的原始音频字节数（s16）。"""
        return int(self._tts_sr / FPS) * 2 if self._tts_sr else 0

    def _pop_tts_audio(self, n_frames: int) -> bytes:
        """取 n_frames/25 秒的原始音频（s16），不够补静音 —— 和视频同步发出。"""
        n_bytes = self._frame_audio_bytes() * n_frames
        if n_bytes == 0:
            return b""
        take = bytes(self._tts_audio[:n_bytes])
        del self._tts_audio[:len(take)]
        if len(take) < n_bytes:
            take += b"\x00" * (n_bytes - len(take))
        return take

    def _pop_audio(self, buf: bytearray) -> bytes:
        take = bytes(buf[:BYTES_PER_BLOCK])
        del buf[:len(take)]
        if len(take) < BYTES_PER_BLOCK:                   # 缺则补静音
            take += b"\x00" * (BYTES_PER_BLOCK - len(take))
        return take

    def _to_16k_mono(self, frame) -> bytes:
        pcm = np.frombuffer(frame.audio, dtype=np.int16)
        if frame.num_channels == 2:
            pcm = pcm.reshape(-1, 2).mean(axis=1).astype(np.int16)
        if frame.sample_rate != SR:   # TODO: 换正经 resampler
            n = int(len(pcm) * SR / frame.sample_rate)
            pcm = np.interp(np.linspace(0, len(pcm), n, endpoint=False),
                            np.arange(len(pcm)), pcm).astype(np.int16)
        return pcm.tobytes()

    def _decode_raw(self, frame) -> np.ndarray:
        """廉价解码：Daily 帧字节 → RGB np 数组（不检测、不 resize，放主循环里很轻）。"""
        w, h = frame.size
        buf = np.frombuffer(frame.image, dtype=np.uint8)
        ch = buf.size // (w * h) if (w * h) else 3
        img = buf.reshape(h, w, ch)
        if ch == 4:       # RGBA → RGB（Daily 摄像头常见）
            img = img[:, :, :3]
        elif ch == 1:     # 灰度 → RGB
            img = np.repeat(img, 3, axis=2)
        return np.ascontiguousarray(img)

    def _crop_to_tensor(self, img):
        """人脸裁剪对齐（同训练 preprocess_face）→ 512 张量 [1,3,512,512]。None→空白。"""
        import cv2
        if img is None:
            return torch.zeros(1, 3, 512, 512)
        box = self._detect_face_cached(img)
        if box is None:
            face = cv2.resize(img, (512, 512))            # 检不到脸 → 整帧兜底
        else:
            mx, my, bs = box
            h, w = img.shape[:2]
            x1, y1 = max(mx - bs, 0), max(my - bs, 0)
            x2, y2 = min(mx + bs, w), min(my + bs, h)
            face = img[y1:y2, x1:x2]
            face = cv2.resize(img, (512, 512)) if face.size == 0 else cv2.resize(face, (512, 512))
        t = torch.from_numpy(np.ascontiguousarray(face)).float().permute(2, 0, 1) / 127.5 - 1.0
        return t.unsqueeze(0)

    def _detect_face_cached(self, img):
        """每 FACE_REDETECT 帧重检一次人脸框，其余帧复用缓存（脸不会瞬移）。"""
        self._face_ctr += 1
        if self._face_box is None or self._face_ctr % FACE_REDETECT == 0:
            b = self._detect_face(img)
            if b is not None:
                self._face_box = b
        return self._face_box

    def _detect_face(self, img):
        """复刻 preprocess_face 的检测：缩到高 360 检测 → 居中方框(pad_ratio=1)。返回 (mx,my,bs)。"""
        import cv2
        try:
            fa = self._agent.data_processor.fa
            h = img.shape[0]
            mult = 360.0 / h
            small = cv2.resize(img, (0, 0), fx=mult, fy=mult,
                               interpolation=cv2.INTER_AREA if mult < 1 else cv2.INTER_CUBIC)
            bxs = fa.face_detector.detect_from_image(small)
            bxs = [(x1 / mult, y1 / mult, x2 / mult, y2 / mult, s)
                   for (x1, y1, x2, y2, s) in bxs if s > 0.9]
            if not bxs:
                return None
            x1, y1, x2, y2, _ = bxs[0]
            mx, my = int((x1 + x2) / 2), int((y1 + y2) / 2)
            bs = int(max((x2 - x1) / 2, (y2 - y1) / 2) * 2)   # (1+pad_ratio), pad_ratio=1
            return (mx, my, bs)
        except Exception as e:
            logger.warning(f"人脸检测失败(用兜底): {e}")
            return None

    def _pcm_to_tensor(self, pcm: bytes) -> torch.Tensor:
        # TODO: 逐块归一化差异待评估
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        iv = self._agent.data_processor.wav2vec_preprocessor(
            arr, sampling_rate=SR, return_tensors="pt").input_values
        return iv                                         # [1, samples]

    def _to_output_frame(self, img: torch.Tensor) -> OutputImageRawFrame:
        # ★.contiguous() 必须在 .cpu() 之前：permute 后张量非连续，.cpu() 会走慢路径，
        #   numpy().tobytes() 又在 CPU 上再拷一次。实测 4.03ms/帧 → 0.20ms/帧（20倍）。
        arr = ((img.clamp(-1, 1) + 1) * 127.5).byte().permute(1, 2, 0).contiguous().cpu().numpy()
        if SHARPEN > 0:                       # unsharp mask:把解码器丢掉的边缘对比提回来
            import cv2
            blur = cv2.GaussianBlur(arr, (0, 0), SHARPEN_R)
            arr = cv2.addWeighted(arr, 1 + SHARPEN, blur, -SHARPEN, 0)
        return OutputImageRawFrame(image=arr.tobytes(), size=(512, 512), format="RGB")
