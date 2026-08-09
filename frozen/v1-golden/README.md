# v1-golden — 已验证可用的配置快照

冻结时间：2026-07-27。**这是实测确认效果良好的一版**，出问题时回到这里。

---

## 启动命令（照抄即可）

```bash
# 服务器上（tmux 里跑，脱离 SSH 会话）
tmux new-session -d -s cand "cd ~/AvatarForcing && \
  source /opt/miniforge3/etc/profile.d/conda.sh && conda activate afp && \
  AVATAR=avatarforcing AF_POSE_REG=0.2 AF_REANCHOR_S=0 AF_ANCHOR_PICK=mouth VISION=true \
  python patient_candice.py -t daily --host 0.0.0.0 2>&1 | tee bot_cand.log"
```

本地：
```bash
ssh -p <PORT> -N -L 7860:localhost:7860 root@<IP>      # 隧道
cd ~/Downloads/Avatar/web && python3 -m http.server 8000   # 页面
# 浏览器开 http://localhost:8000
```

---

## 关键参数及其理由

| 参数 | 值 | 解决什么 |
|---|---|---|
| `AF_POSE_REG` | **0.2** | 身份漂移：60s 内 CSIM 从崩塌(0.31) → 稳定(0.90)，漂移率 −0.116 → −0.001 /10s |
| `AF_ANCHOR_PICK` | **mouth** | 倾听时嘴张着：锚不再取首块第 0 帧（live 首块正在说开场白 → 锚被抓在张嘴瞬间），改为扫首块挑嘴最闭的帧 |
| `AF_REANCHOR_S` | **0**（关） | 旧的每 12s 重锚会把画面猛地跳回参考脸，视觉突兀；pose 正则已替代它 |
| `AF_TEMPORAL_EMA` | 0（关，默认） | 时序平滑收益仅 15%（震颤 7.3→6.2）却压抑真实反应，不值 |
| `AF_POSE_REG_MODE` | frame（默认） | 与 mean 模式实测无差别（抖动 10.4 vs 11.4，肉眼分不出），保留简单的那个 |

## 参考脸

| 病人 | 文件 | md5 | 为什么 |
|---|---|---|---|
| Candice | `data/CANDICE_v3/00141.jpg` | `e70c14a8b66544d55c64f6e976112d74` | 正脸 1.000、**神情平淡/悲伤**（临床贴合抑郁）、嘴开度 0.0665 |
| Savannah | `data/savannah/01316.jpg` | `cb2f3f77171bbea26f54c138080c2837` | 正脸 0.864、闭嘴、中性；取自干净区间 200–2250 |

**选参考脸的两条铁律：**
1. **表情优先于嘴闭合。** 嘴的问题由 `AF_ANCHOR_PICK=mouth` 解决，不要为了追求"嘴完全闭合"而选到带笑意的帧
   （踩过：Candice 的 `01795.jpg` 嘴开度 0.0000 但在微笑，对抑郁患者是错的）。
2. **避开首尾污染区。** 素材首尾有黑底标题卡和烧录字幕，官方预处理用"全片平均 bbox"把它们也裁成了"人脸帧"。
   选到带字幕的帧 → **每一帧生成画面都印着那行字**。
   - Candice 干净区间：**141–2187**（黑卡 1–140，字幕 2188+）
   - Savannah 干净区间：**200–2250**（黑卡 1–~120，字幕 ~2300+）

## 代码侧修复（都在本目录的文件里）

| 修复 | 文件 | 说明 |
|---|---|---|
| pose 正则 + 锚点挑选 | `streaming.py` | `_pick_anchor()`；`AF_ANCHOR_PICK=mouth` 时解码首块、逐帧量嘴开合、取最闭的一帧 |
| 显存泄漏 | `streaming.py` | `push()` 末尾 `self.frames.clear()`。不清则每分钟堆 ~1.1GB 显存 → 几分钟后 OOM → 生成块静默失败 → 画面冻住 |
| 打断处理 | `avatarforcing_service.py` | 处理 `InterruptionFrame`（**不是** `StartInterruptionFrame`，pipecat 1.3.0 里无此类名）：丢弃残留音频/画面 + 补静音块把嘴 flush 回闭合 |
| 每病人独立嗓音 | `patient_jordan.py` | 读 `CARTESIA_VOICE_<PATIENT>`，回落 `CARTESIA_VOICE_ID` |
| 启动器设脸 | `patient_candice.py` / `patient_savannah.py` | 之前 candice 没设 `AF_FACE`，会回落到默认 `simli.png` |

## 环境变量（写在 `.env`，不能用命令行传）

`patient_jordan.py` 用 `load_dotenv(override=True)` → **`.env` 会覆盖命令行同名变量**。改嗓音必须改 `.env`。

```
TTS=cartesia
CARTESIA_VOICE_CANDICE=837d4351-f2a7-4761-ada2-c1542c70c8ba
CARTESIA_VOICE_SAVANNAH=71d08ba7-514f-4e36-9b7d-43ee3b5472dc
```

## 运维坑（都踩过）

- **别中途重连**：每次连接加载一份 ~15GB 模型，叠两份就 OOM（24GB 卡只够一路）。要重连先重启 bot 清显存。
- **bot 必须在 tmux 里跑**：直接 ssh 后台跑会随会话一起死。
- **`pkill -f <pattern>` 会杀掉自己**：远端命令行里含同样字符串时。用字符类规避：`pgrep -f "patient_jorda[n]"`。
- **重定向前先 `mkdir -p results`**：新机上 `results/` 不存在会导致 `> results/x.log` 直接失败、脚本没跑。
- **`deploy.sh` 要带上病人启动器**：曾漏掉 `patient_candice.py` / `patient_savannah.py`。
- **锚点预算在新机器上不够**：`AF_ANCHOR_BUDGET_S` 默认 6s，但 face_alignment 首次调用要把模型
  载进 GPU，第一帧就耗 8~9s → 只采到 1 帧 → 锚退化成首块第 0 帧。实测嘴开度 0.0599（听话时嘴微张）
  vs 预算 30s 时 0.0000。已在 `patient_candice.py` / `patient_savannah.py` 里设成 30s + stride 3。
