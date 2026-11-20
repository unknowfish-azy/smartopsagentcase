"""训练账本记录模块（P0-1 修复）。

把训练/评测过程写入后端数据库的 training_run / evaluation_run / model_registry 表，
让"训练过"可追溯、可复算。

设计原则：
* **尽力而为（best-effort）**：数据库不可用时降级为写本地 JSONL，绝不阻塞训练流程。
* **零强依赖**：不强制安装 pymysql，缺失时用标准库 sqlite3 或纯 JSONL 兜底。
* **幂等登记**：同一 (name, version) 的模型重复登记不报错（INSERT ... ON DUPLICATE KEY UPDATE）。
* **诚实口径**：fallback 路径的记录在 metrics_json 中标注 `storage=jsonl`，不冒充 DB 落库。

用法（在训练脚本中）：

    from scripts.training_ledger import record_training_run, register_model

    run_id = record_training_run(
        base_model="AnomalyTransformer",
        method="anomaly_transformer",
        params={"window": 64, "epochs": 20},
        metrics={"f1": 0.87, "precision": 0.91, "recall": 0.83},
        artifact_uri="data/models/anomaly_transformer/anomaly_transformer.pt",
    )
    register_model(
        name="anomaly_transformer",
        version="v1",
        task_type="anomaly_detection",
        artifact_uri="data/models/anomaly_transformer/anomaly_transformer.pt",
        metrics={"f1": 0.87},
    )
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 账本 JSONL 兜底目录：数据库不可用时所有记录落这里
_LEDGER_DIR = Path(__file__).resolve().parents[2] / "data" / "training_ledger"
_LEDGER_DIR.mkdir(parents=True, exist_ok=True)

# 本地开发便捷入口：训练脚本通常直接在 shell 里跑，不会先 source 仓库根 .env
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_ENV_KEYS = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USERNAME", "MYSQL_PASSWORD", "MYSQL_DATABASE")


def _load_env_file(path: Path = _ENV_FILE) -> None:
    """把仓库根 .env 里的 MYSQL_* 补进进程环境（不覆盖已存在的值，缺失文件静默跳过）。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in _ENV_KEYS or os.environ.get(key):
            continue
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ[key] = value


_load_env_file()


def _db_config() -> dict[str, str]:
    """从环境变量读取数据库连接配置。"""
    return {
        "host": os.environ.get("MYSQL_HOST", "localhost"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USERNAME", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", "root"),
        "database": os.environ.get("MYSQL_DATABASE", "smartops"),
    }


def _mysql_available() -> bool:
    """探测 pymysql 是否安装且数据库可达。"""
    try:
        import pymysql  # type: ignore
    except ImportError:
        return False
    cfg = _db_config()
    try:
        conn = pymysql.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


