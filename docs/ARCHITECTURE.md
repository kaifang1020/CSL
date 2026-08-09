8# Real-Time Digital Patient — System Architecture

A research-oriented, real-time conversational **digital patient** for **clinician /
therapist training**. The clinician speaks (and is seen on camera); the patient
reacts in real time — adjusting its replies, vocal tone, and an **explicit, observable
emotional state** — based on *what* the clinician says, *how* they say it (tone), and
their *facial expression*.

> **Core differentiator:** the patient's internal state (Guardedness / Grief / Working
> Alliance) is **explicit, measurable, and controllable** — unlike black-box products
> (e.g., HeyGen Live). This makes the system both a **research instrument** and a
> **product moat** (objective, quantified feedback on clinician skill).

---

## Pipeline v1 — Current (single-speed)

```
   Clinician ──▶ Custom Web Front-End  (mic + camera, WebRTC, self-hosted)
   (browser)            │  audio + video
                        ▼
 ┌─────────────────── INPUT — perceive the clinician ───────────────────┐
 │   WORDS                TONE                  EXPRESSION                │
 │   STT                  SER                   Vision                    │
 │   Deepgram nova-3      wav2vec2 (local)      GPT-4o-mini               │
 │        └───────────────────┴────────────────────┘                     │
 │                            ▼                                           │
 │                ╔══════════════════════════╗   ◀── THE DIFFERENTIATOR  │
 │                ║   PatientBrain (state)    ║                           │
 │                ║   Guardedness · Grief ·   ║   explicit, observable,   │
 │                ║   Working Alliance        ║   controllable state      │
 │                ╚════════════╤═════════════╝                           │
 ├─────────────────── OUTPUT — respond ─────────┼───────────────────────┤
 │            LANGUAGE            VOICE          │   FACE                 │
 │            LLM (Talker)   ──▶  TTS        ──▶ │   Avatar      ──▶ back │
 │            gpt-4o-mini         Cartesia       │   Simli Trinity-1      │
 │                               (tone driven    │   (Gaussian, cheap)    │
 │                                by state)       │                       │
 └────────────────────────────────────┬──────────────────────────────────┘
                                       ▼
            Session Logger ──▶ CSV / JSONL ──▶ Emotional-trajectory plots
            (per-turn state: Guardedness / Alliance / Grief over time)
```

---

## Components — model, latency, cost

> Latency = time-to-first-byte (TTFB) per component. **Replace with your measured
> values from the live panel.** Cost = per minute of session (estimates — verify
> against your Cartesia plan and Simli usage dashboard).

| Stage | Component | Model / Service | Location | Latency (TTFB) | Cost / min |
|---|---|---|---|---|---|
| Transport | WebRTC | SmallWebRTC (self-hosted) | Local | ~0 | $0 |
| Input · words | STT | Deepgram `nova-3-general` | Cloud | ~0.4 s | ~$0.004 |
| Input · tone | SER | wav2vec2 (`superb` ER) | Local | background¹ | $0 |
| Input · expression | Vision | GPT-4o-mini (vision) | Cloud | background¹ | ~$0.002 |
| Turn-taking | VAD + end-of-turn | Silero + Smart-Turn v3 | Local | — | $0 |
| **Brain** | **State machine** | **custom logic** | Local | ~0 | $0 |
| Output · language | LLM (Talker) | `gpt-4o-mini` | Cloud | ~1.3 s | ~$0.0005 |
| Output · voice | TTS | Cartesia `sonic-3.5` | Cloud | ~0.15 s | ~$0.025 |
| Output · face | Avatar | Simli **Trinity-1** (Gaussian) | Cloud | ~0.2 s | <$0.01 |
| Data | Logging + plots | local Python | Local | — | $0 |

¹ "background" = runs off the critical path — SER / Vision update the state for the
*next* turn and do **not** add to response latency.

**Totals**
- **Response latency** (clinician stops → patient starts speaking): **~1.5–2.0 s**
  - current bottleneck = **LLM TTFB (~1.3 s)** → next optimization target
- **Cost:** **~$0.04 / min ≈ ~$1.8 per 45-min session**
- **vs HeyGen Live (~$0.10–0.19/min): ~4–8× cheaper**, and not vendor-locked

