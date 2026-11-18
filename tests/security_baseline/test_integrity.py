"""插件完整性校验测试：哈希钉扎、HMAC 签名、fail-closed 各分支。"""

from __future__ import annotations

import json
import os

import pytest

from agent.security_baseline import (
    PIN_FILE_NAME,
    PluginIntegrityGuard,
    generate_pin_file,
    load_pin_file,
    verify_pin_signature,
    write_pin_file,
)
from agent.security_baseline.audit_sink import _canonical
from agent.security_baseline.integrity import _sign_payload

SECRET = "ops-ci-secret-2026"


@pytest.fixture
def plugin_dir(tmp_path):
    root = tmp_path / "robot"
    (root / "tools").mkdir(parents=True)
    (root / "__pycache__").mkdir()
    (root / "plugin.py").write_text("class RobotPlugin: ...\n", encoding="utf-8")
    (root / "manifest.yaml").write_text("plugin:\n  id: robot\n", encoding="utf-8")
    (root / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tools" / "voice.py").write_text("def speak(): ...\n", encoding="utf-8")
    # 运行态产物不应参与钉扎
    (root / "__pycache__" / "plugin.cpython-314.pyc").write_bytes(b"\x00\x01")
    return root


@pytest.fixture
def guard():
    return PluginIntegrityGuard()


def _write_pin(plugin_dir, **kwargs):
    pin = generate_pin_file(plugin_dir, "robot", **kwargs)
    write_pin_file(plugin_dir / PIN_FILE_NAME, pin)
    return pin


# --------------------------------------------------------------------------
# 正常路径
# --------------------------------------------------------------------------


def test_clean_plugin_passes_unsigned(guard, plugin_dir):
    _write_pin(plugin_dir)
    decision = guard.verify(plugin_dir)

    assert decision.allowed is True
    assert decision.signature_verified is False
    assert set(decision.verified_files) == {
        "manifest.yaml", "plugin.py", "tools/__init__.py", "tools/voice.py",
    }


def test_signed_plugin_passes_with_secret(guard, plugin_dir):
    _write_pin(plugin_dir, secret=SECRET, key_id="ci-1")
    decision = guard.verify(plugin_dir, secret=SECRET)

    assert decision.allowed is True
    assert decision.signature_verified is True


def test_pin_excludes_pycache_and_pin_file_itself(guard, plugin_dir):
    pin = _write_pin(plugin_dir)
    assert all("__pycache__" not in name for name in pin["files"])
    assert PIN_FILE_NAME not in pin["files"]
    assert "tools/voice.py" in pin["files"]  # 嵌套路径用 POSIX 相对键


# --------------------------------------------------------------------------
# 哈希钉扎拦截
# --------------------------------------------------------------------------


def test_tampered_file_is_denied(guard, plugin_dir):
    _write_pin(plugin_dir)
    (plugin_dir / "tools" / "voice.py").write_text("def backdoor(): ...\n", encoding="utf-8")

    decision = guard.verify(plugin_dir)
    assert decision.allowed is False
    assert decision.mismatched == ("tools/voice.py",)
    assert "完整性校验失败" in decision.reason


def test_deleted_pinned_file_is_denied(guard, plugin_dir):
    _write_pin(plugin_dir)
    (plugin_dir / "plugin.py").unlink()

    decision = guard.verify(plugin_dir)
    assert decision.allowed is False
    assert decision.missing == ("plugin.py",)


def test_unexpected_new_file_is_denied(guard, plugin_dir):
    _write_pin(plugin_dir)
    (plugin_dir / "tools" / "backdoor.py").write_text("EVIL = 1\n", encoding="utf-8")

    decision = guard.verify(plugin_dir)
    assert decision.allowed is False
    assert decision.unexpected == ("tools/backdoor.py",)


def test_tampered_file_caught_even_under_valid_signature(guard, plugin_dir):
    # 签名只保护 pin 清单本身，文件篡改仍由哈希比对兜底
    _write_pin(plugin_dir, secret=SECRET)
    (plugin_dir / "plugin.py").write_text("def pwned(): ...\n", encoding="utf-8")

    decision = guard.verify(plugin_dir, secret=SECRET)
    assert decision.allowed is False
    assert decision.mismatched == ("plugin.py",)
    assert decision.signature_verified is True


# --------------------------------------------------------------------------
# 签名分支
# --------------------------------------------------------------------------


def test_wrong_secret_denied(guard, plugin_dir):
    _write_pin(plugin_dir, secret=SECRET)
    decision = guard.verify(plugin_dir, secret="attacker-guess")
    assert decision.allowed is False
    assert "HMAC 签名校验失败" in decision.reason


def test_signed_pin_without_secret_denied(guard, plugin_dir):
    _write_pin(plugin_dir, secret=SECRET)
    decision = guard.verify(plugin_dir)
    assert decision.allowed is False
    assert "未提供校验密钥" in decision.reason


def test_require_signature_rejects_unsigned_pin(guard, plugin_dir):
    _write_pin(plugin_dir)
    decision = guard.verify(plugin_dir, require_signature=True)
    assert decision.allowed is False
    assert "未签名" in decision.reason


def test_pin_content_forgery_invalidates_signature(guard, plugin_dir):
    pin = _write_pin(plugin_dir, secret=SECRET)
    # 攻击者改写钉扎哈希但拿不到密钥重签
    pin["files"]["plugin.py"] = "a" * 64
    write_pin_file(plugin_dir / PIN_FILE_NAME, pin)

    decision = guard.verify(plugin_dir, secret=SECRET)
    assert decision.allowed is False
    assert "HMAC 签名校验失败" in decision.reason


def test_verify_pin_signature_unit():
    pin = {"version": 1, "files": {"a.py": "x"}}
    pin["signature"] = _sign_payload(pin, SECRET, "k1")
    assert verify_pin_signature(pin, SECRET) is True
    assert verify_pin_signature(pin, "wrong") is False

    pin["signature"]["alg"] = "MD5"
    assert verify_pin_signature(pin, SECRET) is False


# --------------------------------------------------------------------------
# fail-closed 边界
# --------------------------------------------------------------------------


def test_missing_pin_file_denied(guard, plugin_dir):
    decision = guard.verify(plugin_dir)
    assert decision.allowed is False
    assert "pin 清单缺失" in decision.reason


def test_empty_files_map_denied(guard, plugin_dir):
    pin = generate_pin_file(plugin_dir, "robot")
    pin["files"] = {}
    write_pin_file(plugin_dir / PIN_FILE_NAME, pin)

    decision = guard.verify(plugin_dir)
    assert decision.allowed is False
    assert "files 为空" in decision.reason


def test_nonexistent_plugin_dir_fails_closed(guard, tmp_path):
    # 目录整体不存在：内联 pin 触发读盘异常，校验器仍须 fail-closed
    pin = {"version": 1, "plugin_id": "ghost", "algorithm": "sha256",
           "files": {"a.py": "0" * 64}}
    decision = guard.verify(tmp_path / "never-existed", pin=pin)
    assert decision.allowed is False
    assert "完整性校验异常" in decision.reason


def test_existing_dir_with_missing_pinned_file_denied(guard, tmp_path):
    # 目录存在但钉扎文件缺失：走 missing 分支，同样拒绝
    root = tmp_path / "plugin-x"
    root.mkdir()
    pin = {"version": 1, "plugin_id": "x", "algorithm": "sha256",
           "files": {"a.py": "0" * 64}}
    decision = guard.verify(root, pin=pin)
    assert decision.allowed is False
    assert decision.missing == ("a.py",)


def test_symlink_is_rejected(guard, plugin_dir):
    _write_pin(plugin_dir)
    outside = plugin_dir.parent / "outside.py"
    outside.write_text("SECRET = 1\n", encoding="utf-8")
    try:
        os.symlink(outside, plugin_dir / "tools" / "link.py")
    except OSError:
        pytest.skip("当前环境无创建符号链接权限")

    decision = guard.verify(plugin_dir)
    assert decision.allowed is False
    assert "tools/link.py" in decision.unexpected


def test_symlink_flag_rejected_without_privilege(guard, plugin_dir, monkeypatch):
    # 无符号链接特权时，用 monkeypatch 模拟 is_symlink 标记覆盖同一拦截分支
    from pathlib import Path

    _write_pin(plugin_dir)
    original = Path.is_symlink

    def fake_is_symlink(self):
        if self.name == "voice.py":
            return True
        return original(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    decision = guard.verify(plugin_dir)
    assert decision.allowed is False
    assert "tools/voice.py" in decision.unexpected


def test_pin_file_round_trip(plugin_dir):
    pin = generate_pin_file(plugin_dir, "robot", secret=SECRET)
    path = plugin_dir / PIN_FILE_NAME
    write_pin_file(path, pin)
    loaded = load_pin_file(path)
    assert loaded == json.loads(path.read_text(encoding="utf-8"))
    assert loaded["plugin_id"] == "robot"
    assert loaded["signature"]["alg"] == "HMAC-SHA256"
    # 签名基于规范化序列化，键顺序重排不影响验签
    raw = json.loads(path.read_text(encoding="utf-8"))
    reordered = {k: raw[k] for k in reversed(list(raw))}
    assert verify_pin_signature(reordered, SECRET) is True
    assert _canonical(reordered) == _canonical(raw)
