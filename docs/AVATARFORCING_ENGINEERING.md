# AvatarForcing → Real-Time Reactive Avatar — Engineering Notes

技术梳理:把开源的 **AvatarForcing**(离线 talking-head 扩散模型)改造成 Pipecat 实时
数字病人里"会对治疗师做出真实反应"的 avatar,截止 2026-06-26 的全部工程细节。
配套:整体系统见 [ARCHITECTURE.md](ARCHITECTURE.md);云部署见 [VAST_DEPLOY.md](VAST_DEPLOY.md)。

---

## 0. 目标与定位

- **AvatarForcing**(arxiv 2601.00664):block-causal **diffusion-forcing** transformer,
  以一张参考脸 + 音频 + "用户视频"为条件,自回归地逐块生成说话/反应的人脸视频。
- **为什么自托管它替代 Simli**:它能让 avatar **对真人实时做出自然反应**(点头、侧头、
  移开视线、表情)——这是纯对口型方案(Simli/HeyGen)给不了的,正是数字病人的差异化卖点。
- **最终落地**:接进 ClinicalSkillsLab 训练工具(`FISTrainingTool`,Next.js),摄像头可开可不开。

## 1. 核心挑战:离线批处理 → 实时流式反应

AvatarForcing 原版是**离线批处理**:整段音频进 → 整段视频出(`G.inference(data=...)`)。
要做成实时,有四道坎:

| 坎 | 原版 | 我们要的 |
|---|---|---|
| 接口 | 一次性喂全程音频 | 增量:喂一小块、出一小块 |
| 音频特征 | 预抽全程 wav2vec | 在线滑窗 wav2vec(边来边算) |
| 反应性 | 用预录的 user 视频 | 实时治疗师摄像头/麦克风驱动 |
| 时长 | 有界(≤30s 一段) | 无界(整个会话) |

> 论文假设"音频特征已预抽" + "有界片段",**流式音频**和**无界生成**都是论文没解决的缺口,
> 是我们改造里最硬的两块,也是后面多个 bug 的根源。

## 2. 系统位置(它在 Pipecat 管线的哪)

```
transport.input ─▶ STT(Deepgram) ─▶ 端点检测(Silero+SmartTurn) ─▶ LLM ─▶ TTS(Cartesia)
                                                                              │
                                                  ┌───────────────────────────▼─────────────┐
   治疗师麦克风/摄像头 ─────────────────────────▶ │  AvatarForcingVideoService (我们的桥)     │
                                                  │  吃 TTS 音频 + 治疗师音视频 → 吐 avatar 帧 │
                                                  └───────────────────────────┬─────────────┘
                                                                              ▼  transport.output ─▶ 浏览器
```

`AvatarForcingVideoService` 占据原 `SimliVideoService` 的位置,对管线是即插即换。

---

## 3. Part A — 流式引擎重构 (`streaming.py`)

把离线 `sample()` 拆成可增量调用的 `StreamingAvatarForcing`:

- **`begin_live(avatar_ref)`**:一次性静态设置——编码参考脸(身份锚 `s_r` / `r_s`)、
  初始化 KV cache、清空缓冲、`position=0`。**再次调用即"全状态重置"(重锚)。**
- **`push(avatar_audio, user_audio, user_frames, flush)`**:喂一块原始输入,攒够前瞻就
  生成,返回这次能产出的图像帧 list(可能为空)。内部:
  - 滚动原始音频缓冲 → 逐块**滑窗 wav2vec**(`lctx` 左上下文 / `rctx` 右前瞻)算特征;
  - `first_block()`(首块 NC=50 帧)+ `step()`(后续每块 NB=10 帧 = 0.4s);
  - 维护 KV cache、`x_t` 末2帧连续性、`position`,复用已验证的生成核。
