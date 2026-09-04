# Savannah live demo — 已验证不卡的完整配置(2026-09-04)

这一版是**实测流畅**的状态。出问题时拿它对照。

---

## 代码来源(混合的,必须记清楚)

| 来源 | 文件 |
|---|---|
| `jbnhandsome/clinical-avatar-demo` @ **`4f36d8f`**(main) | 基线 |
| 分支 **`eval-hierarchy-20260825`** @ `e82f5d9` | `avatarforcing_service.py` · `streaming.py` · `af_presets.sh` · `offline_test.py` · `seam_jitter.py` · `lipsync_check.py` |
| 本地(未提交) | `patient_jordan.py`(含新 `SAVANNAH_PROMPT` + 移植的 `_vad()`)· `patient_savannah.py` · `patient_greg.py` |

> ⚠️ **不是直接 checkout 那个分支。** 分支上的 Savannah 是旧版(2.5k 字符、旧参考帧),
> 只取了引擎文件,人设保留本地的新版。全量切分支会**回退人设**。

md5(前 12 位):

```
avatarforcing_service.py  25017c7a2915
streaming.py              9577bfb27a4d
patient_jordan.py         fa2aecc6c745
patient_savannah.py       15a4611a5467
```

---

## 机器

| | |
|---|---|
| GPU | **RTX 4090** 24GB,最高 3105 MHz |
| CPU | **AMD EPYC 7B13**(Zen 3)· **max 3539.79 MHz** · 32/256 vCPU |
| 内存 / 盘 | 1007 GB / 100 GB NVMe(11.6 GB/s) |
| Vast | `ssh -p 41805 root@108.39.26.2` · 108.39.26.2 |

> **CPU 主频是硬指标,不是可选项。** 同一块 A100 换 CPU(EPYC 7542 Zen2 → 7763 Zen3)
> 每块从 770ms 降到 280ms。租机器时 `CPU max MHz` < 3400 就别要。

---

## 环境

```
torch 2.0.1+cu118 · numpy 1.26.4 · face_alignment 1.5.0 · Python 3.11
provision.sh 一把过,约 5 分钟
```

numpy 必须是 1.x(2.x 与 torch 2.0.1 ABI 不兼容 → `RuntimeError: Numpy is not available`)。
`face_alignment` 必须 1.5.0(1.4.x 没有 `LandmarksType.TWO_D`)。

---

## 参考帧

```
data/savannah_hq.png     md5 e13597b9cc65f898c3101919d95bcf70
```

1254×1254,脸宽 776px。本地存档 `frozen/v1-golden/ref_frames/SAVANNAH_hq.png`。

> 旧的 `data/savannah/01316.jpg` 是官方预处理出的 512 裁剪帧,源视频里她的脸只有
> **~356px**,要放大 1.44× 才够 512 → 发糊。**换帧救不了**(全片脸宽标准差仅 7px)。
>
> ⚠️ 这张高清图**嘴是微张的**,静息嘴型靠 `AF_ANCHOR_PICK=mouth` 兜底,不能漏。
>
> ⚠️ `pick_ref.py` 的前 6 名全落在**字幕污染区**(preproc 2338–2416),
> 选中会把 "Now it is your turn to talk" 印进每一帧 —— 见 `results/sav_stress.mp4` 实证。

---

## 启动

```bash
AVATAR=avatarforcing AF_POSE_REG=0.2 AF_REANCHOR_S=0 AF_ANCHOR_PICK=mouth \
VISION=true AF_SEAM_BLEND=2 AF_MAX_Q=10 AF_VAD_START=0.5 AF_SHARPEN=0.6 \
python -u patient_savannah.py -t daily --host 0.0.0.0
```

`AF_SKIP_USER_ZERO` 默认就是开的,不用写。

**回退开关:** `AF_SKIP_USER_ZERO=0` · `AF_SHARPEN=0` · `AF_SEAM_BLEND=0` · `AF_VAD_START=0.2`

---

## 让它不卡的四个改动(按贡献排)

