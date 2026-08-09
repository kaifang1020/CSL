# Avatar 视频质量 — 评估指标速查 + 阅读地图

> 用途:**这不是替代你读 paper,是让你读得有的放矢。** 每个指标:测什么 / 要不要 ground-truth /
> 去哪篇 paper 读定义 / 用哪个现成代码 / 对我们"变形"问题多相关。
> 读法建议见文末"阅读顺序"——**只精读 3~4 篇的特定章节,其余用库、读定义即可。**
> 配套:根因见 [DRIFT_ANALYSIS.md](DRIFT_ANALYSIS.md);系统见 [ARCHITECTURE.md](ARCHITECTURE.md)。

关键分野:**有没有 ground truth(GT)**。我们那 32 个真人 clip **解锁了"有 GT"这一类(成对比对)**——比"无 GT(分布级)"强得多。

---

## 一、视觉质量

| 指标 | 测什么 | 要GT? | 读哪篇(定义) | 代码/库 | 对"变形"相关度 |
|---|---|---|---|---|---|
| **FID** | 单帧真实度(和真实分布的距离) | 否 | Heusel 2017 (TTUR / FID) | `pytorch-fid`, `clean-fid` | 中 |
| **FVD** | **视频级**真实度 + 时序连贯 | 否 | Unterthiner 2018 (FVD) | StyleGAN-V 的 FVD 实现 | **高**(时序稳定/漂移) |
| **LPIPS** ⭐ | 感知差异(逐帧对 GT) | 是 | Zhang 2018 (LPIPS) | `lpips`(pip) | **高**(离真人多远,直接测糊) |
| **SSIM / PSNR** | 结构/像素相似 | 是 | Wang 2004 (SSIM) | `skimage`, `piq` | 低-中(不感知,参考用) |
| **CPBD / 锐度** ⭐ | **模糊程度** | 否 | Narvekar 2011 (CPBD) | 现成实现 | **高**(直接测"糊",随时间画曲线) |

## 二、身份保持(直接量变形)⭐

| 指标 | 测什么 | 要GT? | 读哪篇 | 代码/库 | 相关度 |
|---|---|---|---|---|---|
| **CSIM** ⭐⭐ | 人脸身份相似(对参考脸的 cos-sim) | 否(对参考)/可对GT | 用 **ArcFace**(Deng 2019)嵌入 | `insightface` | **最高**:随时间画 = **漂移曲线** |

## 三、口型同步

| 指标 | 测什么 | 要GT? | 读哪篇 | 代码/库 | 相关度 |
|---|---|---|---|---|---|
| **LSE-C / LSE-D** | 口型与音频同步(置信度/距离) | 否 | **Wav2Lip**(Prajwal 2020),基于 **SyncNet**(Chung 2016) | Wav2Lip repo 的 eval | 中-高 |
| **LMD(嘴部)** | 嘴部关键点误差 | 是 | 各文常用 | landmark 检测器 | 中 |

## 四、运动/表情准确度(要 GT)

| 指标 | 测什么 | 要GT? | 工具 | 相关度 |
|---|---|---|---|---|
| **Head-pose error** ⭐ | 头姿误差(对真人) | 是 | SixDRepNet / OpenFace | **高**(姿势漂移) |
| **AU / expression error** | 表情(动作单元)误差 | 是 | OpenFace | 中 |

---

## 五、专门量"我们的变形"的三条曲线 ⭐

变形 = 质量**随时间**下降,所以关键不是单个数,是**曲线**:
1. **CSIM vs 时间**(身份还在不在)
2. **锐度(CPBD)vs 时间**(糊没糊)
3. **(有GT)LPIPS / 偏离真人 vs 时间**(离真实录像越漂越远)

这三条把"感觉糊了"变成**可对比的曲线**——任何"推理期修/微调"有没有用,看曲线降不降。

---

## 六、阅读顺序(只读这几篇的特定章节)

1. **AvatarForcing 2601 —— Experiments 一节** ⭐必读第一篇
   看它**到底报了哪些指标**(FID/CSIM/LSE/…),我们对齐它,结果才可比。
2. **一篇近期 SOTA talking-head 的 Experiments** —— 看整套 metric 在真实语境里怎么用/定义。
   从 **Hallo / VASA-1 / EMO / SadTalker** 挑一篇(近、指标全)。
3. **要实现哪个,才去读那个 metric 的原文/README**(且多数直接用库,读定义即可,不啃全文):
   - LPIPS → Zhang 2018 + `lpips` README
   - FVD → Unterthiner 2018 + StyleGAN-V FVD README
   - LSE → Wav2Lip README(SyncNet 评测)
   - CSIM → ArcFace(Deng 2019)+ `insightface`

> 原则:**①②精读(建立概念)③按需查(直接用代码)。** 不要一上来通读十几篇 metric 原文。

---

## 七、对我们项目,先实现哪几个

按"便宜 + 直击变形"排:
1. **CSIM vs time**(insightface,几十行)⭐ —— 第一条漂移曲线
2. **锐度(CPBD)vs time** —— 直接量"糊"
3. **有 GT 后**:LPIPS vs time + head-pose error(对真人 clip)
4. 补齐:FVD、LSE-C/D(对齐领域标准,写论文要)

先 1+2 出 baseline 曲线,再逐步补。
