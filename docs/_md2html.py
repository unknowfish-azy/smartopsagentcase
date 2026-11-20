"""Markdown → HTML 轻量转换器（仅支持本文件用到的语法）。

用法：python _md2html.py input.md output.html
"""
from __future__ import annotations
import sys
import html as _html
import re


def convert(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_code = False
    code_lang = ""
    code_buf: list[str] = []
    in_table = False
    table_head: list[str] = []
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal table_head, table_rows, in_table
        if not in_table:
            return
        out.append("<table>")
        if table_head:
            out.append("<thead><tr>")
            for cell in table_head:
                out.append(f"<th>{inline(cell)}</th>")
            out.append("</tr></thead>")
        out.append("<tbody>")
        for row in table_rows:
            out.append("<tr>")
            for cell in row:
                out.append(f"<td>{inline(cell)}</td>")
            out.append("</tr>")
        out.append("</tbody></table>")
        table_head = []
        table_rows = []
        in_table = False

    while i < len(lines):
        line = lines[i]

        # 代码块
        if line.startswith("```"):
            if not in_code:
                flush_table()
                in_code = True
                code_lang = line[3:].strip()
                code_buf = []
            else:
                lang_cls = f' class="language-{code_lang}"' if code_lang else ""
                out.append(f"<pre><code{lang_cls}>{_html.escape(chr(10).join(code_buf))}</code></pre>")
                in_code = False
                code_lang = ""
                code_buf = []
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # 空行
        if not line.strip():
            flush_table()
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            flush_table()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # 表格（首行含 | 且非标题分隔）
        if "|" in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # 下一行如果是分隔行则表头
            if i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$", lines[i + 1]):
                flush_table()
                in_table = True
                table_head = cells
                i += 2
                continue
            if in_table:
                table_rows.append(cells)
                i += 1
                continue

        flush_table()

        # 引用（以 > 开头，可能连续）
        if line.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].startswith(">"):
                quote_lines.append(lines[i][1:].lstrip())
                i += 1
            inner = "\n".join(convert_inline_paragraphs(quote_lines))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # 列表
        if re.match(r"^[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                items.append(lines[i][2:])
                i += 1
            out.append("<ul>")
            for it in items:
                out.append(f"<li>{inline(it)}</li>")
            out.append("</ul>")
            continue

        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i]))
                i += 1
            out.append("<ol>")
            for it in items:
                out.append(f"<li>{inline(it)}</li>")
            out.append("</ol>")
            continue

        # 分隔线
        if re.match(r"^---+\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        # 普通段落（合并连续非空非特殊行）
        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "```", ">", "-", "*", "|")) and not re.match(r"^\d+\.\s+", lines[i]) and not re.match(r"^---+\s*$", lines[i]):
            para_lines.append(lines[i])
            i += 1
        out.append(f"<p>{inline(' '.join(para_lines))}</p>")

    flush_table()
    if in_code:
        out.append(f"<pre><code>{_html.escape(chr(10).join(code_buf))}</code></pre>")

    return "\n".join(out)


def convert_inline_paragraphs(lines: list[str]) -> list[str]:
    """引用块内的行：图片单独成 <p>，其余合并。"""
    result: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if ln.strip().startswith("!["):
            if buf:
                result.append(f"<p>{inline(' '.join(buf))}</p>")
                buf = []
            result.append(f"<p>{inline(ln)}</p>")
        else:
            buf.append(ln)
    if buf:
        result.append(f"<p>{inline(' '.join(buf))}</p>")
    return result


def inline(text: str) -> str:
    """行内转换：图片、链接、粗体、代码、行内公式。"""
    # 先转义
    result = _html.escape(text)

    # 行内 code `...`
    result = re.sub(r"`([^`]+)`", r"<code>\1</code>", result)

    # **bold**
    result = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", result)

    # ![alt](path) — 图片路径里的 / \ 不做转义恢复
    def img_repl(m: re.Match) -> str:
        alt = m.group(1)
        path = m.group(2)
        return f'<img src="{path}" alt="{alt}">'
    result = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", img_repl, result)

    # [text](href)
    def link_repl(m: re.Match) -> str:
        txt = m.group(1)
        href = m.group(2)
        target = ' target="_blank" rel="noopener"' if href.startswith(("http://", "https://", "file://")) else ""
        return f'<a href="{href}"{target}>{txt}</a>'
    result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, result)

    return result


HTML_WRAPPER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --bg: #0b1020;
    --surface: #111827;
    --border: #1e293b;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #38bdf8;
    --code-bg: #0f172a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif;
    line-height: 1.7;
    font-size: 15px;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 48px 32px 80px; }}
  h1 {{ font-size: 28px; border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-top: 0; }}
  h2 {{ font-size: 22px; margin-top: 40px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
  h3 {{ font-size: 18px; margin-top: 28px; }}
  h4 {{ font-size: 15px; margin-top: 20px; color: var(--accent); }}
  p {{ margin: 12px 0; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  table {{
    width: 100%; border-collapse: collapse; margin: 16px 0;
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden;
  }}
  th, td {{ padding: 10px 14px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
  th {{ background: #1a2332; font-weight: 600; color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }}
  tr:last-child td {{ border-bottom: none; }}
  code {{
    background: var(--code-bg); padding: 2px 7px; border-radius: 4px;
    font-family: "JetBrains Mono", "Fira Code", Consolas, monospace; font-size: 13px;
  }}
  pre {{
    background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 16px; overflow-x: auto; margin: 16px 0;
  }}
  pre code {{ background: none; padding: 0; font-size: 13px; line-height: 1.55; }}
  blockquote {{
    border-left: 3px solid var(--accent); padding: 8px 20px; margin: 20px 0;
    background: var(--surface); border-radius: 0 8px 8px 0; color: var(--muted);
  }}
  blockquote img {{ display: block; max-width: 100%; border-radius: 6px; margin: 12px auto; }}
  hr {{ border: none; border-top: 1px solid var(--border); margin: 32px 0; }}
  img {{ max-width: 100%; border-radius: 6px; }}
  ul, ol {{ padding-left: 24px; }}
  li {{ margin: 4px 0; }}
  thead {{ background: #1a2332; }}
</style>
</head>
<body>
<div class="wrap">
{body}
</div>
</body>
</html>
"""


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python _md2html.py input.md output.html")
        return 1
    src = sys.argv[1]
    dst = sys.argv[2]
    with open(src, "r", encoding="utf-8") as f:
        md = f.read()
    body = convert(md)
    title_match = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    title = title_match.group(1) if title_match else "Document"
    html_doc = HTML_WRAPPER.format(title=_html.escape(title), body=body)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"✓ {dst}  ({len(html_doc)//1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
