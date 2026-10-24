# SmartOpsAgent 代码修复实验报告

| 项目 | 内容 |
|---|---|
| 实验名称 | SmartOpsAgent 智维AI智能运维系统 —— 功能修复 / 外部API鉴权注释与Mock占位 |
| 实验日期 | 2026-09-14 |
| 实验环境 | Windows 11（D 盘路径）、Python 3.14.3、pytest 9.1.1 |
| 项目根目录 | `D:\SmartOpsAgent` |
| 约束 | 目录结构 100% 保留，不新增/删除/移动文件夹，不删除业务逻辑 |

---

## 一、实验目的

1. 修复项目中会导致「直接运行报错」的代码问题（导入错误、变量未定义、依赖缺失、数据类成员描述符取值错误等）。
2. 将所有调用外部 API / 需要密钥、卡密、token、api-key、模型服务鉴权的代码**注释掉并增加 Mock 占位返回**，保证缺少密钥时程序不崩溃。
3. 兼容 Windows 环境。
4. 补全 `.env.example`，新增 Windows `.bat` 一键启动脚本。
5. 保证 `tests/` 目录下 pytest 可执行。

---

## 二、修改文件清单（共 16 个）

| # | 文件路径 | 问题类型 | 修复方式 |
|---|---|---|---|
| 1 | `agent/sdk/skill.py` | 导入错误（Skill 类缺失） | 重写为 Skill 数据类 |
| 2 | `agent/sdk/manifest.py` | 依赖缺失（yaml 硬导入） | 改为懒加载 |
| 3 | `agent/sdk/events.py` | 导入错误（AGENT_EVENT 未定义） | 改为 AgentEvent |
| 4 | `ai-service/app/services/llm.py` | 外部 API（Ollama） | 注释 + Mock |
| 5 | `knowledge/embedding/__init__.py` | 依赖缺失（在线下载模型） | 延迟导入 |
| 6 | `knowledge/embedding/sentence_transformer.py` | 外部模型服务 | 注释 + Mock |
| 7 | `knowledge/ocr/__init__.py` | 依赖缺失（pytesseract/PIL） | 延迟导入 |
| 8 | `knowledge/ocr/tesseract.py` | 外部 OCR 引擎 | 注释 + Mock |
| 9 | `knowledge/document-parser/base.py` | 导入错误 | 相对导入 |
| 10 | `knowledge/document-parser/__init__.py` | 导入错误（__getattr__ 抛异常） | 正常导出 |
| 11 | `knowledge/document-parser/pdf_parser.py` | 依赖缺失（pypdf） | 延迟导入 |
| 12 | `knowledge/ingestion/pipeline.py` | 导入错误（连字符目录） | importlib 加载 |
| 13 | `knowledge/evaluation/__init__.py` | 导入错误 | 删除错误行 |
| 14 | `tests/conftest.py` | 运行报错（slots 描述符） | 去掉 slots=True |
| 15 | `.env.example` | 配置缺失 | 补全变量 |
| 16 | `scripts/windows/start-dev.bat` | 缺少启动脚本 | 新增 bat |

---

## 三、逐文件「修改前 → 修改后」变化

### 1. `agent/sdk/skill.py`

**问题**：该文件内容被误写成了 `Plugin` 类（与 `plugin.py` 重复），导致 `from agent.sdk.skill import Skill` 全项目崩溃，pytest 无法收集用例。

**修改前**（关键片段）：
```python
from abc import ABC

from agent.sdk.manifest import PluginManifest


class Plugin(ABC):
    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest
    # ... 无 Skill 类
```

**修改后**（关键片段）：
```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    name: str
    description: str = ""
    version: str = "1.0.0"
    path: str | Path | None = None
    tags: list[str] = field(default_factory=list)
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches(self, query: str) -> bool:
        query = (query or "").strip().lower()
        if not query:
            return True
        haystack = " ".join([self.name, self.description, *self.tags]).lower()
        return query in haystack
```

---

### 2. `agent/sdk/manifest.py`

**问题**：模块级 `import yaml`，未安装 PyYAML 时导致 `agent.sdk` 整体导入失败。

**修改前**：
```python
from typing import Any

import yaml          # <- 硬依赖

from agent.policies.risk import RiskLevel
```

**修改后**：
```python
from typing import Any

from agent.policies.risk import RiskLevel
```
并在 `from_yaml` 内懒加载：
```python
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "解析 Manifest 需要安装 PyYAML：pip install pyyaml"
            ) from exc
```

---

