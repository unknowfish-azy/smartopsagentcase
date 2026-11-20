"""Z0-03：评测注册表守卫。

注册表只回答一件事：**这套评测是谁的、跑没跑过**。
指标本身仍留在各 runner 自己的 `latest*.json` 里，注册表不复制指标，
否则迟早出现"manifest 说 0.75、latest.json 说 0.56"的双份真相。

两条防伪规则：
- `status=RUN` 必须能落到磁盘（目录/runner/报告都在）；
- `status=NOT_RUN` 必须 `path=null` 且磁盘上不存在同名指标文件。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO_ROOT / "data" / "training" / "eval"
MANIFEST = EVAL_DIR / "manifest.json"

ALLOWED_KINDS = {"llm_judgement", "numeric_regression", "vision_event", "agent_slo"}
ALLOWED_STATUS = {"RUN", "NOT_RUN"}
REQUIRED_FIELDS = {"id", "kind", "path", "runner", "owner", "status"}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_exists_and_shape_is_minimal():
    manifest = _manifest()
    assert manifest["version"] == 1
    sets = manifest["sets"]
    assert sets, "注册表为空"

    for entry in sets:
        missing = REQUIRED_FIELDS - set(entry)
        assert missing == set(), f"{entry.get('id')} 缺字段：{sorted(missing)}"
        # 指标字段不许进注册表，避免双份真相
        assert set(entry) == REQUIRED_FIELDS, f"{entry['id']} 有多余字段：{sorted(set(entry) - REQUIRED_FIELDS)}"


def test_ids_unique_and_enums_valid():
    sets = _manifest()["sets"]
    ids = [entry["id"] for entry in sets]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    assert duplicates == [], f"评测集 id 重复：{duplicates}"

    for entry in sets:
        assert entry["kind"] in ALLOWED_KINDS, f"{entry['id']} 的 kind 非法：{entry['kind']}"
        assert entry["status"] in ALLOWED_STATUS, f"{entry['id']} 的 status 非法：{entry['status']}"


@pytest.mark.parametrize("entry", _manifest()["sets"], ids=lambda entry: entry["id"])
def test_run_entries_are_actually_on_disk(entry: dict):
    if entry["status"] != "RUN":
        pytest.skip("仅校验 RUN 项")

    assert entry["path"], f"{entry['id']} 标了 RUN 却没有 path"
    assert (REPO_ROOT / entry["path"]).exists(), f"{entry['id']} 的 path 不存在：{entry['path']}"
    assert (REPO_ROOT / entry["runner"]).exists(), f"{entry['id']} 的 runner 不存在：{entry['runner']}"
    assert list(EVAL_DIR.glob("latest*.json")), f"{entry['id']} 标了 RUN 但没有任何 latest*.json"


@pytest.mark.parametrize("entry", _manifest()["sets"], ids=lambda entry: entry["id"])
def test_not_run_entries_have_no_fake_artifacts(entry: dict):
    if entry["status"] != "NOT_RUN":
        pytest.skip("仅校验 NOT_RUN 项")

    assert entry["path"] is None, f"{entry['id']} 未跑却声明了 path：{entry['path']}"
    fakes = sorted(EVAL_DIR.glob(f"*{entry['id']}*"))
    assert fakes == [], f"{entry['id']} 标了 NOT_RUN 但磁盘上有指标文件：{[str(p.name) for p in fakes]}"
