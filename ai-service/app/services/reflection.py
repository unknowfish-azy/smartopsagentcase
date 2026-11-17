"""P2-3 策略自优化反思服务。

Agent 处置完一个故障 → 调 /learn-from-incident → 反思 → 写进 faiss 案例库。

反思逻辑（轻量规则，不依赖 LLM）：
- outcome='failed' / 'pending' → 自动补 lesson 草稿 + recommendation 反推失败原因
- outcome='resolved' → 自动补 recommendation 草稿（基于 action + category）
- quality 判定：symptom 够长 + 有 lesson → good；只有 symptom → weak；中间 → mediocre

P2-3 不做 LLM 级"深度反思"（那是后续增强），但确保每次 learn 都有：
- 完整 symptom（向量检索的锚点）
- 至少一条 usable 的 lesson / recommendation
- 防重复（case_retriever.has_incident_key）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from ..services import case_retriever  # noqa: E402


# ---------------------------------------------------------------------------
# 反思模板（按 outcome + category 生成 lesson / recommendation 草稿）
# ---------------------------------------------------------------------------

_ACTION_SUCCESS_RECS: dict[str, dict[str, str]] = {
    "oom": {
        "restart": "下次遇到 OOM 先重启救急，再扩容 JVM heap 或 scale_out",
        "scale_out": "OOM 扩容有效；同时查 heap dump 找泄漏，避免反复 scale",
        "rollback": "OOM 由新代码引入内存泄漏，rollback 后补压测防回归",
    },
    "timeout": {
        "scale_out": "timeout 扩容有效；同时查慢 SQL / 连接池耗尽根因",
        "config_change": "timeout 通过调大连接池解决；设 circuit breaker 防雪崩",
        "restart": "timeout 是进程卡死所致；配置 liveness probe 自动重启",
    },
    "disk_full": {
        "manual_cleanup": "disk 满先 prune 救急，再配 logrotate / 定时清理",
        "scale_out": "disk 扩容救急；根因是日志爆炸 or WAL 增长",
        "config_change": "disk 满通过 logrotate 解决；设磁盘用量 >80% 预警",
    },
    "connection_refused": {
        "restart": "conn refused 通常进程挂了；配 supervisor/systemd 自动拉起",
        "scale_out": "conn refused 由后端全挂所致；检查 readiness probe",
    },
    "process_crash": {
        "restart": "crash 先重启救急；查 core dump / exit code 找根因",
        "rollback": "crash 由新代码引入；rollback 后加单元测试覆盖",
    },
    "auth_error": {
        "config_change": "auth_error 通过 flush JWKS / 重新发证书解决；设证书过期前 7d 告警",
        "code_fix": "auth_error 由 token 验证逻辑变更引入；补集成测试",
    },
    "network_error": {
        "config_change": "network_error 由 ACL / SecurityGroup 变更引入；变更后做连通性测试",
        "manual_cleanup": "network_error 由路由表污染所致；刷新路由 + 抓包定位",
    },
}


def _auto_lesson(outcome: str, symptom: str, action: str, category: str) -> str | None:
    """根据 outcome 自动生成 lesson 草稿（仅当用户没传 lesson 时调）。"""
    symptom_short = symptom[:60] + ("..." if len(symptom) > 60 else "")

    if outcome == "failed":
        return f"本次 {category} 故障用 {action} 失败。symptom: {symptom_short}. 下次避免盲目用 {action}，先查根因。"

    if outcome == "pending":
        return f"本次 {category} 故障处置未完成（{action}）。symptom: {symptom_short}. 需要后续跟进并标注最终结果。"

    if outcome == "mitigated":
        return f"本次 {category} 故障用 {action} 缓解但未根治。symptom: {symptom_short}. 需要后续做根因修复。"

    # resolved — 根据 category/action 查表
    rec = _ACTION_SUCCESS_RECS.get(category, {}).get(action)
    if rec:
        return rec
    return None  # resolved 但没模板 → 不自动填


def _auto_recommendation(outcome: str, action: str, category: str, lesson: str | None) -> str | None:
    """自动生成 recommendation 草稿。"""
    if outcome in ("failed", "pending"):
        return f"下次 {category} 故障先检索历史案例，不要直接用 {action}。"
    if outcome == "resolved":
        rec = _ACTION_SUCCESS_RECS.get(category, {}).get(action)
        if rec and lesson and rec == lesson:
            # lesson 就是 rec，那 recommendation 简化一下
            return f"下次同类 {category} 故障 → {action}（参见 lesson 细节）"
        if rec:
            return rec
    return None


def _extract_signals(text: str, category: str) -> list[str]:
    """从 symptom 里抽关键信号词（运维常见告警关键词）。"""
    keyword_sets = {
        "oom": ["outofmemory", "heap", "killed", "oom", "gc", "memory"],
        "timeout": ["timeout", "504", "deadline", "p99", "slow", "latency"],
        "disk_full": ["no space", "100%", "wal", "inode", "disk", "prune"],
        "connection_refused": ["econnrefused", "connection refused", "refused", "dial", "connect"],
        "process_crash": ["segfault", "exit code", "crash", "killed", "core dumped"],
        "auth_error": ["401", "403", "unauthorized", "forbidden", "jwt", "token", "cert"],
        "network_error": ["packet loss", "reset", "nxdomain", "dns", "connection reset"],
    }
    keys = keyword_sets.get(category, [])
    low = text.lower()
    hits = [k for k in keys if k in low]
    # 额外抽数字模式（端口 / 百分比 / 错误码）
    extras = re.findall(r"\b(\d{3,4})\b", text)
    hits.extend(extras[:3])
    return list(dict.fromkeys(hits))[:8]  # 去重保序，最多 8 个


def _assess_quality(symptom: str, lesson: str | None, outcome: str) -> Literal["good", "mediocre", "weak"]:
    """反思质量判定。"""
    if len(symptom) < 10:
        return "weak"
    if lesson and len(lesson) > 20:
        return "good"
    if outcome in ("resolved", "mitigated") and len(symptom) >= 20:
        return "mediocre"
    return "weak"


# ---------------------------------------------------------------------------
# Service 主入口
# ---------------------------------------------------------------------------

def get_model_info() -> dict:
    """GET /api/nn/reflection-info — 复用 case_retriever 元信息。"""
    info = case_retriever.get_model_info()
    info["kind"] = "reflection_loop"
    info["available"] = True  # P2-3 永远可用（就算没 faiss，也会 init 空索引）
    return info


def learn_from_incident(request) -> dict:
    """主入口：反思 → 调 case_retriever.learn() → 返回 review 报告。"""
    # 1. 构造 meta_dict
    category = request.category
    severity = request.severity
    symptom = request.symptom
    analysis = request.analysis or ""
    action = request.action_taken
    outcome = request.outcome
    duration = request.duration_minutes

    # 2. 反思：自动补 lesson / recommendation
    lesson = request.lesson
    lesson_auto = False
    if not lesson or len(lesson.strip()) < 5:
        lesson = _auto_lesson(outcome, symptom, action, category)
        lesson_auto = lesson is not None

    recommendation = request.recommendation
    rec_auto = False
    if not recommendation or len(recommendation.strip()) < 3:
        recommendation = _auto_recommendation(outcome, action, category, lesson)
        rec_auto = recommendation is not None

    review = {
        "reflection_quality": _assess_quality(symptom, lesson, outcome),
        "auto_lesson": lesson if lesson_auto else None,
        "auto_recommendation": recommendation if rec_auto else None,
        "signals": _extract_signals(symptom, category),
        "lessons_from_user": not lesson_auto,
        "recommendation_from_user": not rec_auto,
    }

    # 3. 调 case_retriever.learn()
    meta_dict = {
        "incident_key": request.incident_key,
        "category": category,
        "severity": severity,
        "symptom": symptom,
        "analysis": analysis,
        "action_taken": action,
        "outcome": outcome,
        "lesson": lesson or "",
        "recommendation": recommendation or "",
        "duration_minutes": duration,
    }

    result = case_retriever.learn(meta_dict)

    mode: Literal["learned", "skipped_duplicate", "partial"]
    reason: str | None = None
    if result.get("ok") and not result.get("skipped"):
        mode = "learned"
    elif result.get("skipped"):
        mode = "skipped_duplicate"
        reason = result.get("reason")
    else:
        mode = "partial"
        reason = result.get("reason")

    return {
        "ok": bool(result.get("ok")),
        "mode": mode,
        "reason": reason,
        "index_size": result.get("index_size", 0),
        "added_incident_key": result.get("incident_key", ""),
        "category": category,
        "outcome": outcome,
        "review": review,
    }


# ---------------------------------------------------------------------------
# History 查询
# ---------------------------------------------------------------------------

def get_history(limit: int = 20, category: str | None = None, outcome: str | None = None) -> dict:
    """从 learn_history.jsonl 读学习历史（faiss index 也有，但 jsonl 更容易遍历）。"""
    state = case_retriever.get_state()
    history_path = state.index_dir / "learn_history.jsonl" if state.index_dir else None

    entries: list[dict] = []
    if history_path and history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ent = dict(json_loads(line))
                    except Exception:
                        continue
                    if category and ent.get("category") != category:
                        continue
                    if outcome and ent.get("outcome") != outcome:
                        continue
                    entries.append(ent)
        except Exception:
            pass

    # 倒序（最新在前）+ limit
    entries = list(reversed(entries))[:limit]
    return {"total": len(entries), "entries": entries}


def json_loads(text: str) -> dict:
    """延迟 import json（避免模块级开销）。"""
    import json
    return json.loads(text)
