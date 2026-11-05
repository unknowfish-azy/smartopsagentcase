# -*- coding: utf-8 -*-
"""
合成《答辩知识手册》打印版：项目知识要点 + 答辩实战问答
复用 _gen_plan_pdf.py 里的 markdown 转换器与已调好的宽松版式 CSS
"""
import re, os

BASE = r"D:\SmartOpsAgent\docs\competition"

# —— 复用既有转换器与版式（保证两本册子排版一致）——
_src = open(os.path.join(BASE, "_gen_plan_pdf.py"), encoding="utf-8").read()
_ns = {}
exec(_src.split("raw = open(")[0], _ns)
esc, inline, convert = _ns["esc"], _ns["inline"], _ns["convert"]
CSS = re.search(r'CSS = """(.*?)"""', _src, re.S).group(1)

FILES = [
    ("册一", "项目知识要点 · 把项目彻底讲透", "项目知识要点手册.md"),
    ("册二", "答辩实战问答 · 58 题怎么答", "答辩实战问答手册.md"),
]

sections = []
for idx, (tag, title, fname) in enumerate(FILES):
    md = open(os.path.join(BASE, fname), encoding="utf-8").read()
    body = convert(md)
    sections.append(f"""
    <section class="part{' first' if idx == 0 else ''}">
      <div class="part-divider">
        <div class="part-tag">{tag}</div>
        <div class="part-title">{esc(title)}</div>
        <div class="part-src">{esc(fname)}</div>
      </div>
      <div class="part-body">{body}</div>
    </section>""")

# 分册分隔页样式（沿用答辩册的深蓝分隔条，但只在分隔页用，正文仍浅色省墨）
CSS += """
.part { page-break-before:always; }
.part.first { page-break-before:auto; }
.part-divider { border:2pt solid #12385c; border-radius:8px; padding:8mm 9mm; margin:4mm 0 9mm;
                background:#12385c; color:#fff; page-break-after:avoid; }
.part-divider .part-tag { font-size:12pt; font-weight:700; letter-spacing:4px; opacity:.9; }
.part-divider .part-title { font-size:19pt; font-weight:800; margin-top:2mm; }
.part-divider .part-src { font-size:9pt; opacity:.7; margin-top:3mm; }
"""

TOC = [
    ("封面", "封面 + 打印顺序", "1"),
    ("目录", "怎么用这本册子", "2"),
    ("册一", "项目知识要点手册", "3 起"),
    ("— 0", "30 秒讲清这个项目", ""),
    ("— 1", "它到底解决什么问题（三个真痛点）", ""),
    ("— 2", "系统全景：6 个服务与真实规模", ""),
    ("— 3", "必须能讲的功能清单", ""),
    ("— 4", "核心算法知识点（命根子）", ""),
    ("— 5/6", "后端要点 / 前端要点", ""),
    ("— 7", "数据、测试、部署的真实数字", ""),
    ("— 8", "真相清单：哪些是真做、哪些是基线", ""),
    ("— 9/10", "一页数字卡 / 三个必须默写的为什么", ""),
    ("册二", "答辩实战问答手册（58 题）", ""),
    ("— 开场", "3 分钟陈述稿", ""),
    ("— 一", "定位与价值 5 题", ""),
    ("— 二", "算法深挖 12 题", ""),
    ("— 三", "架构与工程 8 题", ""),
    ("— 四", "真实性与边界 12 题（最危险）", ""),
    ("— 五", "安全与伦理 5 题", ""),
    ("— 六", "产品与商业 6 题", ""),
    ("— 七", "团队与个人 4 题", ""),
    ("— 八", "刁钻题 6 题", ""),
]
toc_rows = "".join(
    f'<tr><td class="num">{a}</td><td class="name">{esc(b)}</td><td class="desc">{esc(c)}</td></tr>'
    for a, b, c in TOC
)

doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>智维 Agent · 答辩知识手册</title>
<style>{CSS}</style>
</head>
<body>

<section class="cover">
  <div class="rule-top"></div>
  <div class="kicker">答辩知识手册</div>
  <h1>把项目讲透<br/>把问题答穿</h1>
  <div class="sub">
    册一 · 项目知识要点　｜　册二 · 答辩实战问答（58 题）<br/>
    <b>智维 Agent（SmartOpsAgent）</b>　可信 AI 智能运维与知识协同平台
  </div>
  <div class="divider"></div>
  <div class="thesis">
    <div class="lab">核心主张</div>
    <div class="txt">AI 负责思考，人负责授权，系统负责留痕。</div>
  </div>
  <table class="metatbl">
    <tr><td class="k">赛事</td><td class="v">2026 第八届全球校园人工智能算法精英大赛 · 河南赛区 · 算法创新赛</td></tr>
    <tr><td class="k">本册性质</td><td class="v">可直接背诵的知识要点 + 逐题口播答案</td></tr>
    <tr><td class="k">数字口径</td><td class="v">全部来自代码实测，可当场自证（v1.0 · 2026-11-02）</td></tr>
    <tr><td class="k">上场前</td><td class="v">只看三样：一页数字卡 · 真相清单 · 三个为什么</td></tr>
  </table>
  <div class="foot">
    打印建议：A4 双面（长边翻转）· 缩放 100% · 黑白即可，正文不使用深色底
  </div>
</section>

<section class="front">
  <h2 class="plain">怎么用这本册子</h2>
  <div class="notice">
    <b>册一回答"这个项目是什么"</b>——读完你能从业务背景讲到某一行为什么这么写。<br/>
    <b>册二回答"老师会问什么、我该怎么答"</b>——每题给"老师想听什么 + 口播答案 + 追问链 + 千万别这么说"。<br/>
    <b>最重要的一节是册一第 8 节「真相清单」</b>：8 个"没做完"的地方，<b>主动说出来是加分，被戳穿是事故</b>。
  </div>
  <h2 class="plain">目录</h2>
  <table class="toc">
    <thead><tr><th style="width:18mm">节</th><th style="width:56mm">内容</th><th>页</th></tr></thead>
    <tbody>{toc_rows}</tbody>
  </table>
  <div class="backnote" style="margin-top:8mm">
    <h3>三条铁律</h3>
    <b>一、</b>不报任何准确率 / F1 数字——实验全是 NOT RUN，硬报就是造假。<br/>
    <b>二、</b>被问到没做到的，用「承认 → 给已知 → 划边界 → 给路径」四步接住。<br/>
    <b>三、</b>所有数字以册一第 9 节「一页数字卡」为准，四份材料不许打架。
  </div>
</section>

{''.join(sections)}

</body>
</html>"""

out = os.path.join(BASE, "答辩知识手册-打印版.html")
open(out, "w", encoding="utf-8").write(doc)
print("OK", out, os.path.getsize(out))
