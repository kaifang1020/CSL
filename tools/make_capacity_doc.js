// make_capacity_doc.js — 生成给教授/PI 的英文一页纸(容量规划 + 多模态衔接)。
// 用法: cd ~/Downloads/Avatar/tools && npm install docx (仅首次) && node make_capacity_doc.js
// 输出: ~/Downloads/Avatar/Capacity_and_Multimodal_Integration.docx
//   .docx 拖进 Google Drive → 双击 → 「另存为 Google 文档」，格式(标题层级/表格/项目符号)完整保留。
const d = require("docx");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, LevelFormat,
} = d;
const fs = require("fs");

const W = 9360;                                   // Letter 12240 − 2×1440
const ACC = "1C4E80", INK = "1A1A2E", MUT = "5A6270", HDR = "EAF0F6";
const RED = "B03A2E", AMBER = "B9770E", GREEN = "1E7B4F";

const P = (t, o = {}) => new Paragraph({
  spacing: { after: o.after ?? 120, line: 276 }, alignment: o.align,
  children: [new TextRun({ text: t, bold: o.bold, italics: o.italics,
    color: o.color ?? INK, size: o.size ?? 21, font: "Calibri" })],
});
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 340, after: 140 },
  children: [new TextRun({ text: t, bold: true, size: 28, color: ACC, font: "Calibri" })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 100 },
  children: [new TextRun({ text: t, bold: true, size: 23, color: INK, font: "Calibri" })] });
const BUL = (t) => new Paragraph({ numbering: { reference: "bul", level: 0 }, spacing: { after: 80, line: 276 },
  children: [new TextRun({ text: t, size: 21, color: INK, font: "Calibri" })] });
const GAP = () => new Paragraph({ spacing: { after: 150 }, children: [] });

function T(rows, widths, opts = {}) {
  const cell = (txt, i, isH) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    shading: isH ? { type: ShadingType.CLEAR, fill: HDR, color: "auto" } : undefined,
    margins: { top: 80, bottom: 80, left: 110, right: 110 },
    children: [new Paragraph({ spacing: { after: 0, line: 260 },
      children: [new TextRun({ text: txt, bold: isH, size: opts.size ?? 20,
        color: isH ? INK : MUT, font: "Calibri" })] })],
  });
  return new Table({
    columnWidths: widths, width: { size: W, type: WidthType.DXA },
    borders: {
      top:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"}, bottom:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"},
      left:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"}, right:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"},
      insideHorizontal:{style:BorderStyle.SINGLE,size:2,color:"DDE4EA"}, insideVertical:{style:BorderStyle.SINGLE,size:2,color:"DDE4EA"},
    },
    rows: rows.map((r, ri) => new TableRow({ tableHeader: ri === 0,
      children: r.map((c, ci) => cell(c, ci, ri === 0)) })),
  });
}

const body = [];

// ───────── Title ─────────
body.push(new Paragraph({ spacing: { after: 60 },
  children: [new TextRun({ text: "Digital Patient — Capacity Planning and Multimodal Evaluation Integration",
    bold: true, size: 38, color: INK, font: "Calibri" })] }));
body.push(new Paragraph({ spacing: { after: 40 },
  children: [new TextRun({ text: "Two decisions currently blocked on requirements, and what it would take to connect trainee FIS assessment",
    size: 22, color: MUT, font: "Calibri" })] }));
body.push(new Paragraph({ spacing: { after: 260 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACC } },
  children: [new TextRun({ text: "Kaifang Mao  ·  July 2026", size: 19, color: MUT, font: "Calibri" })] }));

// ───────── Exec summary ─────────
body.push(H1("Executive summary"));
body.push(BUL("Compute cost is not the constraint. At current measured rates one student-session of 15 minutes costs about $0.10 of GPU time — roughly two orders of magnitude below a human standardized patient, and about 14× below a commercial interactive-avatar API."));
body.push(BUL("Concretely: a class of twenty students costs about $4 per session, or roughly $60 across a fifteen-week term — about $3 per student per term."));
body.push(BUL("The dominant cost lever is scheduling policy, not engineering. The same capacity left running continuously, instead of being started for scheduled blocks, would cost around $1,400 per month at 0.6 % utilisation. That 100× difference is decided by policy rather than technology — and it is why the figures above are small."));
body.push(BUL("One requirement could invalidate the whole architecture: whether trainee audio/video may be processed on third-party GPU marketplaces. This is the single question worth answering first."));
body.push(BUL("Connecting the multimodal FIS assessment is instrumentation, not re-architecture. The gaps are logging fields, timestamps, and session recording — no model or pipeline redesign. Incremental running cost is approximately zero (a few dollars per month of storage)."));

