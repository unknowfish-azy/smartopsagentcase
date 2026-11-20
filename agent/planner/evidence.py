"""M1-1 / M1-2 证据融合层：把多路感知结果压成统一证据包。

ReAct 循环里四路感知工具（异常 / 根因 / 日志分类 / 案例检索）各自返回一份格式不同的
裸 JSON，直接回填给模型会让上下文迅速膨胀，也容易让模型把不同字段名记混。

EvidenceBundle 做两件事：

1. **归一**：每个工具的结果收敛为同一结构（source_tool / ok / model_status /
   score / top_k / summary），不管是正常返回、参数错误还是服务不可用，形态一致；
2. **压缩**：渲染成一段紧凑文本注入 Prompt，显式标注「缺失」的证据源，
   让模型知道哪一维没有证据、禁止编造。

设计边界：只做适配与降级标注，不解释、不决策，不改变任何工具语义。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# 三源证据编排涉及的证据工具（异常 + 根因 + 日志分类 + 案例检索）
EVIDENCE_TOOL_NAMES: tuple[str, ...] = (
    "nn.anomaly",
    "nn.rootcause",
    "nn.log_classify",
    "nn.retrieve",
)

# status 语义：
#   ok          服务正常返回且有有效结果
#   fallback    服务降级（如模型缺失走启发式），结果仍可用
#   unavailable 服务不可达 / 模型不可用
#   error       参数错误或执行失败
#   missing     本轮未调用该证据源
_STATUS_OK = "ok"
_STATUS_FALLBACK = "fallback"
_STATUS_UNAVAILABLE = "unavailable"
_STATUS_ERROR = "error"
_STATUS_MISSING = "missing"


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


@dataclass
class EvidenceItem:
    """单路证据的统一视图。"""

    source_tool: str
    ok: bool = False
    model_status: str = _STATUS_MISSING
    summary: str = ""
    score: float | None = None
    top_k: list[dict[str, Any]] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """降级（fallback）仍可用；不可达 / 参数错误 / 未调用不可用。"""

        return self.ok and self.model_status in {_STATUS_OK, _STATUS_FALLBACK}

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_tool": self.source_tool,
            "ok": self.ok,
            "model_status": self.model_status,
            "summary": self.summary,
            "score": self.score,
            "top_k": list(self.top_k),
        }


@dataclass
class EvidenceBundle:
    """多路证据的统一容器（按工具名覆盖写入，天然去重）。"""

    expected: tuple[str, ...] = EVIDENCE_TOOL_NAMES
    items: dict[str, EvidenceItem] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def add(self, source_tool: str, output: Any) -> EvidenceItem | None:
        """把某工具的一次返回归一后写入；非证据工具直接忽略。"""

        if source_tool not in self.expected:
            return None
        item = self._normalize(source_tool, output)
        self.items[source_tool] = item
        return item

    def missing(self) -> list[str]:
        """未拿到可用证据的源（未调用 / 不可达 / 报错）。"""

        return [name for name in self.expected if not self.items.get(name, EvidenceItem(name)).usable]

    def has_usable(self) -> bool:
        return any(item.usable for item in self.items.values())

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def render(self, max_chars: int = 1200) -> str:
        """渲染为紧凑文本，缺失源显式标注「禁止编造」。"""

        lines = ["【证据统一视图】（只列已获取的结构化证据，缺失维度不要编造）"]
        for name in self.expected:
            item = self.items.get(name)
            if item is None:
                lines.append(f"- {name}: 缺失（本轮未调用）——不要假设该维度结论")
                continue
            if not item.usable:
                reason = item.summary or item.model_status
                lines.append(f"- {name}: 缺失（{reason}）——不要假设该维度结论")
                continue
            status = "" if item.model_status == _STATUS_OK else f"[{item.model_status}]"
            lines.append(f"- {name}{status}: {item.summary}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "…（证据视图过长已截断）"
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": {name: item.to_dict() for name, item in self.items.items()},
            "missing": self.missing(),
        }

    # ------------------------------------------------------------------
    # 归一实现
    # ------------------------------------------------------------------

    def _normalize(self, source_tool: str, output: Any) -> EvidenceItem:
        payload = self._coerce_payload(output)
        if payload is None:
            return EvidenceItem(
                source_tool=source_tool,
                ok=False,
                model_status=_STATUS_ERROR,
                summary="返回内容无法解析",
            )

        if payload.get("ok") is False:
            status = payload.get("model_status")
            if status == _STATUS_UNAVAILABLE:
                detail = payload.get("error") or "感知服务不可用"
            else:
                detail = payload.get("error") or "工具执行失败"
            return EvidenceItem(
                source_tool=source_tool,
                ok=False,
                model_status=_STATUS_UNAVAILABLE if status == _STATUS_UNAVAILABLE else _STATUS_ERROR,
                summary=str(detail),
            )

        model_status = str(payload.get("model_status") or _STATUS_OK)
        normalizer = getattr(self, f"_normalize_{source_tool.replace('.', '_')}", None)
        if normalizer is None:
            return EvidenceItem(
                source_tool=source_tool,
                ok=True,
                model_status=model_status,
                summary="已返回结构化结果",
            )
        item = normalizer(payload)
        item.model_status = model_status if model_status in {_STATUS_OK, _STATUS_FALLBACK} else _STATUS_OK
        return item

    @staticmethod
    def _coerce_payload(output: Any) -> dict[str, Any] | None:
        if isinstance(output, dict):
            return output
        if isinstance(output, str):
            try:
                parsed = json.loads(output)
            except (TypeError, ValueError):
                return None
            return parsed if isinstance(parsed, dict) else None
        return None

    # --- 各工具专属归一 ------------------------------------------------

    @staticmethod
    def _normalize_nn_anomaly(payload: dict[str, Any]) -> EvidenceItem:
        results = [r for r in _as_list(payload.get("results")) if isinstance(r, dict)]
        peaks = [(r.get("metric"), _as_float(r.get("peak_score"))) for r in results]
        peaks = [(m, s) for m, s in peaks if s is not None]
        if not peaks:
            return EvidenceItem(
                source_tool="nn.anomaly", ok=True, summary="未返回异常结果（可能序列过短）"
            )
        metric, peak = max(peaks, key=lambda item: item[1] or 0.0)
        span_count = sum(int(r.get("span_count") or 0) for r in results)
        summary = f"指标 {metric or 'unknown'} 峰值异常分 {peak:.2f}，异常段 {span_count} 段"
        return EvidenceItem(
            source_tool="nn.anomaly",
            ok=True,
            summary=summary,
            score=peak,
            top_k=[
                {"metric": m, "peak_score": s}
                for m, s in sorted(peaks, key=lambda item: item[1] or 0.0, reverse=True)[:3]
            ],
        )

    @staticmethod
    def _normalize_nn_rootcause(payload: dict[str, Any]) -> EvidenceItem:
        candidates = [c for c in _as_list(payload.get("candidates")) if isinstance(c, dict)]
        if not candidates:
            return EvidenceItem(source_tool="nn.rootcause", ok=True, summary="未返回根因候选")
        top = candidates[0]
        score = _as_float(top.get("score"))
        top_k = [
            {
                "rank": c.get("rank"),
                "alert_id": c.get("alert_id"),
                "score": _as_float(c.get("score")),
                "server": c.get("server"),
                "metric": c.get("metric"),
            }
            for c in candidates[:3]
        ]
        score_text = f"{score:.2f}" if score is not None else "n/a"
        summary = f"Top1 根因 {top.get('alert_id')}（score {score_text}），共 {len(candidates)} 个候选"
        return EvidenceItem(
            source_tool="nn.rootcause", ok=True, summary=summary, score=score, top_k=top_k
        )

    @staticmethod
    def _normalize_nn_log_classify(payload: dict[str, Any]) -> EvidenceItem:
        total = int(payload.get("num_total") or 0)
        kept = int(payload.get("num_kept") or 0)
        distribution = payload.get("label_distribution") or {}
        if not isinstance(distribution, dict):
            distribution = {}
        ratio = (kept / total) if total else None
        dist_text = ", ".join(f"{k}={v}" for k, v in list(distribution.items())[:5]) or "无"
        summary = f"保留 {kept}/{total} 条非噪声日志，类别分布 {dist_text}"
        return EvidenceItem(
            source_tool="nn.log_classify",
            ok=True,
            summary=summary,
            score=ratio,
            top_k=[{"label": k, "count": v} for k, v in distribution.items()],
        )

    @staticmethod
    def _normalize_nn_retrieve(payload: dict[str, Any]) -> EvidenceItem:
        cases = [c for c in _as_list(payload.get("results") or payload.get("cases")) if isinstance(c, dict)]
        if not cases:
            return EvidenceItem(
                source_tool="nn.retrieve", ok=True, summary="未检索到相似历史案例"
            )
        top = cases[0]
        score = _as_float(top.get("score"))
        score_text = f"{score:.2f}" if score is not None else "n/a"
        summary = (
            f"命中 {len(cases)} 条历史案例，Top1 {top.get('category')}/{top.get('outcome')}"
            f"（score {score_text}）"
        )
        return EvidenceItem(
            source_tool="nn.retrieve",
            ok=True,
            summary=summary,
            score=score,
            top_k=[
                {
                    "incident_key": c.get("incident_key"),
                    "category": c.get("category"),
                    "outcome": c.get("outcome"),
                    "score": _as_float(c.get("score")),
                }
                for c in cases[:3]
            ],
        )


__all__ = [
    "EVIDENCE_TOOL_NAMES",
    "EvidenceBundle",
    "EvidenceItem",
]
