"""统一证据封套（DS-01）。

作用：把 `app/schemas/` 下各 domain schema 的输出归一成 LLM 侧可比的证据包。
只做归一化，不改任何业务模块的语义。

三条硬规则（继承 recovery-contract 的纪律）：
1. 没有证据时必须显式声明 `gaps`，不能静默当作"一切正常"；
2. 坏证据（`quality != ok`）不得标成直接观测（`derivation == observed`）；
3. 给了 `rejection_reason` 就必须把 `quality` 降为非 ok。

`digest` 直接复用 `agent.recovery_contracts.models` 的 `object_digest`，
算法只有一份，不在这里重写。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# 生产部署和 pytest 都必须能 import agent —— 仓库根在 ai-service/ 之上 3 层。
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from agent.recovery_contracts.models import object_digest  # noqa: E402

EvidenceKind = Literal["metric", "topology", "log", "trace", "vision", "memory", "knowledge", "rule"]
Derivation = Literal["observed", "derived", "inferred"]
Quality = Literal["ok", "stale", "partial", "rejected"]

_NON_OK_QUALITIES = ("stale", "partial", "rejected")


def _iso_utc(value: str) -> str:
    """把 datetime 串归一成 UTC，避免同一时刻因时区写法不同算出两个 digest。"""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class EvidenceRef(BaseModel):
    """单条证据的引用头。内容本身仍在各模块的原始产物里，这里只记可比字段。"""

    evidence_id: str = Field(min_length=1)
    kind: EvidenceKind
    module: str = Field(min_length=1, description="产出该证据的 service，如 anomaly_detector")
    module_version: str = Field(min_length=1)
    captured_at: datetime
    derivation: Derivation = Field(
        description="证据的认知来源：observed=直接观测，derived=由观测推导，inferred=模型推断",
    )
    quality: Quality
    rejection_reason: str | None = None
    summary: str | None = Field(default=None, description="可选：给人看的证据摘要，不参与判定")

    @model_validator(mode="after")
    def _invariants(self) -> "EvidenceRef":
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at 必须带时区：朴素时间会让 digest 随机器时区漂移")
        if self.quality != "ok" and self.derivation == "observed":
            raise ValueError("quality 非 ok 的证据不得标记为 observed")
        if self.rejection_reason and self.quality not in _NON_OK_QUALITIES:
            raise ValueError("给了 rejection_reason 就必须把 quality 降为 rejected/stale/partial")
        return self


class EvidenceEnvelope(BaseModel):
    """一轮证据的封套。签发后不可改写：追加证据 = 新 `round` + 新 `digest`。"""

    run_id: str = Field(min_length=1)
    subject: str = Field(min_length=1, description="被观测对象：服务 / 节点 / 主机")
    round: int = Field(ge=0)
    refs: list[EvidenceRef] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list, description="显式缺口，如 no_trace_for_order_svc")
    provenance: dict[str, str] = Field(default_factory=dict)
    digest: str = Field(default="", description="canonical JSON SHA-256，由 seal() 写入")

    @model_validator(mode="after")
    def _invariants(self) -> "EvidenceEnvelope":
        if not self.refs and not self.gaps:
            raise ValueError("refs 为空时必须显式声明 gaps：没有证据不等于证据正常")
        if self.digest and self.digest != self.compute_digest():
            raise ValueError(
                "digest 与内容不一致：封套签发后不可改写，追加证据请开新 round",
            )
        return self

    def compute_digest(self) -> str:
        return object_digest(self._canonical_payload())

    def _canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        for ref in payload["refs"]:
            ref["captured_at"] = _iso_utc(ref["captured_at"])
        return payload

    @classmethod
    def seal(cls, **data: Any) -> "EvidenceEnvelope":
        """构造并签发：写入 digest，之后任何字段改动都会在下次校验时被拒。"""
        envelope = cls(digest="", **data)
        return envelope.model_copy(update={"digest": envelope.compute_digest()})
