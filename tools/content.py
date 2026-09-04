# -*- coding: utf-8 -*-
"""重排后的框架内容 —— 图和文档共用这一份,保证两边永远一致。"""

TITLE    = "Avatar Evaluation — Temporal Hierarchical Framework"
SUBTITLE = "Each timescale is assessed on two independent axes. A metric belongs to the smallest level at which its failure becomes visible."

AXES = [
    ("A", "TECHNICAL FIDELITY",
     "Does the system render the interaction correctly?"),
    ("B", "PSYCHOLOGICAL FIDELITY",
     "Does the simulated patient behave plausibly?"),
]

RULES = [
 ("Levelling rule",
  "A metric belongs to the smallest level at which its failure becomes visible. A blurred face shows up in a single still (frame); "
  "jitter is invisible in a still but obvious over a few seconds (turn); identity drift only emerges across the whole conversation (session)."),
 ("Sample size is not a level",
  "How many samples an estimator needs is a property of the statistic, not of the level. FID requires thousands of frames, "
  "but what it tests — whether an individual frame looks real — is a frame-level property, so it stays at frame level."),
 ("Reporting principle",
  "Do not average the metrics into a single score. Report a temporal profile: frame → perceptual realism, turn → interaction quality, "
  "session → identity and trajectory. Separating the two axes keeps a technical artifact (e.g. a lip-sync failure) from being misread "
  "as a psychological failure (e.g. an implausible emotional reaction)."),
]

# (aspect, 在测什么问题, [具体指标])
LEVELS = [
 dict(key="FRAME", scale="one rendered image", dur="≈ 40 ms",
      test="Freeze the video. Is this single image correct?",
      tech=[
        ("Identity consistency",
         "Does the generated face remain the same person as the reference?",
         "CSIM · ArcFace similarity against the reference portrait"),
        ("Image quality",
         "Is the frame realistic, sharp and free of artifacts?",
         "sharpness (Laplacian variance) · FID, aggregated across frames · LPIPS — requires a ground-truth frame, so controlled replay only"),
      ],
      psy=[
        ("Facial-state congruence",
         "Does the visible expression match the patient state the system intends to portray?",
         "blinded expression rating against the intended state; sadness must not render as happiness, restricted affect must not become exaggerated"),
      ]),
 dict(key="TURN", scale="one patient–therapist exchange", dur="seconds",
      test="Play one exchange. Does it move correctly and respond correctly?",
      tech=[
        ("Temporal coherence",
         "Are consecutive frames stable, or does the picture shake, flicker and stall?",
         "landmark displacement · jitter rate · flicker rate · freeze rate"),
        ("Audio-visual synchronisation",
         "Does the mouth match the sound being produced?",
         "LSE-D / LSE-C (SyncNet, 5-frame window) · lip-landmark error — requires a ground-truth mouth shape"),
        ("Responsiveness",
         "Does the patient reply quickly enough to sustain a real conversation?",
         "time-to-first-response · end-to-end latency · interruption recovery"),
        ("Listening behaviour",
         "Is the avatar convincing while it is not speaking?",
         "natural resting face · mouth closure · idle-state animation"),
      ],
      psy=[
        ("Response appropriateness",
         "Is the answer reasonable given what the therapist just said?",
         "blinded clinician rating of appropriateness · off-target response rate"),
        ("Conditional behavioural response",
         "Does the patient react differently to empathy, pressure, judgment and support? This probes the internal model, not the surface text.",
         "paired-probe design: same content delivered with different stances, measuring divergence in the reply"),
        ("Interactional style",
         "Are length, elaboration and hesitation consistent with the persona?",
         "response length distribution · elaboration rate · hesitation and self-repair markers · turn-taking pattern"),
        ("Cross-modal state congruence",
         "Do text, voice, face and gesture agree with what the patient is expressing?",
         "blinded 1–5 compatibility rating across the four modalities · unsupported contradiction rate"),
      ]),
 dict(key="SESSION", scale="the entire trajectory", dur="tens of minutes",
      test="Watch the whole session. Is it still the same person, and did the system hold up?",
      tech=[
        ("Longitudinal visual consistency",
         "Does rendering quality hold up, or degrade as the session runs on?",
         "CSIM curve · FVD · cumulative jitter"),
        ("Identity drift",
         "Does the avatar slowly turn into a different person?",
         "ArcFace similarity-curve slope · drift-onset time · sustained-drift event rate"),
        ("System reliability",
         "Can the system sustain a full-length interaction?",
         "failure incidents · sustained throughput (real-time factor) · computational cost"),
      ],
      psy=[
        ("Persona consistency",
         "Is the patient still the same person at the end as at the beginning?",
         "case-fact consistency · personality / state distribution fidelity"),
        ("Clinical coherence",
         "Do symptoms, functional impairment and everyday descriptions stay compatible with one another?",
         "symptom–impairment compatibility audit · contradiction rate against the case ground truth"),
        ("State dynamics",
         "Does the emotional and therapeutic state evolve plausibly rather than monotonically?",
         "within-session state change · recovery after emotional activation · trajectory shape (waveform vs monotonic decline)"),
      ]),
]