---

## Pipeline v2 — Target (dual-speed cognition)

**v2 keeps the same end-to-end pipeline as v1.** The only change is *inside the
cognition layer* (PatientBrain): **how `PatientState` is computed.** It becomes a
**two-speed mind** — fast enough to talk in real time, with richer "thinking" that
runs between turns.

- **Fast lane** (every turn, real-time ~1 s): read the state, speak the reply — one
  LLM call, so latency is unchanged.
- **Slow lane** (between turns, async ~1–3 s): a **Reasoner / multi-agent system**
  re-appraises and updates the state during the clinician's *next* utterance — adds
  **no** response latency.
- **Shared PatientState**: the single object both lanes touch (fast **reads**, slow **writes**).

> Grounded in: *Talker-Reasoner* (Google DeepMind, 2024), *Generative Agents*
> (Stanford, 2023), System-1 / System-2.

```
   ┌───────────┐  reads   ┌──────────────┐  writes  ┌───────────┐
   │   FAST    │ ◀─────── │ PatientState │ ◀─────── │   SLOW    │
   │  "speaks" │          │  (the mood)  │          │  "thinks" │
   │  ~1s/turn │          │ guardedness… │          │  ~1–3s    │
   └───────────┘          └──────────────┘          └───────────┘
   reads the mood          the only shared           studies the turn,
   → replies instantly     object                    updates the mood
   (real-time)                                        (in the background,
                                                       between turns)
```

**What changes from v1 → v2**

| | v1 (current) | v2 (target) |
|---|---|---|
| State update | keyword + SER, **synchronous** on the fast path | **async Reasoner / MAS** between turns |
| Appraisal | keyword matching (brittle) | **LLM-based** (understands meaning + tone) |
| Affect dynamics | single step size | inertia · baseline regression · occasional withdrawal |
| Cognition modules | — | Appraisal · Affect · Defense · Memory · Alliance |
| Research value | observable state | **per-module, ablatable** (which module drives realism?) |
| Latency | real-time | **still real-time** (fast path unchanged; thinking is hidden between turns) |

> The fast path is unchanged in spirit — still one LLM call → still ~1 s. The richer
> cognition is moved **off the critical path**, so realism improves without hurting
> latency. This also lets the keyword/wav2vec2 appraisal (and its research-only licence)
> be retired.

---

## Avatar track — Self-hosted reactive avatar (AvatarForcing) · current work

Orthogonal to the v1→v2 *cognition* axis, this track replaces the **avatar layer**
(the `FACE` box in v1: Simli Trinity-1) with a **self-hosted, reactive** talking-head
engine — [AvatarForcing](https://arxiv.org/abs/2601.00664) — on a rented cloud GPU.
Two things change: (1) **no per-minute avatar vendor**; (2) the avatar becomes
**reactive** — it doesn't only lip-sync while speaking, it **reacts to the clinician**
(nods, gaze, expression) *while listening*, driven by the clinician's live camera.
This **reactive listening** is offered by neither Simli/HeyGen/Tavus nor either
AvatarForcing paper — it is the novel piece.

> Engineering details: [AVATARFORCING_ENGINEERING.md](AVATARFORCING_ENGINEERING.md).
> Central open problem (long-horizon drift): [DRIFT_ANALYSIS.md](DRIFT_ANALYSIS.md).

### Deployment topology (media via Daily cloud; bot on the GPU)

Two separate paths — heavy **media** goes through Daily's cloud; a single lightweight
**control** call goes through the SSH tunnel:

```
   ┌─────────────────────┐  ① media  ┌───────────────┐  ① media  ┌───────────────────────────┐
   │  YOUR MAC           │ (WebRTC)  │  DAILY CLOUD  │ (WebRTC)  │  VAST.ai  RTX 4090        │
   │  browser            │◀═════════▶│  managed      │◀═════════▶│  Pipecat bot              │
   │  (avatar-client)    │           │  media relay  │           │  patient_jordan.py        │
   │  mic + camera       │           └───────────────┘           │  :7860  (localhost only)  │
   └──────────┬──────────┘                                       └─────────────▲─────────────┘
              │                                                                 │
              └──── ② POST /start ──── SSH tunnel  -L 7860:localhost:7860 ──────┘
                    (one HTTP call, sent when you click "Connect")

   ① MEDIA   — your mic + camera (up) & avatar video + voice (down); continuous, relayed by Daily
   ② CONTROL — one /start call that launches the bot session; goes through the SSH tunnel
               (the bot's port 7860 is localhost-only on the GPU, so the tunnel bridges to it)
```

**Why two paths:** the bot's audio/video flows over Daily (managed WebRTC — works
through NAT/firewalls, no public port needed). The *only* thing that must reach the
GPU directly is the `/start` HTTP call to spin up a session — and since the bot binds
`7860` to `localhost` on the GPU, an SSH port-forward (`-L 7860`) bridges the browser
to it. **Media never touches the tunnel.**

