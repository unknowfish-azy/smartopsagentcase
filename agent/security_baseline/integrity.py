"""插件/脚本仓库完整性校验（工具链投毒防护）。

威胁模型：Agent 加载的插件目录或运维脚本仓库在发布后被篡改——
植入后门文件、改写工具代码、删除审计模块、替换 manifest。

防护机制（全部 fail-closed）：
* SHA-256 钉扎：发布时对目录内每个受保护文件计算哈希写入 pin 清单，
  加载前重算比对，篡改/缺失/夹带未登记文件一律拒绝；
* HMAC-SHA256 签名（标准库实现，无第三方依赖）：pin 清单本身可被签名，
  防止攻击者连哈希清单一起伪造；require_signature=True 时无签名清单直接拒收；
* 符号链接按可疑项拒绝，避免链接跳出插件目录借道投毒；
* __pycache__、pin 清单自身等非受保护文件不参与哈希，避免运行态噪声误报。

典型用法（CI 发布侧）：
    pin = generate_pin_file(plugin_dir, "robot", secret=os.environ["PIN_SECRET"])
    write_pin_file(plugin_dir / "integrity.pins.json", pin)

加载侧：
    guard = PluginIntegrityGuard()
    decision = guard.verify(plugin_dir, secret=os.environ["PIN_SECRET"],
                            require_signature=True)
    if not decision.allowed:
        raise PermissionError(decision.reason)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit_sink import _canonical

PIN_FILE_NAME = "integrity.pins.json"
DEFAULT_INCLUDE_SUFFIXES = (".py", ".yaml", ".yml", ".json", ".sh", ".ps1")
_EXCLUDED_DIR_NAMES = {"__pycache__", ".git", ".pytest_cache", "node_modules"}
_ALGORITHM = "sha256"
_SIGN_ALG = "HMAC-SHA256"


@dataclass(frozen=True)
class IntegrityDecision:
    """完整性校验结论。allowed=False 时调用方必须中止插件注册。"""

    allowed: bool
    plugin_id: str
    reason: str = ""
    verified_files: tuple[str, ...] = ()
    mismatched: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    signature_verified: bool = False

    @property
    def discrepancies(self) -> dict[str, tuple[str, ...]]:
        return {
            "mismatched": self.mismatched,
            "missing": self.missing,
            "unexpected": self.unexpected,
        }


# ---------------------------------------------------------------------------
# 哈希与 pin 清单生成（CI 发布侧）
# ---------------------------------------------------------------------------


def _iter_protected_files(root: Path):
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(part in _EXCLUDED_DIR_NAMES for part in rel_parts):
            continue
        if path.name == PIN_FILE_NAME:
            continue
        if path.is_symlink():
            # 符号链接不受信任：可能指向目录外的受控外文件
            yield path, True
            continue
        if path.is_file() and path.suffix.lower() in DEFAULT_INCLUDE_SUFFIXES:
            yield path, False


def compute_directory_hashes(root: str | Path) -> dict[str, str]:
    """计算目录下受保护文件的 SHA-256，键为 POSIX 风格相对路径。"""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"插件目录不存在: {root}")
    hashes: dict[str, str] = {}
    for path, is_symlink in _iter_protected_files(root):
        if is_symlink:
            continue
        rel = path.relative_to(root).as_posix()
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def generate_pin_file(
    plugin_dir: str | Path,
    plugin_id: str,
    *,
    secret: str | bytes | None = None,
    key_id: str = "ops-ci-default",
) -> dict[str, Any]:
    """生成 pin 清单；提供 secret 时同时附 HMAC 签名。"""
    plugin_dir = Path(plugin_dir)
    pin: dict[str, Any] = {
        "version": 1,
        "plugin_id": plugin_id,
        "algorithm": _ALGORITHM,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": compute_directory_hashes(plugin_dir),
    }
    if secret is not None:
        pin["signature"] = _sign_payload(pin, secret, key_id)
    return pin


def write_pin_file(path: str | Path, pin: dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(pin, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_pin_file(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# HMAC 签名
# ---------------------------------------------------------------------------


def _sign_payload(payload: dict[str, Any], secret: str | bytes, key_id: str) -> dict[str, str]:
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    digest = hmac.new(key, _canonical(payload).encode("utf-8"), hashlib.sha256).hexdigest()
    return {"alg": _SIGN_ALG, "kid": key_id, "value": digest}


def verify_pin_signature(pin: dict[str, Any], secret: str | bytes) -> bool:
    """校验 pin 清单签名；签名缺失、算法不符或密钥不匹配均返回 False。"""
    signature = pin.get("signature")
    if not isinstance(signature, dict) or signature.get("alg") != _SIGN_ALG:
        return False
    unsigned = {k: v for k, v in pin.items() if k != "signature"}
    expected = _sign_payload(unsigned, secret, signature.get("kid", ""))
    return hmac.compare_digest(expected["value"], str(signature.get("value", "")))


# ---------------------------------------------------------------------------
# 加载侧校验器
# ---------------------------------------------------------------------------


class PluginIntegrityGuard:
    """插件目录完整性校验器，无状态、线程安全，可全局复用。"""

    def verify(
        self,
        plugin_dir: str | Path,
        *,
        pin_path: str | Path | None = None,
        pin: dict[str, Any] | None = None,
        secret: str | bytes | None = None,
        require_signature: bool = False,
    ) -> IntegrityDecision:
        plugin_dir = Path(plugin_dir)
        plugin_id = ""
        try:
            if pin is None:
                pin_file = Path(pin_path) if pin_path else plugin_dir / PIN_FILE_NAME
                if not pin_file.exists():
                    return IntegrityDecision(
                        allowed=False,
                        plugin_id=plugin_id,
                        reason=f"pin 清单缺失: {pin_file.name}",
                    )
                pin = load_pin_file(pin_file)
            plugin_id = str(pin.get("plugin_id", ""))

            signature = pin.get("signature")
            signature_verified = False
            if signature is not None:
                if secret is None:
                    return self._deny(plugin_id, "pin 清单带签名但未提供校验密钥")
                if not verify_pin_signature(pin, secret):
                    return self._deny(plugin_id, "pin 清单 HMAC 签名校验失败，清单可能被伪造")
                signature_verified = True
            elif require_signature:
                return self._deny(plugin_id, "策略要求签名但 pin 清单未签名")

            if pin.get("algorithm") != _ALGORITHM:
                return self._deny(
                    plugin_id, f"不支持的哈希算法: {pin.get('algorithm')}"
                )
            if not isinstance(pin.get("files"), dict) or not pin["files"]:
                return self._deny(plugin_id, "pin 清单 files 为空或结构非法")

            return self._compare_files(plugin_dir, pin, plugin_id, signature_verified)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            # 校验器自身读盘/解析异常一律 fail-closed，不放行未验明的插件
            return self._deny(plugin_id, f"完整性校验异常: {type(exc).__name__}: {exc}")

    def _compare_files(
        self,
        plugin_dir: Path,
        pin: dict[str, Any],
        plugin_id: str,
        signature_verified: bool,
    ) -> IntegrityDecision:
        pinned: dict[str, str] = dict(pin["files"])
        mismatched: list[str] = []
        missing: list[str] = []
        verified: list[str] = []

        for rel, expected_hash in sorted(pinned.items()):
            target = plugin_dir / rel
            if target.is_symlink():
                mismatched.append(rel)
                continue
            if not target.is_file():
                missing.append(rel)
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if not hmac.compare_digest(actual, str(expected_hash)):
                mismatched.append(rel)
            else:
                verified.append(rel)

        actual_files = compute_directory_hashes(plugin_dir)
        unexpected = sorted(set(actual_files) - set(pinned))
        # 符号链接不会出现在 actual_files 中，单独作为可疑项并入 unexpected
        for path, is_symlink in _iter_protected_files(plugin_dir):
            if is_symlink:
                unexpected.append(path.relative_to(plugin_dir).as_posix())
        unexpected = sorted(set(unexpected))

        if mismatched or missing or unexpected:
            parts = []
            if mismatched:
                parts.append(f"哈希不匹配 {len(mismatched)} 个: {','.join(mismatched[:5])}")
            if missing:
                parts.append(f"文件缺失 {len(missing)} 个: {','.join(missing[:5])}")
            if unexpected:
                parts.append(f"未登记文件 {len(unexpected)} 个: {','.join(unexpected[:5])}")
            return IntegrityDecision(
                allowed=False,
                plugin_id=plugin_id,
                reason="插件完整性校验失败；" + "；".join(parts),
                verified_files=tuple(verified),
                mismatched=tuple(mismatched),
                missing=tuple(missing),
                unexpected=tuple(unexpected),
                signature_verified=signature_verified,
            )

        return IntegrityDecision(
            allowed=True,
            plugin_id=plugin_id,
            reason="",
            verified_files=tuple(verified),
            signature_verified=signature_verified,
        )

    @staticmethod
    def _deny(plugin_id: str, reason: str) -> IntegrityDecision:
        return IntegrityDecision(allowed=False, plugin_id=plugin_id, reason=reason)


__all__ = [
    "IntegrityDecision",
    "PluginIntegrityGuard",
    "generate_pin_file",
    "write_pin_file",
    "load_pin_file",
    "compute_directory_hashes",
    "verify_pin_signature",
    "PIN_FILE_NAME",
]
