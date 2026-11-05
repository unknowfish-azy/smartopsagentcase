# -*- coding: utf-8 -*-
"""
Markdown -> Word(.docx) 生成器（手写 OOXML，无需 python-docx）

排版规格（按需求）：
- A4 页面；上下页边距 2.5cm（左右同为 2.5cm，保证打印不出界）
- 正文行距 1.5 倍；段落之间空一行（段后 12pt）
- 正文中文字体 宋体 12pt（小四），标题 黑体，等宽代码 Consolas
- 清理：零宽字符 / 控制字符 / 多余空行 / 水印与乱码残留
- 保留原文内容，仅做格式转换
"""
import re, os, zipfile
from xml.sax.saxutils import escape

BASE = r"D:\SmartOpsAgent\docs\competition"
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

# ---------------- 文本清洗 ----------------
BAD_CHARS = ["​", "﻿", "‌", "‍", "⁠", " ", "⁠"]


def clean(t: str) -> str:
    for c in BAD_CHARS:
        t = t.replace(c, "" if c != " " else " ")
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t)   # 控制字符
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = t.strip().lstrip("　 ").rstrip("　 ")
    return t


def esc(t: str) -> str:
    return escape(t, {'"': "&quot;"})


# ---------------- Markdown 解析 ----------------
def parse(md: str):
    lines = md.replace("\r\n", "\n").split("\n")
    blocks, i, n = [], 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):                                    # 代码块
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            blocks.append(("code", "\n".join(buf)))
            continue
        if s.startswith("|") and s.count("|") >= 2:                # 表格
            block = []
            while i < n and lines[i].strip().startswith("|"):
                block.append(lines[i].strip()); i += 1
            if len(block) >= 2 and re.match(r"^\|?[\s:|-]+\|?$", block[1]) and "-" in block[1]:
                head = [c.strip() for c in block[0].strip("|").split("|")]
                rows = [[c.strip() for c in r.strip("|").split("|")] for r in block[2:]]
                blocks.append(("table", head, rows))
            else:
                blocks.append(("p", " ".join(block)))
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)                      # 标题
        if m:
            blocks.append(("h", len(m.group(1)), clean(m.group(2)))); i += 1; continue
        if re.match(r"^---+$", s):                                 # 分隔线
            blocks.append(("hr",)); i += 1; continue
        if s.startswith(">"):                                      # 引用
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip()); i += 1
            blocks.append(("quote", clean(" ".join(buf))))
            continue
        if re.match(r"^[-*]\s+\[[\sx]?\]\s+", s):                  # 复选框
            items = []
            while i < n and re.match(r"^[-*]\s+\[[\sx]?\]\s+", lines[i].strip()):
                items.append(clean(re.sub(r"^[-*]\s+\[[\sx]?\]\s+", "", lines[i].strip()))); i += 1
            blocks.append(("check", items)); continue
        if re.match(r"^[-*]\s+", s):                               # 无序
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(clean(re.sub(r"^[-*]\s+", "", lines[i].strip()))); i += 1
            blocks.append(("ul", items)); continue
        if re.match(r"^\d+\.\s+", s):                              # 有序
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(clean(re.sub(r"^\d+\.\s+", "", lines[i].strip()))); i += 1
            blocks.append(("ol", items)); continue
        buf = []                                                   # 段落
        while i < n:
            t = lines[i].strip()
            if (not t or t.startswith("#") or t.startswith("```") or t.startswith("|")
                    or t.startswith(">") or re.match(r"^[-*]\s+", t)
                    or re.match(r"^\d+\.\s+", t) or re.match(r"^---+$", t)):
                break
            buf.append(t); i += 1
        blocks.append(("p", clean("".join(buf))))
    return blocks


# ---------------- OOXML 零件 ----------------
def run(text, rpr="", preserve=True):
    if text == "":
        return ""
    sp = ' xml:space="preserve"' if preserve else ""
    return f'<w:r>{f"<w:rPr>{rpr}</w:rPr>" if rpr else ""}<w:t{sp}>{esc(text)}</w:t></w:r>'


def runs_inline(text, base_rpr=""):
    """处理 **加粗** 与 `代码`"""
    out = ""
    for tk in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
        if not tk:
            continue
        if tk.startswith("**") and tk.endswith("**"):
            out += run(tk[2:-2], base_rpr + "<w:b/>")
        elif tk.startswith("`") and tk.endswith("`"):
            out += run(tk[1:-1], base_rpr + '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:eastAsia="Consolas"/><w:color w:val="A31515"/><w:sz w:val="20"/>')
        else:
            out += run(tk, base_rpr)
    return out


def para(text, style="Normal", extra_ppr="", base_rpr=""):
    return (f'<w:p><w:pPr><w:pStyle w:val="{style}"/>{extra_ppr}</w:pPr>'
            f'{runs_inline(text, base_rpr)}</w:p>')


