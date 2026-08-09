# Digital Patient Avatar — Progress Brief

*Prepared for a non-engineering (clinical/psychology) audience.*

---

## 1. How to present the results — suggested script

### Slide 1 — Side-by-side video *(show this first, say almost nothing)*
> "On the left is a real recording of our standardized patient. On the right is our digital patient, driven by **the same audio**. Same person, same words. I'll let you watch for twenty seconds before I say anything."

*Rationale: the audience forms their own judgement before any number frames it. Nothing you say will be as persuasive as what they see.*

### Slide 2 — `prof_vs_human.png` *(the "% of real human" chart)*
> "To make this measurable rather than impressionistic, we benchmarked the avatar **against the real recording of the same person** — the real footage is our 100% ceiling. Three dimensions matter clinically:
>
> - **Identity preservation — 100%.** After a full minute of conversation, the avatar is still recognizably the same person, exactly as stable as the real recording. This is the problem we solved this cycle: the face used to visibly degrade after about fifteen seconds.
> - **Lip-sync accuracy — 67%.** The mouth genuinely tracks the speech — the audio and video are aligned to within one frame — but the articulation reads less crisply than a real person's.
> - **Image sharpness — 57%.** This is our honest weak point. The avatar is softer than real video, and this is what also drags the lip-sync number down.
>
> So: identity is solved, and the remaining gap is essentially one problem — **resolution** — which we've traced to a specific component of the model."

### Slide 3 — `posereg_sweep.png` *(the drift curve — the engineering story)*
> "This is what we fixed. Each line is the avatar's identity similarity over sixty seconds of conversation.
>
> The **blue line** is the original model: within fifteen seconds the face starts drifting and by the end the patient is no longer recognizable. The **red line** is our fix — flat for the full minute.
>
> We diagnosed this as an accumulation problem inherent to this class of model, and solved it by adding a weak restoring force that continuously pulls the face back toward a clean reference — without freezing the patient's reactions."

### If asked "is this good enough for training?"
> "Identity and audio-video alignment are at human parity, so it holds up as a person. The sharpness gap is real and we know its cause. The honest answer is that we have not yet run the study that would settle it — a **human evaluation with clinicians**, which is the next thing we'd want your input on designing."

**Presentation rules of thumb**
- Never say "CSIM", "FID", or "LSE-C" out loud. Say *identity*, *realism*, *lip-sync*.
- Always anchor to **"compared with the real person"** — that's the frame a clinician already thinks in (criterion validity).
- Volunteer the weak number (57%) before you're asked. It buys credibility for the 100%.

---

## 2. Progress this cycle — what is better than before

| # | Problem before | Status now | How |
|---|---|---|---|
| 1 | **Face drifted / "melted" after ~15 s** — patient became unrecognizable (identity similarity fell 0.9 → 0.3 over 60 s) | **Solved.** Flat for the full minute (0.90 at 60 s); drift rate cut from −0.116 to −0.001 per 10 s — **at parity with real footage** | Pose regularization: a weak restoring force pulling the motion representation toward a clean anchor at every generation step |
| 2 | **Visible jitter / trembling** | **Reduced 65%** (21.0 → 7.3) | Same mechanism — the drift fix also stabilized the tremor |
| 3 | **Froze after a few minutes** of conversation | **Solved.** Zero failures across a full live session | Found a GPU memory leak: decoded frames were accumulating at ~1.1 GB/min until the card ran out and generation blocks silently failed. One-line buffer fix |
| 4 | **Jarring "snap back"** every 12 s (the old anti-drift hack reset the face to a reference image) | **Removed entirely** | The new regularization makes the reset unnecessary |
| 5 | **Speech cut off mid-sentence; mouth left hanging open** | **Fixed** | The service ignored interruption events — stale audio and frames kept playing and the mouth was never closed. Now it discards stale buffers and flushes the mouth shut |
| 6 | **No objective evaluation at all** | **Established.** First ground-truth benchmark: identity, sharpness, realism (FID), lip-sync — all against real footage of the same person | Built the measurement pipeline (drift curves, tremor, FID, SyncNet lip-sync) |

**Two honest negative results** *(worth reporting — they prevented bad changes from shipping)*
- A proposed fix for the open-mouth problem (feeding low-level room tone instead of digital silence) was **falsified** by offline testing and **not shipped**.
- Temporal smoothing (EMA) delivered only a 15% gain while damping genuine reactions → **dropped**.

---

## 3. Next plan — where to focus

### Priority 1 — Image sharpness *(the one real quality gap: 57%)*
The avatar is softer than real footage, and this also depresses lip-sync confidence. We traced the cause to the model's **image decoder**, which cannot be improved by tuning at run time. The realistic paths are:
- **Decoder personalization / fine-tuning** on the target identity (constrained: the authors released inference code only).
- Alternatively, evaluate a higher-resolution synthesis path.

**Expected payoff: this single fix should lift both sharpness and lip-sync.**

### Priority 2 — Complete the evaluation
- **FVD** — video-level realism (currently only frame-level FID).
- **Comparison against commercial SOTA** (Simli / Tavus) — we can currently say "how close to real", not "how we compare to what's on the market".
- **Human evaluation (MOS / paired preference)** — the naturalness judgement no objective metric captures. **We'd want your input designing this.**

### Priority 3 — Multi-turn coherence *(the "brain", not the face)*
Persona consistency, coherent affective trajectory, memory of earlier disclosures, and — a real failure we've observed — the patient never breaking character into the clinician's role. **This is arguably what decides clinical credibility, and it's the dimension where clinical expertise matters most.**

### Priority 4 — Fairness across identities
Verify the model does not degrade more on some faces than others (our current patient is dark-skinned with textured hair). Both an ethical requirement and a quality check before any multi-patient deployment.

### Priority 5 — Concurrency / cost
Each session currently occupies ~15 GB, so one GPU serves **one student at a time**. This must be addressed before classroom-scale deployment.

---

*Supporting data: `EVALUATION_LEDGER_EN.md` (all measured numbers, with method and caveats); `EVALUATION_METRICS.md` (metric definitions).*
