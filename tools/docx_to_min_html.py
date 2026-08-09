"""docx_to_min_html.py — 把 .docx 反解成精简 HTML,用于上传 Google Drive 转成原生 Google Doc。

LibreOffice 导出的 HTML 有大量内联样式(435KB),而 Drive 转换只需要语义标签。
这里直接用 python-docx 读结构,只保留 h1/h2/h3、p、表格、超链接、粗体/斜体,
体积约为 LibreOffice 版的 1/10。

用法: python3 tools/docx_to_min_html.py <in.docx> <out.html>
"""
import html
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


def iter_blocks(parent):
    """按文档顺序交替产出 Paragraph 与 Table(python-docx 默认把两者分开)。"""
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, parent)
        elif child.tag == qn('w:tbl'):
            yield Table(child, parent)


def on(el):
    """w:b / w:i 这类开关元素:缺省为开,w:val 为 0/false 时是显式关闭。"""
    if el is None:
        return False
    v = el.get(qn('w:val'))
    return v is None or v not in ('0', 'false', 'off')


def runs_html(par, rels):
    """渲染段落内联内容:粗体/斜体 + 超链接。"""
    out = []
    for child in par._p.iterchildren():
        if child.tag == qn('w:hyperlink'):
            rid = child.get(qn('r:id'))
            url = rels[rid].target_ref if rid in rels else ''
            txt = ''.join(t.text or '' for t in child.iter(qn('w:t')))
            if txt:
                out.append(f'<a href="{html.escape(url, quote=True)}">{html.escape(txt)}</a>')
        elif child.tag == qn('w:r'):
            txt = ''.join(t.text or '' for t in child.iter(qn('w:t')))
            if not txt:
                continue
            txt = html.escape(txt)
            rpr = child.find(qn('w:rPr'))
            if rpr is not None:
                # <w:b/> 开启,但 <w:b w:val="0"/> 是显式关闭 —— 必须看 val,否则整篇会被误标
                if on(rpr.find(qn('w:b'))):
                    txt = f'<strong>{txt}</strong>'
                if on(rpr.find(qn('w:i'))):
                    txt = f'<em>{txt}</em>'
            out.append(txt)
    return ''.join(out)


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    doc = Document(str(src))
    rels = doc.part.rels

    parts = ['<html><head><meta charset="utf-8"></head><body>']
    for blk in iter_blocks(doc):
        if isinstance(blk, Table):
            parts.append('<table border="1">')
            for r in blk.rows:
                parts.append('<tr>')
                for c in r.cells:
                    inner = ' '.join(runs_html(p, rels) for p in c.paragraphs).strip()
                    parts.append(f'<td>{inner}</td>')
                parts.append('</tr>')
            parts.append('</table>')
            continue

        inner = runs_html(blk, rels).strip()
        if not inner:
            continue
        style = (blk.style.name if blk.style else '') or ''
        if style.startswith('Heading') or style == 'Title':
            lvl = 1 if style == 'Title' else min(int(style.split()[-1]) + 1, 6) \
                if style.split()[-1].isdigit() else 2
            parts.append(f'<h{lvl}>{inner}</h{lvl}>')
        else:
            parts.append(f'<p>{inner}</p>')
    parts.append('</body></html>')

    out = '\n'.join(parts)
    dst.write_text(out, encoding='utf-8')
    print(f'{dst}  {len(out)} 字符')


if __name__ == '__main__':
    main()
