# Evaluation Ledger — Real-Time Reactive Patient Avatar (AvatarForcing)

> **Purpose**: A single authoritative record of every **measured** result — each number annotated with its configuration, test condition, interpretation, gap to real footage, and where the data lives.
> This is the **results ledger**. For metric *definitions and algorithms*, see [EVALUATION_METRICS.md](EVALUATION_METRICS.md); for the paper reading map, see [EVALUATION.md](EVALUATION.md).
> Last updated: 2026-07-17. All numbers come from this project's `results/` directory and the `*.py` scripts listed in §10.

---

## 0. TL;DR — Key Findings and Locked-In Configuration

**Deployment configuration (each choice validated experimentally):**

| Setting | Value | Rationale |
|---|---|---|
| Pose regularization | **frame mode, λ = 0.1–0.2** | Eliminates identity drift (§1) |
| Temporal smoothing (EMA) | **off (0)** | Marginal benefit only (§2) |
| Re-anchoring | **off (`AF_REANCHOR_S=0`)** | Visually jarring; pose reg. supersedes it |
| Mean-mode pose reg. | **dropped** | Statistically indistinguishable from frame mode (§2) |
| Memory-leak fix | **`self.frames.clear()`** | Fixes the "freezes after a few minutes" failure (§5) |

**Status in one sentence**: Identity preservation now **matches real footage**; the principal remaining gap is **reduced sharpness** (which in turn weakens lip-sync confidence); drift, jitter, and freezing are all resolved; comparisons against **SOTA competitors, FVD, multi-turn coherence, and human evaluation** have not yet been performed.

---

## 1. Identity Preservation / Drift (CSIM)

### 1.1 Pose-regularization sweep (listening stress test, u_cfg = 1.0, 60 s)

| Configuration | Mean CSIM | Drift slope /10 s | End CSIM |
|---|---|---|---|
| λ = 0 (baseline) | 0.55 | **−0.116** (collapse) | 0.31 |
| λ = 0.05 | 0.79 | −0.035 | 0.72 |
| λ = 0.1 | 0.85 | −0.016 | 0.82 |
| **λ = 0.2** | **0.91** | **−0.001** (flat) | **0.90** |

**Interpretation**: Pose regularization drives the drift slope from −0.116 to ≈ 0 — it **removes** drift rather than merely delaying collapse. Figure: `results/posereg_sweep.png`.

### 1.2 u_cfg sweep (reactivity strength, 60 s listening)

| u_cfg | Mean CSIM | Drift /10 s |
|---|---|---|
| 1.0 | 0.548 | −0.116 |
| 0.5 | 0.592 | −0.118 |
| 0.3 | 0.737 | −0.093 (best resting point) |
| 0.0 | 0.703 | −0.094 |

**Interpretation**: Lowering u_cfg postpones collapse but never flattens the curve; flattening comes only from pose regularization. (Figures for this sweep were lost with a reclaimed server; numbers retained.)

---

## 2. Temporal Stability / Jitter (tremor, jitter)

### 2.1 High-frequency tremor (u_cfg = 1.0, 60 s)

| Configuration | tremor_hf (‰ of inter-ocular distance) | v1_jitter |
|---|---|---|
| Baseline (no regularization) | **21.0** | 30.4 |
| Pose reg. λ = 0.1 | 7.3 | 10.9 |
| + EMA 0.2 | 7.3 | 10.8 |
| + EMA 0.4 | 6.8 | 10.3 |
| + EMA 0.6 | 6.2 | 10.1 |

**Interpretation**: Pose regularization cuts tremor from 21.0 to 7.3 (−65 %). Adding EMA only reaches 6.2 (a further 15 %) at the cost of damping genuine reactions — **not worth it**. Figure: `results/jitter_hf.png`.

### 2.2 Frame mode vs. mean mode

Jitter is essentially identical (frame λ = 0.2 → 10.4 vs. mean λ = 0.2 → 11.4), and the two are visually indistinguishable → **mean mode dropped**. Figure lost with a reclaimed server (`jitter_fa.png`); numbers retained.

---

## 3. Visual Fidelity (Sharpness / FID) — with Ground-Truth Comparison

