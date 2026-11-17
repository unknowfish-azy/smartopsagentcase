# -*- coding: utf-8 -*-
"""把参考语料目录通过 /api/documents 热摄入运行中的知识服务（无需重启）。

幂等性（对应 docs/reports/项目知识库热摄入与检索验证-20261117.md §8）：
  `POST /api/documents` 本身不幂等——service.add_documents 对每个 chunk 直接
  `_chunks.append`，没有内容去重，同一文件重复提交会虚增语料。因此本脚本在
  客户端侧做幂等校验：
    1. document_id 由 knowledge.ingest_ids.reference_document_id 确定性派生，
       与启动扫描（server._seed_reference_corpus）共用同一口径；
    2. 摄入前先 GET /api/knowledge/{document_id}/chunks 探测是否已存在；
    3. 已存在 → 跳过；探针异常 → 也跳过（宁可少录，不可重复）；
    4. 仅对确实不存在的文件发起摄入，并显式带上同一个 document_id。

用法：
    python ingest_docker_corpus.py            # 默认子目录 Docker运维课
    python ingest_docker_corpus.py RH教材      # 指定子目录
    python ingest_docker_corpus.py ALL        # 全量：遍历 ops-knowledge-rag 全部子目录

重建索引后直接跑 `ALL`，应得到「新增 0 篇，跳过 N 篇」——这就是幂等生效的证据。
"""
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from knowledge.ingest_ids import reference_document_id  # noqa: E402

SUBDIR = sys.argv[1] if len(sys.argv) > 1 else "Docker运维课"
ROOT_BASE = pathlib.Path(__file__).resolve().parent / "reference" / "ops-knowledge-rag"

if SUBDIR.upper() == "ALL":
    ROOT = ROOT_BASE
    SOURCE_PREFIX = "reference"
else:
    ROOT = ROOT_BASE / SUBDIR
    SOURCE_PREFIX = f"reference/{SUBDIR}"

BASE = os.environ.get("KNOWLEDGE_SERVICE_URL", "http://127.0.0.1:8002").rstrip("/")
KEY = os.environ.get(
    "KNOWLEDGE_API_KEY", "local-dev-70869b4bfaac35d7a16feff0e732208a")
HEADERS = {"Content-Type": "application/json", "X-API-Key": KEY}


def existing_chunk_count(document_id: str) -> int:
    """查询该 document_id 已存在的 chunk 数。

    探针自身失败时向调用方抛异常：调用方据此跳过摄入，
    宁可不录也不能重复写入。
    """
    url = f"{BASE}/api/knowledge/{urllib.parse.quote(document_id)}/chunks"
    req = urllib.request.Request(url, headers={"X-API-Key": KEY})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return int(json.loads(resp.read().decode("utf-8")).get("count", 0))


def ingest(source: str, content: str, document_id: str) -> dict:
    body = json.dumps({
        "content": content,
        "source": source,
        "version": "reference",
        "document_id": document_id,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/documents", data=body, method="POST", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


added, skipped, failed = [], [], []
for path in sorted(ROOT.rglob("*.md")):
    name = path.relative_to(ROOT).as_posix()
    with open(path, encoding="utf-8", errors="ignore") as handle:
        content = handle.read()
    if not content.strip():
        continue

    source = f"{SOURCE_PREFIX}/{name}"
    document_id = reference_document_id(source, content)

    try:
        count = existing_chunk_count(document_id)
    except Exception as exc:  # noqa: BLE001 - 探针失败必须保守处理
        failed.append((name, f"幂等探针失败，已跳过以免重复写入：{exc}"))
        print(f"SKIP {name}: 探针失败，保守跳过（{exc}）")
        continue

    if count > 0:
        skipped.append(name)
        print(f"SKIP {name}: 已摄入（{count} chunks, id={document_id}）")
        continue

    try:
        resp = ingest(source, content, document_id)
        added.append(name)
        print(f"OK   {name} -> +{resp.get('added')} chunks, "
              f"total={resp.get('total_chunks')}, id={document_id}")
    except Exception as exc:  # noqa: BLE001 - 单篇失败不中断整批
        failed.append((name, str(exc)))
        print(f"FAIL {name}: {exc}")

print(f"\n完成：新增 {len(added)} 篇，跳过 {len(skipped)} 篇，失败 {len(failed)} 篇")
for name, reason in failed:
    print(f"  FAIL {name}: {reason}")
