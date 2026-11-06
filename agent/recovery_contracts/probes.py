"""N03 只读探针：不可变登记与有界 GET 执行器。

冻结规则来源：
- ``docs/design/recovery-contract-v1/semantics.md`` §4.1（1 秒单调绝对时限）、
  §5（探针登记）、§8.1（谓词输入契约）。
- 交接书 N03 卡（第 907-925 行）。

设计边界（有意如此，不是遗漏）：
- 执行器不内置真实 socket transport；调用方必须注入 ``transport`` 与 ``clock``，
  因此测试不会访问外网，也不会启动真实服务。
- 方法、端点、路径由登记与执行器共同限制；不提供任意 URL、shell 或写操作入口。
- 只接受 JSON 对象；非 2xx/3xx 只写 ``error``（``HTTP_<status>``），不得塞 ``payload``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .models import (
    ContractError,
    EvidenceObservation,
    Target,
    _ID_RE,
    _ms,
    add_ms,
    format_time,
    parse_time,
    payload_digest,
)

# 只允许 loopback 明文 HTTP；端口由注册方注入，不接收任意主机。
PROBE_HOST = "127.0.0.1"
ALLOWED_PATHS = ("/health", "/ready", "/api/health")
MAX_RESPONSE_BYTES = 4096
ABSOLUTE_TIMEOUT_MS = 1000
PROBE_POLICY_VERSION = "recovery-probe/v1"


class ProbeError(ValueError):
    """探针登记/执行失败的基类。"""


class ProbeRegistrationError(ProbeError):
    """探针描述不满足只读或有界约束。"""


class ProbeExecutionError(ProbeError):
    """执行器无法按冻结参数发起请求。"""


class ProbeDeadlineError(ProbeExecutionError):
    """run 剩余时间不足以发起哪怕一次探针调用。"""


Clock = Callable[[], datetime]
Transport = Callable[["ProbeRequest"], "TransportResponse"]


@dataclass(frozen=True)
class ProbeRequest:
    """执行器交给 transport 的唯一请求形状；transport 不得改写这些字段。"""

    method: str
    url: str
    host: str
    port: int
    path: str
    timeout_ms: int
    deadline_at: datetime
    max_bytes: int
    follow_redirects: bool = False
    use_proxy: bool = False


@dataclass(frozen=True)
class TransportResponse:
    """transport 的原始响应；错误码由 transport 显式报告，不靠异常文本猜测。"""

    status_code: int | None
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str = ""


@dataclass(frozen=True)
class Probe:
    """不可变探针描述。登记前不做业务推断，登记本身也不代表采集成功。"""

    probe_id: str
    collector_id: str
    collector_version: str
    obligation_ids: tuple[str, ...]
    cost: int | float
    permission: str
    read_only: bool
    endpoint: str
    path: str
    target_id: str
    source_group: str

    def __post_init__(self) -> None:
        # 强制不可变容器，避免注册后被外部列表原地修改。
        object.__setattr__(self, "obligation_ids", tuple(self.obligation_ids))


def loopback_endpoint(port: int) -> str:
    """生成注入端口的 loopback 基地址；只接受 1..65535。"""
    if isinstance(port, bool) or not isinstance(port, int):
        raise ProbeRegistrationError("端口必须是整数")
    if not 1 <= port <= 65535:
        raise ProbeRegistrationError(f"端口越界：{port}")
    return f"http://{PROBE_HOST}:{port}"


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ProbeRegistrationError(f"{name} 不是合法标识：{value!r}")
    return value


def _non_empty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProbeRegistrationError(f"{name} 必须是非空字符串")
    return value


def _loopback_port(endpoint: Any) -> int:
    """只接受 http://127.0.0.1:<port> 基地址，拒绝用户信息/查询/片段/额外路径。"""
    _non_empty(endpoint, "endpoint")
    parts = urlsplit(str(endpoint))
    if parts.scheme != "http":
        raise ProbeRegistrationError("endpoint 只允许 http://127.0.0.1:<port>")
    if parts.hostname != PROBE_HOST:
        raise ProbeRegistrationError(f"endpoint 主机必须是 {PROBE_HOST}")
    if parts.username is not None or parts.password is not None:
        raise ProbeRegistrationError("endpoint 不得包含用户信息")
    if parts.query or parts.fragment:
        raise ProbeRegistrationError("endpoint 不得包含查询串或片段")
    if parts.path not in ("", "/"):
        raise ProbeRegistrationError("endpoint 不能自带路径，路径须由 path 字段显式登记")
    try:
        port = parts.port
    except ValueError as exc:
        raise ProbeRegistrationError(f"endpoint 端口非法：{endpoint!r}") from exc
    if port is None or not 1 <= port <= 65535:
        raise ProbeRegistrationError("endpoint 必须包含 1..65535 端口")
    return port


