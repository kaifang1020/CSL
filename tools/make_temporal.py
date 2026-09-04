# -*- coding: utf-8 -*-
import html, textwrap
from content import TITLE, SUBTITLE, AXES, RULES, LEVELS

W, M, GAP = 1520, 40, 18
AXIS_X = M + 12
CX     = M + 38
CELL_W = (W - CX - M - GAP) // 2
XA, XB = CX, CX + CELL_W + GAP

INK, BODY, MUTED, RULE = "#0F172A", "#475569", "#64748B", "#E2E8F0"
TECH = ("#1D4ED8", "#F4F8FF", "#C7D9FA")
PSY  = ("#B45309", "#FFFAF2", "#F3DCB3")
FS_I, FS_M, LH = 15.5, 12.4, 16.2

esc = lambda s: html.escape(s, quote=False)
def wrap(s, px, fs): return textwrap.wrap(s, max(12, int(px/(fs*0.503)))) or [""]
def item_h(met):     return 21 + LH*len(wrap(met, CELL_W-68, FS_M)) + 14

Y_HEAD, HEAD_H, ROW_HDR = 116, 58, 30
Y0 = Y_HEAD + HEAD_H + 26
geo, y = [], Y0
for L in LEVELS:
    ha = sum(item_h(m) for _,_,m in L["tech"]) + 12
    hb = sum(item_h(m) for _,_,m in L["psy"])  + 12
    geo.append((y, ha, hb)); y += ROW_HDR + max(ha, hb) + 30
Y_END = y - 12

foot = []
for t, b in RULES:
    foot.append((t, wrap(b, W-2*M-40, 12.8)))
FOOT_H = 20 + sum(22 + 17*len(ls) for _, ls in foot)
H = Y_END + 18 + FOOT_H + 14

S=[]; A=S.append
A(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
  'font-family="Inter, -apple-system, Helvetica Neue, Arial, sans-serif">')
A(f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>')
A('<defs><linearGradient id="ax" x1="0" y1="0" x2="0" y2="1">'
  f'<stop offset="0" stop-color="#D7DEE8"/><stop offset="1" stop-color="{INK}"/></linearGradient></defs>')
A(f'<text x="{M}" y="46" font-size="28" font-weight="700" fill="{INK}" letter-spacing="-0.5">{esc(TITLE)}</text>')
for i, ln in enumerate(wrap(SUBTITLE, W-2*M, 14.5)):
    A(f'<text x="{M}" y="{75+i*19}" font-size="14.5" fill="{BODY}">{esc(ln)}</text>')
A(f'<line x1="{M}" y1="94" x2="{W-M}" y2="94" stroke="{RULE}" stroke-width="1.4"/>')

for x, (tag, nm, gl), (acc,bg,bd) in ((XA, AXES[0], TECH), (XB, AXES[1], PSY)):
    A(f'<rect x="{x}" y="{Y_HEAD}" width="{CELL_W}" height="{HEAD_H}" rx="9" fill="{bg}" stroke="{bd}" stroke-width="1.3"/>')
    A(f'<text x="{x+20}" y="{Y_HEAD+25}" font-size="15" font-weight="700" fill="{acc}" letter-spacing="0.7">{tag} &#183; {nm}</text>')
    A(f'<text x="{x+20}" y="{Y_HEAD+45}" font-size="12.8" fill="{BODY}">{esc(gl)}</text>')

A(f'<line x1="{AXIS_X}" y1="{Y0-4}" x2="{AXIS_X}" y2="{Y_END-4}" stroke="url(#ax)" stroke-width="2.4" stroke-linecap="round"/>')
A(f'<path d="M {AXIS_X-5.5} {Y_END-13} L {AXIS_X} {Y_END-1} L {AXIS_X+5.5} {Y_END-13} Z" fill="{INK}"/>')

for (ry, ha, hb), L in zip(geo, LEVELS):
    A(f'<circle cx="{AXIS_X}" cy="{ry+9}" r="6.5" fill="#FFFFFF" stroke="{INK}" stroke-width="2.3"/>')
    A(f'<text x="{CX}" y="{ry+14}" font-size="16" font-weight="700" fill="{INK}" letter-spacing="0.4">{L["k" if "k" in L else "key"]}</text>')
    A(f'<text x="{CX+len(L["key"])*11+16}" y="{ry+14}" font-size="12.6" font-weight="600" fill="{MUTED}">{esc(L["dur"]+"  ·  "+L["scale"])}</text>')
    A(f'<text x="{XB+20}" y="{ry+14}" font-size="12.8" font-style="italic" fill="{MUTED}">{esc(L["test"])}</text>')
    cy0 = ry + ROW_HDR
    for x, items, (acc,bg,bd), ch in ((XA, L["tech"], TECH, ha), (XB, L["psy"], PSY, hb)):
        A(f'<rect x="{x}" y="{cy0}" width="{CELL_W}" height="{ch}" rx="10" fill="{bg}" stroke="{bd}" stroke-width="1.2"/>')
        A(f'<rect x="{x}" y="{cy0}" width="4.5" height="{ch}" rx="2.2" fill="{acc}" opacity="0.6"/>')
        iy = cy0 + 26
        for title, _q, met in items:
            A(f'<circle cx="{x+26}" cy="{iy-5}" r="3.2" fill="{acc}"/>')
            A(f'<text x="{x+38}" y="{iy}" font-size="{FS_I}" font-weight="650" fill="{INK}">{esc(title)}</text>')
            yy = iy + 15
            for ln in wrap(met, CELL_W-68, FS_M):
                A(f'<text x="{x+38}" y="{yy}" font-size="{FS_M}" fill="{BODY}">{esc(ln)}</text>'); yy += LH
            iy = yy + 14

fy = Y_END + 18
A(f'<rect x="{M}" y="{fy}" width="{W-2*M}" height="{FOOT_H}" rx="10" fill="#F8FAFC" stroke="{RULE}" stroke-width="1.3"/>')
ty = fy + 26
for t, lines in foot:
    A(f'<text x="{M+22}" y="{ty}" font-size="13.4" font-weight="700" fill="{INK}">{esc(t)}</text>'); ty += 20
    for ln in lines:
        A(f'<text x="{M+22}" y="{ty}" font-size="12.8" fill="{BODY}">{esc(ln)}</text>'); ty += 17
    ty += 5
A('</svg>')
open("temporal_framework.svg","w").write("\n".join(S)); print("ok", W, H)
