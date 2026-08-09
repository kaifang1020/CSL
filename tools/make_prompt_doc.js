// make_prompt_doc.js — 生成 persona prompt v1 vs v2 对比文档(英文,给教授/合作者)。
// 用法: cd ~/Downloads/Avatar/tools && node make_prompt_doc.js
// 输出: ~/Downloads/Avatar/Patient_Prompt_Redesign.docx
//   .docx 拖进 Google Drive(登录你想用的账号,如 km6704@nyu.edu)→ 双击 →「另存为 Google 文档」
const d = require("docx");
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
        Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, LevelFormat } = d;
const fs = require("fs"), path = require("path");

const W = 9360;
const ACC = "1C4E80", INK = "1A1A2E", MUT = "5A6270", HDR = "EAF0F6";
const OLDBG = "FDF1F0", NEWBG = "EFF7F1";

const P = (t, o = {}) => new Paragraph({
  spacing: { after: o.after ?? 120, line: 276 }, alignment: o.align,
  children: [new TextRun({ text: t, bold: o.bold, italics: o.italics,
    color: o.color ?? INK, size: o.size ?? 21, font: "Calibri" })] });
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
      children: [new TextRun({ text: txt, bold: isH, size: opts.size ?? 19,
        color: isH ? INK : MUT, font: "Calibri" })] })] });
  return new Table({ columnWidths: widths, width: { size: W, type: WidthType.DXA },
    borders: { top:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"}, bottom:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"},
      left:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"}, right:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"},
      insideHorizontal:{style:BorderStyle.SINGLE,size:2,color:"DDE4EA"}, insideVertical:{style:BorderStyle.SINGLE,size:2,color:"DDE4EA"} },
    rows: rows.map((r, ri) => new TableRow({ tableHeader: ri === 0,
      children: r.map((c, ci) => cell(c, ci, ri === 0)) })) });
}

// 整段 prompt 原文:等宽、带底色框
function promptBlock(text, isNew) {
  return new Table({ columnWidths: [W], width: { size: W, type: WidthType.DXA },
    borders: { top:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"}, bottom:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"},
      left:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"}, right:{style:BorderStyle.SINGLE,size:2,color:"C9D3DD"},
      insideHorizontal:{style:BorderStyle.NONE}, insideVertical:{style:BorderStyle.NONE} },
    rows: [new TableRow({ children: [new TableCell({
      width: { size: W, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: isNew ? NEWBG : OLDBG, color: "auto" },
      margins: { top: 140, bottom: 140, left: 160, right: 160 },
      children: text.split("\n").map(line => new Paragraph({
        spacing: { after: line.trim() === "" ? 60 : 20, line: 250 },
        children: [new TextRun({ text: line || " ", size: 17, font: "Consolas",
          color: INK })] })) })] })] });
}

// 读 v2 文本
const v2src = fs.readFileSync(path.join(__dirname, "prompts_v2.py"), "utf8");
const grab = (name) => v2src.match(new RegExp(name + ' = """([\\s\\S]*?)"""'))[1].trim();
const CANDICE_V2 = grab("CANDICE_V2"), SAVANNAH_V2 = grab("SAVANNAH_V2");

// 读 v1 文本(从 patient_jordan.py)
const pj = fs.readFileSync(path.join(__dirname, "..", "patient_jordan.py"), "utf8");
const grabPJ = (name) => pj.match(new RegExp(name + ' = """([\\s\\S]*?)"""'))[1].trim();
const CANDICE_V1 = grabPJ("CANDICE_PROMPT"), SAVANNAH_V1 = grabPJ("SAVANNAH_PROMPT");

const body = [];

body.push(new Paragraph({ spacing: { after: 60 }, children: [new TextRun({
  text: "Simulated Patient — Persona Prompt Redesign", bold: true, size: 38, color: INK, font: "Calibri" })] }));
body.push(new Paragraph({ spacing: { after: 40 }, children: [new TextRun({
  text: "Current prompts, proposed revisions, and the clinical literature each change is grounded in",
  size: 22, color: MUT, font: "Calibri" })] }));
body.push(new Paragraph({ spacing: { after: 260 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACC } },
  children: [new TextRun({ text: "Kaifang Mao  ·  July 2026", size: 19, color: MUT, font: "Calibri" })] }));