| 改动 | 效果 | 出处 |
|---|---|---|
| **`AF_SKIP_USER_ZERO`** 说话态跳过乘 0 会被丢弃的 user CFG 分支 | **−118 ms/块** | 分支 `e9cfbbc` |
| **`_to_output_frame` 加 `.contiguous()` 并移进线程池** | **4.03 → 0.20 ms/帧**;每块还给事件循环 ~51ms | 分支 `e9cfbbc` |
| **`AF_VAD_START=0.5`** 降低抢话灵敏度 | 原值 0.2 下,咳嗽/键盘声/**avatar 自己经音箱回麦** 都会触发打断,而每次打断**清空整个输出队列**(实测 85s 内 18 次、丢 202 帧 = 8 秒画面) | 分支 + 本地移植 `_vad()` |
| `AF_SEAM_BLEND=2` 块接缝融合 · `AF_SHARPEN=0.6` 输出锐化 | 观感 | 分支 `5b1b6f1` |

> **`.contiguous()` 的道理:** `permute` 之后张量在显存里不连续,`.cpu()` 会走慢路径
> —— 显卡只能零散地挑着搬,到了内存还要再整理一遍。先让显卡整块打包再搬。

---

## 实测(2026-09-04,本机)

| | 改之前(8-22 在 4090 上录的那批) | **改之后** |
|---|---|---|
| 块耗时中位 | 333 ms | **272 ms** |
| 超 400ms 预算 | 3.6% | **0%** |
| **输出队列深度中位** | **5 帧** | **10 帧**(顶到 `AF_MAX_Q=10` 上限) |
| **队列见底率** | **30%** | **6%** |
| VAD 打断 | — | **0 次** |

队列长期顶在上限 = 生成明显快过播放,不会再饿死。**画面卡的根因就是队列见底时冻帧。**

---

## 声音

```
CARTESIA_VOICE_SAVANNAH=71d08ba7-514f-4e36-9b7d-43ee3b5472dc   # 私有克隆,名字 "Savannah"
TTS=cartesia
```

⚠️ **配置只在 `~/Downloads/Avatar/.env` 里**,`clinical-avatar-demo` 本地没有 `.env`。
部署时必须从 Avatar 那份传,否则回落到 OpenAI TTS 的 `ash`(男声)。

起来后确认日志里有:`Cartesia voice(savannah): 71d08ba7-…`

---

## 起来后必查的四行

```bash
grep -aE "Cartesia voice|\[anchor\]|节点已启动|402" bot_savannah.log
```

| 该看到 | 不对说明 |
|---|---|
| `Cartesia voice(savannah): 71d08ba7-…` | `.env` 没生效 |
| `[anchor] pick=mouth -> 嘴开度 0.0000, 检了 17 帧` | 只检 1 帧 = 锚点预算没生效 |
| `AvatarForcing 节点已启动` | — |
| `402` 计数 0 | Cartesia 额度 |

---

## 坑

- **`pkill -f "patient_jordan.py"` 会杀掉自己**(执行的 shell 命令行里含那串字)。
  用 `pgrep -f "[p]atient_jordan.py"` 拿 PID 再逐个 kill。
- **pipecat 有 idle timeout**:建好房间约 5 分钟没人进,bot 自己退房间
  (日志 `Idle timeout detected`)。不是崩溃,重新 POST `/start` 即可。
- **`ServiceSettings: NOT_GIVEN: model` 是无害的**,pipecat 1.3.0 的校验唠叨,
  不影响 Cartesia 路径。
- **录制时戴耳机。** 外放会让 avatar 的声音回到麦克风,即使 `AF_VAD_START=0.5`
  也可能触发打断。这条比任何代码改动都直接。

---

## 已知没修的

- `streaming.py:147` 还有**第二处**同样的 `permute(...).cpu()` 慢路径(离线渲染用,
  不在 live 关键路径上)。
- **新 `SAVANNAH_PROMPT`(8685 字符 / 10 小节)尚未按 demo 脚本完整跑过一遍。**
  优先验 `docs/SAVANNAH_DEMO_SCRIPT.md` 的第 3、5、8 句。
