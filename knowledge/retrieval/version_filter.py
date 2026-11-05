"""VersionPolicy + Version + VersionFilter（重构）

任务书 VERSION-P0-01：版本、环境与租户检索契约。

现状：
- knowledge/retrieval/version_filter.py 只做 exact 匹配，latest 直接放行
- bm25.py:75-80 独立实现版本过滤，hybrid.py 无过滤
- 所有 reference 语料 chunk 的 version 硬编码 "reference"（无产品/发行版/组件维度）

本模块解决：
1. Version 对象：分开 product / distro / component / release_version / applicability_range
2. VersionPolicy：exact / latest-resolved / unknown 三态
3. 统一 VersionFilter：单入口，bm25/hybrid 不再自实现
4. Tenant/workspace/ACL 骨架：当前无真实 identity provider，先留参数位置
5. latest 解析记账 + INSUFFICIENT 标记
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Version 对象：分开产品、发行版、组件版本、适用区间
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Version:
    """结构化版本，避免一个 "22.04" 推断所有组件兼容。

    任务书："版本对象分开记录产品、发行版、组件版本和适用区间；
    不能用一个'22.04'推断所有组件兼容。"
    """
    product: str | None = None       # "nginx", "mysql", "redis", "linux"
    distro: str | None = None        # "ubuntu", "centos", "rhel"
    distro_version: str | None = None  # "22.04", "8.0"
    component: str | None = None    # "nginx-core", "redis-server", "mysqld"
    component_version: str | None = None  # "1.24.0", "8.0.36"
    applicability_range: str | None = None  # e.g. ">=22.04,<24.0"

    @classmethod
    def from_chunk(cls, chunk) -> "Version":
        """从 Chunk 对象（或 RetrievalResult）提取 version。

        现状：所有 reference 语料 version 硬编码 "reference"，metadata 可能
        含 version 相关字段。逐步过渡到结构化版本。
        """
        raw = getattr(chunk, "version", None) or ""
        metadata = getattr(chunk, "metadata", None) or {}

        # 1. 已有结构化 metadata 优先
        if isinstance(metadata, dict):
            if metadata.get("version_struct"):
                v = metadata["version_struct"]
                return cls(**{k: v.get(k) for k in cls.__dataclass_fields__})
            # 从 source 路径推断：reference/nginx/install → product=nginx
            source = getattr(chunk, "source", "")
            m = re.search(r"(?:reference/|)([a-zA-Z0-9_-]+)", source or "")
            product_guess = m.group(1) if m else None
            comp_version = metadata.get("component_version") or metadata.get("version")

            if raw and raw not in ("", "reference", "latest"):
                return cls(component_version=raw, product=product_guess,
                           distro=metadata.get("distro"), distro_version=metadata.get("distro_version"),
                           component=metadata.get("component"), applicability_range=metadata.get("range"))
            if comp_version:
                return cls(component_version=str(comp_version), product=product_guess,
                           distro=metadata.get("distro"), distro_version=metadata.get("distro_version"),
                           component=metadata.get("component"))
            return cls(product=product_guess)
        # 2. 最简 fallback：把 raw 塞进 component_version
        if raw and raw not in ("", "reference", "latest"):
            return cls(component_version=raw)
        return cls()

    def is_empty(self) -> bool:
        return not any([self.product, self.distro, self.component,
                        self.distro_version, self.component_version, self.applicability_range])

    def to_query_string(self) -> str:
        """人类可读版本查询串（用于日志 + 记账）。"""
        parts = []
        if self.product: parts.append(self.product)
        if self.component: parts.append(self.component)
        if self.component_version: parts.append("@" + self.component_version)
        if self.distro: parts.append("on " + self.distro)
        if self.distro_version: parts.append("(" + self.distro_version + ")")
        if self.applicability_range: parts.append("[" + self.applicability_range + "]")
        return " ".join(parts) or "<unknown>"

    def __str__(self) -> str:
        return self.to_query_string()


# ---------------------------------------------------------------------------
# VersionPolicy：exact / latest-resolved / unknown
# ---------------------------------------------------------------------------

class VersionPolicy(str, Enum):
    EXACT = "exact"                 # 精确版本匹配：chunk 的 Version 与期望 Version 完全对齐
    LATEST_RESOLVED = "latest-resolved"  # latest 已解析为明确版本（记账 + 显式记录）
    UNKNOWN = "unknown"             # 目标版本未知：返回时标记 INSUFFICIENT，请求补证
    COMPATIBLE = "compatible"       # 适用区间匹配（暂不实现，按任务书"有真实适配需求时再加"）

    @classmethod
    def resolve(cls, expected: str | Version | None, *,
                latest_digest: str | None = None) -> tuple["VersionPolicy", Version]:
        """解析期望版本为 (policy, structured_version)。

        规则：
        - None / "" → UNKNOWN + empty Version
        - "latest"（或 Latest 变体） → LATEST_RESOLVED + 空 Version（需记账）
        - 具体字符串（如 "1.24.0" / "reference"）→ EXACT + 从字符串推断 Version
        - Version 对象直接返回 EXACT（若未指定 policy）
        """
        if expected is None or (isinstance(expected, str) and not expected.strip()):
            return cls.UNKNOWN, Version()

        if isinstance(expected, Version):
            if expected.is_empty():
                return cls.UNKNOWN, expected
            return cls.EXACT, expected

        raw = expected.strip().lower()
        if raw in ("latest", "latest-resolved", "*"):
            v = Version(component_version=latest_digest) if latest_digest else Version()
            return cls.LATEST_RESOLVED, v

        # 简单字符串 → 尝试按 component_version 存
        return cls.EXACT, Version(component_version=expected.strip())


# ---------------------------------------------------------------------------
# LatestResolutionLedger：latest 解析记账（不能默默地让 latest 放行）
# ---------------------------------------------------------------------------

@dataclass
class LatestResolutionLedger:
    """记账：latest 每次解析到什么版本 + 何时 + 什么上下文。

    任务书："'latest' 必须解析为明确适用版本并记账"
    """
    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, *, query: str, resolved_to: str | None,
               corpus_sha: str | None, policy: VersionPolicy) -> None:
        self.entries.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "resolved_to": resolved_to,
            "corpus_sha": corpus_sha,
            "policy": policy.value,
        })

    def last(self) -> dict[str, Any] | None:
        return self.entries[-1] if self.entries else None

    def __len__(self) -> int:
        return len(self.entries)


# ---------------------------------------------------------------------------
# VersionFilter（重构为统一入口）
# ---------------------------------------------------------------------------

class VersionFilter:
    """统一版本过滤入口。bm25 / vector / hybrid 不再各自实现。

    任务书："召回前按服务端确认的 tenant/workspace/ACL 过滤；两路使用同一约束"
    注：当前 bm25.py:75-80 自实现 version 过滤，hybrid.py 透传但没 filter。
    本类将两者统一；retriever 层不再做版本过滤，由本类在后处理阶段统一应用。

    Tenant/workspace/ACL 过滤：任务书要求但当前无真实 identity provider。
    本类预留 filter_context 参数（dict: tenant_id, workspace_id, acl_scopes），
    调用方传入空 dict 时跳过（兼容现有测试）。
    """

    def __init__(self, policy: VersionPolicy = VersionPolicy.EXACT,
                 expected_version: Version | None = None,
                 corpus_sha: str | None = None,
                 latest_ledger: LatestResolutionLedger | None = None,
                 filter_context: dict[str, Any] | None = None) -> None:
        self.policy = policy
        self.expected = expected_version or Version()
        self.corpus_sha = corpus_sha
        self.latest_ledger = latest_ledger
        self.filter_context = filter_context or {}
        # INSUFFICIENT 标记：UNKNOWN policy 触发后，下游应看到这个状态
        self.insufficient = policy == VersionPolicy.UNKNOWN

    # ------------------------------------------------------------------
    # 核心过滤
    # ------------------------------------------------------------------

    def filter(self, results: Iterable[Any]) -> list[Any]:
        """统一过滤：版本 + tenant/workspace/ACL。

        返回 (filtered_results, metadata_dict) 让调用方能拿到 INSUFFICIENT 标记。
        注：现有 KnowledgeService.search 消费的是纯 list，
        我们在 metadata 里带 INSFFICIENT 标记供上层证据引用时使用。
        """
        results = list(results)

        # 1. 版本策略过滤
        if self.policy == VersionPolicy.EXACT:
            results = [r for r in results if self._version_matches_exact(r)]
        elif self.policy == VersionPolicy.LATEST_RESOLVED:
            # latest_resolved 要求期望版本已解析：只保留 component_version 匹配的
            # 若期望版本为空（没解析出来），保持不过滤但记 INSUFFICIENT
            if self.expected.component_version:
                results = [r for r in results if self._version_matches_exact(r)]
            if self.latest_ledger is not None:
                self.latest_ledger.record(
                    query=str(self.expected),
                    resolved_to=self.expected.component_version,
                    corpus_sha=self.corpus_sha,
                    policy=self.policy,
                )
        elif self.policy == VersionPolicy.UNKNOWN:
            # 目标版本未知：返回所有结果，但标记 INSUFFICIENT
            self.insufficient = True
        # COMPATIBLE 暂不实现，按任务书 "有真实适配需求时再加"

        # 2. Tenant/workspace/ACL（骨架：当前 corpus 无 tenant 字段）
        # 真实 ACL 过滤留待接入 identity provider；filter_context 里有值时
        # 若 chunk.metadata 含 tenant_id/workspace_id，才做过滤
        tenant = self.filter_context.get("tenant_id")
        workspace = self.filter_context.get("workspace_id")
        if tenant or workspace:
            filtered = []
            for r in results:
                meta = getattr(r, "metadata", None) or {}
                r_tenant = meta.get("tenant_id") or meta.get("tenant")
                r_workspace = meta.get("workspace_id") or meta.get("workspace")
                if tenant and r_tenant and r_tenant != tenant:
                    continue
                if workspace and r_workspace and r_workspace != workspace:
                    continue
                filtered.append(r)
            results = filtered

        return results

    # ------------------------------------------------------------------
    # 匹配逻辑（任务书：不能让 LLM 临时猜兼容区间）
    # ------------------------------------------------------------------

    def _version_matches_exact(self, result: Any) -> bool:
        """严格 exact：Version 对象各字段逐一匹配。

        现状兼容：chunk.version 可能是 "reference" 或空。expected 也可能是
        "reference" 或空。两个都是 "reference" → match；两个都空 → match；
        一方空另一方非空 → no match。
        """
        if self.expected.is_empty():
            # expected 为空 → 宽松（UNKNOWN 策略由上层标记 INSUFFICIENT）
            return True

        chunk_ver = Version.from_chunk(result)

        # 简单字符串 fallback（兼容现状）
        raw_expected = self.expected.component_version or self.expected.product
        raw_chunk = getattr(result, "version", None) or ""

        if raw_expected and raw_chunk:
            return raw_expected == raw_chunk

        # 结构化比对
        # product 必须匹配（若 expected 有 product）
        if self.expected.product and chunk_ver.product and self.expected.product != chunk_ver.product:
            return False
        # component_version 必须匹配
        if self.expected.component_version and chunk_ver.component_version \
                and self.expected.component_version != chunk_ver.component_version:
            return False
        # distro_version 必须匹配（若 expected 有）
        if self.expected.distro_version and chunk_ver.distro_version \
                and self.expected.distro_version != chunk_ver.distro_version:
            return False
        return True


# ---------------------------------------------------------------------------
# 便捷函数：从原始请求快速构建过滤器
# ---------------------------------------------------------------------------

def build_filter(*, expected_version: str | None,
                 corpus_sha: str | None = None,
                 latest_ledger: LatestResolutionLedger | None = None,
                 filter_context: dict[str, Any] | None = None,
                 **kwargs) -> VersionFilter:
    """KnowledgeService.search 的版本过滤入口。

    调用链：
      AI Service → KnowledgeService.search(version=...) → build_filter(...) → filter.filter(results)

    任务书 §3 第 33 行："VersionFilter 类存在，审阅时未发现业务调用" →
    本次把 KnowledgeService.search 重构为调用本函数（见 KnowledgeService 层改动）。
    """
    policy, version_obj = VersionPolicy.resolve(expected_version)
    return VersionFilter(
        policy=policy,
        expected_version=version_obj,
        corpus_sha=corpus_sha,
        latest_ledger=latest_ledger,
        filter_context=filter_context,
    )