### Bot internals (same brain, new avatar service)

```
 Daily in ─▶ STT ─▶ [PatientBrain state] ─▶ LLM ─▶ TTS ─┐
 (audio+cam)                                            ▼
        ┌──────────────  AvatarForcingVideoService (the bridge)  ─────────────┐
        │  producer/consumer @ strict 25 fps, synced audio                    │
        │   • SPEAK   TTS audio → lips              (u_cfg = 0)                │
        │   • LISTEN  clinician camera/voice → reactions   (u_cfg = 1)        │
        │   • re-anchor every ~12 s  (drift reset + 8-frame cross-fade)       │
        │  StreamingAvatarForcing engine — block-causal, KV cache, warmup     │
        └───────────────────────────────┬────────────────────────────────────┘
                                        ▼  avatar video ─▶ Daily out
```

### Model internals — how one avatar frame is made

Inside `StreamingAvatarForcing`, the engine is a **CNN + Transformer hybrid**: CNNs at
both ends (image ↔ latent), a Transformer in the middle that generates the *motion*.

```
  ── ENCODE (CNN, once per reference) ───────────────────────────────────────────
  reference face 512×512 ─[ CNN encoder ]─▶  s_r        identity  (who it is)
                                             s_r_feats   detail feature maps
                                             r_s         pose / motion baseline ──┐
                                                                                  │ conditioning
  ── PER-FRAME INPUTS ─────────────────────────────────────────────────────────  │
  clinician camera ─[ CNN face-crop (SFD) ]─▶ user motion ──────────────────────  ┤
  avatar audio (TTS) ─[ wav2vec ]─▶ audio features ────────────────────────────  ┤
                                                                                  ▼
              ┌────────────────────────────────────────────────────────────────────┐
              │  TRANSFORMER  (diffusion, block-causal)                             │
              │  flow_transformer · KV cache = ~1.6 s sliding window                │ ◀ generates a
              │  → one MOTION latent per frame        (attention — NOT a CNN)       │   motion latent
              └───────────────────────────────┬────────────────────────────────────┘
                                              ▼  motion latent (per frame)
              ┌────────────────────────────────────────────────────────────────────┐
              │  CNN GAN DECODER  (StyleGAN-style, styledecoder.py)                 │
              │  4→8→…→512, conv weights style-modulated by (identity + motion);    │ ◀ renders each
              │  s_r_feats injected for fine detail          (heaviest step)        │   512×512 frame
              └───────────────────────────────┬────────────────────────────────────┘
                                              ▼
                                       512×512 avatar frame
```

- **Reference → 3 tensors (encoded once):** `s_r` (identity) + `s_r_feats` (detail
  feature maps) + `r_s` (pose baseline). Note `r_s` enters as **conditioning**, *not*
  through the attention window — so the clean reference is not a persistent attention
  anchor (a key reason drift is uncorrected).
- **Where drift vs deformation live:** the Transformer's autoregressive rollout is
  where pose/gaze **drift** accumulates; the CNN decoder is where it **shows up** — if
  drift pushes the motion latent to an out-of-distribution pose, the decoder (trained
  mostly near-frontal) can't render it → blur / melt. Full analysis:
  [DRIFT_ANALYSIS.md](DRIFT_ANALYSIS.md).

### What's different from the v1 avatar layer