IND_LIST = '<w:ind w:left="420" w:hanging="260"/>'
IND_QUOTE = '<w:ind w:left="360" w:right="200"/>'


def block_to_xml(b):
    k = b[0]
    if k == "h":
        lvl = min(b[1], 4)
        return para(b[2], f"Heading{lvl}")
    if k == "p":
        return para(b[1])
    if k == "quote":
        return para(b[1], "Quote")
    if k == "ul":
        return "".join(para("• " + it, "ListParagraph", IND_LIST) for it in b[1])
    if k == "ol":
        return "".join(para(f"{i}. {it}", "ListParagraph", IND_LIST) for i, it in enumerate(b[1], 1))
    if k == "check":
        return "".join(para("☐ " + it, "ListParagraph", IND_LIST) for it in b[1])
    if k == "hr":
        return ('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" '
                'w:color="BFBFBF"/></w:pBdr></w:pPr></w:p>')
    if k == "code":
        out = ""
        for ln in b[1].split("\n"):
            ln = ln.rstrip()
            out += (f'<w:p><w:pPr><w:pStyle w:val="Code"/></w:pPr>'
                    f'{run(ln, "", preserve=True)}</w:p>')
        return out
    if k == "table":
        head, rows = b[1], b[2]
        ncol = len(head)

        def vw(t):  # 视觉宽度：中日韩按 2 计
            return sum(2 if ord(c) > 0x2E80 else 1 for c in re.sub(r"[*`]", "", t))
        weights = [max([vw(head[c])] + [vw(r[c]) if c < len(r) else 1 for r in rows]) for c in range(ncol)]
        total = 9072  # A4(11906) - 左右边距(2×1417)
        s = sum(weights) or 1
        widths = [max(int(total * w / s), 600) for w in weights]
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
        borders = ("<w:tblBorders>"
                   + "".join(f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>'
                             for e in ("top", "left", "bottom", "right", "insideH", "insideV"))
                   + "</w:tblBorders>")

        def cell(text, w, header=False):
            shd = '<w:shd w:val="clear" w:color="auto" w:fill="D9E2F3"/>' if header else ""
            rpr = '<w:sz w:val="21"/>'
            body = runs_inline(text, rpr + ("<w:b/>" if header else ""))
            return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shd}'
                    '<w:vAlign w:val="center"/></w:tcPr>'
                    f'<w:p><w:pPr><w:spacing w:line="240" w:lineRule="auto" w:after="0" w:before="0"/></w:pPr>'
                    f'{body}</w:p></w:tc>')

        htr = ('<w:tr><w:trPr><w:tblHeader/></w:trPr>'
               + "".join(cell(h, widths[i], True) for i, h in enumerate(head)) + '</w:tr>')
        btrs = "".join(
            '<w:tr>' + "".join(cell(r[c] if c < len(r) else "", widths[c]) for c in range(ncol)) + '</w:tr>'
            for r in rows)
        return (f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="5000" w:type="pct"/>'
                f'{borders}<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
                f'<w:bottom w:w="60" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tblCellMar>'
                f'</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{htr}{btrs}</w:tbl>'
                + para(""))  # 表后空行
    return ""


# ---------------- 样式表 ----------------
def styles_xml():
    h = ""
    for i, (sz, color) in enumerate([(36, "1F3864"), (30, "1F3864"), (26, "2E5496"), (24, "2E5496")], start=1):
        h += (f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/>'
              f'<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/>'
              f'<w:spacing w:before="240" w:after="120" w:line="360" w:lineRule="auto"/>'
              f'<w:outlineLvl w:val="{i-1}"/></w:pPr>'
              f'<w:rPr><w:rFonts w:ascii="黑体" w:hAnsi="黑体" w:eastAsia="黑体"/>'
              f'<w:b/><w:color w:val="{color}"/><w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr></w:style>')
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W}>
<w:docDefaults>
  <w:rPrDefault><w:rPr>
    <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体" w:cs="Times New Roman"/>
    <w:sz w:val="24"/><w:szCs w:val="24"/>
  </w:rPr></w:rPrDefault>
  <w:pPrDefault><w:pPr>
    <w:spacing w:line="360" w:lineRule="auto" w:after="240" w:before="0"/>
  </w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
{h}
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:qFormat/>
  <w:pPr><w:ind w:left="360" w:right="200"/><w:spacing w:line="360" w:lineRule="auto" w:after="240"/></w:pPr>
  <w:rPr><w:shd w:val="clear" w:color="auto" w:fill="FFF8E1"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/><w:qFormat/>
  <w:pPr><w:ind w:left="200" w:right="200"/><w:spacing w:line="240" w:lineRule="auto" w:after="0" w:before="0"/></w:pPr>
  <w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:eastAsia="Consolas"/>
    <w:sz w:val="20"/><w:szCs w:val="20"/><w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>
  <w:pPr><w:ind w:left="420" w:hanging="260"/><w:spacing w:line="360" w:lineRule="auto" w:after="60"/></w:pPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>
  <w:tblPr><w:tblBorders>
    <w:top w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>
    <w:left w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>
    <w:bottom w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>
    <w:right w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>
    <w:insideH w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>
    <w:insideV w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>
  </w:tblBorders></w:tblPr></w:style>