- **验证**:`begin_live+push` 与离线 `run_all` 在 **u_cfg=0 时逐比特一致(diff=0)**,逻辑正确。
  - 教训:diff-vs-offline 不是好指标——模型自回归,任何特征微扰都会走出"有效但不同"的轨迹;
    质量靠**眼睛看**(口型/抖动),不看像素差。唯一退化源是 wav2vec 滑窗(感受野截断 + 重采样接缝)。

**关键常量**:`SR=16000`、`FPS=25`、`NB=10`(0.4s/块)、`NC=50`(首块 2s)、`rctx=10`(前瞻 0.4s)。

---

## 4. Part B — Pipecat 桥 (`avatarforcing_service.py`)

`AvatarForcingVideoService(AIService)`,核心结构:

- **帧路由 (`process_frame`)**:`TTSAudioRawFrame`→病人音频缓冲(驱动嘴);
  `InputAudioRawFrame`→治疗师音频;`InputImageRawFrame`→治疗师画面(并打时间戳判断摄像头是否在开)。
- **生产者/消费者解耦**(防卡顿的关键):
  - **`_generate_loop`(生产者)**:按模式凑一块输入 → 线程池里 `engine.push` → 把
    (视频帧, 对应音频切片) 丢进 `asyncio.Queue`。GPU 推理在 executor,不卡事件循环。
  - **`_emit_loop`(消费者)**:严格**每 40ms(25fps)**从队列取一帧发出 + 同步音频;
    队列空时保持上一帧(不黑屏/不卡顿)。
- **自愈**:生成块外包 try/except,单块出错只跳过 + 记日志,绝不让循环死掉(避免画面永久冻结)。

---

## 5. 双模式设计(产品机制核心)

同一引擎,靠 **per-push 动态切 `engine.u_cfg_scale`** 实现两种行为:

| 模式 | 触发 | avatar 音频 | u_cfg | 驱动源 | 输出 |
|---|---|---|---|---|---|
| **说话 Speaking** | 有 TTS 音频 | TTS | `U_SPEAK=0` | 音频→嘴 | 视频 + 同步音频,干净对口型 |
| **倾听 Listening** | 无 TTS + 摄像头在开 | 静音(嘴闭) | `U_LISTEN=1.0` | 真实人脸+语音→反应 | 仅视频(Jordan 在听),自然反应 |
| **沉默回退** | 无 TTS + 无摄像头 | — | — | — | 冻结上一帧(防漂移) |

- u_cfg 可调:`AF_U_SPEAK` / `AF_U_LISTEN` 环境变量。
- 说话↔倾听切换 = 头部回正对口型 ↔ 侧头点头做反应。

---

## 6. 解决的问题(工程主体)— 症状 / 根因 / 修法

### 6.1 音视频不同步(声音先到、脸后到)
- **症状**:Jordan 先出声,脸过 ~2s 才动。
- **根因**:TTS 音频被立即透传(马上响),但视频要经引擎缓冲+生成才出,**两条路延迟不一**。
- **修法**:桥**扣住 TTS 音频**,在生成循环里把音频按帧切片,**和对应视频帧一起发出**——
  两者延迟同样的量 → 同步。代价是总延迟略增,换来正确口型。

### 6.2 RoPE 位置溢出(avatar 在第 3 个 turn 冻死)⭐
- **症状**:聊到 ~41 秒(约第 3 turn)avatar 突然冻住,bot 抛 `ValueError`。
- **根因**:`flow_transformer.py` 的 RoPE 位置编码表 `freqs_cis` 只预算 **`max_seq_len=1024`** 帧
  (=41s@25fps);而 live 里 `self.position += NB` **持续累加不归零**,超过 1024 即
  `Required position exceeds precomputed max length` → push 崩 → 生成循环死。
- **本质**:论文按"有界片段"设计,我们做"无界流",撞上了写死的上限假设。
- **修法**:`max_seq_len 1024 → 50000`(33min/次连接)。安全性论证:
  `freqs_cis` 是 `persistent=False`(不在权重里,不影响加载);RoPE 是**相对位置**编码 +
  注意力是 40 帧**滑动窗口**,相对位置永远 ≤40(训练分布内),所以绝对位置调大数学上无害。
  `begin_live` 每次连接重置 `position=0`。
