# -*- coding: utf-8 -*-
"""
数学建模合成数据生成器
======================
按 SmartOpsAgent 真实表结构生成 90 天的模拟运行数据，列结构与
scripts/export_modeling_data.py 导出的 CSV 完全一致，下游建模代码
可直接在「真实导出」与「合成数据」之间无缝切换。

数据形态设计（对应建模方案）：
  - inspector_event:          日周期 + 周周期 + 缓慢漂移 + 注入 5 段突发异常
                              -> 方案一：时序预测 / 异常检测 / 变点检测
  - model_invocation_usage:   延迟长尾分布 + 冷启动尖峰 + 异常期失败率抬升
                              -> 方案一：延迟序列 / 方案三：性能指标
  - agent_decision_loop:      stage 分布、闭环率、置信度差异
                              -> 方案三：可靠性评价指标
  - operation_run_record / knowledge_candidate: 辅助维度

附带输出 ground_truth_incidents.csv（注入异常的真值窗口），
用于评估方案一问题 2/3 的异常检测与预警准确率。

用法：
  python scripts/generate_modeling_synthetic.py [--days 90] [--seed 42]
输出目录：data/modeling-export-synthetic/
"""

import argparse
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_modeling_data import (  # noqa: E402
    ROOT,
    aggregate_hourly_events,
    aggregate_loop_metrics,
    aggregate_model_usage,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = ROOT / "data" / "modeling-export-synthetic"

SEVERITY_NORMAL = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
SEVERITY_P_NORMAL = [0.55, 0.35, 0.08, 0.02]
SEVERITY_P_INCIDENT = [0.10, 0.25, 0.40, 0.25]  # 异常期高危占比大幅抬升

STATUS_NORMAL = ["RESOLVED", "OPEN", "REVIEW"]
STATUS_P_NORMAL = [0.80, 0.15, 0.05]
STATUS_INCIDENT = ["RESOLVED", "OPEN", "PENDING", "REVIEW"]
STATUS_P_INCIDENT = [0.45, 0.35, 0.12, 0.08]

CATEGORIES = ["LOG_DIAGNOSIS", "INSPECTION", "VISION", "MODEL_DEGRADE", "PATROL_PLAN"]
TARGETS = ["server-01", "server-02", "server-03", "db-primary", "cache-node", "gateway"]
STAGES = ["ANALYZE", "MEMORIZE", "DECIDE", "EXECUTE", "REVIEW", "LEARNED"]
SOURCE_TYPES_LOOP = ["MANUAL", "INSPECTOR", "PATROL", "ALERT"]
SOURCE_TYPES_KC = ["LOG_DIAGNOSIS", "SCIVERSE", "INSPECTION", "CRAWL"]
KC_STATUS = ["PENDING_REVIEW", "ADOPTED", "REJECTED"]
KC_STATUS_P = [0.55, 0.35, 0.10]
MODELS = ["qwen2.5vl:3b", "qwen2.5:7b", "deepseek-r1:8b"]


def hour_multiplier(ts: pd.Timestamp) -> float:
    """时间乘子：日周期（工作时段高）+ 周周期（工作日高）。"""
    hour_factor = {**{h: 0.4 for h in range(0, 7)},
                   **{h: 0.9 for h in range(7, 9)},
                   **{h: 1.6 for h in range(9, 12)},
                   **{h: 1.3 for h in range(12, 14)},
                   **{h: 1.6 for h in range(14, 18)},
                   **{h: 1.0 for h in range(18, 22)},
                   **{h: 0.5 for h in range(22, 24)}}
    weekday_factor = 1.2 if ts.weekday() < 5 else (1.0 if ts.weekday() == 5 else 0.7)
    return hour_factor[ts.hour] * weekday_factor


def plan_incidents(rng: np.random.Generator, index: pd.DatetimeIndex) -> list[dict]:
    """在时序中布置互不重叠的异常窗口，并追加末段缓升漂移。"""
    incidents = []
    n_hours = len(index)
    # 5 段突发异常：随机分布在中后段，长度 3~10 小时，强度 4~8 倍
    starts = sorted(rng.choice(np.arange(n_hours // 4, n_hours - 48), size=5, replace=False))
    for i, s in enumerate(starts):
        length = int(rng.integers(3, 11))
        incidents.append({
            "incident_id": f"INC-{i + 1:03d}",
            "type": "SPIKE",
            "start": index[int(s)],
            "end": index[min(int(s) + length, n_hours - 1)],
            "rate_multiplier": float(rng.uniform(4.0, 8.0)),
            "failure_boost": float(rng.uniform(0.15, 0.35)),
        })
    return incidents


def drift_multiplier(ts: pd.Timestamp, index: pd.DatetimeIndex, drift_days: int) -> float:
    """末段缓升漂移：最后 drift_days 天内基线从 1.0 缓升至 1.4（模拟隐患积累）。"""
    last = index[-1]
    days_left = (last - ts).total_seconds() / 86400.0
    if days_left >= drift_days:
        return 1.0
    return 1.0 + 0.4 * (1.0 - days_left / drift_days)


def in_incident(ts, incidents):
    for inc in incidents:
        if inc["start"] <= ts <= inc["end"]:
            return inc
    return None


def gen_inspector_events(rng, index, incidents, base_lambda=2.5):
    rows = []
    for ts in index:
        inc = in_incident(ts, incidents)
        lam = base_lambda * hour_multiplier(ts) * drift_multiplier(ts, index, 20)
        if inc:
            lam *= inc["rate_multiplier"]
        n = rng.poisson(lam)
        for _ in range(n):
            rows.append({
                "id": uuid.uuid4().hex[:32],
                "task_id": f"task-{rng.integers(1000, 9999)}",
                "target": rng.choice(TARGETS),
                "status": rng.choice(STATUS_INCIDENT, p=STATUS_P_INCIDENT) if inc
                          else rng.choice(STATUS_NORMAL, p=STATUS_P_NORMAL),
                "severity": rng.choice(SEVERITY_NORMAL, p=SEVERITY_P_INCIDENT) if inc
                            else rng.choice(SEVERITY_NORMAL, p=SEVERITY_P_NORMAL),
                "category": rng.choice(CATEGORIES),
                "requires_human": bool(rng.random() < (0.35 if inc else 0.05)),
                "agent_claim": f"自动研判：{rng.choice(CATEGORIES)} 类风险，置信度 {rng.uniform(0.5, 0.95):.2f}",
                "reason": "合成数据：模拟异常信号触发纠察规则",
                "recommendation": "建议人工复核或执行预案",
                "created_at": ts,
            })
    return pd.DataFrame(rows)


def gen_model_invocations(rng, index, incidents, base_lambda=8):
    rows = []
    for ts in index:
        inc = in_incident(ts, incidents)
        lam = base_lambda * hour_multiplier(ts)
        n = rng.poisson(lam)
        for _ in range(n):
            model = rng.choice(MODELS)
            # 延迟：对数正态长尾；10% 概率冷启动尖峰；异常期延迟抬升 1.6 倍
            duration = float(rng.lognormal(mean=np.log(320), sigma=0.35))
            if rng.random() < 0.10:
                duration += rng.uniform(1500, 4000)  # 冷启动
            if inc:
                duration *= rng.uniform(1.4, 1.9)
            # 失败率：基线 3%，异常期抬升至 15%~50%
            p_fail = 0.03 if inc is None else inc["failure_boost"]
            status = "FAILED" if rng.random() < p_fail else "SUCCESS"
            rows.append({
                "id": str(uuid.uuid4()),
                "user_id": int(rng.integers(1, 5)),
                "connection_id": int(rng.integers(1, 4)),
                "model_name": model,
                "started_at": ts,
                "status": status,
                "duration_ms": int(duration),
                "input_tokens": int(rng.lognormal(mean=np.log(280), sigma=0.4)),
                "output_tokens": int(rng.lognormal(mean=np.log(480), sigma=0.4)),
                "total_tokens": 0,  # 占位，下方合并
            })
    df = pd.DataFrame(rows)
    df["total_tokens"] = df["input_tokens"] + df["output_tokens"]
    return df


def gen_decision_loops(rng, index, incidents, base_lambda=0.12):
    rows = []
    for ts in index:
        inc = in_incident(ts, incidents)
        lam = base_lambda * hour_multiplier(ts)
        n = rng.poisson(lam)
        for _ in range(n):
            stage = rng.choice(STAGES, p=[0.30, 0.10, 0.20, 0.15, 0.15, 0.10])
            closed = rng.random() < (0.95 if stage in ("REVIEW", "LEARNED") else 0.45)
            rows.append({
                "id": uuid.uuid4().hex[:32],
                "user_id": int(rng.integers(1, 5)),
                "incident_key": f"loop-{rng.integers(100, 999)}",
                "source_type": rng.choice(SOURCE_TYPES_LOOP),
                "stage": stage,
                "severity": "HIGH" if inc else rng.choice(["LOW", "MEDIUM", "HIGH"], p=[0.3, 0.5, 0.2]),
                "requires_human": bool(rng.random() < (0.4 if inc else 0.12)),
                "outcome": "RESOLVED" if closed else None,
                "confidence": float(np.clip(rng.normal(0.75 if closed else 0.45, 0.12), 0.05, 0.99)),
                "learned_count": int(rng.integers(0, 6)) if closed else 0,
                "reviewed_at": ts + pd.Timedelta(hours=float(rng.uniform(1, 8))) if closed else None,
                "created_at": ts,
                "updated_at": ts + pd.Timedelta(hours=float(rng.uniform(0.5, 9))),
            })
    return pd.DataFrame(rows)


def gen_run_records(rng, index, incidents, base_lambda=0.5):
    rows = []
    for ts in index:
        inc = in_incident(ts, incidents)
        n = rng.poisson(base_lambda)
        for _ in range(n):
            ok = inc is None and rng.random() < 0.92
            status = "SUCCESS" if ok else rng.choice(["FAILED", "TIMEOUT"], p=[0.6, 0.4])
            started = ts + pd.Timedelta(minutes=float(rng.uniform(0, 55)))
            dur = rng.uniform(30, 900) if ok else rng.uniform(600, 3600)
            rows.append({
                "id": int(rng.integers(10**8, 10**9)),
                "trace_id": uuid.uuid4().hex[:64],
                "user_id": int(rng.integers(1, 5)),
                "tool_id": rng.choice(["ssh-exec", "http-probe", "log-collect", "db-check"]),
                "status": status,
                "started_at": started,
                "ended_at": started + pd.Timedelta(seconds=float(dur)),
                "created_at": started,
            })
    return pd.DataFrame(rows)


def gen_knowledge_candidates(rng, index, base_lambda=0.8):
    rows = []
    for ts in index:
        n = rng.poisson(base_lambda * (1.2 if ts.weekday() < 5 else 0.6))
        for _ in range(n):
            rows.append({
                "id": int(rng.integers(10**8, 10**9)),
                "user_id": int(rng.integers(1, 5)),
                "source_type": rng.choice(SOURCE_TYPES_KC),
                "trace_id": uuid.uuid4().hex[:64],
                "tool_id": rng.choice(["log-diagnosis", "web-research", "inspector", "crawler"]),
                "title": f"合成知识候选 #{rng.integers(1, 9999)}",
                "status": rng.choice(KC_STATUS, p=KC_STATUS_P),
                "created_at": ts,
                "updated_at": ts + pd.Timedelta(hours=float(rng.uniform(1, 72))),
            })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="生成建模合成数据")
    parser.add_argument("--days", type=int, default=90, help="生成时长（天）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    end = pd.Timestamp.now().floor("h")
    index = pd.date_range(end=end - pd.Timedelta(hours=1), periods=args.days * 24, freq="1h")
    incidents = plan_incidents(rng, index)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"生成范围：{index[0]} ~ {index[-1]}（{args.days} 天，seed={args.seed}）")
    print(f"注入异常窗口：{len(incidents)} 段突发 + 末段 20 天缓升漂移\n")

    def save(df: pd.DataFrame, name: str):
        df.to_csv(OUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")
        print(f"  {name}: {len(df)} 行 -> {name}.csv")

    ev = gen_inspector_events(rng, index, incidents)
    mu = gen_model_invocations(rng, index, incidents)
    loop = gen_decision_loops(rng, index, incidents)
    runs = gen_run_records(rng, index, incidents)
    kcs = gen_knowledge_candidates(rng, index)

    save(ev, "inspector_events")
    save(mu, "model_invocation_usage")
    save(loop, "agent_decision_loop")
    save(runs, "operation_run_record")
    save(kcs, "knowledge_candidates")

    print("\n[聚合层（复用导出脚本聚合函数）]")
    hourly = aggregate_hourly_events(ev)
    hourly_mu = aggregate_model_usage(mu)
    stage_metrics = aggregate_loop_metrics(loop)
    save(hourly, "hourly_event_series")
    save(hourly_mu, "model_usage_hourly")
    save(stage_metrics, "loop_stage_metrics")

    # 真值标注：异常检测/预警评估的 ground truth
    gt = pd.DataFrame([{
        "incident_id": inc["incident_id"],
        "type": inc["type"],
        "start": inc["start"],
        "end": inc["end"],
        "rate_multiplier": round(inc["rate_multiplier"], 2),
        "failure_boost": round(inc["failure_boost"], 2),
    } for inc in incidents])
    gt.to_csv(OUT_DIR / "ground_truth_incidents.csv", index=False, encoding="utf-8-sig")
    print(f"  ground_truth_incidents: {len(gt)} 行 -> ground_truth_incidents.csv")

    print("\n[自检：异常窗口 vs 正常时段事件均值]")
    hourly["created_at"] = pd.to_datetime(hourly["created_at"])
    normal = hourly[~hourly["created_at"].apply(lambda t: in_incident(t, incidents) is not None)]["total"]
    for inc in incidents:
        seg = hourly[(hourly["created_at"] >= inc["start"]) & (hourly["created_at"] <= inc["end"])]["total"]
        ratio = seg.mean() / max(normal.mean(), 1e-9)
        print(f"  {inc['incident_id']}: 窗口均值 {seg.mean():.1f} / 正常均值 {normal.mean():.1f} = {ratio:.1f}x")
    print(f"\n完成。输出目录：{OUT_DIR}")


if __name__ == "__main__":
    main()
