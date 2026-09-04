# -*- coding: utf-8 -*-
"""Temporal Hierarchical Framework —— 3(时间粒度) x 2(technical/psychological)"""
import html, textwrap

W, M, GAP = 1500, 40, 18
AXIS_X    = M + 12
CX        = M + 38                       # 内容左边界
CELL_W    = (W - CX - M - GAP) // 2
XA, XB    = CX, CX + CELL_W + GAP

INK, BODY, MUTED, RULE = "#0F172A", "#475569", "#64748B", "#E2E8F0"
TECH = ("#1D4ED8", "#F4F8FF", "#C7D9FA")
PSY  = ("#B45309", "#FFFAF2", "#F3DCB3")
FS_I, FS_M, LH = 15.5, 12.4, 16.2

esc = lambda s: html.escape(s, quote=False)
def wrap(s, px, fs):
    return textwrap.wrap(s, max(12, int(px / (fs * 0.503)))) or [""]
def item_h(met):
    return 21 + LH * len(wrap(met, CELL_W - 68, FS_M)) + 14

ROWS = [
 dict(k="FRAME", sc="≈ 40 ms  ·  one rendered unit",
      q="Is each individual visual / audio unit generated correctly?",
      tech=[("Identity consistency", "CSIM · ArcFace similarity"),
            ("Visual rendering quality", "FID · sharpness · LPIPS · LSE-D / LSE-C · lip-landmark error"),
            ("Temporal coherence", "landmark displacement · jitter rate · flicker rate · freeze rate"),
            ("Multimodal affect congruence", "consistency of emotional state across modalities")],
      psy=[("Facial-state congruence", "expression matches the intended patient state — sadness must not render as happiness; restricted affect must not become exaggerated"),
           ("Cross-modal state congruence", "blinded 1–5 compatibility rating across text / voice / face / gesture · unsupported contradiction rate")]),
 dict(k="TURN", sc="seconds  ·  one patient–therapist exchange",
      q="Does the patient respond naturally to the therapist?",
      tech=[("Responsiveness", "time-to-first-response · end-to-end latency · interruption recovery"),
            ("Listening behaviour", "natural resting face · mouth closure · idle-state animation")],
      psy=[("Response appropriateness", "is the answer reasonable given the therapist's prompt?"),
           ("Conditional behavioural response", "does the patient react differently to empathy, pressure, judgment, support?  ← the internal model"),
           ("Interactional style", "response length · elaboration · hesitation · conversational patterns consistent with the persona")]),
 dict(k="SESSION", sc="tens of minutes  ·  the entire trajectory",
      q="Does the system maintain a coherent patient throughout?",
      tech=[("Longitudinal visual consistency", "CSIM curve · FVD · cumulative jitter · drift onset"),
            ("Identity drift", "ArcFace similarity-curve slope · drift-onset time · sustained-drift event rate"),
            ("System reliability", "freezing rate · failure incidents · computational cost")],
      psy=[("Persona consistency", "case-fact consistency · personality / state distribution fidelity"),
           ("Clinical coherence", "symptoms, impairment and functional descriptions remain compatible"),
           ("State dynamics", "within-session state change · recovery after emotional activation")]),
]

Y_HEAD, HEAD_H = 116, 58
Y0 = Y_HEAD + HEAD_H + 26
ROW_HDR = 30                                  # 行标题带高度

geo, y = [], Y0
for r in ROWS:
    ha = sum(item_h(m) for _, m in r["tech"]) + 12
    hb = sum(item_h(m) for _, m in r["psy"])  + 12
    geo.append((y, ha, hb))
    y += ROW_HDR + max(ha, hb) + 30
Y_END = y - 12
H = Y_END + 128

S = []; A = S.append
A(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
  'font-family="Inter, -apple-system, Helvetica Neue, Arial, sans-serif">')