### 3. `agent/sdk/events.py`

**问题**：导入了不存在的 `AGENT_EVENT`（实际类名为 `AgentEvent`）。

**修改前**：
```python
from agent.kernel.event.events import (
    AGENT_EVENT,
)

__all__ = ["AGENT_EVENT"]
```

**修改后**：
```python
from agent.kernel.event.events import (
    AgentEvent,
    PLUGIN_MOUNTED,
    PLUGIN_UNMOUNTED,
    SKILL_LOADED,
    SKILL_UNLOADED,
    TOOL_BEFORE_CALL,
    TOOL_AFTER_CALL,
    EXECUTION_STARTED,
    EXECUTION_FINISHED,
)

__all__ = [
    "AgentEvent", "PLUGIN_MOUNTED", "PLUGIN_UNMOUNTED",
    "SKILL_LOADED", "SKILL_UNLOADED", "TOOL_BEFORE_CALL",
    "TOOL_AFTER_CALL", "EXECUTION_STARTED", "EXECUTION_FINISHED",
]
```

---

### 4. `ai-service/app/services/llm.py`

**问题**：`_ollama_generate` 直接调用外部 Ollama HTTP API（模型服务鉴权）。

**修改前**（关键片段）：
```python
        try:
            import httpx
        except ImportError as exc:
            raise LLMException("未安装 httpx") from exc

        payload = {"model": settings.llm_model, "prompt": prompt, "stream": False}
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            response = await client.post(
                f"{settings.llm_base_url}/api/generate", json=payload,
            )
        if response.status_code != 200:
            raise LLMException("Ollama 调用失败：" f"{response.status_code}")
        data = response.json()
        return data.get("response", "")
```

**修改后**：
```python
        # 保留请求参数构造骨架，后续恢复密钥/服务地址即可直接使用。
        payload = {"model": settings.llm_model, "prompt": prompt, "stream": False}
        if system_prompt:
            payload["system"] = system_prompt

        # 【此处为外部 API/卡密调用，已临时注释，后续填入密钥即可恢复】
        # try:
        #     import httpx
        # except ImportError as exc:
        #     raise LLMException("未安装 httpx") from exc
        # async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        #     response = await client.post(
        #         f"{settings.llm_base_url}/api/generate", json=payload,
        #     )
        # if response.status_code != 200:
        #     raise LLMException("Ollama 调用失败：" f"{response.status_code}")
        # data = response.json()
        # return data.get("response", "")

        # 模拟占位返回：避免缺少 Ollama 服务时程序崩溃。
        return (
            "（Ollama 模拟回答）\n\n"
            "当前 LLM Provider 为 ollama，外部模型服务调用已临时注释。\n"
            f"用户问题：{prompt}"
        )
```

---

### 5. `knowledge/embedding/__init__.py`

**问题**：`SentenceTransformerEmbedding` 在导入时即触发在线下载大模型。

**修改前**：
```python
from .base import EmbeddingModel
from .hash_embedding import HashEmbedding
from .sentence_transformer import SentenceTransformerEmbedding   # <- 立即导入

__all__ = ["EmbeddingModel", "HashEmbedding", "SentenceTransformerEmbedding"]
```

**修改后**：
```python
from .base import EmbeddingModel
from .hash_embedding import HashEmbedding

__all__ = ["EmbeddingModel", "HashEmbedding", "SentenceTransformerEmbedding"]


def __getattr__(name: str):
    if name == "SentenceTransformerEmbedding":
        from .sentence_transformer import SentenceTransformerEmbedding
        return SentenceTransformerEmbedding
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

---

### 6. `knowledge/embedding/sentence_transformer.py`

**问题**：外部模型服务调用（下载预训练模型）。

**修改前**：
```python
from sentence_transformers import SentenceTransformer

class SentenceTransformerEmbedding:
    def __init__(self, model_name: str):
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()

    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()
```

**修改后**：
```python
from .hash_embedding import HashEmbedding

class SentenceTransformerEmbedding:
    def __init__(self, model_name: str):
        self.model_name = model_name
        # 【此处为外部模型服务调用，已临时注释，后续填入密钥即可恢复】
        # from sentence_transformers import SentenceTransformer
        # self.model = SentenceTransformer(model_name)
        self._fallback = HashEmbedding(dimension=384)

    def encode(self, texts: list[str]) -> list[list[float]]:
        # 【此处为外部模型服务调用，已临时注释，后续填入密钥即可恢复】
        # vectors = self.model.encode(texts, normalize_embeddings=True)
        # return vectors.tolist()
        return self._fallback.encode(texts)

    def dimension(self) -> int:
        return self._fallback.dimension()