| | v1 (Simli Trinity-1) | Avatar track (AvatarForcing) |
|---|---|---|
| Hosting | Cloud vendor, per-minute | Self-hosted on rented GPU (~$0.05/hr flat) |
| Reactivity | Lip-sync only (speaking) | **Reactive while listening** (camera-driven) ⭐ |
| Transport | SmallWebRTC (local) | Daily (managed media; bot is remote) |
| Control | Black box | Full engine access (modes, `u_cfg`, re-anchor) |
| Open issue | — | **Long-horizon drift** → [DRIFT_ANALYSIS.md](DRIFT_ANALYSIS.md) |

### Measured (RTX 4090)

| Metric | Value |
|---|---|
| Engine / block (10 frames = 0.4 s video) | ~150 ms (bench) · ~230–290 ms (live, w/ face-crop) |
| Real-time factor | ~2.6× (generates faster than playback) |
| Peak VRAM | ~15.8 GB / 24 GB |
| End-to-end (clinician stops → patient speaks) | ~1 s fluent · ~1.85 s fragmented |
| GPU cost | ~$0.046 / hr (Vast 4090) — **no per-minute avatar fee** |

### Key mechanisms
- **Two-mode reactive design** — one engine, dynamic `u_cfg`: SPEAK (clean lip-sync,
  weak reaction) vs LISTEN (avatar audio silenced; clinician camera/voice drive reactions).
- **Streaming refactor** — offline batch model → incremental `push()`-per-block engine
  feeding a producer/consumer that emits at a strict 25 fps with synced audio.
- **Cold-start warmup** — pre-runs `first_block`/`step` at startup so the first utterance
  isn't eaten by ~5 s of kernel-compile latency.
- **Drift management** — periodic re-anchor + cross-fade. This is a *mitigation*; the
  drift itself is an architectural limit (2 s training horizon, no future-window
  refinement) — see [DRIFT_ANALYSIS.md](DRIFT_ANALYSIS.md).

---

## Key elements to highlight in the meeting

1. **Observable & controllable patient state** — Guardedness / Grief / Working
   Alliance, logged per turn → objective, quantified measure of clinician skill
   (black-box products cannot provide this).
2. **Multimodal perception** — patient responds to *words* (STT), *tone* (SER), and
   *facial expression* (Vision).
3. **State-driven output** — both *what* the patient says and *how it sounds* change
   with the state (e.g., guarded → clipped & flat; opening up → softer, slower).
4. **Modular & swappable** — avatar, TTS, LLM are config switches (Simli↔Tavus,
   OpenAI↔Cartesia, etc.); no lock-in.
5. **Cost advantage** — 4–8× cheaper than HeyGen Live; avatar cost solved with
   Trinity-1 (Gaussian splatting, <1¢/min).
6. **Local / privacy path** — STT/LLM/TTS can be moved on-device for clinical-data
   privacy (relevant to HIPAA / deployment).
7. **Research output** — per-session **emotional-trajectory plots** (the unique
   artifact; show one in the deck).

---

## Status & roadmap

**Done**
- Real-time voice conversation with explicit emotional state
- State-driven replies + state-driven patient voice (Cartesia)
- SER (tone) + Vision (expression) perception
- Per-turn session logging + trajectory visualization
- Custom web front-end (mic + camera) + live state / latency panel
- Trinity-1 avatar (cheap, working lip-sync)

**Next**
- Upgrade state appraisal: keyword/wav2vec2 → **LLM-based** (more accurate, frees CPU,
  removes the research-only SER licence concern)
- Lower latency further (faster LLM host, e.g., Groq)
- Patient *facial* reaction while listening (expression clips ↔ avatar switching)
- Deployment (server + Daily), website embedding, multi-session scale
- Compliance review (HIPAA) for real clinical use

---

## Notes / caveats
- Latency & cost above are **estimates** — substitute measured panel values + your
  actual Cartesia/Simli pricing.
- The local **SER model (wav2vec2-superb)** may be research-only licensed — swapping it
  for LLM-based appraisal also resolves commercial-use licensing.
- Clinical-data **privacy/compliance (HIPAA)** is a separate gate from model licensing.