A(f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>')
A('<defs><linearGradient id="ax" x1="0" y1="0" x2="0" y2="1">'
  f'<stop offset="0" stop-color="#D7DEE8"/><stop offset="1" stop-color="{INK}"/></linearGradient></defs>')

A(f'<text x="{M}" y="46" font-size="28" font-weight="700" fill="{INK}" letter-spacing="-0.5">'
  'Avatar Evaluation — Temporal Hierarchical Framework</text>')
A(f'<text x="{M}" y="75" font-size="14.5" fill="{BODY}">'
  'Evaluation follows the lifecycle of an interaction. Each timescale is assessed on two independent axes.</text>')
A(f'<line x1="{M}" y1="94" x2="{W-M}" y2="94" stroke="{RULE}" stroke-width="1.4"/>')

for x, tag, nm, gl, (acc, bg, bd) in ((XA, "A", "TECHNICAL FIDELITY", "Does the system render the interaction correctly?", TECH),
                                      (XB, "B", "PSYCHOLOGICAL FIDELITY", "Does the simulated patient behave plausibly?", PSY)):
    A(f'<rect x="{x}" y="{Y_HEAD}" width="{CELL_W}" height="{HEAD_H}" rx="9" fill="{bg}" stroke="{bd}" stroke-width="1.3"/>')
    A(f'<text x="{x+20}" y="{Y_HEAD+25}" font-size="15" font-weight="700" fill="{acc}" letter-spacing="0.7">{tag} &#183; {nm}</text>')
    A(f'<text x="{x+20}" y="{Y_HEAD+45}" font-size="12.8" fill="{BODY}">{esc(gl)}</text>')

A(f'<line x1="{AXIS_X}" y1="{Y0-4}" x2="{AXIS_X}" y2="{Y_END-4}" stroke="url(#ax)" stroke-width="2.4" stroke-linecap="round"/>')
A(f'<path d="M {AXIS_X-5.5} {Y_END-13} L {AXIS_X} {Y_END-1} L {AXIS_X+5.5} {Y_END-13} Z" fill="{INK}"/>')

for (ry, ha, hb), r in zip(geo, ROWS):
    A(f'<circle cx="{AXIS_X}" cy="{ry+9}" r="6.5" fill="#FFFFFF" stroke="{INK}" stroke-width="2.3"/>')
    A(f'<text x="{CX}" y="{ry+14}" font-size="16" font-weight="700" fill="{INK}" letter-spacing="0.4">{r["k"]}</text>')
    A(f'<text x="{CX+len(r["k"])*11+16}" y="{ry+14}" font-size="12.6" font-weight="600" fill="{MUTED}">{esc(r["sc"])}</text>')
    A(f'<text x="{XB+20}" y="{ry+14}" font-size="12.8" font-style="italic" fill="{MUTED}">{esc(r["q"])}</text>')

    cy0 = ry + ROW_HDR
    for x, items, (acc, bg, bd), ch in ((XA, r["tech"], TECH, ha), (XB, r["psy"], PSY, hb)):
        A(f'<rect x="{x}" y="{cy0}" width="{CELL_W}" height="{ch}" rx="10" fill="{bg}" stroke="{bd}" stroke-width="1.2"/>')
        A(f'<rect x="{x}" y="{cy0}" width="4.5" height="{ch}" rx="2.2" fill="{acc}" opacity="0.6"/>')
        iy = cy0 + 26
        for title, met in items:
            A(f'<circle cx="{x+26}" cy="{iy-5}" r="3.2" fill="{acc}"/>')
            A(f'<text x="{x+38}" y="{iy}" font-size="{FS_I}" font-weight="650" fill="{INK}">{esc(title)}</text>')
            yy = iy + 15
            for ln in wrap(met, CELL_W-68, FS_M):
                A(f'<text x="{x+38}" y="{yy}" font-size="{FS_M}" fill="{BODY}">{esc(ln)}</text>'); yy += LH
            iy = yy + 14

fy = Y_END + 16
A(f'<rect x="{M}" y="{fy}" width="{W-2*M}" height="96" rx="10" fill="#F8FAFC" stroke="{RULE}" stroke-width="1.3"/>')
A(f'<text x="{M+22}" y="{fy+27}" font-size="13.6" font-weight="700" fill="{INK}">Reporting principle</text>')
A(f'<text x="{M+22}" y="{fy+51}" font-size="13" fill="{BODY}">Do <tspan font-weight="700">not</tspan> average the metrics into one score. '
  'Report a <tspan font-weight="700">temporal profile</tspan> — frame &#8594; perceptual realism · turn &#8594; interaction quality · session &#8594; identity and trajectory.</text>')
A(f'<text x="{M+22}" y="{fy+75}" font-size="13" fill="{BODY}">Separating the two axes keeps a <tspan font-weight="700">technical artifact</tspan> '
  '(e.g. lip-sync failure) from being misread as a <tspan font-weight="700">psychological failure</tspan> (e.g. an implausible emotional reaction).</text>')
A('</svg>')
open("temporal_framework.svg","w").write("\n".join(S)); print("ok", W, H)
