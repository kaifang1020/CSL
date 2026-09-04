# Greg live demo — 产出录像的完整配置(2026-08-22)

在 RTX 4090 上录制。这份是**能复现那段 demo 的全部参数**。

## 代码

| | |
|---|---|
| 代码基 | `github.com/jbnhandsome/clinical-avatar-demo` @ `4f36d8f` + Greg 移植(未提交) |
| 入口 | `patient_greg.py`(**必须走它** —— 直接跑 `patient_jordan.py` 会跳过锚点预算) |
| `GREG_PROMPT` | **6434 字符**(含 `RESPONSE LENGTH` 四条,已删除字面示例回复) |

## 参考帧

```
data/greg_hq.png     md5 6d3df0218930396b37780425883fa931
```

1254×1254,脸宽 477px → 裁剪框约 953px → 到 512 是**缩小 0.54×**。
本地存档:`frozen/v1-golden/ref_frames/GREG_hq.png`

> 对比:从视频里裁的 `data/GREG_v3/01920.jpg` 脸宽仅 183px,需**放大 1.40×**,
> 锐度 16.1;高清图锐度 **269.7(16.8 倍)**,而嘴闭合/睁眼/正脸各项不差。

## 环境变量

```bash
AVATAR=avatarforcing
AF_POSE_REG=0.2            # 全程同值(分模式版本未启用)
AF_REANCHOR_S=0            # 关重锚
AF_ANCHOR_PICK=mouth
AF_ANCHOR_BUDGET_S=30      # patient_greg.py 内设;默认 6s 在冷机上只够采 1 帧
AF_ANCHOR_STRIDE=3
VISION=true
AF_VIDEO_BITRATE=2500000   # ★新增:之前根本没设,Daily 自适应压糊了脸
```

## 引擎 / 传输

| | |
|---|---|
| `nfe` | 10 |
| `fps` | 25 |
| `num_frames_per_block` | 10(=0.4s) |
| `input_size` | 512(**权重定死,改不了**) |
| Daily 视频输出 | 512×512 · **2.5 Mbps** · 25fps |

## TTS

```
TTS=cartesia
CARTESIA_VOICE_GREG=9c617ca4-c244-4c65-aaf4-10d08bae05c5
```

⚠️ Cartesia **TTS 额度耗尽时 WebSocket 返 HTTP 402**,而 REST `/voices` 仍返 200 ——
**key 有效不代表能用**。退路:`.env` 改 `TTS=openai`,配
`OPENAI_TTS_VOICE=ash` + `OPENAI_TTS_INSTRUCTIONS`(老年男性语气)。

## 实测性能

| | 每块(10帧) | 实时倍率 |
|---|---|---|
| **RTX 4090** | 102–229ms | **3.0×** ✅ |
| A100-SXM4-40GB *(EPYC 7542, Zen 2)* | **770ms** | **0.52×** ❌ |
| A100-SXM4-80GB *(EPYC 7763, Zen 3)* | **280ms** | **1.43×** ✅ |

> ⚠️ **更正(2026-09-04):** 原先记的"A100 跑不动实时"是**错的** —— 那台的瓶颈是 CPU 不是 GPU。
> 同一款 A100 只换 CPU(Zen 2 → Zen 3),每块 770ms → 280ms,**快 2.75 倍**。
> 这个负载是 latency-bound(一块 21,580 次微小运算,GPU 利用率仅 35%),
> **选机器看 GPU 主频 + CPU 单核,不看型号档次和显存。** 4090 仍然最优(3.0×)。

峰值显存 ~6.3GB(bot)/ 9.84GB(bench)—— **24GB 已是数倍富余,不必为更大显存付钱。**

## 未启用但已就绪的旋钮

- `AF_POSE_REG_SPEAK` / `AF_POSE_REG_LISTEN`(分模式)—— Candice 上离线双赢,
  **Greg 上未复现**(嘴开度 +16% 而非 −73%)
- `AF_A_SPEAK` / `AF_A_LISTEN`
- `AF_ANCHOR_PICK=ref` —— Candice 上有害(她参考图嘴微张 0.0665);
  **Greg 的参考帧嘴是抿紧的,该机制不成立,值得重测**
- `AF_USER_MOTION` / `AF_USER_AUDIO` 通道消融
