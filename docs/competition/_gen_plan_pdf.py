# -*- coding: utf-8 -*-
"""
生成《四件套万全之策》打印版 HTML
- 浅色版式：省墨、黑白打印不失真
- 表格禁止跨页断开、表头重复
- 代码/框图不折行
- 目录手工撰写要点（无页码，用章节号导航）
"""
import re, html, os

BASE = r"D:\SmartOpsAgent\docs\competition"
SRC = os.path.join(BASE, "submission-master-plan.md")
OUT = os.path.join(BASE, "四件套万全之策-打印版.html")


def esc(s):
    return html.escape(s, quote=False)


def inline(text):
    t = esc(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


def is_table_sep(line):
    s = line.strip()
    return bool(re.match(r"^\|?[\s:|-]+\|?$", s)) and "-" in s and "|" in s


def convert(md):
    lines = md.splitlines()
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 围栏代码块
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            out.append('<pre class="fig"><code>' + esc("\n".join(buf)) + "</code></pre>")
            continue

        # 表格
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
                out.append('<table><thead><tr>' + th + '</tr></thead><tbody>' + "".join(rows) + "</tbody></table>")
            else:
                for b in block:
                    out.append("<p>" + inline(b) + "</p>")
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            lvl = len(m.group(1))
            txt = inline(m.group(2).strip())
            cls = ' class="sec"' if lvl == 2 else ""
            out.append(f"<h{lvl}{cls}>{txt}</h{lvl}>")
            i += 1
            continue

        # 分隔线
        if re.match(r"^---+$", stripped):
            out.append('<hr class="sep"/>'); i += 1; continue

        # 引用块（提示/话术）
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(inline(lines[i].strip()[1:].strip()))
                i += 1
            out.append('<div class="callout">' + "<br/>".join(buf) + "</div>")
            continue

        # 复选框列表
        if re.match(r"^[-*]\s+\[\s?\]\s+", stripped):
            items = []
            while i < n and re.match(r"^[-*]\s+\[\s?\]\s+", lines[i].strip()):
                txt = re.sub(r"^[-*]\s+\[\s?\]\s+", "", lines[i].strip())
                items.append('<li class="chk">' + inline(txt) + "</li>")
                i += 1
            out.append('<ul class="checklist">' + "".join(items) + "</ul>")
            continue

        # 无序列表
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(inline(re.sub(r"^[-*]\s+", "", lines[i].strip())))
                i += 1
            out.append("<ul>" + "".join("<li>" + x + "</li>" for x in items) + "</ul>")
            continue

        # 有序列表
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(inline(re.sub(r"^\d+\.\s+", "", lines[i].strip())))
                i += 1
            out.append("<ol>" + "".join("<li>" + x + "</li>" for x in items) + "</ol>")
            continue

        if stripped == "":
            i += 1
            continue

        # 段落
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


raw = open(SRC, encoding="utf-8").read()

# 拆出：主标题 / 元信息引用块 / 正文
lines = raw.splitlines()
title = ""
meta_block = []
body_start = 0
for idx, l in enumerate(lines):
    if l.startswith("# ") and not title:
        title = l[2:].strip()
    if l.strip() == "---" and meta_block:
        body_start = idx + 1
        break
    if l.strip().startswith(">") and title:
        meta_block.append(l.strip()[1:].strip())

meta_html = "<br/>".join(inline(x) for x in meta_block if x)
body_md = "\n".join(lines[body_start:])
body_html = convert(body_md)

TOC = [
    ("0", "一句话战略", "全局判断，以及三种“死法”的对应解法"),
    ("1", "评委怎么读这四份材料", "四把尺子：谁在读、找什么、一票否决点"),
    ("2", "总架构：一源·四层·三线", "从事实源到四份材料的派生关系"),
    ("3", "单一事实源（口径台账）", "9 条可用底数 + 5 项待测 + 禁用口径"),
    ("4", "分工矩阵：一份只答一个问题", "四份材料零重复的划界表"),
    ("5", "逐份作战方案", "四份材料的目录大纲、页数预算、扣分点"),
    ("6", "三条红线与标准话术", "数据集 / 实验 / 规则基线的统一说法"),
    ("7", "佐证材料清单", "L1 / L2 / L3 三级证据打勾表"),
    ("8", "一致性矩阵", "同一事实在四份材料里的四种写法"),
    ("9", "七天作战排期", "含依赖关系的写作顺序"),
    ("10", "交付前 30 项自检", "打印前逐条过一遍"),
    ("11", "需要你确认的 4 件事", "决定写法的决策点"),
    ("附", "与既有材料的关系", "答辩稿体系如何复用"),
]

toc_rows = "".join(
    f'<tr><td class="num">{n}</td><td class="name">{esc(t)}</td><td class="desc">{esc(d)}</td></tr>'
    for n, t, d in TOC
)

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html, body { margin:0; padding:0; }
body {
  font-family: "Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif;
  color:#1b1f24; font-size:10.5pt; line-height:1.92;
  text-align: justify; text-justify: inter-ideograph;
  -webkit-font-smoothing: antialiased;
}

/* ============ 封面 ============ */
.cover { height: 257mm; display:flex; flex-direction:column; page-break-after:always;
         padding: 6mm 0 0 0; position:relative; }
.cover .rule-top { height:3.2pt; background:#12385c; width:100%; }
.cover .kicker { margin-top:26mm; font-size:10.5pt; letter-spacing:4px; color:#2a6fb0; font-weight:700; }
.cover h1 { font-size:34pt; line-height:1.24; margin:8mm 0 0; color:#0f2b46; font-weight:800; letter-spacing:1px; }
.cover .sub { font-size:13pt; color:#3c4a5a; margin-top:5mm; line-height:1.9; }
.cover .sub b { color:#0f2b46; }
.cover .divider { width:64mm; height:2.2pt; background:#2a6fb0; margin:8mm 0; }
.cover .thesis { border-left:4pt solid #2a6fb0; background:#f4f8fd; padding:6mm 7mm; margin-top:2mm; }
.cover .thesis .lab { font-size:8.8pt; letter-spacing:2px; color:#2a6fb0; font-weight:700; }
.cover .thesis .txt { font-size:12.5pt; font-weight:700; color:#0f2b46; line-height:1.8; margin-top:2mm; }
.cover .metatbl { margin-top:10mm; width:100%; border-collapse:collapse; font-size:9.6pt; }
.cover .metatbl td { padding:2.2mm 0; border-bottom:0.6pt solid #dde5ee; vertical-align:top; }
.cover .metatbl td.k { width:26mm; color:#68788c; }
.cover .metatbl td.v { color:#1b1f24; font-weight:600; }
.cover .foot { margin-top:auto; padding-top:6mm; border-top:0.8pt solid #dde5ee;
               font-size:8.6pt; color:#7b8a9c; line-height:1.8; }

/* ============ 说明 + 目录 ============ */
.front { page-break-after:always; }
.front h2.plain { font-size:16pt; color:#0f2b46; margin:0 0 4mm; padding-bottom:2.5mm;
                  border-bottom:2pt solid #0f2b46; font-weight:800; }
.notice { background:#f4f8fd; border:0.8pt solid #cfe0f2; padding:5mm 6mm; font-size:9.6pt;
          line-height:1.85; color:#2b3a4b; margin-bottom:9mm; }
.notice b { color:#0f2b46; }
.toc { width:100%; border-collapse:collapse; font-size:9.8pt; }
.toc th { background:#12385c; color:#fff; font-weight:700; padding:3mm 3.4mm; text-align:left; font-size:9.4pt; letter-spacing:1px; }
.toc td { padding:3.8mm 3.4mm; border-bottom:0.6pt solid #e2e9f1; vertical-align:top; line-height:1.8; }
.toc tr:nth-child(even) td { background:#fafcfe; }
.toc td.num { width:14mm; font-weight:800; color:#2a6fb0; font-size:11pt; text-align:center; }
.toc td.name { width:52mm; font-weight:700; color:#0f2b46; }
.toc td.desc { color:#3c4a5a; }

/* ============ 正文排版 ============ */
.body { padding-bottom: 2mm; }
h1 { font-size:19pt; color:#0f2b46; margin:0 0 5mm; padding-bottom:2.5mm;
     border-bottom:2pt solid #0f2b46; page-break-after:avoid; font-weight:800; }
h2.sec { font-size:14.4pt; color:#0f2b46; margin:10mm 0 4.5mm; padding:2.6mm 0 2.6mm 5mm;
         border-left:4pt solid #2a6fb0; background:#f7fafd; page-break-after:avoid;
         font-weight:800; letter-spacing:.3px; }
h3 { font-size:11.6pt; color:#12385c; margin:7mm 0 3.2mm; page-break-after:avoid; font-weight:700; }
h4 { font-size:10.6pt; color:#1b1f24; margin:4.5mm 0 2.2mm; page-break-after:avoid; font-weight:700; }
p { margin:3mm 0; orphans:3; widows:3; }
ul, ol { margin:3mm 0 3.6mm; padding-left:7.5mm; }
li { margin:1.8mm 0; line-height:1.85; }
strong { color:#0b2e4a; font-weight:700; }
code { font-family:Consolas,"Cascadia Mono","Courier New",monospace; background:#eef2f7;
       padding:0.3mm 1.1mm; border-radius:2px; font-size:9pt; color:#8c2f5a; }

/* 框图/代码：浅底、不折行、不跨页 */
pre.fig { background:#f6f8fa; border:0.8pt solid #d6dee8; border-left:3pt solid #2a6fb0;
          padding:5mm 5.5mm; margin:4.5mm 0 6mm; page-break-inside:avoid;
          white-space:pre; overflow:hidden; font-size:8.6pt; line-height:1.7; }
pre.fig code { background:none; color:#1b2b3a; padding:0; font-size:8.4pt; }

/* 话术提示块 */
.callout { background:#fffdf4; border:0.8pt solid #eadfc0; border-left:3pt solid #c79a2e;
           padding:4.5mm 5.5mm; margin:4mm 0 5mm; font-size:9.8pt; line-height:1.92;
           color:#3a3427; page-break-inside:avoid; }

/* 表格 */
table { width:100%; border-collapse:collapse; margin:4.5mm 0 6mm; font-size:9.3pt;
        page-break-inside:avoid; }
thead { display: table-header-group; }
th { background:#e8f0f8; color:#0f2b46; font-weight:700; padding:2.9mm 3.2mm;
     border:0.6pt solid #b9c8d8; text-align:left; line-height:1.62; }
td { padding:2.8mm 3.2mm; border:0.6pt solid #cbd6e3; vertical-align:top; line-height:1.75;
     word-break: break-word; }
tbody tr:nth-child(even) td { background:#fafbfd; }

hr.sep { border:none; border-top:0.8pt dashed #c3cfdd; margin:7mm 0; }

/* 复选框 */
ul.checklist { list-style:none; padding-left:1mm; }
li.chk { position:relative; padding-left:7.2mm; margin:2.2mm 0; }
li.chk:before { content:"☐"; position:absolute; left:0; font-size:12pt; color:#2a6fb0; line-height:1.35; }

/* 末页说明 */
.backnote { margin-top:6mm; border:0.8pt solid #cfe0f2; background:#f4f8fd; padding:5mm 6mm; font-size:9.3pt; line-height:1.85; }
.backnote h3 { margin-top:0; }
"""

doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>四件套万全之策 · 提交材料作战方案</title>
<style>{CSS}</style>
</head>
<body>

<!-- ============ 封面 ============ -->
<section class="cover">
  <div class="rule-top"></div>
  <div class="kicker">提交材料 · 作战方案</div>
  <h1>四件套万全之策</h1>
  <div class="sub">
    技术方案 &nbsp;·&nbsp; 技术报告 &nbsp;·&nbsp; 佐证材料 &nbsp;·&nbsp; 商业报告书<br/>
    项目：<b>智维 Agent（SmartOpsAgent）</b>　面向 Linux 运维场景的可信智能体
  </div>
  <div class="divider"></div>
  <div class="thesis">
    <div class="lab">核心判断</div>
    <div class="txt">四份材料不是四篇文章，<br/>而是同一个论证被四把不同的尺子量。</div>
  </div>
  <table class="metatbl">
    <tr><td class="k">赛事</td><td class="v">2026 第八届全球校园人工智能算法精英大赛 · 河南赛区 · 算法创新赛</td></tr>
    <tr><td class="k">文档性质</td><td class="v">写作作战方案（不是材料本身）</td></tr>
    <tr><td class="k">版本</td><td class="v">v1.0　·　2026-11-02</td></tr>
    <tr><td class="k">阅读用时</td><td class="v">全文约 20 分钟；赶时间只读第 0、3、6、8 节</td></tr>
  </table>
  <div class="foot">
    打印建议：A4 双面（长边翻转）· 缩放 100% · 黑白即可，全册不使用深色底，省墨且不糊
  </div>
</section>

<!-- ============ 说明 + 目录 ============ -->
<section class="front">
  <h2 class="plain">怎么用这份方案</h2>
  <div class="notice">
    {meta_html}
  </div>
  <h2 class="plain">目录</h2>
  <table class="toc">
    <thead><tr><th style="width:14mm">节</th><th style="width:52mm">内容</th><th>你会拿到什么</th></tr></thead>
    <tbody>{toc_rows}</tbody>
  </table>
  <div class="backnote" style="margin-top:8mm">
    <h3>三句话读完</h3>
    <b>一、</b>先做「口径台账」（第 3 节），再写任何一份材料——否则四份必然互相打脸。<br/>
    <b>二、</b>四份材料各答一个问题：为什么这么设计 / 实际做成什么 / 凭什么信 / 谁付钱，<b>内容不许重复</b>。<br/>
    <b>三、</b>本项目有三处必须提前备好话术：数据集仅 14 条且全 DRAFT、实验 NOT RUN、多个组件是规则基线（第 6 节）。
  </div>
</section>

<!-- ============ 正文 ============ -->
<section class="body">
{body_html}
</section>

</body>
</html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(doc)

print("OK", OUT)
print("size", os.path.getsize(OUT))
