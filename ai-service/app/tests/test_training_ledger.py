"""训练账本的降级与本地配置加载。"""

import json
import os

from scripts import training_ledger


def test_load_env_file_fills_missing_without_override(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text('MYSQL_PASSWORD="secret"\nOTHER_KEY=1\n', encoding="utf-8")

    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
    training_ledger._load_env_file(env)
    assert os.environ["MYSQL_PASSWORD"] == "secret"
    # 只补 MYSQL_*，不把任意变量带进进程环境
    assert "OTHER_KEY" not in os.environ

    monkeypatch.setenv("MYSQL_PASSWORD", "kept")
    training_ledger._load_env_file(env)
    assert os.environ["MYSQL_PASSWORD"] == "kept"


def test_record_training_run_falls_back_to_jsonl(monkeypatch, tmp_path):
    """数据库不可用时不能让训练流程失败，记录落 JSONL 兜底文件。"""
    monkeypatch.setattr(training_ledger, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(training_ledger, "_execute_mysql", lambda *args, **kwargs: None)

    assert training_ledger.record_training_run(
        base_model="demo-model", method="demo-method", metrics={"f1": 0.5}
    ) is None

    lines = (tmp_path / "training_run.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["method"] == "demo-method"
    assert record["metrics"] == {"f1": 0.5}
    assert record["_storage"] == "jsonl"
