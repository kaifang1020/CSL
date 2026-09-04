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
        #   ★ref=在"嘴闭合"的前提下挑整体表情最接近参考图的那帧(推荐)。
        #     为什么不是给 mouth 判据再加一项"嘴角惩罚":那样是用互相独立的单项指标拼一张脸,
        #     容易挑出嘴角向下但眉毛抬着、或嘴处在发音中途的帧——每项都合格,整体不和谐。
        #     参考图本身是一张真实连贯的人脸,且是按临床贴合度挑的,直接以它的表情为目标更稳。
        #     注意嘴开合不参与"接近参考图"的比较(参考图自己可能就微张),它是独立的一项。
        self.anchor_pick = os.environ.get('AF_ANCHOR_PICK', 'mouth')
        self.anchor_w_gap = float(os.environ.get('AF_ANCHOR_W_GAP', '1.0'))    # 嘴闭合权重
        self.anchor_w_ref = float(os.environ.get('AF_ANCHOR_W_REF', '1.0'))    # 贴近参考表情权重
        self.anchor_w_asym = float(os.environ.get('AF_ANCHOR_W_ASYM', '0.5'))  # 左右不对称惩罚
        self._ref_bgr = None                                       # 参考图(预处理后)的 BGR，ref 模式用
        # ★用户条件的通道拆解。CFG 第 3 分支同时喂 wa_user(对方声音)+motion_user(对方人脸)，
        #   u_cfg 是管着这两者的单一标量 → 想要"跟着语流反应"就必然连"抄对方的脸"一起要，
        #   倾听时嘴跟着张、笑跟着传染就是这么来的。这两个开关把通道拆开单独测：
        #     AF_USER_MOTION=zero → 只喂声音,不喂脸(要的:由语流驱动的反应,不镜像)
        #     AF_USER_AUDIO=zero  → 只喂脸,不喂声音(反向对照:反应到底来自哪一路)
        #   默认 full/full = 原行为。
        self.user_motion = os.environ.get('AF_USER_MOTION', 'full')
        self.user_audio = os.environ.get('AF_USER_AUDIO', 'full')
        # 时序平滑(EMA 低通,输出后置滤波):压高频震颤"发抖"。与 pose 正则正交。0=关。
        # 只滤解码前的潜码,不动 x_t/KV,纯输出滤波;越大越顺但反应越迟钝。
        self.ema = float(os.environ.get('AF_TEMPORAL_EMA', '0'))
        self.ema_prev = None                                       # 上一帧(平滑后)潜码,跨块延续
        # ★接缝融合:每块只有 10 帧,跨块只靠上块尾 2 帧当上下文(step 里 context_len=2),
        #   其余 10 帧从全新噪声起步 → 边界上有个硬跳。实测(倾听,seam_jitter.py)块内帧间差 ~0.4、
        #   接缝那一帧 1.30(每秒抽 2.5 下),而 42.6% 的帧几乎静止 → 读起来就是"僵住—抽一下"的呆滞。
        #   解码是逐帧独立的(decode_block 把 B*L 摊进 batch),所以在潜码上抹平接缝 = 在画面上抹平,
        #   零额外算力。做法:新块前 k 帧向"上块末帧按其速度的线性延拓"做斜坡混合
        #   (权重 i=0 最大、到 k 归零)。与 EMA 的区别:EMA 是全程低通(连真实反应一起压,实测把静止帧
        #   从 42.6% 推到 50.3%),这个只动边界那 2~4 帧,块内的反应一点不碰。
        #   同样是输出后置滤波:不改 x_t/KV,不影响后续块的生成轨迹。0=关,推荐 2(k=4 会压过头)。
        self.seam = int(os.environ.get('AF_SEAM_BLEND', '0'))
        self.seam_tail = None                                      # 上块(融合后)末两帧潜码

    @torch.inference_mode()
    def begin(self, data):
        """开场一次。搬自 inference() 224-230 + sample() 263-271。"""
        G = self.G
        # ① 编码参考脸（静态，只算一次）
        s = data['avatar_ref'].to(self.rank)
        self._ref_bgr = self._to_bgr(s[0])                 # ref 挑锚模式要拿它当表情目标
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
        # ★通道消融(默认不动)。放在算 T 之后，免得置零影响总帧数。
        if self.user_audio == 'zero':
            user_a = torch.zeros_like(user_a)
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
        if self.user_motion == 'zero':
            self.user_r_d = torch.zeros_like(self.user_r_d)
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

    @staticmethod
    def _to_bgr(t):
        """[3,512,512] in [-1,1] → 512x512 BGR uint8（关键点检测要的格式）"""
        v = t.permute(1, 2, 0).detach().clamp(-1, 1).float().cpu().numpy()
        return ((v + 1.0) * 127.5).clip(0, 255).astype(np.uint8)[:, :, ::-1]

    def _expr(self, bgr):
        """从 68 点抽一组"表情"特征，全部按双眼距归一化 → 与脸大小/位置/身份无关。
        返回 (gap, vec, asym)：
          gap  内唇开度，单独作为"嘴闭合"项，不参与和参考图的比较
               （参考图自己可能就微张，硬去贴它反而把嘴拉开）
          vec  嘴角上扬 / 眉-眼距 / 眼开度 / 嘴宽 —— 用来衡量"整体表情像不像"
          asym 左右不对称度：嘴角高度差 + 眉高差。真实表情基本对称，
               中途过渡帧和生成瑕疵往往不对称，读起来就是"歪"、"皮笑肉不笑"。
        检不到脸返回 None。"""
        # 必须关掉 autocast：外层跑在 bf16 里，face_alignment 在半精度下会检歪
        with torch.autocast(device_type='cuda', enabled=False):
            out = self._agent.data_processor.fa.get_landmarks(np.ascontiguousarray(bgr[:, :, ::-1]))
        if not out:
            return None
        k = out[0].astype(np.float32)
        le, re = k[36:42].mean(0), k[42:48].mean(0)
        iod = np.linalg.norm(le - re) + 1e-6
        ec_y = (le[1] + re[1]) / 2.0

        def ear(e):
            return (np.linalg.norm(e[1] - e[5]) + np.linalg.norm(e[2] - e[4])) \
                   / (2 * np.linalg.norm(e[0] - e[3]) + 1e-6)

        gap = float(np.linalg.norm(k[62] - k[66]) / iod)
        smile = float(((k[51, 1] + k[57, 1]) / 2.0 - (k[48, 1] + k[54, 1]) / 2.0) / iod)
        brow = float((ec_y - k[17:27, 1].mean()) / iod)
        eye = float((ear(k[36:42]) + ear(k[42:48])) / 2.0)
        width = float(np.linalg.norm(k[48] - k[54]) / iod)
        asym = float((abs(k[48, 1] - k[54, 1]) + abs(k[19, 1] - k[24, 1])) / iod)
        return gap, np.array([smile, brow, eye, width], dtype=np.float32), asym

    @torch.inference_mode()
    def _pick_anchor_ref(self, x_t, stride, budget, t0):
        """ref 模式：挑"嘴闭合 + 整体表情最接近参考图 + 左右对称"的那帧。
        评分越小越好：w_gap*嘴开度 + w_ref*‖表情向量−参考‖ + w_asym*不对称度。"""
        import time
        base = self._expr(self._ref_bgr)
        if base is None:
            print("[anchor] 参考图没检到脸，退回 mouth 模式", flush=True)
            return None
        _, ref_vec, _ = base
        imgs = self._decode(x_t)
        best_i, best_s, best_dbg, n = 0, float('inf'), None, 0
        for i in range(0, imgs.shape[0], stride):
            if time.time() - t0 > budget:
                break
            m = self._expr(self._to_bgr(imgs[i]))
            n += 1
            if m is None:
                continue
            gap, vec, asym = m
            d = float(np.linalg.norm(vec - ref_vec))
            s = self.anchor_w_gap * gap + self.anchor_w_ref * d + self.anchor_w_asym * asym
            if s < best_s:
                best_i, best_s, best_dbg = i, s, (gap, d, asym, vec[0])
        if best_dbg is None:
            return None
        gap, d, asym, smile = best_dbg
        print(f"[anchor] pick=ref -> 首块第 {best_i} 帧 (评分 {best_s:.4f} = 嘴开度 {gap:.4f} + "
              f"距参考表情 {d:.4f} + 不对称 {asym:.4f}；该帧嘴角 {smile:+.4f})，"
              f"检了 {n} 帧，用时 {time.time()-t0:.1f}s", flush=True)
        return x_t[:, best_i:best_i + 1].detach().clone()

    @torch.inference_mode()
    def _pick_anchor(self, x_t):
        """挑 pose 正则的锚。mouth 模式:解码首块,量嘴开合(内唇距/双眼距),取最闭的一帧。
        first 模式(原行为):直接用第 0 帧。
        ★抽样 + 限时:预热路径也会走这里(用静音+空白帧,挑出的锚随后被 begin_live 丢掉),
          全量 50 帧检测会把启动卡住 → 每 STRIDE 帧检一次,并设总时间预算。
        任何异常/超时都安全回落到第 0 帧。"""
        if self.anchor_pick not in ('mouth', 'ref'):
            return x_t[:, :1].detach().clone()
        import time
        STRIDE = int(os.environ.get('AF_ANCHOR_STRIDE', '5'))       # 每几帧检一次
        BUDGET = float(os.environ.get('AF_ANCHOR_BUDGET_S', '6'))   # 总时间预算(秒)
        # ★纯时间预算会静默退化:2026-08-19 实测,GPU 被别的进程挤住时 face_alignment 第一次
        #   调用就花了 47s,30s 预算当场爆掉 → 只检了 1 帧 → 回落首块第 0 帧(嘴开度 0.2182 大张),
        #   pose_reg 此后每帧往这个锚拉 → 整段倾听嘴都挂着(实测 10 个块内位置均匀退化到 0.11)。
        #   锚是"一次定终身"的,宁可多等几秒 → 预算到了也至少检 MIN_CHECK 帧,另设硬上限防无限等。
        MIN_CHECK = int(os.environ.get('AF_ANCHOR_MIN_CHECK', '6'))
        HARD = BUDGET * float(os.environ.get('AF_ANCHOR_HARD_X', '3'))
        t0 = time.time()
        try:
            if self.anchor_pick == 'ref' and self._ref_bgr is not None:
                r = self._pick_anchor_ref(x_t, STRIDE, BUDGET, t0)
                if r is not None:
                    return r
                # 参考图没检到脸/全部候选检测失败 → 落到下面的 mouth 逻辑，别直接放弃
            fa = self._agent.data_processor.fa
            imgs = self._decode(x_t)                       # [L,3,512,512]
            v = imgs.permute(0, 2, 3, 1).detach().clamp(-1, 1).float().cpu().numpy()
            bgr = ((v + 1.0) * 127.5).clip(0, 255).astype(np.uint8)[:, :, :, ::-1]
            best_i, best_gap, n_checked = 0, float('inf'), 0
            for i in range(0, bgr.shape[0], STRIDE):
                el = time.time() - t0
                if el > HARD or (el > BUDGET and n_checked >= MIN_CHECK):
                    break
                with torch.autocast(device_type='cuda', enabled=False):
                    out = fa.get_landmarks(np.ascontiguousarray(bgr[i][:, :, ::-1]))
                n_checked += 1
                if not out:
                    continue
                k = out[0].astype(np.float32)
                iod = np.linalg.norm(k[36:42].mean(0) - k[42:48].mean(0)) + 1e-6
                gap = float(np.linalg.norm(k[62] - k[66]) / iod)
                if gap < best_gap:
                    best_i, best_gap = i, gap
            warn = ''
            if n_checked < MIN_CHECK:
                warn = f'  ⚠️ 只检了 {n_checked} 帧(<{MIN_CHECK})，锚可能退化，本段结果不可信'
            elif best_gap > 0.05:
                warn = f'  ⚠️ 锚本身嘴就张着({best_gap:.4f})，倾听大概率闭不上嘴'
            print(f"[anchor] pick=mouth -> 首块第 {best_i} 帧(嘴开度 {best_gap:.4f}), "
                  f"检了 {n_checked} 帧, 用时 {time.time()-t0:.1f}s{warn}", flush=True)
            return x_t[:, best_i:best_i + 1].detach().clone()
        except Exception as e:
            print(f"[anchor] mouth 挑锚失败({e}),回落第 0 帧", flush=True)
            return x_t[:, :1].detach().clone()

    def _seam_blend(self, z):
        """抹平块与块的接缝。z: [B,L,dim] 本块要出图的潜码。
        用上块末两帧的速度做线性延拓当"本该长成的样子",与新块前 k 帧按斜坡权重混合;
        i=0 权重最大、第 k 帧权重归零 → 只影响边界,块内不动。seam<=0 时原样返回。"""
        if self.seam <= 0:
            return z
        k = min(self.seam, z.shape[1])
        if self.seam_tail is not None:
            last, prev = self.seam_tail[:, -1], self.seam_tail[:, -2]
            vel = last - prev                                       # 上块末速度,保住动势不"顿一下"
            z = z.clone()
            for i in range(k):
                w = (k - i) / (k + 1.0)
                z[:, i] = (1.0 - w) * z[:, i] + w * (last + vel * (i + 1))
        self.seam_tail = z[:, -2:].detach().clone() if z.shape[1] >= 2 else self.seam_tail
        return z

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
        imgs = self._decode(self._ema_smooth(self._seam_blend(x_t)))  # ★每块即时解码出图(先接缝融合+时序平滑)
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
        imgs = self._decode(self._ema_smooth(self._seam_blend(new)))  # ★每块即时解码出图(先接缝融合+时序平滑)
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
        self._ref_bgr = self._to_bgr(s[0])                 # ref 挑锚模式要拿它当表情目标
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

    def _ablate_user(self, user_audio, new_r_d):
        """按开关把用户条件的某一路置零。置零而不是不传：wa_user/motion_user 都要保持
        形状连续(step() 里按帧切片)，而全零正是 prepare_cfg_condition 给空分支用的值。"""
        if self.user_audio == 'zero' and user_audio is not None:
            user_audio = torch.zeros_like(user_audio)
        if self.user_motion == 'zero' and new_r_d is not None:
            new_r_d = torch.zeros_like(new_r_d)
        return user_audio, new_r_d

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
    def push(self, avatar_audio=None, user_audio=None, user_frames=None, flush=False,
             user_motion_zero=0):
        """喂一块原始输入，返回这次能产出的图像帧 list（攒够才出，可能为空）。
        avatar_audio/user_audio: [B,samples]；user_frames: 帧 list。
        flush=True：流结束，把剩余不足前瞻的块也算出来。
        user_motion_zero=n>0：跳过 encode_user_motion，直接补 n 帧零运动潜码。
          只在 u_cfg_scale==0 时用（说话态）——那一路 CFG 分支算完就乘 0 丢弃，
          跑编码器纯属白算。实测省 118ms/块。副作用（零潜码进 KV 缓存、影响之后的
          倾听块）实测在模型自身 run-to-run 噪声量级内，见 HANDOFF_20260822 §3。"""
        G = self.G
        spf = G.samples_per_frame
        # 1) 追加原始音频
        self.avatar_buf = self._cat_audio(self.avatar_buf, avatar_audio)
        # 2) 治疗师帧逐帧编码后追加（逐帧独立，无需窗口）
        if user_motion_zero:
            new_r_d = torch.zeros(1, user_motion_zero, self.dim_w, device=self.rank)
        else:
            new_r_d = G.encode_user_motion(user_frames) if user_frames else None
        user_audio, new_r_d = self._ablate_user(user_audio, new_r_d)   # ★通道消融(默认不动)
        self.user_buf = self._cat_audio(self.user_buf, user_audio)
        if new_r_d is not None:
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