// ───── Why ─────
body.push(H1("Why revise the prompts"));
body.push(P("The simulated patient's dialogue is produced by a single static system prompt plus GPT-4o-mini and the growing conversation history. For the two patients drawn from the FIS stimulus clips — Candice and Savannah — there is no state model, no memory, and no mechanism by which anything the trainee does changes the patient's internal condition. Everything the patient does therefore has to be carried by the prompt."));
body.push(P("Two problems follow. First, a prompt can only express constant rules (“always do X, never do Y”), whereas clinical realism largely consists of when to do X rather than Y. Second, the base model is trained to be helpful, agreeable, and accommodating, and that prior leaks through: in real session logs the patient says things like “take your time”, “I totally understand”, “that sounds like solid advice”, and “thanks for that” — it behaves like a therapist rather than a patient, and it accepts every suggestion gratefully."));
body.push(P("The revisions below do not fix the missing state model. They do two achievable things: remove instructions that actively push the patient away from clinical realism, and install the behaviours the literature identifies as characteristic of patients in this condition.", { bold: true }));

// ───── Sources ─────
body.push(H1("Clinical sources"));
body.push(T([
  ["Source", "What it contributes"],
  ["Bryan (2007), the case of “John” — Pragmatic Case Studies in Psychotherapy",
   "Fluid vulnerability theory: chronic suicidality means a higher baseline and a lower threshold for activation, not permanent maximal activation. The Suicide Status Form's six constructs (psychological pain, stress, agitation, hopelessness, self-hate, overall risk), each with a precise definition, and each patient having a characteristic dominant profile rather than all constructs maximal. Ambivalence rated as two independent axes: desire to live and desire to die held simultaneously. Above all, a recorded exchange in which the patient denies suicidal thinking twice and discloses only after the clinician surfaces and addresses the consequence he fears."],
  ["Henriques (2023), the case of “Maggie” — Pragmatic Case Studies in Psychotherapy",
   "The triple-negative neurotic loop: the pathology lies not in the primary feeling but in the maladaptive secondary reaction to it — avoidance, blame, or rigid control. Shame-based depression, in which an inner critical voice responds to the patient's own distress, and — critically — the louder that voice becomes, the more the patient shuts down. A patient who had been talked off a bridge the previous night opens the session by saying she is “fine” and standing up to leave."],
  ["Cox et al. (2021), Suicide and Life-Threatening Behavior, 269 online crisis chats",
   "Helping behaviours are functional and ordinal: the later functions can only be served once the earlier ones have been. Sessions that resolved and sessions that did not began identically; they diverged because in the unresolved sessions the counsellor moved to problem-solving before distress had come down and a relationship had formed. When the relationship is weak, clients become resistant to directive or prescriptive moves."],
], [2500, 6860]));

// ───── Change table ─────
body.push(H1("What changes, and why"));
body.push(T([
  ["#", "Current prompt", "Revision", "Grounds"],
  ["1", "“Portray yourself in a LOUD, DRAMATIC, over-the-top way”; “you pour everything out at once” (Candice)",
   "Disclosure is gated by a specific feared consequence. The patient reveals quieter, more private material only once she believes that fear has been addressed.",
   "John denies suicidal thinking twice and discloses only after his fear of hospitalisation and career damage is addressed; Maggie tells no one for three years. Non-disclosure is a theme throughout both treatments, not a single event."],
  ["2", "No instruction about how to respond differently to empathy versus advice.",
   "Explicit contingent rules: accurate reflection produces softening and one plain disclosure; advice or a technique offered before the patient feels understood produces escalation (Candice) or dismissal and sharpness (Savannah).",
   "Cox: premature problem-solving is what distinguished unresolved from resolved sessions; weak relationships produce resistance to directive moves. This is the single most important addition."],
  ["3", "“Do NOT be calm, brief, or composed”; “every single reply is venting, pleading, catastrophizing, or demanding help — nothing else”",
   "Brevity, flatness, “I don't know”, and half-finished answers are explicitly permitted and described as often more realistic than a speech.",
   "Real transcripts range from “I guess” delivered in a neutral tone to sobbing to a calm, almost triumphant disclosure. The original instruction forbids exactly the range the transcripts show."],
  ["4", "“You catastrophize” — encourages global statements.",
   "Concreteness is required: name the actual bills, the car, the specific day, the call not returned; never global summaries such as “everything is terrible.”",
   "John writes about ACLS training and not being “on top of my game”; Maggie about a chemistry final. Real distress is expressed through mundane particulars."],
  ["5", "Nothing about the patient's relationship to her own feelings.",
   "A secondary-reaction layer: shame about needing so much (Candice), contempt for her own neediness (Savannah), self-blame that then makes the distress worse.",
   "Henriques' neurotic loop — the pathology is the secondary reaction. John: “I feel guilty about thinking this.” Maggie apologises to her mother for sneaking out while disclosing her own rape."],
  ["6", "Distress is expressed by saying more.",
   "The relationship is loosened, and shutting down is made available as a response to intense distress.",
   "Henriques: as the inner critical voice grew louder, Maggie shut down further. The current model has the direction reversed."],
  ["7", "Anti-role-flip clause forbids comforting, advising, and reassuring in general terms.",
   "The same clause plus an explicit list of banned phrases (“take your time”, “I understand”, “I'm here for you”, “thanks for that”, “that's good advice”), a prohibition on thanking the trainee or agreeing that a suggestion is helpful, and a prohibition on patiently reconstructing unclear speech.",
   "Observed in our own session logs: the patient produced all of these, and reconstructed the trainee's meaning more than eight times in a single session. General prohibitions did not suppress the model's assistant prior; specific ones have a better chance."],
  ["8", "The patient is equally distressed in every turn.",
   "The patient's state is stated to move during the session, in both directions.",
   "John improved, then deteriorated sharply at session eight, then improved again. Maggie recovered, relapsed with nightmares, recovered. Fluid vulnerability theory treats acute episodes as inherently time-limited."],
  ["9", "Suicidality presented as a single intensity.",
   "Wanting to die and wanting to be rescued are both true at once, and the patient does not resolve the contradiction.",
   "The Suicide Status Form rates desire for life and desire for death as independent axes. John reported low desire for death together with very high desire to live."],
], [400, 2500, 3200, 3260], { size: 18 }));
body.push(GAP());
body.push(P("Note on Savannah: the current Savannah prompt already contains an informal version of change 2 (“being handed solutions repeats the exact role you are trapped in, and it makes you more frustrated, not less”), written from the clinical case description before this literature was reviewed. The revision makes the rule explicit and adds the feared consequence, the secondary reaction, and the permitted register range.", { italics: true }));

