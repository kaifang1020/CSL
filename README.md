# ClinicalSkillLab — 实时数字人患者(Real-time Digital Patient)

一个**研究导向**的实时数字人"患者",用于**训练治疗师(therapist)**:治疗师用语音(可选摄像头)与一个有**显式情绪状态**的虚拟患者对话,患者会根据治疗师**说了什么 / 怎么说(语气) / 表情**实时调整自己的回应、语气和状态。每节对话的状态轨迹会被记录,可用于量化评估和研究。

核心区别于 HeyGen/Tavus 等黑盒产品的地方:**患者的情绪状态(防御/哀伤/联盟)是显式、可观测、可记录的** —— 既是研究工具,也是产品护城河(能给治疗师客观反馈)。

---

## 架构(Pipeline)

```
治疗师(浏览器:麦克风 + 摄像头)
        │ WebRTC
        ▼
  transport.input()
        │
   ┌────┴─────────────────────────┐
   ▼(说什么)      ▼(怎么说/语气)   ▼(表情)
  STT(Deepgram)   SER(本地)       VISION(GPT-4o-mini 看图)
        │              │               │
        └──────────────┴───────┬───────┘
                               ▼
                      PatientBrain(状态机)
                  guardedness / grief / alliance
                   · 按状态注入 system prompt
                   · 按状态控制 TTS 语气
                               ▼
              LLM(gpt-4o-mini, Talker)→ TTS → Avatar(Simli)→ 浏览器
                               │
                       SessionLogger → sessions/*.csv,*.jsonl
```

---

## 文件说明

| 文件 | 作用 |
|---|---|
| **`patient_jordan.py`** | 主程序:整条 pipeline + PatientBrain 状态机 + 状态/语气注入 + 实时状态写出 |
| **`ser.py`** | 语音情绪识别(SER):听治疗师语气 → 写 `state.therapist_warmth`(opt-in) |
| **`vision.py`** | 摄像头表情分析:GPT-4o-mini 看治疗师表情 → 写 `state.therapist_attentiveness`(opt-in) |
| **`session_log.py`** | 每节对话落盘:治疗师话 + 患者回复 + 当时状态 → CSV/JSONL |
| **`plot_session.py`** | 把一节 session 的情绪轨迹画成图(PNG) |
| **`web/index.html`** | 自定义前端:麦克风+摄像头,连 bot,显示患者 + 实时状态面板 |
| **`start.command`** | 一键启动:清理旧进程 → 起网页服务器 → 开浏览器 → 跑 bot |
| `simli_demo.py` / `tavus_demo.py` / `test.py` | 早期厂商 API 试验脚本(legacy,key 已打码) |
| `.env`(本地,不提交) | 所有 API key 和功能开关 |
| `sessions/`(本地,不提交) | 自动生成的会话记录 |

---

## 环境准备

```bash
# Python 3.12,建议用 conda/venv
pip install "pipecat-ai[simli,openai,silero,webrtc,whisper,deepgram,runner]" python-dotenv
# SER(可选):pip install transformers torch torchaudio
# VISION(可选):pip install Pillow
# 画图(可选):pip install matplotlib
```

`.env`(复制下面模板,填入你自己的 key):
```
SIMLI_API_KEY=...
SIMLI_FACE_ID=...           # app.simli.ai → Faces 里选一张脸
OPENAI_API_KEY=...          # 同时给 LLM 和 TTS 用
DEEPGRAM_API_KEY=...        # 不填则回退本地 Whisper(慢)
# 可选开关:
# SER=true                  # 开语气识别
# VISION=true               # 开摄像头表情识别
# AVATAR=tavus              # 换 Tavus avatar(默认 Simli)
# SIMLI_TRINITY=true        # 仅当确认走 Trinity playImmediate 路径时;一般保持关闭
```

---

## 用法

**一键启动(推荐):**
```bash
./start.command            # 或在 Finder 里双击
```
它会自动:起网页服务器 → 打开浏览器 → 跑 bot。然后在网页点 **Connect**,允许摄像头/麦克风。

**手动启动(两个终端):**
```bash
# 终端 1:bot
python patient_jordan.py
# 终端 2:前端
cd web && python -m http.server 8000
# 浏览器开 http://localhost:8000
```

**看情绪轨迹图:**
```bash
python plot_session.py          # 画最新一节
```

---

## 功能开关(`.env`)

| 开关 | 作用 |
|---|---|
| `SER=true` | 患者感知治疗师**语气**(本地 wav2vec2) |
| `VISION=true` | 患者感知治疗师**表情**(GPT-4o-mini 看图;前端需开摄像头) |
| `AVATAR=tavus` | 用 Tavus avatar(唇形更好,更贵);默认 Simli |
| `DEEPGRAM_API_KEY` | 填了用云端 Deepgram(快);留空回退本地 Whisper |

---

## ⚠️ 注意事项

1. **不要提交 `.env`**(含真实 key)。已在 `.gitignore`。
2. **商用许可**:云 API(OpenAI/Deepgram/Simli)可商用;**本地 SER 模型(wav2vec2-superb)可能是 research-only**,商用前需核实其许可,或换成 LLM 判断语气。
3. **临床合规**:对话/视频会经过云 API,真实临床使用前需评估 HIPAA / 数据合规。

---

## 状态:研究原型 → 应用

- ✅ 实时语音对话、显式情绪状态、状态驱动语气/回复、SER 语气感知、VISION 表情感知、数据落盘、可视化、自定义前端;
- 🔜 状态评估升级(关键词/wav2vec2 → LLM 语义判断)、避开 research-only 模型、部署(Daily/服务器)、接入网站、合规。
