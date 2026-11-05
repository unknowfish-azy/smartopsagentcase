"""
State Verifier（Level 4）。

不直接相信 Agent 的「问题已解决」结论，
而是用实际系统状态与之对比。

    Agent Claim：「故障已解决」
    Actual State：502 仍存在
    => FALSE_SUCCESS / REJECTED
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
import re
from datetime import datetime, timezone
import socket
import subprocess
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

try:
    import psutil as _psutil
except ImportError:  # pragma: no cover - minimal hosts use command fallback
    _psutil = None

from agent.inspector.enums import InspectionCategory, Severity
from agent.inspector.models import InspectorIssue

_RESOLVED_PATTERNS = (
    "已解决",
    "已恢复",
    "恢复正常",
    "解决",
    "恢复",
    "resolved",
    "fixed",
    "recovered",
    "ok",
    # 动作完成类："服务已启动""配置已更新""重启处理完毕"等
    # 这些表达在真实运维对话里比"已解决"更常见，早期词表只覆盖后者，
    # 导致假成功漏检（见 06-工程整改/C-R9-纠察消融报告.md）。
    "已启动",
    "已重启",
    "已更新",
    "已生效",
    "已应用",
    "已部署",
    "已上线",
    "已修复",
    "已完成",
    "已处理",
    "已回滚",
    "已扩容",
    "启动完成",
    "重启完成",
    "更新完成",
    "部署完成",
    "修复完成",
    "处理完成",
    "处理完毕",
    "操作完成",
    "执行完成",
    "已经完成",
    # 状态可用类："进程起来了""集群修好了""后端现在可用了"
    "可以用了",
    "可用了",
    "能用了",
    "正常了",
    "修好了",
    "起来了",
    "已可用",
    "恢复可用",
)


CLAIM_ASSERTS = "asserts_success"
CLAIM_DENIES = "denies_success"
CLAIM_UNKNOWN = "unknown"

# 中文里"没/不"不总是否定成功声称："没问题了"= 成功。
# 这些惯用表达必须先于否定词判断。
_POSITIVE_IDIOMS = ("没有问题", "没问题", "没毛病", "没异常", "无异常", "正常无误")
_NON_COMPLETION_PATTERNS = ("解决方案", "如何解决", "怎么解决", "建议解决", "可解决", "用于解决")

_NEGATION_PATTERN = re.compile(
    r"尚未|没有|未|不|失败|不能|无法|待|暂|"
    r"\b(?:not|never|failed|unresolved|pending)\b"
)


def classify_claim(agent_claim: str | None) -> str:
    """把结论分成三态：声称成功 / 明确否定 / 无法判定。

    三态而不是布尔，是因为"没匹配到任何成功词"既可能是 agent 在陈述失败，
    也可能是用了词表没覆盖的说法。后者若当成"没声称成功"静默放行，
    就成了假成功的漏检通道。
    """
    if not agent_claim or not agent_claim.strip():
        return CLAIM_UNKNOWN

    text = agent_claim.lower()
    sentences = [sentence for sentence in re.split(r"[。！？\n.!?]", text) if sentence.strip()]
    if not sentences:
        return CLAIM_UNKNOWN

    saw_negation = False
    for sentence in sentences:
        for phrase in _NON_COMPLETION_PATTERNS:
            sentence = sentence.replace(phrase, "")
        if any(idiom in sentence for idiom in _POSITIVE_IDIOMS):
            return CLAIM_ASSERTS
        if _NEGATION_PATTERN.search(sentence):
            saw_negation = True
            continue
        if any(pattern in sentence for pattern in _RESOLVED_PATTERNS):
            return CLAIM_ASSERTS

    return CLAIM_DENIES if saw_negation else CLAIM_UNKNOWN


def claims_resolved(agent_claim: str | None) -> bool:
    """兼容旧接口：是否在声称已解决。无法判定时返回 False。"""
    return classify_claim(agent_claim) == CLAIM_ASSERTS



_HEALTHY_STATUSES = {
    "ok",
    "healthy",
    "up",
    "ready",
    "running",
    "open",
    "listening",
    "connected",
    "success",
    "200",
    "204",
    "301",
    "302",
    "303",
    "307",
    "308",
}
_UNHEALTHY_STATUSES = {
    "closed",
    "down",
    "failed",
    "failure",
    "error",
    "stopped",
    "dead",
    "crashed",
    "partial",
    "degraded",
    "timeout",
    "timed_out",
    "refused",
}


def probe_type(probe: Mapping[str, Any]) -> str:
    """Return a stable, human-readable probe shape label."""
    value = probe.get("probe_type", probe.get("type", "unknown"))
    return str(value).strip().lower().replace("-", "_").replace(" ", "_") or "unknown"


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1", "on"}:
            return True
        if normalized in {"false", "no", "n", "0", "off"}:
            return False
    return None


def _status(probe: Mapping[str, Any]) -> str:
    value = probe.get("status", probe.get("state", ""))
    return str(value).strip().lower().replace("-", "_")


def _timed_out(probe: Mapping[str, Any]) -> bool:
    return any(
        _as_bool(probe.get(key)) is True
        for key in ("timed_out", "timeout", "timedout")
    )


def _explicit_health(probe: Mapping[str, Any]) -> bool | None:
    for key in ("healthy", "ok", "reachable", "connected", "running", "open", "found"):
        value = _as_bool(probe.get(key))
        if value is not None:
            return value
    return None


def _member_health(probe: Mapping[str, Any]) -> bool | None:
    members = probe.get("members")
    if not isinstance(members, Sequence) or isinstance(members, (str, bytes)):
        return None
    if not members:
        return False
    states: list[bool] = []
    for member in members:
        if isinstance(member, Mapping):
            state = _explicit_health(member)
            if state is None:
                state = _status_health(member)
        else:
            state = _as_bool(member)
        if state is None:
            return False
        states.append(state)
    return all(states)


def _status_health(probe: Mapping[str, Any]) -> bool | None:
    value = _status(probe)
    if value in _HEALTHY_STATUSES:
        return True
    if value in _UNHEALTHY_STATUSES:
        return False
    return None


def _probe_healthy(probe: Mapping[str, Any]) -> bool | None:
    if _timed_out(probe):
        return False

    kind = probe_type(probe)
    explicit = _explicit_health(probe)
    status = _status(probe)

    if probe.get("error") not in (None, "", False):
        return False

    if kind in {"http", "https", "http_status"}:
        code = probe.get("status_code", probe.get("http_status"))
        if isinstance(code, str) and code.isdigit():
            code = int(code)
        if isinstance(code, int) and 100 <= code <= 599:
            if not 200 <= code < 400:
                return False
            if "expected_version" in probe:
                if "observed_version" not in probe:
                    return None
                return probe["expected_version"] == probe["observed_version"]
            return True
        if code is not None:
            return None
    if kind in {"cluster", "cluster_health", "cluster_status"}:
        if status == "partial" or _as_bool(probe.get("partial")) is True:
            return False
        healthy_nodes = probe.get("healthy_nodes")
        total_nodes = probe.get("total_nodes")
        if isinstance(healthy_nodes, int) and isinstance(total_nodes, int):
            return total_nodes > 0 and healthy_nodes == total_nodes
        member_health = _member_health(probe)
        if member_health is not None:
            return member_health
    if kind in {"all", "all_healthy", "health", "aggregate"}:
        checks = probe.get("checks", probe.get("probes"))
        if isinstance(checks, list):
            return resolve_from_probes(checks)
    if explicit is not None:
        return explicit
    if status:
        status_health = _status_health(probe)
        if status_health is not None:
            return status_health
    return None


def resolve_from_probes(probes: list[Mapping[str, Any]] | Sequence[Any]) -> bool:
    """Derive resolved state exclusively from a non-empty probes array.

    Every probe must be a recognized healthy signal. Unknown or malformed
    probes fail closed so a missing observation cannot become a false pass.
    """
    if not isinstance(probes, list) or not probes:
        return False
    if not all(isinstance(probe, Mapping) for probe in probes):
        return False
    return all(_probe_healthy(probe) is True for probe in probes)


def _probe_timeout(timeout: float | int) -> float:
    """Clamp live probe timeouts to a small bounded value."""
    try:
        value = float(timeout)
    except (TypeError, ValueError):
        value = 2.0
    return min(max(value, 0.01), 2.0)


def http_probe(url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    """Perform a bounded read-only HTTP GET and return a probe record."""
    bounded_timeout = _probe_timeout(timeout)
    probe: dict[str, Any] = {
        "probe_type": "http",
        "url": str(url),
        "timeout": bounded_timeout,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    request = urllib_request.Request(str(url), method="GET")
    try:
        opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))
        with opener.open(request, timeout=bounded_timeout) as response:
            code = int(response.getcode())
        probe.update({"status": "ok" if 200 <= code < 400 else "error", "status_code": code, "timed_out": False})
    except urllib_error.HTTPError as exc:
        probe.update({"status": "error", "status_code": int(exc.code), "timed_out": False})
    except (TimeoutError, socket.timeout) as exc:
        probe.update({"status": "timeout", "timed_out": True, "error_type": type(exc).__name__})
    except urllib_error.URLError as exc:
        reason = getattr(exc, "reason", None)
        timed_out = isinstance(reason, (TimeoutError, socket.timeout))
        probe.update({"status": "timeout" if timed_out else "error", "timed_out": timed_out, "error_type": type(exc).__name__})
    except OSError as exc:
        probe.update({"status": "error", "timed_out": False, "error_type": type(exc).__name__})
    return probe


def port_probe(host: str, port: int, *, timeout: float = 2.0) -> dict[str, Any]:
    """Check TCP reachability without sending application data."""
    bounded_timeout = _probe_timeout(timeout)
    probe = {"probe_type": "port", "host": str(host), "port": int(port), "timeout": bounded_timeout,
             "observed_at": datetime.now(timezone.utc).isoformat()}
    try:
        with socket.create_connection((str(host), int(port)), timeout=bounded_timeout):
            probe.update({"status": "open", "timed_out": False})
    except (TimeoutError, socket.timeout):
        probe.update({"status": "timeout", "timed_out": True})
    except ConnectionRefusedError:
        probe.update({"status": "closed", "timed_out": False})
    except (OSError, ValueError) as exc:
        probe.update({"status": "error", "timed_out": False, "error_type": type(exc).__name__})
    return probe


def _psutil_matches(pattern: str) -> list[dict[str, Any]]:
    if _psutil is None:
        return []
    matches: list[dict[str, Any]] = []
    needle = pattern.casefold()
    try:
        processes = _psutil.process_iter(["pid", "name", "exe", "cmdline"])
        for process in processes:
            try:
                info = getattr(process, "info", {}) or {}
                name = str(info.get("name") or "")
                exe = str(info.get("exe") or "")
                if needle and needle in f"{name} {os.path.basename(exe)}".casefold():
                    matches.append({"pid": info.get("pid"), "name": name})
            except Exception:
                continue
    except Exception:
        return []
    return matches


def _command_matches(pattern: str) -> list[dict[str, Any]]:
    command = ["tasklist"] if os.name == "nt" else ["ps", "-eo", "pid=,comm=,args="]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=_probe_timeout(2.0), check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    needle = pattern.casefold()
    return [{"line": line.strip()} for line in completed.stdout.splitlines() if needle and needle in line.casefold()]


def process_probe(name: str) -> dict[str, Any]:
    """Report whether a process name/command pattern appears locally."""
    pattern = str(name).strip()
    matches = _psutil_matches(pattern)
    if _psutil is None:
        matches = _command_matches(pattern)
    return {
        "probe_type": "process",
        "name": pattern,
        "pattern": pattern,
        "status": "running" if matches else "stopped",
        "match_count": len(matches),
        "matches": matches,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def _target_values(value: Any) -> list[Any]:
    if isinstance(value, (str, bytes, Mapping)):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    return [value]


def _split_port_target(value: Any) -> tuple[str, int, float]:
    if isinstance(value, Mapping):
        return str(value.get("host", "127.0.0.1")), int(value["port"]), float(value.get("timeout", 2.0))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 2:
        return str(value[0]), int(value[1]), 2.0
    host, separator, port = str(value).rpartition(":")
    if not separator or not host or not port:
        raise ValueError("port target must be HOST:PORT")
    return host, int(port), 2.0


def collect_probes(targets: Mapping[str, Any] | Sequence[Any]) -> list[dict[str, Any]]:
    """Collect live probes from grouped target descriptors; return probes only."""
    probes: list[dict[str, Any]] = []
    if isinstance(targets, Mapping) and "probe_type" not in targets and "type" not in targets:
        for kind, values in targets.items():
            normalized = str(kind).strip().lower().replace("-", "_")
            for value in _target_values(values):
                try:
                    if normalized in {"http", "https"}:
                        target = value if isinstance(value, Mapping) else {"url": value}
                        probes.append(http_probe(target["url"], timeout=float(target.get("timeout", 2.0))))
                    elif normalized == "port":
                        host, port, probe_timeout = _split_port_target(value)
                        probes.append(port_probe(host, port, timeout=probe_timeout))
                    elif normalized == "process":
                        pattern = value.get("pattern", value.get("name", "")) if isinstance(value, Mapping) else value
                        probes.append(process_probe(pattern))
                except (KeyError, TypeError, ValueError):
                    continue
        return probes
    sequence = [targets] if isinstance(targets, Mapping) else targets
    for target in sequence:
        if not isinstance(target, Mapping):
            continue
        kind = probe_type(target)
        try:
            if kind in {"http", "https"}:
                probes.append(http_probe(target["url"], timeout=float(target.get("timeout", 2.0))))
            elif kind == "port":
                host, port, probe_timeout = _split_port_target(target)
                probes.append(port_probe(host, port, timeout=probe_timeout))
            elif kind == "process":
                probes.append(process_probe(target.get("pattern", target.get("name", ""))))
        except (KeyError, TypeError, ValueError):
            continue
    return probes


class StateVerifier:
    """
    根据实际系统状态验证 Agent 结论。

    actual_state 形如：

        {"probes": [{"probe_type": "http", "status_code": 502}]}
    """

    def verify(
        self,
        agent_claim: str | None,
        actual_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not agent_claim or not isinstance(actual_state, Mapping):
            return {
                "checked": False,
                "passed": None,
                "reason": "缺少结论或实际状态 probes 数组，跳过验证",
            }

        probes = actual_state.get("probes")
        if not isinstance(probes, list) or not probes:
            return {
                "checked": False,
                "passed": None,
                "reason": "实际状态必须提供非空 probes 数组，跳过验证",
            }

        resolved_claim = claims_resolved(agent_claim)
        claim_state = classify_claim(agent_claim)
        if not all(isinstance(probe, Mapping) for probe in probes):
            return {"checked": False, "passed": None, "reason": "探针格式无效"}
        states = [_probe_healthy(probe) for probe in probes]
        if None in states and False not in states:
            return {"checked": False, "passed": None, "reason": "探针观测不足，待核验"}
        actual_resolved = all(state is True for state in states)
        probe_types = [probe_type(probe) for probe in probes]

        if resolved_claim and not actual_resolved:
            return {
                "checked": True,
                "passed": False,
                "false_success": True,
                "claim_state": claim_state,
                "probe_types": probe_types,
                "reason": (
                    "Agent 声称已解决，但探针仍报告异常："
                    f"{', '.join(probe_types)}"
                ),
            }

        # 声称无法解析、而探针显示仍未恢复：不判假成功（证据不足），
        # 但也不能静默放行——显式标记为存疑，交由人工复核。
        if claim_state == CLAIM_UNKNOWN and not actual_resolved:
            return {
                "checked": True,
                "passed": None,
                "false_success": False,
                "uncertain": True,
                "claim_state": claim_state,
                "probe_types": probe_types,
                "reason": (
                    "无法从结论判定是否在声称成功，且探针显示未完全恢复："
                    f"{', '.join(probe_types)}；需人工复核"
                ),
            }

        return {
            "checked": True,
            "passed": True,
            "false_success": False,
            "claim_state": claim_state,
            "probe_types": probe_types,
            "reason": "结论与实际状态一致",
        }

    def check(self, context: dict[str, Any]) -> list[InspectorIssue]:
        result = self.verify(
            context.get("agent_claim"),
            context.get("actual_state"),
        )

        if result.get("false_success"):
            return [
                InspectorIssue(
                    category=InspectionCategory.VERIFICATION,
                    severity=Severity.HIGH,
                    reason=result["reason"],
                    recommendation=(
                        "验证失败，触发 Re-plan，"
                        "重新分析并再次验证"
                    ),
                )
            ]

        return []


__all__ = [
    "StateVerifier",
    "claims_resolved",
    "classify_claim",
    "CLAIM_ASSERTS",
    "CLAIM_DENIES",
    "CLAIM_UNKNOWN",
    "probe_type",
    "resolve_from_probes",
    "http_probe",
    "port_probe",
    "process_probe",
    "collect_probes",
]