```

---

### 7. `knowledge/ocr/__init__.py`

**问题**：`TesseractOCR` 在导入时即要求 pytesseract/Pillow 与本机 Tesseract。

**修改前**：
```python
from .base import OCRService
from .noop import NoopOCR
from .tesseract import TesseractOCR   # <- 立即导入

__all__ = ["OCRService", "NoopOCR", "TesseractOCR"]
```

**修改后**：
```python
from .base import OCRService
from .noop import NoopOCR

__all__ = ["OCRService", "NoopOCR", "TesseractOCR"]


def __getattr__(name: str):
    if name == "TesseractOCR":
        from .tesseract import TesseractOCR
        return TesseractOCR
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

---

### 8. `knowledge/ocr/tesseract.py`

**问题**：外部 OCR 引擎调用（pytesseract + PIL）。

**修改前**：
```python
import pytesseract
from PIL import Image

class TesseractOCR:
    def __init__(self, lang: str = "chi_sim+eng"):
        self.lang = lang

    def extract_text(self, image_path: str) -> str:
        image = Image.open(image_path)
        return pytesseract.image_to_string(image, lang=self.lang)
```

**修改后**：
```python
class TesseractOCR:
    def __init__(self, lang: str = "chi_sim+eng"):
        self.lang = lang

    def extract_text(self, image_path: str) -> str:
        # 【此处为外部 OCR 引擎调用，已临时注释，后续填入密钥即可恢复】
        # import pytesseract
        # from PIL import Image
        # image = Image.open(image_path)
        # return pytesseract.image_to_string(image, lang=self.lang)

        # 模拟占位返回：避免缺少 OCR 引擎时程序崩溃。
        return (
            f"[OCR 模拟结果] 未启用真实 OCR 引擎，"
            f"图片路径：{image_path}"
        )
```

---

### 9. `knowledge/document-parser/base.py`

**问题**：绝对导入 `from models import` 在包内无法解析。

**修改前**：
```python
from models import ParsedDocument
```

**修改后**：
```python
from .models import ParsedDocument
```

---

### 10. `knowledge/document-parser/__init__.py`

**问题**：`__getattr__` 对任意属性都抛 `AttributeError`，包无法使用。

**修改前**（关键片段）：
```python
def __getattr__(name: str):
    raise AttributeError(
        f"module 'document-parser' has no attribute {name!r}"
    )
```

**修改后**：
```python
from .base import DocumentParser
from .models import ParsedDocument
from .text_parser import TextParser
from .markdown_parser import MarkdownParser
from .pdf_parser import PdfParser
from .parser_factory import ParserFactory

__all__ = [
    "DocumentParser", "ParsedDocument", "TextParser",
    "MarkdownParser", "PdfParser", "ParserFactory",
]
```

---

### 11. `knowledge/document-parser/pdf_parser.py`

**问题**：模块级 `from pypdf import PdfReader`，缺 pypdf 时拖垮整个包。

**修改前**：
```python
from pypdf import PdfReader

from .base import DocumentParser
from .models import ParsedDocument
```

**修改后**：
```python
from .base import DocumentParser
from .models import ParsedDocument

# 在 parse() 内延迟导入：
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError("解析 PDF 需要安装 pypdf：pip install pypdf") from exc
```

---

### 12. `knowledge/ingestion/pipeline.py`

**问题**：`from document_parser.parser_factory import ParserFactory`，但目录名是 `document-parser`（含连字符），无法作为标准模块导入。

**修改前**：
```python
from document_parser.parser_factory import ParserFactory
from .chunker import TextChunker
from .metadata import enrich_chunk

class IngestionPipeline:
    def __init__(self, parser_factory: ParserFactory, chunker: TextChunker):
        self.parser_factory = parser_factory
        self.chunker = chunker
```

**修改后**：
```python
import importlib.util
import sys
from pathlib import Path

from .chunker import TextChunker
from .metadata import enrich_chunk


def _load_parser_factory():
    package_name = "knowledge.document_parser"
    module = sys.modules.get(package_name)
    if module is not None:
        return module.ParserFactory

    knowledge_dir = Path(__file__).resolve().parent.parent
    parser_dir = knowledge_dir / "document-parser"

    spec = importlib.util.spec_from_file_location(
        package_name,
        parser_dir / "__init__.py",
        submodule_search_locations=[str(parser_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError("无法加载 document-parser 包")

    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module.ParserFactory


class IngestionPipeline:
    def __init__(self, parser_factory=None, chunker: TextChunker | None = None):
        self.parser_factory = parser_factory or _load_parser_factory()
        self.chunker = chunker or TextChunker()
```