- *(更优雅做法是位置循环复用永不增长,但复杂;加大表对任何正常时长会话足够。)*

### 6.3 卡顿(一阵一阵、有上句没下句)
- **根因**:旧生成循环**每 0.4s 一次性猛推 10 帧**再等,浏览器收到的是脉冲式,不平滑;
  音频又被绑在这节奏上 → 也卡。
- **修法**:生产/播放解耦(见 §4)——后台尽快生成入队,消费循环严格 25fps 平滑发帧。

### 6.4 脸变形/融化(drift)⭐
- **症状**:连续生成越久脸越"融化",尤其无摄像头时。
- **根因**:**自回归误差累积(exposure bias)**——下一帧基于"自己生成的、带误差的前几帧",
  误差滚雪球。两个放大因素:(a) `u_cfg=0` 去掉了"用户真实动作"这个稳定锚;
  (b) 沉默期引擎仍空转生成,纯惯性贡献大量漂移。
- **多管齐下修法**:
  1. **双模式**:倾听时 `u_cfg≥1` + 真实人脸/语音做锚;
  2. **沉默不生成**(无摄像头时):冻结上一帧,掐掉空转漂移;
  3. **人脸裁剪对齐**(见 6.6);
  4. **换真人脸**(见 6.7)。
- **稳定锚的原理**:真实人脸是每帧新鲜、不带模型误差的**外部真值**;CFG 的
  `u_cfg·(用户引导−基础)` 项每步把生成往"和真人一致的合法脸"方向推(恢复力),
  同时让模型回到"训练时见过的分布内"工作区。**前提:必须是真实摄像头**(喂黑屏空白帧 +
  高 u_cfg 反而会贴合垃圾)。

### 6.5 治疗师摄像头收不到(`cam_total=0`)⭐ — 两个叠加 bug
- **bug A(服务端)**:`maybe_capture_participant_camera` 默认 **`framerate=0`**,而 Daily
  `transport.py` 里 `if framerate > 0:` 才推 `UserImageRawFrame` → 0 帧进管线。
  **修**:`patient_jordan.py` 里传 `framerate=25`。
- **bug B(客户端)**:Pipecat Playground / 旧测试页都 **`enableCam: false`**,根本没发摄像头。
  **修**:自建 `web/avatar-client.html`(`PipecatClient` + `DailyTransport`,**`enableCam: true`**,
  左显 avatar、右显本地预览、带摄像头开关)——**这就是 ClinicalSkillsLab 客户端的基础**。
- 媒体走 **Daily 云中继**:bot 与浏览器都连出到 Daily,所以只需 `/start` 的 HTTP 端点可达,
  视频流不需要 bot 有公网 UDP。

### 6.6 人脸裁剪对齐(治疗师帧)
- **症状**:摄像头通了、反应也有了,但 avatar 严重变形。
- **根因**:直接把宽幅 webcam 画面 resize 成 512 喂引擎;模型训练用的是**裁剪+对齐的人脸**,
  错位输入 = 坏锚 → 产出乱动作 → 变形。
- **修法**:在桥里复刻训练的 `preprocess_face`——用 `data_processor.fa.face_detector` 检测人脸 →
  居中裁正方形(pad_ratio=1)→ 512。性能:**人脸框缓存,每 12 帧重检一次**,裁剪在线程池里跑。

### 6.7 真人脸 vs 风格化脸(分布)⭐ — 最大的一招
- **观察**:换掉风格化的 `rumi.jpg`(3D 游戏角色)、改用**真人照片 `simli.png`** 后,脸立刻
  又稳又自然、不再融化。
