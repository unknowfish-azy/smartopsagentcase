from dataclasses import dataclass, field


@dataclass
class EvaluationCase:

    question: str

    expected_chunk_ids: list[str] = field(default_factory=list)

    # 文档级判定：命中任意一个 source 即算相关。
    # 语料按文件摄入、chunk_id 每次启动都会重新生成，
    # 因此默认用稳定的 source 做判定。
    expected_sources: list[str] = field(default_factory=list)

    expected_answer: str = ""

    version: str = "latest"

    # verbatim = 保留原标题词；paraphrase = 同义改写，用于检验语义召回。
    style: str = "verbatim"