def _write_jsonl(table: str, record: dict[str, Any]) -> None:
    """JSONL 兜底：每条记录一行，文件名 = 表名。"""
    record = dict(record)
    record["_storage"] = "jsonl"
    record["_written_at"] = datetime.now(timezone.utc).isoformat()
    path = _LEDGER_DIR / f"{table}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _execute_mysql(sql: str, params: tuple = ()) -> int | None:
    """执行 MySQL 写入，返回 lastrowid；失败返回 None（由调用方降级 JSONL）。"""
    try:
        import pymysql  # type: ignore
    except ImportError:
        return None
    cfg = _db_config()
    try:
        conn = pymysql.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                last_id = cur.lastrowid
            conn.commit()
            return last_id
        finally:
            conn.close()
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dataset(name: str, task_type: str, storage_uri: str = "data/lake") -> int | None:
    """确保默认数据集存在并返回 id（脚本未显式登记数据集时使用）。

    training_run / evaluation_run 的 dataset_id 是 NOT NULL + 外键，缺省会整条插入失败；
    这里用 (name, split) 唯一键做 upsert，并用 LAST_INSERT_ID(id) 让重复命中时也能拿回 id。
    """
    sql = """
        INSERT INTO training_dataset
            (name, task_type, source, sample_count, storage_uri, split, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)
    """
    return _execute_mysql(
        sql,
        (name, task_type, "training_script", 0, storage_uri, "train", "脚本未显式登记数据集，自动创建"),
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def record_training_run(
    *,
    base_model: str,
    method: str,
    params: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    artifact_uri: str | None = None,
    dataset_id: int | None = None,
    status: str = "COMPLETED",
) -> int | None:
    """登记一次训练运行，返回 run_id（MySQL）或 None（JSONL 降级）。"""
    started = _now_iso()
    if dataset_id is None:
        dataset_id = _ensure_dataset(f"{method}-default", method)
    sql = """
        INSERT INTO training_run
            (dataset_id, base_model, method, params_json, status, metrics_json,
             artifact_uri, started_at, finished_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params_json = json.dumps(params or {}, ensure_ascii=False, default=str)
    metrics_json = json.dumps(metrics or {}, ensure_ascii=False, default=str)
    last_id = _execute_mysql(
        sql,
        (
            dataset_id,
            base_model,
            method,
            params_json,
            status,
            metrics_json,
            artifact_uri,
            started,
            started,  # 简化：训练脚本一次性跑完，started≈finished
        ),
    )
    if last_id is None:
        _write_jsonl(
            "training_run",
            {
                "base_model": base_model,
                "method": method,
                "params": params or {},
                "status": status,
                "metrics": metrics or {},
                "artifact_uri": artifact_uri,
            },
        )
    return last_id


def record_evaluation_run(
    *,
    model_ref: str,
    metrics: dict[str, Any] | None = None,
    report_uri: str | None = None,
    dataset_id: int | None = None,
    note: str | None = None,
) -> int | None:
    """登记一次评测运行，返回 eval_id（MySQL）或 None（JSONL 降级）。"""
    if dataset_id is None:
        dataset_id = _ensure_dataset(f"{model_ref}-eval", "evaluation")
    sql = """
        INSERT INTO evaluation_run
            (dataset_id, model_ref, status, metrics_json, report_uri, note)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    metrics_json = json.dumps(metrics or {}, ensure_ascii=False, default=str)
    last_id = _execute_mysql(
        sql,
        (
            dataset_id,
            model_ref,
            "COMPLETED",
            metrics_json,
            report_uri,
            note,
        ),
    )
    if last_id is None:
        _write_jsonl(
            "evaluation_run",
            {
                "model_ref": model_ref,
                "metrics": metrics or {},
                "report_uri": report_uri,
                "note": note,
            },
        )
    return last_id


def register_model(
    *,
    name: str,
    version: str,
    task_type: str,
    artifact_uri: str,
    metrics: dict[str, Any] | None = None,
    status: str = "STAGED",
) -> int | None:
    """登记模型到 model_registry，幂等（同 name+version 更新 metrics/status）。

    返回 model_id（MySQL）或 None（JSONL 降级）。
    """
    metrics_json = json.dumps(metrics or {}, ensure_ascii=False, default=str)
    sql = """
        INSERT INTO model_registry
            (name, version, task_type, artifact_uri, status, metrics_json)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            artifact_uri = VALUES(artifact_uri),
            status = VALUES(status),
            metrics_json = VALUES(metrics_json)
    """
    last_id = _execute_mysql(
        sql,
        (name, version, task_type, artifact_uri, status, metrics_json),
    )
    if last_id is None:
        _write_jsonl(
            "model_registry",
            {
                "name": name,
                "version": version,
                "task_type": task_type,
                "artifact_uri": artifact_uri,
                "status": status,
                "metrics": metrics or {},
            },
        )
    return last_id


def record_dataset(
    *,
    name: str,
    task_type: str,
    source: str,
    sample_count: int,
    storage_uri: str,
    split: str = "train",
    note: str | None = None,
) -> int | None:
    """登记数据集，返回 dataset_id（MySQL）或 None（JSONL 降级）。"""
    sql = """
        INSERT INTO training_dataset
            (name, task_type, source, sample_count, storage_uri, split, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            sample_count = VALUES(sample_count),
            storage_uri = VALUES(storage_uri),
            id = LAST_INSERT_ID(id)
    """
    last_id = _execute_mysql(
        sql,
        (name, task_type, source, sample_count, storage_uri, split, note),
    )
    if last_id is None:
        _write_jsonl(
            "training_dataset",
            {
                "name": name,
                "task_type": task_type,
                "source": source,
                "sample_count": sample_count,
                "storage_uri": storage_uri,
                "split": split,
                "note": note,
            },
        )
    return last_id


def ledger_status() -> dict[str, Any]:
    """返回账本存储状态，供体检脚本调用。"""
    mysql_ok = _mysql_available()
    jsonl_files = list(_LEDGER_DIR.glob("*.jsonl"))
    return {
        "mysql_available": mysql_ok,
        "jsonl_fallback_dir": str(_LEDGER_DIR),
        "jsonl_files": {f.name: sum(1 for _ in f.open(encoding="utf-8")) for f in jsonl_files},
    }


if __name__ == "__main__":
    import pprint

    pprint.pprint(ledger_status())
