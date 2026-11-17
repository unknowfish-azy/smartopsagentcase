# -*- coding: utf-8 -*-
"""Markdown → Word 转换脚本（python-docx 实现）

功能：
  - 标题层级 / 粗体 / 行内代码 / 数学公式降级
  - Markdown 表格 → Word 表格（首行浅灰底）
  - 图片嵌入（相对路径解析，按页面宽度 90% 缩放）
  - 有序 / 无序列表、水平线、段落

用法：
  python scripts/md_to_docx.py docs/modeling/建模论文-正文.md
  # 输出：docs/modeling/建模论文-正文.docx（与输入同目录，改后缀）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# ---------------------------------------------------------------------------
# 正则
# ---------------------------------------------------------------------------
RE_IMAGE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
RE_LINK = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
RE_BOLD = re.compile(r'\*\*([^*]+)\*\*')
RE_CODE = re.compile(r'`([^`]+)`')
RE_INLINE_MATH = re.compile(r'\$([^$\n]+)\$')
# 块级公式：$$...$$ 允许跨行，用 DOTALL
RE_BLOCK_MATH = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
RE_HEADING = re.compile(r'^(#{1,6})\s+(.*)$')
RE_HR = re.compile(r'^\s*---+\s*$')
RE_OL = re.compile(r'^(\s*)(\d+)\.\s+(.*)$')
RE_UL = re.compile(r'^(\s*)[-*+]\s+(.*)$')

# 表格分隔行：|---|---|
RE_TABLE_SEP = re.compile(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$')
RE_TABLE_ROW = re.compile(r'^\s*\|(.*)\|\s*$')


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def set_run_font(run, cn: str = 'Microsoft YaHei', en: str = 'Cambria', size_pt: float | None = None,
                 bold: bool | None = None, italic: bool | None = None):
    """设置 run 的中英文字体（python-docx 默认只设西文字体，中文字体要改 XML）。"""
    run.font.name = en
    r = run._element
    rPr = r.find(qn('w:rPr'))
    if rPr is None:
        rPr = OxmlElement('w:rPr')
        r.insert(0, rPr)
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    rFonts.set(qn('w:eastAsia'), cn)
    rFonts.set(qn('w:ascii'), en)
    rFonts.set(qn('w:hAnsi'), en)
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_cell_shading(cell, color_hex: str):
    """给表格单元格设背景色（16 进制，不带 #）。"""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), color_hex)
    tc_pr.append(shd)


def clear_paragraph(paragraph):
    """清空段落的所有 run。"""
    p = paragraph._element
    for child in list(p):
        if child.tag != qn('w:pPr'):
            p.remove(child)


