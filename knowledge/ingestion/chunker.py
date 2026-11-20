import re
from uuid import uuid4

from .models import DocumentChunk

_HEADING = re.compile(r"^(#{1,6})[ \t]+(\S.*?)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
# Python/shell 注释在 PDF 转写文本里与 Markdown 一级标题同形（"# xxx"），
# 含这些字符的 "#" 行按代码处理，不进标题路径。
_CODEISH_H1 = re.compile(r"[()=;{}]")


class TextChunker:
    """Markdown 结构感知切块。

    - 结构完整的 Markdown（有标题层级）：按"标题路径 + 段落/代码块"组织，
      不在段落中间拦腰切断，且每块带文档标题与小节路径前缀，
      让 BM25/向量都能拿到主题上下文。
    - 只有一个标题的文档（如 PDF 转写稿）：定长切片 + 文档标题前缀。
    - 无标题的普通文本（如 catalog 故障条目）：保持原有定长 + 重叠切片。
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ):
        if chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap 必须小于 chunk_size"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(
        self,
        document_id: str,
        content: str,
        source: str = "",
        version: str = "latest",
    ) -> list[DocumentChunk]:

        content = content.strip()

        if not content:
            return []

        title = self._document_title(content, source)
        units = self._markdown_units(content)

        if units is None:
            # 无标题：纯定长切片，行为与旧实现一致（不加任何前缀）
            pieces = self._split_fixed(content, self.chunk_size)
            return self._to_chunks(document_id, pieces, source, version)

        if not units:
            # 只有标题、没有可靠层级：定长切片，但补文档标题上下文
            prefix = self._prefix(title, "")
            size = max(self.chunk_size - len(prefix), 1)
            pieces = self._split_fixed(content, size, prefix)
            return self._to_chunks(document_id, pieces, source, version)

        pieces = self._pack_units(units, title)
        return self._to_chunks(document_id, pieces, source, version)

    # ------------------------------------------------------------------
    # 通用：定长切片（普通文本，或超长段落的兜底）
    # ------------------------------------------------------------------

    def _split_fixed(self, content: str, size: int, prefix: str = "") -> list[str]:
        size = max(size, 1)
        # 前缀占用额度后 size 可能小于 overlap，直接缩小重叠，
        # 否则步长会退化成 1，产生大量重复碎块。
        overlap = min(self.chunk_overlap, size // 2)
        pieces = []
        start = 0
        while start < len(content):
            end = min(start + size, len(content))
            piece = content[start:end].strip()
            if piece:
                pieces.append(prefix + piece)
            if end >= len(content):
                break
            start = end - overlap
        return pieces

    @staticmethod
    def _to_chunks(document_id, pieces, source, version) -> list[DocumentChunk]:
        return [
            DocumentChunk(
                chunk_id=str(uuid4()),
                document_id=document_id,
                content=piece,
                chunk_index=index,
                source=source,
                version=version,
            )
            for index, piece in enumerate(pieces)
            if piece.strip()
        ]

    # ------------------------------------------------------------------
    # Markdown：解析为 (标题路径, 文本块) 单元
    # ------------------------------------------------------------------

    @staticmethod
    def _markdown_units(content: str):
        """解析 Markdown 单元。

        返回值：
        - ``None``：全文没有任何标题，走纯定长逻辑；
        - ``[]``：有标题但没有可用层级（如 PDF 转写稿只有标题），
          走"定长 + 标题前缀"逻辑；
        - 非空列表：``(标题路径, 文本块)``，走结构合并。
        """
        units: list[tuple[str, str]] = []
        stack: list[tuple[int, str]] = []
        buf: list[str] = []
        in_fence = False
        heading_count = 0
        has_sub_heading = False

        def path() -> str:
            return " / ".join(text for _, text in stack)

        def flush():
            if not buf:
                return
            text = "\n".join(buf).strip()
            buf.clear()
            if text:
                units.append((path(), text))

        for line in content.split("\n"):
            if _FENCE.match(line):
                in_fence = not in_fence
                buf.append(line)
                continue

            heading = None if in_fence else _HEADING.match(line)
            if heading and len(heading.group(1)) == 1 and _CODEISH_H1.search(line):
                heading = None  # 代码注释，不是标题

            if heading:
                heading_count += 1
                if len(heading.group(1)) >= 2:
                    has_sub_heading = True
                flush()
                level = len(heading.group(1))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, heading.group(2).strip()))
                # 标题行保留在正文里：跨小节合并成块时不丢结构信息
                buf.append(line)
                continue

            if not line.strip() and not in_fence:
                flush()
                continue

            buf.append(line)

        flush()
        if heading_count == 0:
            return None
        if heading_count < 2 or not has_sub_heading:
            return []
        return units

    @staticmethod
    def _document_title(content: str, source: str) -> str:
        for line in content.split("\n"):
            match = _HEADING.match(line)
            if match and len(match.group(1)) == 1 and not _CODEISH_H1.search(line):
                return match.group(2).strip()
        if source:
            return source.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return ""

    def _prefix(self, title: str, path: str) -> str:
        # 前缀只提供主题上下文：默认不超过 120 字，
        # 且最多占切块预算的 1/3，避免小 chunk_size 下挤占全部正文。
        text = title if not path or path == title else f"{title} / {path}"
        text = text.strip()
        limit = min(120, self.chunk_size // 3)
        if not text or limit <= 0:
            return ""
        return f"【{text[:limit]}】\n"

    def _pack_units(self, units, title: str) -> list[str]:
        pieces: list[str] = []
        buf: list[str] = []
        prefix = ""

        def flush():
            nonlocal buf, prefix
            if not buf:
                return
            body = "\n\n".join(buf).strip()
            buf = []
            if body:
                pieces.append(prefix + body)

        for path, text in units:
            if not buf:
                prefix = self._prefix(title, path)

            available = max(self.chunk_size - len(prefix), 1)
            current = sum(len(part) for part in buf) + 2 * max(len(buf) - 1, 0)

            if current and current + len(text) + 2 > available:
                flush()
                prefix = self._prefix(title, path)
                available = max(self.chunk_size - len(prefix), 1)

            if len(text) > available:
                # 单个单元就超长：先合并已有缓冲，再对该单元做定长兜底切片
                flush()
                prefix = self._prefix(title, path)
                available = max(self.chunk_size - len(prefix), 1)
                pieces.extend(self._split_fixed(text, available, prefix))
                buf = []
                continue

            buf.append(text)

        flush()
        return pieces
