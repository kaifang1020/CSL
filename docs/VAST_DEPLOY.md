# Vast 云 GPU 部署清单(AvatarForcing live demo)

租到机器后,SSH 进去照着一步步贴。HPC 上踩过的坑已提前解决。
占位符:`<PORT>` / `<HOST>` 用 Vast 给你的 SSH 连接信息填。

---

## 0. 租实例
- **1x RTX 4090**(或 3090),**VRAM ≥24GB**,**Disk 拉到 ≥40GB**,**verified**,**Reliability ≥99.5%**,地区离测试者近。
- 模板:**PyTorch (Vast)** 或 **NVIDIA CUDA**(要带 **SSH** 标签;CUDA 版本随便,ARM 标签无视)。

---

## 1. ⭐ 先验 WebRTC 出网(没过就停掉换实例,别往下)
SSH 进去后:
```bash
unset http_proxy https_proxy
curl -sI --max-time 10 https://api.daily.co | head -1     # 要返回 HTTP 状态行
nc -u -z -w5 stun.l.google.com 19302 && echo "UDP OK" || echo "UDP BLOCKED"
```
- **curl 通** → 继续(WebRTC 至少能走 TCP 回退)。
- **curl 超时** → 这台没直接出网,**停掉换一台**。

---

## 2. 建 afp 环境(Python 3.11 + torch cu118)
```bash
# 没有 conda 就装 miniconda（PyTorch 模板一般已自带 conda，可跳过这步）
which conda || (curl -sL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/mc.sh && bash /tmp/mc.sh -b -p $HOME/miniconda && source $HOME/miniconda/bin/activate && conda init bash && exec bash)

conda create -n afp python=3.11 -y
conda activate afp
pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 \
  --index-url https://download.pytorch.org/whl/cu118
```

---

## 3. 传代码 + 权重(这两条在你 Mac 上跑)
```bash
# 引擎 + 权重 + streaming/bench（AvatarForcing-main 里）
rsync -avz -e "ssh -p <PORT>" --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  ~/Downloads/AvatarForcing-main/ root@<HOST>:~/AvatarForcing/

# bot 文件（Avatar 项目里）
rsync -avz -e "ssh -p <PORT>" \
  ~/Downloads/Avatar/patient_jordan.py ~/Downloads/Avatar/avatarforcing_service.py \
  ~/Downloads/Avatar/session_log.py ~/Downloads/Avatar/vision.py ~/Downloads/Avatar/ser.py \
  ~/Downloads/Avatar/.env \
  root@<HOST>:~/AvatarForcing/
rsync -avz -e "ssh -p <PORT>" ~/Downloads/Avatar/web root@<HOST>:~/AvatarForcing/
```
> 权重 ~3GB,看你 Mac 上行速度,传几分钟。若太慢,可改从 HPC 登录节点 rsync(HPC 网快)。
> **avatar 脸图**:bot 默认用 `data/simli.png`。确保 `~/AvatarForcing/data/` 下有这张脸(没有就把它一并 rsync 过去,或先用仓库自带的 `data/rumi.jpg` 测,跑 bot 时设 `AF_FACE=data/rumi.jpg`)。

---

## 4. 装依赖(回到 Vast,afp 环境,AvatarForcing 目录)
```bash
conda activate afp
cd ~/AvatarForcing

pip install -r requirements.txt
pip install face_alignment
pip install "numpy>=1.26.4,<2"        # requirements 会把 numpy 降到 1.26.0，补回（pipecat 要 ≥1.26.4）

# pipecat（若报 stringzilla 编译失败，先跑下一行再重试本行）
pip install "pipecat-ai[daily,deepgram,silero,webrtc,openai]==1.3.0"
# 万一 stringzilla 编译挂了：pip install --only-binary=:all: stringzilla  然后重跑上面那行

pip install python-dotenv fastapi   # bot 要的小包
conda install -c conda-forge ffmpeg -y
python -c "import nltk; nltk.download('punkt_tab')"   # pipecat 断句要

# 说明：会有 "aiortc 要 av≥14 但装了 av 12" 的冲突警告 —— 休眠冲突，忽略（HPC 用 Daily 不用 aiortc）
```

---

## 5. 验引擎延迟(<400ms 才能实时)
```bash
python bench.py
```
- **平均每块 <250ms** → 🟢 很稳。
- **250–350ms** → 🟡 能跑但紧。
- **>350ms** → 🔴 换更快的实例。

(可选)再验桥在真管线里没问题:`python pipeline_smoke.py`(出 results/pipeline_smoke.mp4)。

---

## 6. 配 Daily + key
编辑 `~/AvatarForcing/.env`,确认这几个填好(没注释掉):
```
DAILY_API_KEY=你的_daily_key
OPENAI_API_KEY=你的_openai_key
DEEPGRAM_API_KEY=你的_deepgram_key   # 没有就会退回本地 whisper（要额外装），建议填
```

---

## 7. 跑 bot + 浏览器连
```bash
conda activate afp
cd ~/AvatarForcing
export AVATAR=avatarforcing        # 用我们的引擎
# 若脸图不是 simli.png：export AF_FACE=data/你的脸.jpg

python patient_jordan.py -t daily
```
- 看终端打印的 **Daily 房间 URL** → 浏览器打开 → 允许麦克风/摄像头 → 和 Jordan 对话。
- 第一次连会触发模型加载(几秒~十几秒),然后 Jordan 开口。

---

## 排查(第一次 live 常见)
- **没声音/没画面但房间连上了**:多半 WebRTC 媒体没通(回到第 1 步确认 UDP/出网;或换实例/地区)。
- **bot 启动报缺包**:`pip install <缺的包>`,再跑(import 会逐个揪出来)。
- **延迟卡顿**:bench 看是不是 GPU 不够快(换卡);或调小 `nfe`(质量换速度);或加桥的前瞻/背压(后续优化)。
- **模型加载报 sm_89 no kernel**(4090):`pip install --upgrade "torch==2.1.*" --index-url https://download.pytorch.org/whl/cu118`(模型代码不变)。

---

## 一句话流程
租(1x4090/24GB/40GB盘/SSH)→ ①验出网 → ②建afp → ③传代码权重 → ④装依赖 → ⑤bench<400ms → ⑥填key → ⑦`AVATAR=avatarforcing python patient_jordan.py -t daily` → 浏览器开 Daily URL。