def _validate_probe(probe: Probe) -> None:
    if not isinstance(probe, Probe):
        raise ProbeRegistrationError("登记项必须是 Probe")
    _identifier(probe.probe_id, "probe_id")
    _identifier(probe.collector_id, "collector_id")
    _non_empty(probe.collector_version, "collector_version")
    _non_empty(probe.permission, "permission")
    _identifier(probe.source_group, "source_group")
    _non_empty(probe.target_id, "target_id")

    if not probe.read_only:
        raise ProbeRegistrationError("探针必须声明 read_only=true，禁止写操作")
    if not probe.obligation_ids:
        raise ProbeRegistrationError("探针必须覆盖至少一个 obligation_id")
    for index, obligation_id in enumerate(probe.obligation_ids):
        _identifier(obligation_id, f"obligation_ids[{index}]")
    if len(set(probe.obligation_ids)) != len(probe.obligation_ids):
        raise ProbeRegistrationError("obligation_ids 不得重复")

    if isinstance(probe.cost, bool) or not isinstance(probe.cost, (int, float)):
        raise ProbeRegistrationError("cost 必须是数值")
    if probe.cost <= 0:
        raise ProbeRegistrationError("cost 必须 > 0")

    if probe.path not in ALLOWED_PATHS:
        raise ProbeRegistrationError(
            f"path 不在固定允许集合 {ALLOWED_PATHS}：{probe.path!r}"
        )
    _loopback_port(probe.endpoint)


class ProbeRegistry:
    """登记表：唯一性、只读、覆盖非空、cost>0 都在注册时校验。"""

    def __init__(self) -> None:
        self._probes: dict[str, Probe] = {}

    def register(self, probe: Probe) -> Probe:
        _validate_probe(probe)
        if probe.probe_id in self._probes:
            raise ProbeRegistrationError(f"probe_id 重复：{probe.probe_id}")
        self._probes[probe.probe_id] = probe
        return probe

    def get(self, probe_id: str) -> Probe:
        if probe_id not in self._probes:
            raise ProbeRegistrationError(f"未登记探针：{probe_id}")
        return self._probes[probe_id]

    def probes(self) -> tuple[Probe, ...]:
        """按 probe_id 字典序返回，保证调度枚举顺序确定。"""
        return tuple(self._probes[key] for key in sorted(self._probes))

    def __len__(self) -> int:
        return len(self._probes)

    def __contains__(self, probe_id: object) -> bool:
        return probe_id in self._probes


