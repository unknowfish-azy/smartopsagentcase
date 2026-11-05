"""从 reference 语料自动生成检索黄金集。

生成两类 query：

- ``verbatim``：保留文档标题原词，检验基础检索能力（词法友好）。
- ``paraphrase``：对标题做同义替换并套用口语模板，检验语义召回。

注意：自动生成的集合只能衡量"改写鲁棒性"，不能替代人工标注；
新增语料后重跑本脚本即可扩充集合。

用法：

    python -m knowledge.evaluation.build_golden_set
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REFERENCE_ROOT = Path(__file__).resolve().parent.parent / "reference" / "ops-knowledge-rag"
OUTPUT_PATH = Path(__file__).resolve().parent / "golden_set.json"

# 同义替换表：偏"书面标题用词" → "运维口语/近义表达"。
_SYNONYMS = [
    ("安装与配置", "搭建"),
    ("安装", "装"),
    ("配置", "设置"),
    ("部署", "上线"),
    ("基础", ""),
    ("管理", "维护"),
    ("操作", "使用"),
    ("原理", "机制"),
    ("启动", "开机"),
    ("停止", "关掉"),
    ("重启", "重新开启"),
    ("查看", "看一下"),
    ("修改", "改成"),
    ("删除", "删掉"),
    ("创建", "新建"),
    ("权限", "能不能访问"),
    ("端口", "哪个口"),
    ("日志", "记录"),
    ("进程", "程序"),
    ("磁盘", "硬盘"),
    ("网络", "上网"),
    ("连接", "连不上"),
    ("超时", "卡住"),
    ("故障处理", "出问题怎么办"),
    ("排障", "排查"),
]

_TEMPLATES = [
    "{topic} 一般怎么处理？",
    "线上遇到 {topic} 相关问题时，排查顺序是什么？",
    "同事问 {topic} 这块该怎么入手，怎么回答？",
    "{topic} 出了问题，第一步先看什么？",
]

_TITLE_NOISE = re.compile(
    r"^[一二三四五六七八九十\d]+[、.．)\s]+|[（(].*?[)）]|课程|课件|教案|第[一二三四五六七八九十\d]+[章节讲]"
)

# 封面、目录、任务背景这类没有检索价值的标题直接跳过。
_GENERIC_TITLES = {
    "",
    "任务背景",
    "封面目录与简介",
    "目录",
    "简介",
    "封面",
}

# 课件模板段落，几乎每篇都有，不适合作为"改写话题"（歧义大）。
_GENERIC_SECTIONS = (
    "基本信息",
    "培训目标",
    "知识目标",
    "能力目标",
    "教学目标",
    "任务背景",
    "任务执行清单",
    "实验环境",
    "文档规范",
    "课程",
    "小结",
    "总结",
    "目录",
    "参考文献",
    "在你开始之前",
    "前言",
    "附录",
    "实验一",
    "实验二",
)


def _clean_title(raw: str) -> str:
    title = _TITLE_NOISE.sub("", raw).strip(" -—:：")
    return title or raw.strip()


def _paraphrase(title: str) -> str:
    result = title
    for source_word, target_word in _SYNONYMS:
        if source_word in result:
            result = result.replace(source_word, target_word)
    result = re.sub(r"[，,。、/、]+", " ", result)
    return re.sub(r"\s+", " ", result).strip() or title


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return _clean_title(line[2:].strip())
    return ""


def _first_section(text: str) -> str:
    """取第一个有检索价值的二级小节标题，作为"正文话题"。"""
    for line in text.splitlines():
        if line.startswith("## "):
            section = _clean_title(line[3:].strip())
            if len(section) >= 4 and not any(
                word in section for word in _GENERIC_SECTIONS
            ):
                return section
    return ""


def build_cases(root: Path = REFERENCE_ROOT) -> list[dict]:
    cases: list[dict] = []
    seen: set[str] = set()

    for path in sorted(root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        title = _first_heading(text) or _clean_title(path.stem)
        if len(title) < 4 or title in _GENERIC_TITLES:
            continue

        source = f"reference/{path.relative_to(root)}"

        # 改写组尽量用正文小节话题，与标题词表形成语义差距。
        topic = _first_section(text) or title

        candidates = [
            (f"{title}怎么操作", "verbatim"),
            (
                _TEMPLATES[len(cases) % len(_TEMPLATES)].format(
                    topic=_paraphrase(topic)
                ),
                "paraphrase",
            ),
        ]

        for question, style in candidates:
            question = re.sub(r"\s+", " ", question).strip()
            if question in seen:
                continue
            seen.add(question)
            cases.append(
                {
                    "question": question,
                    "expected_sources": [source],
                    "style": style,
                    "version": "reference",
                }
            )

    return cases


def main() -> None:
    cases = build_cases()
    OUTPUT_PATH.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已生成 {len(cases)} 条评测用例 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