// ═════════ PART A ═════════
body.push(H1("Part A — GPU capacity: what we need to confirm"));

body.push(H2("A.1 Measured baseline"));
body.push(T([
  ["Quantity", "Measured value", "Note"],
  ["VRAM per concurrent session", "≈ 15 GB", "One session per 24 GB card today"],
  ["Generation speed", "1.75–3.90× real time", "102–229 ms per 0.4 s of video; 2–4× compute headroom"],
  ["End-to-end response latency", "≈ 2.5 s", "2.3 s reasoning + 0.2 s speech"],
  ["GPU rate (on-demand RTX 4090)", "$0.393 / hour", "= $0.0066 per minute of session"],
  ["Output video", "512 × 512 @ 25 fps", "≈ 1–2 Mbps; relayed by Daily (SFU), not a bottleneck"],
], [3000, 2600, 3760]));
body.push(GAP());
body.push(P("Important observation: each connection currently loads its own copy of the model weights, which is why one session occupies ~15 GB. Most of that is duplicated rather than genuinely per-session. A shared-weights refactor is therefore plausible, but the split between weights and per-session state has not yet been measured, so no capacity figure should be promised until it is.", { italics: true }));

body.push(H2("A.2 Questions that change the architecture (ask these first)"));
body.push(T([
  ["#", "Question", "What the answer changes"],
  ["1", "May trainee audio and video be processed on third-party GPU marketplaces (e.g. Vast.ai)? Are there IRB or institutional restrictions?",
   "Could invalidate the current architecture entirely. If not permitted, we must move to university HPC or a specific cloud region — different cost and different engineering."],
  ["2", "Scheduled lab blocks, or anytime access?",
   "≈ $4 per class (scheduled) versus ≈ $1,400 per month (capacity permanently available). Pure policy, no engineering cost."],
  ["3", "Peak simultaneous users — not total enrolment.",
   "This number is the number of GPUs. 100 students spread across a week may need only 3 GPUs."],
  ["4", "Is NYU HPC available, and can it host a long-running interactive service with public network access?",
   "Even if only offline work (evaluation, batch generation) can run there, it removes a meaningful share of rental cost. Interactive serving is often not permitted on HPC."],
], [500, 3900, 4960]));

body.push(H2("A.3 Questions that determine sizing"));
body.push(T([
  ["#", "Question", "What the answer changes"],
  ["5", "Session length (15 minutes or a full 50-minute hour) and sessions per student per term.",
   "Changes capacity by ~3×. Long sessions also require additional long-run stability validation."],
  ["6", "How many patients in total — all 32 FIS clips?",
   "Each patient needs its own preparation (~30 min). Today one process is bound to one patient; switching requires a restart."],
  ["7", "When does this need to serve real students?",
   "Determines how much engineering (containerisation, multi-session, fast patient switching) is feasible beforehand."],
  ["8", "Budget shape: per-term allocation, or usage-based?",
   "Determines whether we optimise peak capacity or total hours."],
], [500, 3900, 4960]));

body.push(H2("A.4 Questions that affect functionality"));
body.push(T([
  ["#", "Question", "Note"],
  ["9", "\"How many users can one patient support?\" — which meaning?",
   "Two very different things. (a) N students each in a private conversation = N GPUs. (b) N people observing one conversation = 1 GPU — Daily is already an SFU, so broadcast is nearly free. (b) is close to free to add and covers instructor demonstration, whole-class observation and group supervision. Worth confirming whether it is wanted."],
  ["10", "Must sessions be recorded?", "Affects storage, consent workflow — and the multimodal assessment very likely requires it."],
  ["11", "Are 2.5 s response latency and 512×512 resolution acceptable?", "Higher requirements imply more expensive hardware."],
  ["12", "What happens if the service fails mid-class?", "Determines whether standby capacity is needed."],
], [500, 3400, 5460]));