@dataclass(frozen=True)
class ExecutionResult:
    """一次有界采集的规范化结果；payload 与 error 至少一个非 null。"""

    probe_id: str
    collector_id: str
    collector_version: str
    source_group: str
    endpoint: str
    path: str
    status_code: int | None
    observed_at: datetime
    elapsed_ms: int
    payload: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    bytes_read: int = 0
    truncated: bool = False
    policy_version: str = PROBE_POLICY_VERSION

    def error_code(self) -> str | None:
        return None if self.error is None else self.error.get("code")

    def to_observation(
        self,
        *,
        observation_id: str,
        run_id: str,
        verification_round: int,
        scope: str,
        target: Target,
        binding_revision: str,
        observed_revision: str | None,
        sequence: int = 0,
        extensions: Mapping[str, Any] | None = None,
    ) -> EvidenceObservation:
        """写入采集元数据。scope 由调用方显式给出，绝不从 payload 反推。"""
        material = self.payload if self.payload is not None else self.error
        raw: dict[str, Any] = {
            "id": observation_id,
            "run_id": run_id,
            "verification_round": verification_round,
            "collector_id": self.collector_id,
            "collector_version": self.collector_version,
            "probe_id": self.probe_id,
            "scope": scope,
            "target": target.to_dict(),
            "binding_revision": binding_revision,
            "observed_revision": observed_revision,
            "source_group": self.source_group,
            "sequence": sequence,
            "observed_at": format_time(self.observed_at),
            # schema 冻结 elapsed_ms <= 1000；超时结果保留真实耗时在 extensions。
            "elapsed_ms": min(self.elapsed_ms, 1000),
            "artifact_digest": payload_digest(material),
        }
        if self.payload is not None:
            raw["payload"] = dict(self.payload)
        if self.error is not None:
            raw["error"] = dict(self.error)
        if extensions:
            raw["extensions"] = dict(extensions)
        return EvidenceObservation.from_dict(raw)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def _safe_message(value: Any, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        return fallback
    # 受控短消息：不得携带任意异常堆栈或凭证。
    return text[:160]


class ProbeExecutor:
    """有界只读 GET 执行器：参数冻结，网络由注入 transport 完成。"""

    def __init__(
        self,
        *,
        transport: Transport,
        clock: Clock,
        max_bytes: int = MAX_RESPONSE_BYTES,
        timeout_ms: int = ABSOLUTE_TIMEOUT_MS,
    ) -> None:
        if not callable(transport):
            raise ProbeExecutionError("必须注入可调用的 transport")
        if not callable(clock):
            raise ProbeExecutionError("必须注入可调用的 clock")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ProbeExecutionError("max_bytes 必须是正整数")
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms <= 0:
            raise ProbeExecutionError("timeout_ms 必须是正整数")
        self._transport = transport
        self._clock = clock
        self._max_bytes = min(max_bytes, MAX_RESPONSE_BYTES)
        self._timeout_ms = min(timeout_ms, ABSOLUTE_TIMEOUT_MS)

    def execute(
        self,
        probe: Probe,
        *,
        run_deadline_at: datetime | str | None = None,
    ) -> ExecutionResult:
        """执行一次 GET；1 秒是含连接/完整读取/解析的单调绝对时限。"""
        started_at = parse_time(self._clock())
        if run_deadline_at is not None:
            deadline_at = parse_time(run_deadline_at)
        else:
            deadline_at = add_ms(started_at, self._timeout_ms)

        remaining_ms = _ms(deadline_at) - _ms(started_at)
        if remaining_ms <= 0:
            raise ProbeDeadlineError("run 剩余时间不足以发起探针调用")
        timeout_ms = min(self._timeout_ms, remaining_ms)

        port = _loopback_port(probe.endpoint)
        request = ProbeRequest(
            method="GET",
            url=f"{probe.endpoint}{probe.path}",
            host=PROBE_HOST,
            port=port,
            path=probe.path,
            timeout_ms=timeout_ms,
            deadline_at=deadline_at,
            max_bytes=self._max_bytes,
            follow_redirects=False,
            use_proxy=False,
        )

        try:
            response = self._transport(request)
        except TimeoutError as exc:
            response = TransportResponse(
                status_code=None,
                error_code="TIMEOUT",
                error_message=_safe_message(exc, "timeout"),
            )
        except OSError as exc:
            response = TransportResponse(
                status_code=None,
                error_code="TRANSPORT_ERROR",
                error_message=_safe_message(exc, "transport error"),
            )
        if not isinstance(response, TransportResponse):
            raise ProbeExecutionError("transport 必须返回 TransportResponse")

        finished_at = parse_time(self._clock())
        elapsed_ms = max(0, _ms(finished_at) - _ms(started_at))
        status = response.status_code
        headers = response.headers or {}
        bytes_read = len(response.body or b"")

        error: dict[str, str] | None = None
        payload: dict[str, Any] | None = None
        truncated = bytes_read > self._max_bytes

        if response.error_code is not None:
            error = {
                "code": response.error_code,
                "message": _safe_message(response.error_message, "transport error"),
            }
        elif status is None:
            error = {"code": "MALFORMED", "message": "缺少状态码"}
        elif elapsed_ms > timeout_ms:
            # slow-drip：即使每次读取都未满 1 秒，累计超过绝对时限也必须停止。
            error = {"code": "TIMEOUT", "message": "超过单探针绝对时限"}
        elif isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
            error = {"code": "MALFORMED", "message": f"非法状态码：{status!r}"}
        elif not 200 <= status < 400:
            # semantics §8.1：非 2xx/3xx 只写 error，不得塞 payload。
            error = {"code": f"HTTP_{status}", "message": f"HTTP {status}"}
        elif 300 <= status < 400 and _header(headers, "location") is not None:
            # 不跟随重定向，也不把重定向当可达证据。
            error = {"code": "REDIRECT_BLOCKED", "message": "拒绝跟随重定向"}
        elif truncated:
            error = {
                "code": "MALFORMED",
                "message": f"响应体超过 {self._max_bytes} 字节上限",
            }
        else:
            try:
                parsed = json.loads(bytes(response.body or b"").decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                parsed = None
            if not isinstance(parsed, dict):
                error = {"code": "MALFORMED", "message": "响应不是 JSON 对象"}
            else:
                payload = parsed

        return ExecutionResult(
            probe_id=probe.probe_id,
            collector_id=probe.collector_id,
            collector_version=probe.collector_version,
            source_group=probe.source_group,
            endpoint=probe.endpoint,
            path=probe.path,
            status_code=status,
            observed_at=finished_at,
            elapsed_ms=elapsed_ms,
            payload=payload,
            error=error,
            bytes_read=bytes_read,
            truncated=truncated,
        )


__all__ = [
    "ABSOLUTE_TIMEOUT_MS",
    "ALLOWED_PATHS",
    "MAX_RESPONSE_BYTES",
    "PROBE_HOST",
    "PROBE_POLICY_VERSION",
    "Clock",
    "ExecutionResult",
    "Probe",
    "ProbeDeadlineError",
    "ProbeError",
    "ProbeExecutionError",
    "ProbeExecutor",
    "ProbeRegistrationError",
    "ProbeRegistry",
    "ProbeRequest",
    "Transport",
    "TransportResponse",
    "loopback_endpoint",
]