</w:styles>'''


def build_docx(title, meta_lines, md_files, out_path):
    body = []
    # 封面标题
    body.append('<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="1440" w:after="120" '
                'w:line="360" w:lineRule="auto"/></w:pPr>'
                + run(title, '<w:rFonts w:ascii="黑体" w:hAnsi="黑体" w:eastAsia="黑体"/>'
                             '<w:b/><w:color w:val="1F3864"/><w:sz w:val="44"/><w:szCs w:val="44"/>')
                + '</w:p>')
    for line in meta_lines:
        body.append('<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:line="360" w:lineRule="auto" w:after="60"/></w:pPr>'
                    + run(line, '<w:sz w:val="24"/><w:color w:val="404040"/>') + '</w:p>')
    body.append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr>'
                '<w:r><w:br w:type="page"/></w:r></w:p>')

    for fname, part_title in md_files:
        if part_title:
            body.append('<w:p><w:pPr><w:spacing w:before="600" w:after="240" w:line="360" w:lineRule="auto"/>'
                        '<w:pBdr><w:bottom w:val="single" w:sz="12" w:space="2" w:color="1F3864"/></w:pBdr></w:pPr>'
                        + run(part_title, '<w:rFonts w:ascii="黑体" w:hAnsi="黑体" w:eastAsia="黑体"/>'
                                          '<w:b/><w:color w:val="1F3864"/><w:sz w:val="32"/><w:szCs w:val="32"/>')
                        + '</w:p>')
        md = open(os.path.join(BASE, fname), encoding="utf-8").read()
        for b in parse(md):
            body.append(block_to_xml(b))

    sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rId2"/>'
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417" '
            'w:header="851" w:footer="992" w:gutter="0"/>'
            '<w:cols w:space="425"/><w:docGrid w:linePitch="312"/></w:sectPr>')
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document {W} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<w:body>{"".join(body)}{sect}</w:body></w:document>')

    footer = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<w:ftr {W}><w:p><w:pPr><w:jc w:val="center"/>'
              '<w:spacing w:line="240" w:lineRule="auto"/></w:pPr>'
              + run("第 ", '<w:sz w:val="18"/><w:color w:val="808080"/>')
              + '<w:r><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
                '<w:r><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr>'
                '<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
                '<w:r><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>'
              + run(" 页", '<w:sz w:val="18"/><w:color w:val="808080"/>')
              + '</w:p></w:ftr>')

    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
          '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
          '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            '</Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
             '</Relationships>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{esc(title)}</dc:title>'
            '<dc:creator>SmartOpsAgent</dc:creator><cp:lastModifiedBy>SmartOpsAgent</cp:lastModifiedBy>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">2026-11-02T00:00:00Z</dcterms:created>'
            '<dcterms:modified xsi:type="dcterms:W3CDTF">2026-11-02T00:00:00Z</dcterms:modified>'
            '</cp:coreProperties>')
    app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
           'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
           '<Application>SmartOpsAgent</Application></Properties>')

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles_xml())
        z.writestr("word/footer1.xml", footer)
        z.writestr("word/_rels/document.xml.rels", drels)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
    print("DOCX ->", out_path, os.path.getsize(out_path))


if __name__ == "__main__":
    meta = [
        "智维 Agent（SmartOpsAgent）· 可信 AI 智能运维与知识协同平台",
        "2026 第八届全球校园人工智能算法精英大赛 · 河南赛区 · 算法创新赛",
        "A4 页面 · 上下页边距 2.5cm · 正文 1.5 倍行距 · 段间空一行 · 宋体小四",
    ]
    build_docx("答辩知识手册",
               meta,
               [("项目知识要点手册.md", "册一　项目知识要点"),
                ("答辩实战问答手册.md", "册二　答辩实战问答")],
               os.path.join(BASE, "答辩知识手册-Word版.docx"))

    build_docx("项目知识要点手册", meta[:2],
               [("项目知识要点手册.md", "")],
               os.path.join(BASE, "项目知识要点-Word版.docx"))
    build_docx("答辩实战问答手册", meta[:2],
               [("答辩实战问答手册.md", "")],
               os.path.join(BASE, "答辩实战问答-Word版.docx"))