- **根因**:AvatarForcing 在**真人说话视频**上训练;风格化卡通脸是**分布外(OOD)**,模型难维持 →
  容易飘。真人脸是分布内 → 又稳又自然。
- **结论**:真人脸 + 摄像头锚 + 人脸对齐三件套叠加,drift 基本压住。

---

## 7. 客户端 & ClinicalSkillsLab 集成路径

- **测试客户端** `web/avatar-client.html`:`PipecatClient({enableMic:true, enableCam:true})` +
  `DailyTransport`,连 bot 的 `/start`,发麦克风+摄像头、显示 avatar。
- **ClinicalSkillsLab(`FISTrainingTool`,Next.js)集成现状**:已有 `PipecatPanel.tsx`,
  就是连我们这套 bot 的现成面板(同栈,作为 HeyGen 面板的 drop-in,provider 可切)。接 AvatarForcing 只需:
  1. `enableCam: false → true`(给 AvatarForcing 这条路,反应靠它);
  2. `NEXT_PUBLIC_PIPECAT_BOT_URL` 指向 GPU bot 的 `/start`;
  3. 把 bot 的 `/start` 暴露成公网 HTTPS(+ CORS);媒体走 Daily 云,无需公网 UDP。
- 注:旧 `PipecatPanel` 注释里 `enableCam:false` 是因为旧 bot 不用视频且 aiortc(SmallWebRTC)
  解码报错;我们走 Daily + 服务端真用视频,已验证 enableCam:true 通且不卡。

---

## 8. 部署(Vast GPU)

- **GPU**:标准 24GB RTX 4090(❌ 避开 48GB 魔改卡,慢);Reliability ≥99.5%(便宜机器会掉线)。
- **torch 2.1.2 + cu118**:4090 是 sm_89,torch 2.0.1 缺 sm_89 kernel。bench **133ms/块(3x 实时)**。
- 坑已填:stringzilla 用 `--only-binary`、numpy<2、python-dotenv/fastapi、nltk punkt_tab、
  权重 `download_weights.sh` 在机上下(比 Mac 上传快)、av 休眠冲突忽略。详见 `VAST_DEPLOY.md`。
- **媒体**:Daily 传输(`-t daily`),浏览器经 SSH 隧道或公网端点连 `:7860/start`。

---

## 9. 当前状态与待办

**已跑通(端到端)**:STT→LLM(Jordan 人设)→TTS→avatar 对口型(音视频同步);治疗师说话时
avatar 实时反应;真人脸下稳定不漂移。

**已修**:音视频同步、RoPE 冻结、卡顿、drift、摄像头不进 bot、人脸对齐、自愈。

**待办 / 待定**:
- **本地"最优版"验收标准**——需开会定(延迟阈值、音视频质量基线)。
- **延迟优化**:每次回应里 avatar 缓冲(为同步而延后音频)是大头;旋钮:rctx 前瞻、队列深度、
  首块 NC(首块 2s 是架构性的,需权衡)。
- **反应调优**:`AF_U_LISTEN` 强度、人脸裁剪质量、说话时是否留轻微反应。
- **长会话 drift 兜底**(若真人脸下仍出现):定期重锚——趁沉默把生成刷回干净参考脸(目前未需要)。
- **集成**:`PipecatPanel` 三处改动 + bot `/start` 公网暴露(cloudflare named tunnel)+ CORS;
  persona 传递(让 bot 演选中的病人而非固定 Jordan)。

---

## 10. 关键数字(项目核心指标)

这类项目(实时交互式生成 avatar)最该盯 5 类数字。值为 2026-06-26 实测/配置。

### 一、延迟(体验第一指标)⭐
| 数字 | 值 | 说明 |
|---|---|---|
| 输出帧率 FPS | 25 fps(40ms/帧) | 流畅度基准 |
| 首块启动延迟 | ≈ 2s(NC=50 缓冲)+ rctx 0.4s | 每次连接暖机,架构性 |
| 单块前瞻 rctx | 10 帧 = 0.4s | 流式必等的"未来" |
| 单块计算 | 133ms(实测) | GPU 生成一块 |
| 音视频同步 | 音频延后对齐视频 | 已同步 |
| **端到端会话延迟** | **⚠️ 待精确测** | 说完→出声出画;优化重点 + 最优标准头号指标 |