// ───── Candice ─────
body.push(H1("Candice — current prompt"));
body.push(promptBlock(CANDICE_V1, false));
body.push(H1("Candice — proposed revision"));
body.push(promptBlock(CANDICE_V2, true));

// ───── Savannah ─────
body.push(H1("Savannah — current prompt"));
body.push(promptBlock(SAVANNAH_V1, false));
body.push(H1("Savannah — proposed revision"));
body.push(promptBlock(SAVANNAH_V2, true));

// ───── Limits ─────
body.push(H1("What this does not fix"));
body.push(BUL("There is still no state. The patient has no representation of distress or alliance that persists and evolves; the contingent rules in the revision are applied, or not, at the discretion of GPT-4o-mini on each turn."));
body.push(BUL("The distinction between reflection and advice — the mechanism Cox identifies as decisive — is left to the model's own judgement rather than being classified explicitly. A classifier over the trainee's turn, using the Helping Skills System categories, would make it reliable."));
body.push(BUL("Nothing accumulates. What the patient has already disclosed, and whether the feared consequence has in fact been addressed, is inferred from the transcript rather than tracked."));
body.push(BUL("The model remains GPT-4o-mini, which is a small model doing sustained character work."));
body.push(GAP());
body.push(P("These are prompt-level changes: worth making because they are cheap and because several current instructions point away from realism, but the ceiling is set by the absence of a state model.", { bold: true }));

// ───── Evaluation ─────
body.push(H1("How to tell whether the revision helped"));
body.push(P("The revision should be evaluated rather than assumed, and four measures can be computed automatically from session transcripts alone. All four correspond to defects observed in our own logs, and none requires ground-truth data:"));
body.push(BUL("Caretaking-language rate — the proportion of patient turns containing therapist-role phrases. Should fall toward zero."));
body.push(BUL("Agreement rate — the proportion of turns in which the patient accepts the trainee's framing or suggestion. Currently close to universal."));
body.push(BUL("Distress-verbosity correlation — the correlation between rated distress and utterance length. Should not be strongly positive."));
body.push(BUL("Deflection rate — the proportion of turns in which the patient minimises, deflects, or declines to answer. Currently close to zero; in real transcripts it is substantial."));
body.push(GAP());
body.push(P("A prerequisite: session logs do not currently record which patient was used, and no Candice or Savannah conversations have been retained. A baseline must be captured before the change, or the comparison cannot be made.", { bold: true }));
body.push(P("The same transcripts also allow a stronger comparison. The three papers contain verbatim patient speech, and the FIS stimulus clips can be transcribed; computing these measures on real patient language as well as on the simulated patient gives a “percentage of human” benchmark, in the same form as the benchmark already used for the avatar's face."));

const doc = new Document({
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 220 } } } }] }] },
  styles: { default: { document: { run: { font: "Calibri", size: 21, color: INK } } } },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 },
    margin: { top: 1300, right: 1440, bottom: 1300, left: 1440 } } }, children: body }] });

Packer.toBuffer(doc).then(b => {
  const out = "/Users/maokaifang/Downloads/Avatar/Patient_Prompt_Redesign.docx";
  fs.writeFileSync(out, b);
  console.log("saved " + out);
});
