# -*- coding: utf-8 -*-
import re, html, os

BASE = r"D:\SmartOpsAgent\docs\competition"
FILES = [
    ("册一", "陈述稿 · 上台陈述（约 8–10 分钟）", "defense.md"),
    ("册二", "答辩全景手册 · 主问答（70 题）", "defense-master.md"),
    ("册三", "问答圣经 · 速查补充（40 题）", "defense-qa.md"),
    ("册四", "答辩补强 · 技术追问 / 产品优势 / 未来前景", "defense-advanced.md"),
]

def esc(s):
    return html.escape(s, quote=False)

def inline(text):
    # escape first
    t = esc(text)
    # inline code `code`
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    # bold **text**
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    # links [t](u)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t

def is_table_sep(line):
    s = line.strip()
    return bool(re.match(r"^\|?[\s:|-]+\|?$", s)) and "-" in s and "|" in s

def convert(md):
    lines = md.splitlines()
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # fenced code
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1  # skip closing
            out.append("<pre><code>" + esc("\n".join(buf)) + "</code></pre>")
            continue

        # table
        if stripped.startswith("|") and "|" in stripped:
            block = []
            while i < n and lines[i].strip().startswith("|"):
                block.append(lines[i]); i += 1
            if len(block) >= 2 and is_table_sep(block[1]):
                header = [c.strip() for c in block[0].strip().strip("|").split("|")]
                body = block[2:]
                th = "".join("<th>" + inline(c) + "</th>" for c in header)
                rows = []
                for r in body:
                    cells = [c.strip() for c in r.strip().strip("|").split("|")]
                    rows.append("<tr>" + "".join("<td>" + inline(c) + "</td>" for c in cells) + "</tr>")
                out.append("<table><thead><tr>" + th + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
            else:
                # not a real table, render as paragraphs
                for b in block:
                    out.append("<p>" + inline(b) + "</p>")
            continue

        # headings
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            lvl = len(m.group(1))
            txt = inline(m.group(2).strip())
            out.append(f"<h{lvl}>{txt}</h{lvl}>")
            i += 1
            continue

        # hr
        if re.match(r"^---+$", stripped):
            out.append("<hr/>"); i += 1; continue

        # blockquote
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(inline(lines[i].strip()[1:].strip()))
                i += 1
            out.append("<blockquote>" + "<br/>".join(buf) + "</blockquote>")
            continue

        # unordered list
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(inline(re.sub(r"^[-*]\s+", "", lines[i].strip())))
                i += 1
            out.append("<ul>" + "".join("<li>" + x + "</li>" for x in items) + "</ul>")
            continue

        # ordered list
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(inline(re.sub(r"^\d+\.\s+", "", lines[i].strip())))
                i += 1
            out.append("<ol>" + "".join("<li>" + x + "</li>" for x in items) + "</ol>")
            continue

        # blank
        if stripped == "":
            i += 1; continue

        # paragraph (accumulate until blank or special)
        buf = []
        while i < n:
            s = lines[i].strip()
            if s == "" or s.startswith("#") or s.startswith("```") or s.startswith("|") \
               or s.startswith(">") or re.match(r"^[-*]\s+", s) or re.match(r"^\d+\.\s+", s) \
               or re.match(r"^---+$", s):
                break
            buf.append(s); i += 1
        out.append("<p>" + "<br/>".join(inline(x) for x in buf) + "</p>")
    return "\n".join(out)

sections_html = []
for idx, (tag, title, fname) in enumerate(FILES):
    path = os.path.join(BASE, fname)
    with open(path, "r", encoding="utf-8") as f:
        md = f.read()
    body = convert(md)
    first = " first" if idx == 0 else ""
    sections_html.append(f"""
    <section class="part{first}">
      <div class="part-divider">
        <div class="part-tag">{tag}</div>
        <div class="part-title">{esc(title)}</div>
        <div class="part-src">源文件：{esc(fname)}</div>
      </div>
      <div class="part-body">{body}</div>
    </section>""")

CHEAT = """
<div class="cheat-card">
  <div class="cheat-head">智维Agent · 一页速记卡（可裁下带上台）</div>
  <div class="cheat-body">
    <p class="big">AI 负责思考，人负责授权，系统负责留痕。</p>
    <p>三道锁：证据锁 / 风险锁 / 边界锁；一本账：审计账。</p>
    <hr/>
    <p><b>混合检索</b>：并行召回 → 各自 max 归一化 → 0.6 向量 + 0.4 BM25 → 合并去重 top_k</p>
    <p><b>trust_score</b>：0.5×证据均分 + 0.3×是否被支持 + 0.2×min(证据数/3, 1)</p>
    <p><b>四级纠察</b>：Rule(规则) → Evidence(证据) → AI(可插拔) → Verifier(状态核验)</p>
    <p><b>假成功</b>：声称已解决 但 实际 resolved=false → REJECTED</p>
    <p><b>风险</b>：CRITICAL 禁自动 / HIGH 必审批（server.restart·stop·delete·shell.execute）</p>
    <p><b>数字</b>：610 个 Python 用例 + 671 个后端 @Test · 119 张表 · 5 模块 · 6 思考阶段 · 零密钥可复现</p>
    <hr/>
    <p><b>被问数据</b>：先认 NOT RUN → 亮"诚实评测框架" → 转"系统能力可演示可验证"</p>
    <p><b>被问边界</b>：先承认 → 给路线图（OCR / 端侧 / 多节点 / 语义版本）</p>
    <p><b>被问竞品</b>：差异在约束，不在模型</p>
  </div>
</div>
"""

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
* { box-sizing: border-box; }
body { font-family: "Microsoft YaHei","PingFang SC","Hiragino Sans GB","Noto Sans CJK SC",sans-serif;
       color:#1a1a1a; font-size:10.5pt; line-height:1.72; margin:0; }
h1,h2,h3,h4 { color:#0f2b46; line-height:1.35; page-break-after:avoid; }
h1 { font-size:20pt; margin:14px 0 10px; border-bottom:2.5px solid #0f2b46; padding-bottom:6px; }
h2 { font-size:14.5pt; margin:16px 0 8px; border-left:5px solid #1f6feb; padding-left:9px; }
h3 { font-size:12pt; margin:12px 0 6px; color:#123c5e; }
h4 { font-size:10.8pt; margin:10px 0 5px; }
p { margin:5px 0; }
ul,ol { margin:6px 0 6px 4px; padding-left:22px; }
li { margin:2px 0; }
strong { color:#0b2e4a; }
code { font-family:"Cascadia Code",Consolas,"Courier New",monospace; background:#f3f5f8;
       padding:1px 4px; border-radius:3px; font-size:9.3pt; color:#b3306b; }
pre { background:#0f2233; color:#e6edf3; padding:10px 12px; border-radius:6px;
      white-space:pre-wrap; word-break:break-word; page-break-inside:avoid; margin:8px 0; }
pre code { background:none; color:inherit; padding:0; font-size:9pt; }
blockquote { border-left:4px solid #c9d4e2; background:#f7f9fc; margin:8px 0;
             padding:6px 12px; color:#33475b; }
table { border-collapse:collapse; width:100%; margin:8px 0; font-size:9.2pt; page-break-inside:avoid; }
th,td { border:1px solid #c4cedb; padding:5px 7px; text-align:left; vertical-align:top; }
th { background:#e8eef6; color:#0f2b46; font-weight:700; }
tr:nth-child(even) td { background:#fafbfd; }
hr { border:none; border-top:1px dashed #c4cedb; margin:14px 0; }
a { color:#1f6feb; text-decoration:none; }

/* cover */
.cover { min-height:92vh; display:flex; flex-direction:column; justify-content:center;
         padding:8mm 2mm; page-break-after:always; }
.cover .kicker { font-size:11pt; color:#1f6feb; letter-spacing:3px; font-weight:700; }
.cover h1.big { font-size:30pt; border:none; margin:10px 0 6px; color:#0f2b46; }
.cover .sub { font-size:13pt; color:#33475b; margin:4px 0; }
.cover .meta { margin-top:18px; font-size:10.5pt; color:#33475b; line-height:1.9; }
.cover .box { margin-top:22px; border:1.5px solid #1f6feb; border-radius:8px; padding:14px 16px; background:#f7faff; }
.cover .box h3 { margin-top:0; color:#1f6feb; }
.cover .box ol { margin:6px 0 0; }
.cover .hint { margin-top:14px; font-size:9.5pt; color:#65758b; }

/* toc */
.toc { page-break-after:always; padding-top:4mm; }
.toc h1 { border-bottom:2.5px solid #0f2b46; }
.toc table { font-size:11pt; }
.toc td:first-child { width:64px; font-weight:700; color:#1f6feb; }
.toc td:nth-child(2) { width:38%; font-weight:700; }
.toc .dot { color:#9fb0c3; }

/* part divider */
.part { page-break-before:always; }
.part.first { page-break-before:auto; }
.part-divider { border:2px solid #0f2b46; border-radius:10px; padding:22px 24px;
                margin:6mm 0 10mm; background:linear-gradient(135deg,#0f2b46,#1f6feb); color:#fff; }
.part-divider .part-tag { font-size:13pt; font-weight:700; letter-spacing:4px; opacity:.9; }
.part-divider .part-title { font-size:20pt; font-weight:800; margin-top:6px; }
.part-divider .part-src { font-size:9.5pt; opacity:.75; margin-top:8px; }
.part-body > h1:first-child { margin-top:0; }

/* cheat */
.cheat-page { page-break-before:always; }
.cheat-card { border:2.5px dashed #0f2b46; border-radius:12px; padding:18px 20px; margin-top:6mm; background:#fffdf5; }
.cheat-head { text-align:center; font-size:15pt; font-weight:800; color:#0f2b46; border-bottom:2px solid #0f2b46; padding-bottom:8px; }
.cheat-body { font-size:11pt; line-height:1.95; }
.cheat-body .big { font-size:14pt; font-weight:800; color:#b3306b; text-align:center; margin:10px 0; }
"""

toc_rows = [
    ("封面", "封面（含打印顺序说明）", "1"),
    ("目录", "目录", "2"),
    ("册一", "陈述稿 · 上台陈述", "3 起"),
    ("册二", "答辩全景手册 · 主问答 70 题", "按分页"),
    ("册三", "问答圣经 · 速查补充 40 题", "按分页"),
    ("册四", "答辩补强 · 技术追问 60 题 / 产品优势 / 未来前景", "按分页"),
    ("附", "一页速记卡（可裁下带上台）", "末页"),
]

toc_html = "<table><tbody>" + "".join(
    f'<tr><td>{a}</td><td>{b}</td><td class="dot">· · · · · · · · · · · · · · · · · · ·</td><td style="text-align:right">{c}</td></tr>'
    for a, b, c in toc_rows) + "</tbody></table>"

doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>智维Agent · 答辩材料打印合订本</title>
<style>{CSS}</style>
</head>
<body>

<section class="cover">
  <div class="kicker">答辩材料 · 打印合订本</div>
  <h1 class="big">智维Agent</h1>
  <div class="sub">面向中小企业的可信 AI 智能运维与知识协同平台</div>
  <div class="sub">SmartOpsAgent · 可信闭环 · 算法创新赛</div>
  <div class="meta">
    赛事：2026 第八届全球校园人工智能算法精英大赛 · 河南赛区 · 算法创新赛<br/>
    团队：<b>【团队名称 / 学校 / 队员 / 指导教师 —— 待填】</b><br/>
    版本：v2.0 &nbsp;·&nbsp; 2026-11
  </div>
  <div class="box">
    <h3>打印与装订顺序（从上到下）</h3>
    <ol>
      <li><b>封面</b>（本页）</li>
      <li><b>目录</b></li>
      <li><b>册一 · 陈述稿</b> —— 上台照着讲（建议单独打印一份拿在手里）</li>
      <li><b>册二 · 答辩全景手册</b> —— 主问答，评委深挖用</li>
      <li><b>册三 · 问答圣经</b> —— 快查补充</li>
      <li><b>册四 · 答辩补强</b> —— 临场技术追问 / 产品优势 / 未来前景</li>
      <li><b>附 · 一页速记卡</b> —— 建议彩打、裁下带上台</li>
    </ol>
    <div class="hint">建议：A4 双面；打印时勾选"页眉页脚/页码"；速记卡单独一张纸。</div>
  </div>
</section>

<section class="toc">
  <h1>目录</h1>
  {toc_html}
</section>

{''.join(sections_html)}

<section class="cheat-page">
  {CHEAT}
</section>

</body>
</html>"""

out_path = os.path.join(BASE, "答辩材料-打印合订本.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(doc)

# also merged markdown for editing
merged = []
merged.append("# 智维Agent 答辩材料合订本（源）\n")
for tag, title, fname in FILES:
    with open(os.path.join(BASE, fname), "r", encoding="utf-8") as f:
        merged.append(f"\n\n<!-- ========== {tag} {title} ========== -->\n\n")
        merged.append(f.read())
merged.append("\n\n<!-- ========== 附 速记卡 ========== -->\n\n")
with open(os.path.join(BASE, "答辩材料-合订本.md"), "w", encoding="utf-8") as f:
    f.write("".join(merged))

print("OK", out_path)
print("size", os.path.getsize(out_path))