def add_inline_runs(paragraph, text: str, base_size: float = 12.0, base_bold: bool = False):
    """把一段富文本（含 **bold**、`code`、$math$）拆成 run 写入段落。"""
    # 先替换块级公式（不应在此出现）
    text = RE_BLOCK_MATH.sub(lambda m: f"[公式] {m.group(1).strip()}", text)

    # 用一个综合占位策略：按匹配位置切分
    # 顺序：行内公式 → 代码 → 粗体 → 链接
    # 为避免冲突，我们逐个替换成带边界的 token，再统一处理
    tokens: list[tuple[str, dict]] = []  # (text, props)
    # 简化：直接递归处理

    # ---- 行内数学 ----
    if '$' in text:
        parts = RE_INLINE_MATH.split(text)
        # split 结果：[before, math, after_before, math2, ...]
        i = 0
        buf = ''
        while i < len(parts):
            if i % 2 == 0:
                buf += parts[i]
            else:
                if buf:
                    tokens.append((buf, {}))
                    buf = ''
                tokens.append((f'${parts[i]}$', {'italic': True, 'en': 'Cambria Math'}))
            i += 1
        if buf:
            tokens.append((buf, {}))
    else:
        tokens.append((text, {}))

    # ---- 粗体 & 代码 ----
    new_tokens: list[tuple[str, dict]] = []
    for txt, props in tokens:
        if not txt:
            continue
        # 先处理代码 `...`
        code_parts = RE_CODE.split(txt)
        # 偶数位普通文本，奇数位代码
        i = 0
        buf = ''
        while i < len(code_parts):
            if i % 2 == 0:
                buf += code_parts[i]
            else:
                if buf:
                    # 对 buf 再做粗体切分
                    for bt, bp in _split_by_bold(buf):
                        merged_props = dict(props)
                        merged_props.update(bp)
                        new_tokens.append((bt, merged_props))
                    buf = ''
                new_tokens.append((f'`{code_parts[i]}`', dict(props, en='Consolas')))
            i += 1
        if buf:
            for bt, bp in _split_by_bold(buf):
                merged_props = dict(props)
                merged_props.update(bp)
                new_tokens.append((bt, merged_props))
    tokens = new_tokens

    # ---- 链接 ----
    new_tokens = []
    for txt, props in tokens:
        if not txt:
            continue
        link_parts = RE_LINK.split(txt)
        i = 0
        buf = ''
        while i < len(link_parts):
            if i % 2 == 0:
                buf += link_parts[i]
            else:
                if buf:
                    new_tokens.append((buf, props))
                    buf = ''
                link_text = link_parts[i]
                # link_parts[i+1] 是 URL
                new_tokens.append((link_text, dict(props, underline=True, color='1F4E79')))
                i += 1  # 跳过 URL
            i += 1
        if buf:
            new_tokens.append((buf, props))
    tokens = new_tokens

    # ---- 写入段落 ----
    for txt, props in tokens:
        if not txt:
            continue
        run = paragraph.add_run(txt)
        set_run_font(
            run,
            cn='Microsoft YaHei',
            en=props.get('en', 'Cambria'),
            size_pt=props.get('size', base_size),
            bold=props.get('bold', base_bold),
            italic=props.get('italic', False),
        )
        if props.get('underline'):
            run.underline = True
        if props.get('color'):
            run.font.color.rgb = RGBColor.from_string(props['color'])


def _split_by_bold(text: str) -> list[tuple[str, dict]]:
    """把文本按 **bold** 切分，返回 [(text, props), ...]。"""
    if '**' not in text:
        return [(text, {})]
    parts = RE_BOLD.split(text)
    result = []
    i = 0
    while i < len(parts):
        if i % 2 == 0:
            if parts[i]:
                result.append((parts[i], {}))
        else:
            result.append((parts[i], {'bold': True}))
        i += 1
    return result


def parse_table(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    """从 start 开始解析 markdown 表格，返回 (矩阵, 下一行索引)。"""
    rows: list[list[str]] = []
    i = start
    # 第一行表头
    m = RE_TABLE_ROW.match(lines[i])
    if not m:
        return [], start
    header = [c.strip() for c in m.group(1).split('|')]
    rows.append(header)
    i += 1
    # 跳过分隔行
    if i < len(lines) and RE_TABLE_SEP.match(lines[i]):
        i += 1
    # 数据行
    while i < len(lines):
        m = RE_TABLE_ROW.match(lines[i])
        if not m:
            break
        row = [c.strip() for c in m.group(1).split('|')]
        rows.append(row)
        i += 1
    return rows, i


def add_table(doc: Document, matrix: list[list[str]]):
    """向文档添加一个 Word 表格。"""
    if not matrix:
        return
    n_rows = len(matrix)
    n_cols = max(len(r) for r in matrix)
    table = doc.add_table(rows=n_rows, cols=n_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # 表头浅灰
    for ci in range(n_cols):
        cell = table.rows[0].cells[ci]
        cell.text = ''
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if ci < len(matrix[0]):
            add_inline_runs(p, matrix[0][ci], base_size=10.5, base_bold=True)
        set_cell_shading(cell, 'D9D9D9')
    # 数据行
    for ri in range(1, n_rows):
        for ci in range(n_cols):
            cell = table.rows[ri].cells[ci]
            cell.text = ''
            p = cell.paragraphs[0]
            if ci < len(matrix[ri]):
                add_inline_runs(p, matrix[ri][ci], base_size=10.5)
    # 整体表框
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{edge}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), '4')
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), '000000')
        borders.append(el)
    tblPr.append(borders)


