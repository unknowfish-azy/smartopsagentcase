# -*- coding: utf-8 -*-
"""确定性 document_id 派生。

启动扫描（server._seed_reference_corpus）与热摄入脚本
（ingest_docker_corpus.py）必须共用同一口径，否则同一文件会得到两个
不同 ID，幂等校验失效、语料被重复写入。

生成规则：``ingest-`` + sha256(source + "\\n" + 内容) 前 16 位。
source 统一使用 POSIX 相对路径（``reference/<子目录>/<文件名>``），
内容先做 CRLF→LF 归一，避免跨平台哈希漂移。
"""
import hashlib

_PREFIX = "ingest-"


def reference_document_id(source: str, content: str) -> str:
    """按 source 与内容生成稳定的 document_id。"""
    normalized = content.replace("\r\n", "\n")
    digest = hashlib.sha256(
        (source + "\n" + normalized).encode("utf-8")).hexdigest()
    return _PREFIX + digest[:16]