body.push(H2("A.5 Cost illustration \u2014 a class of 20 students, 15 minutes each"));
body.push(T([
  ["Delivery model", "Cost", "Utilisation", "Per student"],
  ["RECOMMENDED \u2014 scheduled 2-hour lab; 5 GPUs started for the block, shut down afterwards",
   "$3.93 per class", "50 %", "$0.20"],
  ["The same, across a 15-week term (one session per week)", "\u2248 $59 per term", "50 %", "\u2248 $3 per term"],
  ["Booking system (GPUs started only for reserved windows)", "Lower still", "Higher", "< $0.20"],
  ["NOT RECOMMENDED \u2014 anytime access, 5 GPUs kept permanently available",
   "\u2248 $1,415 / month", "0.6 %", "\u2014"],
], [4000, 2000, 1600, 1760]));
body.push(GAP());
body.push(P("The headline figure is roughly $60 per term for a class of twenty. The final row is included only as a contrast \u2014 it is what happens if capacity is left running continuously, and its 0.6 % utilisation shows that essentially all of that spend would be idle time. It is not a proposal.", { italics: true }));
body.push(P("Consequence for priorities: scheduling already reduces cost to a few dollars per class, so the multi-session-per-GPU optimisation should not be justified on cost grounds. Its real justification would be GPU scarcity or operational simplicity.", { italics: true }));

// ═════════ PART B ═════════
body.push(H1("Part B — Connecting the multimodal FIS assessment"));

body.push(H2("B.1 How the two evaluations relate"));
body.push(T([
  ["", "What it measures", "Owner"],
  ["Our metrics (identity, lip-sync, drift, realism)", "Whether the digital patient is a faithful stand-in for the real FIS stimulus", "This project"],
  ["FIS assessment", "How competently the trainee responded", "Separate team"],
], [3600, 4200, 1560]));
body.push(GAP());
body.push(P("The link is a validity argument: our fidelity is a precondition for their assessment. If the avatar is not a faithful stimulus, trainee scores obtained against it do not transfer to real patients. This is the cleanest way to describe the interface between the two efforts.", { }));

body.push(H2("B.2 What the system already produces"));
body.push(T([
  ["Artefact", "Contents", "Status"],
  ["sessions/session_*.csv and .jsonl", "Per turn: turn index, time, trainee utterance, patient utterance, and five state variables (guardedness, grief accessibility, alliance, trainee vocal warmth, trainee facial engagement)", "47 sessions already logged"],
  ["state.json", "Live affective state plus per-component latency (STT / LLM / TTS)", "Working"],
  ["ser.py", "Trainee vocal affect (warmth) from microphone", "Built, currently disabled"],
  ["vision.py", "Trainee facial engagement from camera", "Built, currently disabled"],
], [2700, 5100, 1560]));

body.push(H2("B.3 Gaps, remedies and difficulty"));
body.push(T([
  ["Severity", "Gap", "Remedy", "Difficulty"],
  ["Blocking", "No media recording at all — not a single frame or second of audio is retained.", "Enable recording (see B.5 for two options).", "Easy technically; gated on data-location decision"],
  ["Blocking", "Timestamps have one-second resolution and only one per turn. Utterance start and end are not recorded.", "Millisecond timestamps; instrument utterance boundaries in the pipeline.", "Moderate (~2 h)"],
  ["Blocking", "No patient or stimulus identifier. The patient column is hard-coded as \"jordan\" regardless of which patient ran.", "Add patient_id and stimulus_id.", "Trivial (~10 min)"],
  ["Serious", "The patient's opening monologue is explicitly skipped and never logged — yet it is the stimulus the assessment should anchor to.", "Log the opening turn.", "Easy"],
  ["Serious", "Two logged columns are not real data. Trainee vocal warmth and facial engagement come from modules that are currently disabled, so the values are defaults but look like measurements.", "Mark as not-available, and recompute offline from recordings.", "Moderate; must be flagged immediately to prevent misuse"],
  ["Serious", "No stable session, participant or condition identifier — sessions are named only by start time.", "Add a session UUID plus participant and condition fields.", "Trivial"],
  ["Serious", "Turn-taking events (interruptions, overlaps, silences) are not logged, although interruptions are already detected.", "Emit these as events.", "Easy (~1 h)"],
  ["Useful", "Per-turn latency is only in the live state file, which is overwritten.", "Persist per turn.", "Trivial"],
  ["Useful", "No provenance: reference frame, voice, regularisation strength and model version are not recorded.", "Write a session header.", "Trivial, but important — if avatar quality differs between cohorts, trainee scores are not comparable"],
], [1100, 3300, 2500, 2460], { size: 19 }));