*(Speaking clip, driven by Candice's own audio, pose_reg = 0.2, u_cfg = 0, 30 s)*

| Metric | Real GT (ceiling) | Generated (ours) | Gap |
|---|---|---|---|
| **Sharpness** (Laplacian var.) | 57.8 ± 106.8 | 32.9 ± 2.4 | **softer, ≈ 57 %** |
| **FID** (distributional distance) | — | **149.13** | first baseline; lower is better |

**Interpretation**: Sharpness is the principal gap — the avatar is softer than real footage, which also depresses lip-sync confidence (§4). The root cause sits in the **GAN decoder's inability to reproduce real-footage crispness**; this is not tunable at inference time and would require decoder personalization or fine-tuning. Data: `results/gen_speak.mp4`; script: `eval_gt_compare.py`.

---

## 4. Lip-Sync (LSE) — with Ground-Truth Comparison

*(Same speaking clip as §3; SyncNet)*

| | AV offset (frames) | LSE-D (distance, ↓ better) | LSE-C (confidence, ↑ better) |
|---|---|---|---|
| **Generated avatar** | −1 | 8.06 | 4.06 |
| **Real Candice** | +1 | 7.00 | 6.04 |

**Interpretation**: Both offsets sit near zero → the avatar's **audio and video are aligned; the mouth genuinely tracks the audio** ✅. However, sync strength is weaker than real footage (LSE-C 4.06 vs. 6.04, ≈ 67 %), consistent with the sharpness deficit. Script: `run_lse.sh` (SyncNet).

---

## 5. Behavior: "Mouth Stays Open While Listening" — Unresolved / Proposed Fix Falsified

| Variant (speak 10 s → listen 30 s) | Speaking | Listening | Final 5 s |
|---|---|---|---|
| u1_zeros (reproduces live: reactive + zero audio) | 0.116 | 0.087 | 0.081 |
| u1_noise (audio fix: reactive + low-amplitude noise) | 0.115 | 0.093 | 0.084 |
| u0_zeros (control: reactivity off) | 0.115 | 0.081 | 0.085 |

**Conclusions**:
- The severe "mouth stuck open" symptom **could not be reproduced offline** — while listening, mouth openness settles at ≈ 0.08 (slightly parted), not agape.
- The proposed **"feed low-amplitude room tone instead of digital zero" fix was falsified** (0.093 vs. 0.087 — marginally *more* open) → **not implemented**.
- The **reactive channel is not the culprit** either (0.087 vs. 0.081).
- Leading hypothesis: the earlier severe symptom stemmed from the **memory leak** — as VRAM approached exhaustion, individual generation blocks failed and were skipped, corrupting the autoregressive state. Live behavior did improve after the leak fix, though this remains **unproven**.

Figure: `results/mouth_live.png`; script: `test_mouth_live.py`.

---

## 6. Latency / Compute

| Metric | Value |
|---|---|
| Per-block (10 frames) latency | 102–229 ms (varies across RTX 4090 hosts) |
| Real-time factor | 1.75–3.90× |
| Peak VRAM, single session | ≈ 15 GB |
| Concurrency | A 24 GB card supports **only one session** (≈ 15 GB per session, no sharing) |

---

## 7. Metric Coverage Status

| Dimension | Metric | Status | GT class |
|---|---|---|---|
| Identity / drift | CSIM + slope | ✅ measured (incl. GT) | C |
| Temporal | tremor / jitter | ✅ measured | C |
| Visual | sharpness | ✅ measured (incl. GT) | C |
| Visual | FID | ✅ measured (GT distribution) | B |
| Lip-sync | LSE-C/D | ✅ measured (incl. GT) | C |
| Latency | TTFB / RT factor | ✅ measured | — |
| Behavior | mouth openness | ✅ measured | C |
| Video realism | **FVD** | ❌ missing (needs I3D) | B |
| **SOTA comparison** | vs. Simli / Tavus | ❌ missing | C |
| Reactiveness | rPCC-Exp / Pose | ❌ missing (needs dyadic GT) | A |
| Multi-turn | persona / affect / role-flip / memory | ❌ missing | — |
| Subjective | MOS / preference | ❌ missing | C |
| Fairness | cross-identity degradation | ❌ missing | C |

*GT classes: **A** = frame-aligned paired ground truth; **B** = distributional ground truth; **C** = reference-free / comparative.*

---

## 8. Gap Roadmap (recommended priority)

1. **One-command evaluation script** — video in → all class-C metrics + curves + FID out. Operationalizes evaluation so every future change yields a report automatically.
2. **FVD + SOTA baseline** — completes both the "vs. real distribution" and "vs. competitor" axes (FVD needs the I3D model; Simli needs a same-input generation).
3. **Multi-turn semantic coherence** — LLM-judge plus probe dialogues; central to digital-patient credibility.
4. **Human evaluation (MOS / pairwise preference vs. SOTA)** — captures naturalness that objective metrics miss.
5. **Fairness** — run the same metric suite across different real identities and examine the variance (Candice is dark-skinned with textured hair; this is both an ethical and a quality requirement).
6. **(Long term) dyadic ground truth** — unlocks rPCC reactiveness and downstream training-efficacy studies.

---

## 9. Methodological Caveats (read before citing any number)

- **CSIM is computed against a single reference frame**, not against the GT distribution; both generated and real footage are scored by "distance to that frame."
- **Generation ≠ reconstruction**: even with identical driving audio, head pose and blinks will not align frame-to-frame with real footage → **per-frame LPIPS/SSIM against GT is not reported** (it would mislead).
- Drift and tremor tests use **u_cfg = 1.0, the worst-case listening regime**; the GT comparisons (FID / LSE / sharpness) use **speaking mode**.
- FID is sensitive to preprocessing and sample size; 149 is a coarse baseline — track the **trend**, not the absolute value.
- Some early figures were lost when preemptible servers were reclaimed (u_cfg sweep, `jitter_fa.png`); the numbers are retained here.

---

## 10. Data / Script Index

| Result | File | Script |
|---|---|---|
| CSIM drift curves | `results/posereg_sweep.png` | `sweep_csim.py` |
| Tremor bar chart | `results/jitter_hf.png` | `jitter_hf.py` |
| GT comparison (CSIM / sharpness / FID) | numbers in §3 | `eval_gt_compare.py`, `run_gt_eval.sh` |
| Lip-sync LSE | numbers in §4 | `run_lse.sh` (SyncNet) |
| Mouth openness | `results/mouth_live.png` | `test_mouth_live.py`, `mouth_metric.py` |
| Generated speaking clip | `results/gen_speak.mp4` | `gen_avatar.py` |
| Ablation videos | `results/posereg_*.mp4`, etc. | `test_drift.py` |