# ---------------------------------------------------------------------------
# 主转换
# ---------------------------------------------------------------------------
def convert(md_path: Path, out_path: Path):
    md = md_path.read_text(encoding='utf-8')
    # 先把块级公式单独拿出来（防止后续正则被 $ 干扰）
    # 简化：块级公式保持原样文本，加 [公式] 标记
    def replace_block_math(m):
        content = m.group(1).strip()
        return f"\n[块级公式]\n{content}\n[/块级公式]\n"
    md = RE_BLOCK_MATH.sub(replace_block_math, md)

    lines = md.split('\n')

    doc = Document()
    # 页面：A4，上下左右 2.54 cm
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.17)
    section.right_margin = Cm(3.17)

    # 基准样式
    normal = doc.styles['Normal']
    normal.font.name = 'Cambria'
    normal.font.size = Pt(12)
    normal._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # 图片基准路径：md 文件所在目录
    base_dir = md_path.parent

    # 标题字号映射
    heading_size = {1: 18, 2: 15, 3: 13, 4: 12, 5: 12, 6: 12}

    i = 0
    in_block_math = False
    block_math_buf: list[str] = []

    while i < len(lines):
        line = lines[i]

        # ---- 块级公式状态 ----
        if in_block_math:
            if line.strip() == '[/块级公式]':
                # 写入块级公式段落（居中、斜体）
                formula_text = '\n'.join(block_math_buf).strip()
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_before = Pt(6)
                p.paragraph_format.space_after = Pt(6)
                run = p.add_run(formula_text)
                run.font.name = 'Cambria Math'
                run.font.size = Pt(11)
                run.italic = True
                rPr = run._element.get_or_add_rPr()
                rFonts = rPr.find(qn('w:rFonts'))
                if rFonts is None:
                    rFonts = OxmlElement('w:rFonts')
                    rPr.insert(0, rFonts)
                rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
                in_block_math = False
                block_math_buf = []
            elif line.strip() == '[块级公式]':
                pass  # 忽略重复开始标记
            else:
                block_math_buf.append(line)
            i += 1
            continue

        if line.strip() == '[块级公式]':
            in_block_math = True
            block_math_buf = []
            i += 1
            continue

        # ---- 跳过空行 ----
        if not line.strip():
            i += 1
            continue

        # ---- 水平线 ----
        if RE_HR.match(line):
            p = doc.add_paragraph()
            pPr = p._element.get_or_add_pPr()
            pBdr = OxmlElement('w:pBdr')
            bottom = OxmlElement('w:bottom')
            bottom.set(qn('w:val'), 'single')
            bottom.set(qn('w:sz'), '8')
            bottom.set(qn('w:space'), '1')
            bottom.set(qn('w:color'), '888888')
            pBdr.append(bottom)
            pPr.append(pBdr)
            i += 1
            continue

        # ---- 图片（整行图片）----
        img_match = RE_IMAGE.fullmatch(line.strip())
        if img_match:
            alt, rel_path = img_match.groups()
            img_path = (base_dir / rel_path).resolve()
            if img_path.exists():
                try:
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p.add_run()
                    # 页面宽度 ~ 14.66 cm（21 - 3.17*2），90%
                    run.add_picture(str(img_path), width=Cm(13.2))
                    # 图注
                    if alt:
                        cap = doc.add_paragraph()
                        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        cap.paragraph_format.space_after = Pt(12)
                        cap_run = cap.add_run(alt)
                        set_run_font(cap_run, size_pt=10.5, italic=True)
                except Exception as e:
                    p = doc.add_paragraph()
                    run = p.add_run(f'[图片插入失败: {rel_path} — {e}]')
                    set_run_font(run, size_pt=10)
            else:
                p = doc.add_paragraph()
                run = p.add_run(f'[图片未找到: {img_path}]')
                set_run_font(run, size_pt=10, italic=True, color='FF0000')
            i += 1
            continue

        # ---- 表格 ----
        if RE_TABLE_ROW.match(line) and i + 1 < len(lines) and RE_TABLE_SEP.match(lines[i + 1]):
            matrix, i = parse_table(lines, i)
            add_table(doc, matrix)
            # 表格后空一行
            doc.add_paragraph()
            continue

        # ---- 标题 ----
        hm = RE_HEADING.match(line)
        if hm:
            level = len(hm.group(1))
            text = hm.group(2).strip()
            # 用 add_heading 让 Word 导航窗格有大纲
            # python-docx 只内置 Heading 1~9，映射 level=1 → 'Heading 1' ...
            style_name = f'Heading {level}' if level <= 9 else 'Heading 9'
            # 先尝试用 Word 内置标题样式
            try:
                p = doc.add_heading(level=level)
            except Exception:
                p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(12 if level <= 2 else 6)
            p.paragraph_format.space_after = Pt(6)
            # 清掉默认样式带的 run，手动写入含富文本的 run
            clear_paragraph(p)
            clean_text = RE_BOLD.sub(r'\1', text)
            add_inline_runs(p, clean_text, base_size=heading_size[level], base_bold=True)
            # 对 paragraph 的 pPr 设置 outline 级别（确保 Word 导航窗格显示）
            pPr = p._element.get_or_add_pPr()
            outlineLvl = OxmlElement('w:outlineLvl')
            outlineLvl.set(qn('w:val'), str(max(0, level - 1)))  # Heading1 = outlineLevel 0
            pPr.append(outlineLvl)
            i += 1
            continue

        # ---- 无序列表 ----
        ul = RE_UL.match(line)
        if ul:
            indent = len(ul.group(1))
            text = ul.group(2)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.75 + indent * 0.5)
            p.paragraph_format.first_line_indent = Cm(-0.5)
            run = p.add_run('• ')
            set_run_font(run, size_pt=12)
            add_inline_runs(p, text, base_size=12)
            i += 1
            continue

        # ---- 有序列表 ----
        ol = RE_OL.match(line)
        if ol:
            indent = len(ol.group(1))
            num = ol.group(2)
            text = ol.group(3)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.75 + indent * 0.5)
            p.paragraph_format.first_line_indent = Cm(-0.6)
            run = p.add_run(f'{num}. ')
            set_run_font(run, size_pt=12)
            add_inline_runs(p, text, base_size=12)
            i += 1
            continue

        # ---- 普通段落 ----
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0.74)  # 2 个中文字符
        p.paragraph_format.line_spacing = 1.5
        # 行内图片（段落中嵌入）
        # 先找有没有 ![xxx](path) 行内图（本例没有，但以防万一）
        def inline_image_replace(m):
            alt, rel = m.groups()
            img_path = (base_dir / rel).resolve()
            if img_path.exists():
                try:
                    ir = p.add_run()
                    ir.add_picture(str(img_path), height=Pt(144))
                except Exception:
                    pass
                return ''
            return m.group(0)
        text = RE_IMAGE.sub(inline_image_replace, line)
        add_inline_runs(p, text, base_size=12)
        i += 1

    # 保存
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    print(f'✅ 已生成 Word：{out_path}')
    print(f'   大小：{out_path.stat().st_size / 1024:.1f} KB')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('md', nargs='?', default='docs/modeling/建模论文-正文.md')
    parser.add_argument('-o', '--output', default=None)
    args = parser.parse_args()

    md_path = Path(args.md).resolve()
    if not md_path.exists():
        print(f'❌ 找不到文件：{md_path}', file=sys.stderr)
        sys.exit(1)

    if args.output:
        out_path = Path(args.output).resolve()
    else:
        out_path = md_path.with_suffix('.docx')

    convert(md_path, out_path)


if __name__ == '__main__':
    main()