body.push(H2("B.4 Proposed interface"));
body.push(P("Rather than extending the current one-row-per-turn CSV, emit a per-session JSONL event stream as the alignment spine: a session header (session identifier, patient and stimulus identifiers, full configuration) followed by timestamped events — trainee speech start and end, patient speech start and end, interruptions, and state snapshots. Raw audio/video is stored under the same session identifier together with a clock offset."));
body.push(P("Three principles:", { bold: true }));
body.push(BUL("We deliver aligned, labelled data; the assessment team owns all scoring logic."));
body.push(BUL("Every artefact is joinable through a single session identifier."));
body.push(BUL("Trainee multimodal analysis runs offline on recordings, not inside the live pipeline — it does not compete with the avatar for GPU, and offline processing can use heavier, more accurate models."));

body.push(H2("B.5 Cost impact of the integration"));
body.push(T([
  ["Item", "Incremental cost"],
  ["Logging fields, timestamps, turn-taking events, provenance", "Zero — a session log is tens of kilobytes"],
  ["Recording, option A: Daily cloud recording", "Daily's recording fee (current rate to be confirmed) plus storage"],
  ["Recording, option B: server-side capture", "Zero third-party cost — the pipeline already holds both parties' audio and video. Requires care so that encoding does not compete with generation"],
  ["Storage", "≈ 0.5 GB per 15-minute session; ≈ 200 GB per term ≈ $4 / month"],
  ["Offline trainee multimodal analysis", "≈ $0.03 per session on interruptible GPUs; free if HPC is available"],
  ["Additional cost on the live path", "Zero, provided the analysis runs offline"],
], [4600, 4760]));
body.push(GAP());
body.push(P("Running the trainee analysis offline is not merely cost-neutral — it is cheaper than the alternative. Those modules are disabled today precisely because they compete with the avatar for GPU; moving them offline restores the capability on cheaper hardware.", { italics: true }));
body.push(P("Two non-monetary costs:", { bold: true }));
body.push(BUL("Consent and IRB process for recording trainees. This is the same question as A.2 #1, and it determines where recordings may live, for how long, and who may access them."));
body.push(BUL("A performance risk if we record server-side: encoding while generating could reduce the real-time factor. This needs one short measurement before adoption."));

body.push(H2("B.6 Effort estimate"));
body.push(T([
  ["Batch", "Contents", "Effort"],
  ["First", "Patient and stimulus identifiers, opening turn, session identifier, provenance header, per-turn latency", "≈ 1 hour"],
  ["Second", "Millisecond timestamps, utterance boundaries, turn-taking events", "≈ 3 hours"],
  ["Third", "Recording (gated on the data-location decision) and offline trainee analysis", "Half a day to one day"],
], [1300, 6100, 1960]));
body.push(GAP());
body.push(P("The first batch is the urgent one. Without a patient identifier and a session identifier, sessions recorded today cannot afterwards be attributed to a patient or a participant — the data is effectively unusable.", { bold: true }));

// ═════════ Next steps ═════════
body.push(H1("Recommended next steps"));
body.push(BUL("Confirm the data-location question (A.2 #1) before any further infrastructure work — it can invalidate the rest."));
body.push(BUL("Establish the usage model: scheduled blocks or anytime access, and peak simultaneous users. Describing the intended teaching format is sufficient; the numbers can be derived from it."));
body.push(BUL("Implement the first logging batch (about one hour) so that sessions recorded from now on are attributable and usable for assessment."));
body.push(BUL("Defer the multi-session-per-GPU optimisation. Scheduling already reduces cost to a few dollars per class."));

body.push(new Paragraph({ spacing: { before: 300 }, border: { top: { style: BorderStyle.SINGLE, size: 4, color: "C9D3DD" } },
  children: [new TextRun({ text: "Measured figures in this document come from this project's own benchmarks and evaluation runs; commercial API rates were taken from vendor pricing pages in July 2026 and should be re-checked before being quoted.",
    size: 19, italics: true, color: MUT, font: "Calibri" })] }));

const doc = new Document({
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 220 } } } }] }] },
  styles: { default: { document: { run: { font: "Calibri", size: 21, color: INK } } } },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 },
    margin: { top: 1300, right: 1440, bottom: 1300, left: 1440 } } }, children: body }],
});

Packer.toBuffer(doc).then(b => {
  const out = "/Users/maokaifang/Downloads/Avatar/Capacity_and_Multimodal_Integration.docx";
  fs.writeFileSync(out, b);
  console.log("saved " + out);
});
