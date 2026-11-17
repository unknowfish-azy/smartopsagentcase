"""基线配置加载器。

加载顺序：显式路径 → 包内 baseline.yaml → 内置 DEFAULT_BASELINE。
任何情况下引擎都能拿到一份完整基线，保证 fail-closed 不依赖外部文件可用性。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.policies.risk import RiskLevel

from .models import BaselineLayer, BaselineRule

_DEFAULT_PATH = Path(__file__).with_name("baseline.yaml")


@dataclass(frozen=True)
class BaselineConfig:
    """不可变基线配置视图。"""

    raw: dict[str, Any]
    source: str

    # -- 通用 ---------------------------------------------------------------

    @property
    def fail_closed(self) -> bool:
        return bool(self.raw.get("enforcement", {}).get("fail_closed", True))

    def layer_config(self, layer: BaselineLayer) -> dict[str, Any]:
        return dict(self.raw.get(layer.value, {}))

    # -- L0/L2 规则 ----------------------------------------------------------

    def rules(self, layer: BaselineLayer) -> list[BaselineRule]:
        key = "rules" if layer is BaselineLayer.L0_COMPLIANCE else "redlines"
        parsed: list[BaselineRule] = []
        for item in self.layer_config(layer).get(key, []):
            parsed.append(
                BaselineRule(
                    id=item["id"],
                    name=item.get("name", ""),
                    pattern=item["pattern"],
                    layer=layer,
                    match=item.get("match", "regex"),
                    message=item.get("message", ""),
                    risk=RiskLevel(str(item.get("risk", "CRITICAL")).upper()),
                    legal_ref=item.get("legal_ref", ""),
                )
            )
        return parsed

    # -- L1 配额 -------------------------------------------------------------

    def quota(self, scope: str) -> tuple[int, float]:
        quotas = self.layer_config(BaselineLayer.L1_GENERIC_AI).get("quotas", {})
        spec = quotas.get(scope)
        if not spec:
            spec = quotas.get("tool_default", {})
        return int(spec.get("capacity", 120)), float(spec.get("refill_per_second", 2))

    # -- L3 传感器/场景 ------------------------------------------------------

    def sensor_profile(self, sensor_type: str) -> dict[str, Any]:
        sensors = self.layer_config(BaselineLayer.L3_MULTIMODAL).get("sensors", {})
        return dict(sensors.get(sensor_type, {}))

    def scenario(self, name: str) -> dict[str, Any]:
        scenarios = self.layer_config(BaselineLayer.L3_MULTIMODAL).get("scenarios", {})
        if name not in scenarios:
            raise KeyError(f"未知多模态仲裁场景: {name}")
        return dict(scenarios[name])

    @property
    def auto_suppression_limit(self) -> int:
        return int(
            self.layer_config(BaselineLayer.L3_MULTIMODAL).get(
                "auto_suppression_limit", 3
            )
        )

    @property
    def destructive_actions(self) -> set[str]:
        return set(
            self.layer_config(BaselineLayer.L3_MULTIMODAL).get(
                "destructive_actions", []
            )
        )


# ---------------------------------------------------------------------------
# 内置兜底基线（与 baseline.yaml 同构；YAML 不可用时的 fail-closed 最后防线）
# ---------------------------------------------------------------------------

DEFAULT_BASELINE: dict[str, Any] = {
    "version": 1,
    "enforcement": {"fail_closed": True, "default_decision": "ALLOW"},
    "L1_GENERIC_AI": {
        "injection": {"block_on_risk": "HIGH", "sanitize_medium": True},
        "output_moderation": {"pii_redact": True, "unclaimed_action_rewrite": True},
        "rag": {"dirty_doc_action": "FILTER", "min_source_trust": 0.6},
        "quotas": {
            "model_api": {"capacity": 60, "refill_per_second": 1},
            "tool_default": {"capacity": 120, "refill_per_second": 2},
            "tool_high_risk": {"capacity": 10, "refill_per_second": 0.2},
        },
    },
    "L2_OPERATIONS": {
        "redlines": [
            {"id": "OL-001", "pattern": r"(?:^|[\s;|&])rm\s+[^\n;|&]*(?:--no-preserve-root|(?:^|\s)(?:/\*?|/etc|/var|/usr|/home|/root|~)(?=\s|$|[/*])|\.\.(?=\s|$)|\.(?=\s|$))", "message": "禁止对根目录/系统目录执行递归删除", "risk": "CRITICAL"},
            {"id": "OL-002", "pattern": r"(?:^|[\s;|&])(mkfs(\.\w+)?|fdisk|parted)\b|dd\s+if=\S+\s+of=/dev/", "message": "禁止格式化/分区/裸盘写入", "risk": "CRITICAL"},
            {"id": "OL-003", "pattern": r"(?:^|[\s;|&])(shutdown|halt|poweroff|reboot|init\s+[06])\b", "message": "关机重启须人工审批", "risk": "HIGH"},
            {"id": "OL-004", "pattern": r"(iptables|ip6tables|nft)\s+[^\n;|&]*(-F|--flush|delete)\b|systemctl\s+(stop|disable)\s+(firewalld|iptables|ufw)\b|ufw\s+disable\b", "message": "禁止关闭防火墙", "risk": "CRITICAL"},
            {"id": "OL-005", "pattern": r"\b(DROP|TRUNCATE)\s+(DATABASE|TABLE|SCHEMA)\b", "message": "禁止自动执行 DROP/TRUNCATE", "risk": "CRITICAL"},
            {"id": "OL-006", "pattern": r"history\s+-c\b|rm\s+[^\n;|&]*/var/log\b|journalctl\s+--vacuum|wevtutil\s+cl\b", "message": "禁止清除审计日志", "risk": "CRITICAL"},
            {"id": "OL-009", "pattern": r"dr\s+switchover\b|rollback\s+--force\b|灾备切换", "message": "灾备切换须双人审批", "risk": "CRITICAL"},
            {"id": "OL-011", "match": "operation", "pattern": "database.drop", "message": "database.drop 禁止自动执行", "risk": "CRITICAL"},
            {"id": "OL-012", "match": "operation", "pattern": "server.delete", "message": "server.delete 禁止自动执行", "risk": "CRITICAL"},
        ],
        "audit_required_events": [
            "baseline.blocked",
            "baseline.redline_hit",
            "baseline.compliance_hit",
            "multimodal.escalation",
        ],
    },
    "L0_COMPLIANCE": {
        "rules": [
            {"id": "CL-001", "pattern": r"(?<![\w.-])(nmap|masscan|zmap|nikto|gobuster|nessus)(?![\w.-])", "legal_ref": "网络安全法第27条/刑法第285条", "message": "未授权扫描违法"},
            {"id": "CL-002", "pattern": r"(?<![\w.-])(ida|ida64|ghidra|x64dbg|jadx|apktool|frida|uncompyle6)(?![\w.-])|upx\s+-d\b", "legal_ref": "著作权法/反不正当竞争法", "message": "禁止未授权逆向"},
            {"id": "CL-003", "pattern": r"(?<![\w.-])(hydra|medusa|hashcat|john)(?![\w.-])", "legal_ref": "刑法第285条", "message": "禁止暴力破解"},
            {"id": "CL-004", "pattern": r"(?<![\w.-])(arpspoof|ettercap|bettercap|responder)(?![\w.-])", "legal_ref": "网络安全法第27条", "message": "禁止内网欺骗嗅探"},
            {"id": "CL-005", "pattern": r"(?<![\w.-])(frpc|frps|ngrok|nps|chisel)(?![\w.-])", "legal_ref": "网络安全法第27条", "message": "禁止私建穿透隧道"},
            {"id": "CL-006", "pattern": r"(?<![\w.-])(msfvenom|meterpreter|mimikatz)(?![\w.-])|菜刀|蚁剑|冰蝎|哥斯拉", "legal_ref": "刑法第285/286条", "message": "禁止木马载荷制作"},
            {"id": "CL-007", "pattern": r"stealth(?:mode)?|2captcha|anticaptcha|captcha[_-]?solver|proxy[_-]?pool", "legal_ref": "网络安全法/数据安全法", "message": "禁止反爬绕过"},
        ],
        "approval_exemptible": False,
    },
    "L3_MULTIMODAL": {
        "sensors": {
            "thermal": {"weight": 1.0, "physical_min": -20.0, "physical_max": 120.0,
                        "alarm_threshold": 65.0, "max_staleness_seconds": 30,
                        "max_change_per_cycle": 25.0, "min_confidence": 0.5},
            "vision_fire": {"weight": 0.9, "max_staleness_seconds": 15, "min_confidence": 0.5},
            "vision_smoke": {"weight": 0.8, "max_staleness_seconds": 15, "min_confidence": 0.5},
            "smoke_sensor": {"weight": 1.0, "max_staleness_seconds": 20, "min_confidence": 0.7},
            "robot_nav": {"weight": 0.4, "max_staleness_seconds": 60, "min_confidence": 0.3},
        },
        "scenarios": {
            "fire_alarm": {"policy": "QUORUM", "required_distinct_types": 2,
                           "destructive_min_types": 2, "weighted_threshold": 1.5},
            "overheat": {"policy": "AND", "required_distinct_types": 2,
                         "destructive_min_types": 2, "weighted_threshold": 1.5},
        },
        "auto_suppression_limit": 3,
        "destructive_actions": [
            "power.off", "circuit.break", "fire_suppression.release", "dr.switchover",
        ],
        "self_test_isolation": True,
    },
}


def load_baseline(path: str | Path | None = None) -> BaselineConfig:
    """加载基线配置。

    显式路径损坏时抛异常交由调用方按 fail-closed 处理；
    包内 YAML 缺失/损坏时静默回退内置默认值并标注 source。
    """
    if path is not None:
        return BaselineConfig(raw=_read_yaml(Path(path)), source=str(path))

    try:
        return BaselineConfig(raw=_read_yaml(_DEFAULT_PATH), source=str(_DEFAULT_PATH))
    except Exception:
        return BaselineConfig(raw=DEFAULT_BASELINE, source="built-in-default")


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - 环境依赖缺失时走默认值
        raise ImportError("解析基线 YAML 需要 PyYAML：pip install pyyaml") from exc
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    _validate(data)
    return data


def _validate(data: dict[str, Any]) -> None:
    """结构校验：规则 ID 不得重复，分层键必须合法。"""
    if not isinstance(data, dict):
        raise ValueError("基线配置必须是映射结构")
    seen: set[str] = set()
    for layer in (BaselineLayer.L0_COMPLIANCE, BaselineLayer.L2_OPERATIONS):
        key = "rules" if layer is BaselineLayer.L0_COMPLIANCE else "redlines"
        for item in data.get(layer.value, {}).get(key, []):
            rule_id = item.get("id")
            if not rule_id:
                raise ValueError(f"{layer.value} 存在缺少 id 的规则")
            if rule_id in seen:
                raise ValueError(f"基线规则 ID 重复: {rule_id}")
            if "pattern" not in item:
                raise ValueError(f"规则 {rule_id} 缺少 pattern")
            seen.add(rule_id)
