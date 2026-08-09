# streaming.py — A2a.5：每块即时解码出图（输出端流式）
# begin 一次；first_block 出首块(50帧)图；step 出后续块(10帧)图。
# A2a.5：音频特征仍整段预算(A2b 再改滑窗)，但出图已改成"每块即时画"。
import math
import os
import numpy as np
import torch
import torch.nn.functional as F


class StreamingAvatarForcing:
    def __init__(self, agent, a_cfg_scale=2.0, u_cfg_scale=1.0, nfe=10, audio_lctx=None, audio_rctx=0):
        self.G = agent.G
        self.a_cfg_scale = a_cfg_scale
        self.u_cfg_scale = u_cfg_scale
        self.nfe = nfe
        # audio_lctx=None → 用完整音频一次性算特征(A2a.5 行为)
        # audio_lctx=整数 → 因果滑动窗口算特征(A2b)，每块左看 audio_lctx 帧
        # audio_rctx=整数 → 前瞻：每块右看 audio_rctx 帧未来音频（换准确度/平滑，代价是延迟）
        self.audio_lctx = audio_lctx
        self.audio_rctx = audio_rctx
        self.NC = self.G.num_frames_for_clip      # 50  首块帧数
        self.NB = self.G.num_frames_per_block     # 10  每块帧数
        self.dim_w = self.G.opt.dim_w
        self.rank = self.G.rank
        # pose 正则:每步把新帧运动潜码往"干净锚"拉 λ,压单向漂移(源头治,无可见重置)。0=关。
        self.pose_reg = float(os.environ.get('AF_POSE_REG', '0'))
        # 模式：frame=逐帧回拉(高频张力,会引入抖动)；mean=只拉整块均值(低频/DC 修正,保留帧间反应,不加抖)
        self.pose_reg_mode = os.environ.get('AF_POSE_REG_MODE', 'frame')
        self.anchor_z = None                                       # 干净锚,first_block 里设
        self._agent = agent                                        # 取 face_alignment 用(挑锚要量嘴)
        # ★挑锚方式:first=首块第0帧(原行为);mouth=首块里"嘴最闭"的那帧。
        #   为什么要挑:live 的首块正是病人在说开场白 → 第0帧很可能张着嘴 → pose 正则
        #   此后把每帧都往"张嘴的锚"拉 → 倾听时嘴一直张着。实测倾听嘴开度 0.08(坏锚)vs 0.02(好锚)。
        self.anchor_pick = os.environ.get('AF_ANCHOR_PICK', 'mouth')
        # 时序平滑(EMA 低通,输出后置滤波):压高频震颤"发抖"。与 pose 正则正交。0=关。
        # 只滤解码前的潜码,不动 x_t/KV,纯输出滤波;越大越顺但反应越迟钝。
        self.ema = float(os.environ.get('AF_TEMPORAL_EMA', '0'))
        self.ema_prev = None                                       # 上一帧(平滑后)潜码,跨块延续

    @torch.inference_mode()
    def begin(self, data):
        """开场一次。搬自 inference() 224-230 + sample() 263-271。"""
        G = self.G
        # ① 编码参考脸（静态，只算一次）
        s = data['avatar_ref'].to(self.rank)
        s_r, r_s_lambda, s_r_feats = G.encode_image_into_latent(s)
        self.s_r, self.s_r_feats = s_r, s_r_feats
        self.r_s = G.motion_autoencoder.dec.direction(r_s_lambda)
        self.B = s_r.shape[0]
        # decode_block 需要的两样（都只算一次）：广播用的 s_r、按 NB 展开的特征
        self.s_r_dec = s_r.unsqueeze(1)                                            # [B,1,dim]
        self.s_r_feats_expanded = [f.repeat_interleave(self.NB, dim=0) for f in s_r_feats]
        # ② setup：总帧数 T、去噪表、记忆、整段音频/动作特征
        avatar_a = data['avatar_a'].to(self.rank)
        user_a = data['user_a'].to(self.rank)
        self.T = math.ceil(max(avatar_a.shape[-1], user_a.shape[-1]) * G.fps / G.sampling_rate)
        G.denoising_step_list = torch.tensor(
            np.linspace(G.opt.num_train_timestep, 0, self.nfe - 1).tolist())
        G.initialize_kv_cache(batch_size=self.B, dtype=avatar_a.dtype, device=self.rank)
        if self.audio_lctx is None:
            # A2a.5：整段一次性算（依赖完整音频）
            self.avatar_wa = G.audio_encoder.inference(avatar_a, seq_len=self.T)
            self.user_wa = G.audio_encoder.inference(user_a, seq_len=self.T)
        else:
            # A2b：滑动窗口逐块算（左看 lctx 帧、右看 rctx 帧前瞻）
            self.avatar_wa = self._features_windowed(avatar_a, self.audio_lctx, self.audio_rctx)
            self.user_wa = self._features_windowed(user_a, self.audio_lctx, self.audio_rctx)
        self.user_r_d = G.encode_user_motion(data['user_frame'])   # 逐帧独立，无需窗口
        # ③ 流式状态
        self.x_t = None
        self.position = 0
        self.frames = []

    def _slice_pad(self, buf, s, e, need):
        """从缓冲切 [s:e]，不足 need 帧 replicate pad（搬 sample 334-336 写法）"""
        seg = buf[:, max(s, 0):e]
        if seg.shape[1] < need:
            seg = F.pad(seg, (0, 0, 0, need - seg.shape[1]), mode='replicate')
        return seg

    @torch.inference_mode()
    def _features_windowed(self, audio, lctx, rctx=0):
        """A2b：滑动窗口算音频特征。逐块[f:f+NB]计算，
        窗口=[f-lctx : f+NB+rctx]（左 lctx 帧上下文 + 右 rctx 帧前瞻），只取目标块那几帧。
        rctx>0 让目标帧落在窗口内部（两侧都有上下文）→ 口型更准、接缝更小。"""
        G = self.G
        spf = G.samples_per_frame
        need = self.T * spf
        if audio.shape[1] < need:
            audio = F.pad(audio, (0, need - audio.shape[1]), mode='replicate')
        feats = []
        f = 0
        while f < self.T:
            blk_end = min(f + self.NB, self.T)
            win_start = max(0, f - lctx)
            win_end = min(self.T, blk_end + rctx)                    # 右侧前瞻
            win = audio[:, win_start * spf: win_end * spf]
            win_frames = win_end - win_start
            wf = G.audio_encoder.inference(win, seq_len=win_frames)  # [B, win_frames, dim_w]
            feats.append(wf[:, f - win_start: blk_end - win_start])  # 只取 [f:blk_end] 这几帧
            f = blk_end
        return torch.cat(feats, dim=1)

    @torch.inference_mode()
    def _decode(self, motion):
        """把一段动作 [B,L,dim] 按每 NB 帧用 decode_block 画成图 [L,3,512,512]。
        最后不足 NB 帧的：pad 到 NB → 解码 → 切回（和离线 decode_latent_into_image 一致）。"""
        imgs = []
        for i in range(0, motion.shape[1], self.NB):
            blk = motion[:, i:i + self.NB]
            bl = blk.shape[1]
            if bl < self.NB:
                blk = F.pad(blk, (0, 0, 0, self.NB - bl), mode='replicate')
            img = self.G.decode_block(blk, self.s_r_dec, self.s_r_feats_expanded, self.NB, self.B)
            if bl < self.NB:
                img = img[:bl]
            imgs.append(img)
        return torch.cat(imgs, dim=0)

    @torch.inference_mode()
    def _pick_anchor(self, x_t):
        """挑 pose 正则的锚。mouth 模式:解码首块,量每帧嘴开合(内唇距/双眼距),取最闭的一帧。
        first 模式(原行为):直接用第 0 帧。开销:一次首块解码 + 逐帧关键点(约 1~2s,仅开场一次)。
        任何一步失败都安全回落到第 0 帧。"""
        if self.anchor_pick != 'mouth':
            return x_t[:, :1].detach().clone()
        try:
            import numpy as np
            fa = self._agent.data_processor.fa
            imgs = self._decode(x_t)                       # [L,3,512,512]
            v = imgs.permute(0, 2, 3, 1).detach().clamp(-1, 1).float().cpu().numpy()
            bgr = ((v + 1.0) * 127.5).clip(0, 255).astype(np.uint8)[:, :, :, ::-1]
            best_i, best_gap = 0, float('inf')
            for i in range(bgr.shape[0]):
                with torch.autocast(device_type='cuda', enabled=False):
                    out = fa.get_landmarks(bgr[i][:, :, ::-1])
                if not out:
                    continue
                k = out[0].astype(np.float32)
                iod = np.linalg.norm(k[36:42].mean(0) - k[42:48].mean(0)) + 1e-6
                gap = float(np.linalg.norm(k[62] - k[66]) / iod)
                if gap < best_gap:
                    best_i, best_gap = i, gap
            print(f"[anchor] pick=mouth → 首块第 {best_i} 帧(嘴开度 {best_gap:.4f})")
            return x_t[:, best_i:best_i + 1].detach().clone()
        except Exception as e:
            print(f"[anchor] mouth 挑锚失败({e}),回落第 0 帧")
            return x_t[:, :1].detach().clone()

    def _ema_smooth(self, z):
        """对 [B,L,dim] 运动潜码逐帧 EMA 低通(因果 IIR),跨块延续 self.ema_prev。
        返回平滑后的副本;ema=0 时原样返回(不拷贝)。压高频震颤,不改 x_t/KV。"""
        if self.ema <= 0:
            return z
        z = z.clone()
        b = self.ema
        for j in range(z.shape[1]):
            if self.ema_prev is not None:
                z[:, j] = (1.0 - b) * z[:, j] + b * self.ema_prev
            self.ema_prev = z[:, j].detach().clone()
        return z

    @torch.inference_mode()
    def first_block(self):
        """首块 50 帧。搬自 sample() 273-324，末尾改成即时解码出图。"""
        G = self.G
        a = self._slice_pad(self.avatar_wa, 0, self.NC, self.NC)
        u = self._slice_pad(self.user_wa, 0, self.NC, self.NC)
        m = self._slice_pad(self.user_r_d, 0, self.NC, self.NC).to(self.rank)
        x_t = torch.randn(self.B, self.NC, self.dim_w, device=self.rank)
        pc, pwr, padaLN = G.prepare_cfg_condition(a, u, m, self.r_s, seq_len=self.NC, context_len=0)
        for i, ct in enumerate(G.denoising_step_list):
            x_t = G.solve_cfg(B=self.B, index=i, current_timestep=ct, x_t=x_t,
                              precomputed_c=pc, precomputed_wr=pwr, precomputed_adaLN=padaLN,
                              start_pos=0, context_len=0, use_kv_cache=False,
                              a_cfg_scale=self.a_cfg_scale, u_cfg_scale=self.u_cfg_scale)
            if i == len(G.denoising_step_list) - 1:
                G.update_kv_cache(final_latents=x_t, precomputed_c=pc, precomputed_wr=pwr,
                                  precomputed_adaLN=padaLN, start_pos=0)
        self.x_t = x_t
        self.position = self.NC
        self.anchor_z = self._pick_anchor(x_t)   # pose 正则的锚(mouth 模式:挑首块里嘴最闭的一帧)
        imgs = self._decode(self._ema_smooth(x_t))  # ★每块即时解码出图(先时序平滑)
        self.frames.append(imgs)
        return imgs

    @torch.inference_mode()
    def step(self):
        """后续一块 10 帧。搬自 sample() 循环体 328-386，末尾改成即时解码出图。"""
        G = self.G
        t = self.position
        start_pos = t - 2
        ss, ee = t, t + self.NB
        a = self._slice_pad(self.avatar_wa, ss - 2, ee, self.NB + 2)
        u = self._slice_pad(self.user_wa, ss - 2, ee, self.NB + 2)
        m = self._slice_pad(self.user_r_d, ss - 2, ee, self.NB + 2).to(self.rank)
        offset_x_t = self.x_t[:, -2:]                                  # 上块尾2帧（连续性）
        noise_t = torch.randn(self.B, self.NB, self.dim_w, device=self.rank)
        x_t = torch.cat([offset_x_t, noise_t], dim=1)
        pc, pwr, padaLN = G.prepare_cfg_condition(a, u, m, self.r_s, seq_len=self.NB, context_len=2)
        for i, ct in enumerate(G.denoising_step_list):
            x_t = G.solve_cfg(B=self.B, index=i, current_timestep=ct, x_t=x_t,
                              precomputed_c=pc, precomputed_wr=pwr, precomputed_adaLN=padaLN,
                              start_pos=start_pos, context_len=2, use_kv_cache=True,
                              a_cfg_scale=self.a_cfg_scale, u_cfg_scale=self.u_cfg_scale)
            if i == len(G.denoising_step_list) - 1:
                G.update_kv_cache(final_latents=x_t, precomputed_c=pc, precomputed_wr=pwr,
                                  precomputed_adaLN=padaLN, start_pos=start_pos)
        # pose 正则:把新帧运动潜码往干净锚拉 λ,压单向漂移。也修正下一步 offset(x_t[:,-2:]),让纠正传播。
        if self.pose_reg > 0 and self.anchor_z is not None:
            if self.pose_reg_mode == 'mean':
                # 只把整块均值(慢漂移/DC)往锚拉;整块平移同一向量 → 帧间差(反应+抖动)不变,不新增抖动
                m = x_t[:, -self.NB:].mean(dim=1, keepdim=True)
                x_t[:, -self.NB:] = x_t[:, -self.NB:] + self.pose_reg * (self.anchor_z - m)
            else:
                # frame:逐帧回拉(强,但高频张力会引入头部抖动)
                x_t[:, -self.NB:] = (1.0 - self.pose_reg) * x_t[:, -self.NB:] + self.pose_reg * self.anchor_z
        self.x_t = x_t
        self.position += self.NB
        new = x_t[:, -self.NB:]
        imgs = self._decode(self._ema_smooth(new))  # ★每块即时解码出图(先时序平滑)
        self.frames.append(imgs)
        return imgs

    @torch.inference_mode()
    def run_all(self):
        """驱动：首块 + 不断 step 到 T，返回拼好的图像帧 [T,3,512,512]。
        （真实 Pipecat 里不调它，而是每来一块音频调一次 step、把返回的帧推走）"""
        self.first_block()
        while self.position < self.T:
            self.step()
        return torch.cat(self.frames, dim=0)[:self.T]

    # ===== B0：真正的"喂一块、出一块"增量接口（接 Pipecat 用）=====

    @torch.inference_mode()
    def begin_live(self, avatar_ref):
        """开场（live版）：只做静态设置 + 初始化空缓冲，不预存音频。
        之后反复调 push() 增量喂音频/帧。avatar_ref: [B,3,512,512]。"""
        G = self.G
        s = avatar_ref.to(self.rank)
        s_r, r_s_lambda, s_r_feats = G.encode_image_into_latent(s)
        self.s_r, self.s_r_feats = s_r, s_r_feats
        self.r_s = G.motion_autoencoder.dec.direction(r_s_lambda)
        self.B = s_r.shape[0]
        self.s_r_dec = s_r.unsqueeze(1)
        self.s_r_feats_expanded = [f.repeat_interleave(self.NB, dim=0) for f in s_r_feats]
        G.denoising_step_list = torch.tensor(
            np.linspace(G.opt.num_train_timestep, 0, self.nfe - 1).tolist())
        G.initialize_kv_cache(batch_size=self.B, dtype=torch.float32, device=self.rank)
        # 原始滚动缓冲（不预算特征）
        self.avatar_buf = None       # [B, samples]
        self.user_buf = None         # [B, samples]
        self.user_r_d = None         # [B, frames, dim]  治疗师动作（逐帧编码后）
        self.avatar_wa = None        # [B, frames, dim_w] 已组装的音频特征
        self.user_wa = None
        # 状态
        self.x_t = None
        self.position = 0            # 已生成到第几帧
        self.feat_pos = 0            # 已组装特征到第几帧
        self.frames = []

    def _cat_audio(self, buf, chunk):
        if chunk is None:
            return buf
        chunk = chunk.to(self.rank)
        return chunk if buf is None else torch.cat([buf, chunk], dim=1)

    @torch.inference_mode()
    def _feat_block(self, buf, f, avail):
        """算特征帧 [f : min(f+NB,avail)]，窗口=[f-lctx : blk_end+rctx]，匹配 _features_windowed 单块。"""
        spf = self.G.samples_per_frame
        blk_end = min(f + self.NB, avail)
        win_start = 0 if self.audio_lctx is None else max(0, f - self.audio_lctx)
        win_end = min(avail, blk_end + self.audio_rctx)
        win = buf[:, win_start * spf: win_end * spf]
        wf = self.G.audio_encoder.inference(win, seq_len=win_end - win_start)
        return wf[:, f - win_start: blk_end - win_start]

    @torch.inference_mode()
    def push(self, avatar_audio=None, user_audio=None, user_frames=None, flush=False):
        """喂一块原始输入，返回这次能产出的图像帧 list（攒够才出，可能为空）。
        avatar_audio/user_audio: [B,samples]；user_frames: 帧 list。
        flush=True：流结束，把剩余不足前瞻的块也算出来。"""
        G = self.G
        spf = G.samples_per_frame
        # 1) 追加原始音频
        self.avatar_buf = self._cat_audio(self.avatar_buf, avatar_audio)
        self.user_buf = self._cat_audio(self.user_buf, user_audio)
        # 2) 治疗师帧逐帧编码后追加（逐帧独立，无需窗口）
        if user_frames:
            new_r_d = G.encode_user_motion(user_frames)
            self.user_r_d = new_r_d if self.user_r_d is None else torch.cat([self.user_r_d, new_r_d], dim=1)
        # 3) 组装特征块（要有 rctx 前瞻才组装；flush 时不要求）
        avail = 0 if self.avatar_buf is None else self.avatar_buf.shape[1] // spf
        while self.feat_pos < avail:
            blk_end = min(self.feat_pos + self.NB, avail)
            if (not flush) and (blk_end + self.audio_rctx > avail):
                break    # 前瞻不够，等下次 push
            a = self._feat_block(self.avatar_buf, self.feat_pos, avail)
            u = self._feat_block(self.user_buf, self.feat_pos, avail)
            self.avatar_wa = a if self.avatar_wa is None else torch.cat([self.avatar_wa, a], dim=1)
            self.user_wa = u if self.user_wa is None else torch.cat([self.user_wa, u], dim=1)
            self.feat_pos = blk_end
        # 4) 特征够了就生成块（复用已验证的 first_block / step）
        out = []
        if self.position == 0 and self.feat_pos >= self.NC:
            out.append(self.first_block())                                  # 首块 50 帧
        while self.position >= self.NC and self.position + self.NB <= self.feat_pos:
            out.append(self.step())                                         # 后续整块 10 帧
        if flush:
            while self.position >= self.NC and self.position < self.feat_pos:
                out.append(self.step())                                     # 末尾不足一块（step 内部 pad）
        # ★live 模式内存泄漏修复:first_block/step 每块都往 self.frames 累积解码图(GPU,512×512×3≈0.75MB/帧,
        #   25fps 下 ~1.1GB/分钟)。离线 run_all 靠它拼接;实时用的是 out 返回值,self.frames 是死数据。
        #   不清 → 几分钟后显存爆 OOM → 生成崩溃 → 画面冻住("先好后卡")。out 已持有帧引用,清列表安全。
        self.frames.clear()
        return out