### 二、实时倍率(能否跟上)⭐
| 数字 | 值 | 说明 |
|---|---|---|
| 单块预算 | 400ms(NB/FPS) | 须在此内生成完才不掉帧 |
| 实测单块 | 133ms | 仅用 1/3 |
| 实时倍率 | 3.0x | >1 才实时;余 2/3 可压延迟/提质量 |

### 三、资源 & 成本
| 数字 | 值 | 说明 |
|---|---|---|
| 显存 | 9.6 GB 实占 / 15.5 GB 预留 | 决定 GPU 选型(24GB 够) |
| 权重 | 1.1 GB(2 个 .pth) | 部署传输 |
| 磁盘需求 | ≥ 40–50 GB | 权重+torch+环境 |
| GPU | 24GB RTX 4090,DLPerf≈97 | torch 2.1.2+cu118(sm_89) |
| 成本 | ~$0.3–0.4/hr(Vast) | 单路会话 |
| 会话时长上限 | 50000 帧 ≈ 33min/连接 | RoPE 表(原 1024=41s) |

### 四、质量 / 行为旋钮
| 数字 | 值 | 说明 |
|---|---|---|
| a_cfg(音频引导) | 2.0(固定) | 嘴跟音频的紧/松 |
| u_cfg(用户引导) | 说话 0 / 倾听 1.0 | 反应强度(双模式,`AF_U_*`) |
| 去噪步数 nfe | 10 | 越多越精细越慢 |
| 输出分辨率 | 512×512 | 模型定死 |

### 五、内部参数(帧/块/音频)
| 数字 | 值 | 说明 |
|---|---|---|
| NB / NC | 10(0.4s)/ 50(2s) | 每块帧数 / 首块帧数 |
| KV cache 窗口 | 40 帧(NC−NB)= 1.6s | 模型有效时间记忆 |
| 音频采样率 SR | 16000 Hz | wav2vec 输入 |
| 每帧采样数 spf | 640(16000/25)= 40ms | 音频对齐视频 |
| lctx / rctx | 16 / 10 帧 | 滑窗左上下文 / 右前瞻 |
| 人脸重检间隔 | 12 帧 | 性能优化 |

**开会三句话**:① 能实时——单块 133ms / 预算 400ms = 3x,余量足;② 延迟——首块 ~2s 暖机 + 每块 0.4s 前瞻,**端到端会话延迟待测、是优化重点**;③ 资源——9.6GB 显存 + 1.1GB 权重,一张 24GB 4090(~$0.35/hr)够跑。

---

## 11. 关键文件索引

| 文件 | 角色 |
|---|---|
| `AvatarForcing-main/streaming.py` | 流式引擎(begin_live/push/first_block/step,滑窗 wav2vec) |
| `AvatarForcing-main/models/avatarforcing/flow_transformer.py` | 模型;`max_seq_len` 改 50000(RoPE 溢出修复) |
| `Avatar/avatarforcing_service.py` | **Pipecat 桥**(双模式、生产/消费、人脸裁剪、同步、自愈) |
| `Avatar/patient_jordan.py` | bot 主程序;AVATAR=avatarforcing 分支、摄像头捕获 `framerate=25` |
| `Avatar/web/avatar-client.html` | 测试客户端(enableCam:true);ClinicalSkillsLab 集成基础 |
| `FISTrainingTool-main/frontend/src/components/PipecatPanel.tsx` | ClinicalSkillsLab 里连本套 bot 的现成面板 |
| `Avatar/VAST_DEPLOY.md` | 云 GPU 从零部署清单 |