---

### 13. `knowledge/evaluation/__init__.py`

**问题**：文件顶部有两行错误的绝对导入（且与下方正确相对导入重复）。

**修改前**：
```python
from evaluation import EvaluationCase
from evaluation import RetrievalEvaluator


"""
SmartOpsAgent Knowledge Evaluation Module.
...
"""
from .models import EvaluationCase
from .evaluator import RetrievalEvaluator
```

**修改后**：
```python
"""
SmartOpsAgent Knowledge Evaluation Module.
...
"""
from .models import EvaluationCase
from .evaluator import RetrievalEvaluator
```

---

### 14. `tests/conftest.py`

**问题**：`@dataclass(slots=True)` 下，`cls.mysql_port` 等返回的是成员描述符（`<member 'mysql_port' of 'TestConfig' objects>`），`str()` 后传给 `int()` 直接抛 `ValueError`，导致全部 api/e2e/integration 用例 error。

**修改前**：
```python
@dataclass(slots=True)
class TestConfig:
    mysql_port: int = 3306
    ...
```

**修改后**：
```python
@dataclass
class TestConfig:
    mysql_port: int = 3306
    ...
```

---

### 15. `.env.example`

**问题**：仅 11 个变量，缺少 LLM/Knowledge/前端/测试等大量环境变量。

**修改前**（仅含）：
```
MYSQL_USERNAME / MYSQL_PASSWORD / REDIS_HOST / REDIS_PORT / REDIS_DATABASE /
REDIS_PASSWORD / SERVER_PORT / MYSQL_URL / AI_SERVICE_URL / OLLAMA_BASE_URL
```

**修改后**：补全为 9 大类、覆盖全部用到的变量（HOST/PORT/DEBUG、LLM_PROVIDER/MODEL/BASE_URL/API_KEY、KNOWLEDGE_SERVICE_URL、前端 VITE_API_BASE_URL、测试 SMARTOPS_* 系列等），密钥全部留空。

---

### 16. `scripts/windows/start-dev.bat`

**问题**：缺少 Windows 一键启动脚本（原仅有 PowerShell 版）。

**修改前**：不存在该文件。

**修改后**：新增批处理脚本，实现——自动定位项目根目录、首次运行自动生成 `.env`、环境检查、依次用 `start /D` 打开 Docker / Backend / AI Service / Frontend 四个独立窗口。

---

## 四、验证结果

| 验证项 | 命令 | 结果 |
|---|---|---|
| 主测试套件 | `python -m pytest tests -q` | **3 passed, 24 skipped, 0 errors** |
| AI Service 测试 | `cd ai-service && python -m pytest app/tests -q` | **7 passed** |
| 全量语法编译 | `python -m compileall agent knowledge ai-service/app tests` | 全部通过 |
| agent 包导入 | `import agent.sdk / agent.registry / agent.skills.local.loader` | 全部 OK |
| knowledge 导入 | `embedding / ocr / ingestion.pipeline` | 全部 OK |

> 说明：api / e2e / integration 用例在 Backend、MySQL、Redis、AI Service 未启动时按设计自动 `skip`；`3 passed` 为 `tests/agent/test_local_skill_loader.py` 中的 Skill 发现/加载/去重用例。

---

## 五、结论

1. 16 个文件已完成修复，目录结构未做任何增删移动，业务逻辑未删除。
2. 关键导入崩溃点（`Skill` 缺失、`AGENT_EVENT`、`from models`、连字符目录、`slots` 描述符）均已修复。
3. 外部 API / 模型 / OCR 调用已按要求「注释 + Mock 占位」，缺密钥可正常走完流程，填入密钥取消注释即可恢复真实调用。
4. `pytest` 可正常执行，无 error；`.env.example` 与 Windows 一键启动脚本已就绪。

## 六、后续恢复真实调用的方式

- **LLM**：`ai-service/app/services/llm.py` 取消注释 Ollama 请求块，并在 `.env` 填 `LLM_BASE_URL` / `LLM_API_KEY`。
- **Embedding**：`knowledge/embedding/sentence_transformer.py` 取消注释，安装 `sentence-transformers`。
- **OCR**：`knowledge/ocr/tesseract.py` 取消注释，安装 `pytesseract`/`Pillow` 并配置 Tesseract 引擎。
