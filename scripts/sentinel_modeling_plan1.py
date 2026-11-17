# -*- coding: utf-8 -*-
"""
方案一落地脚本：把建模论文的 STL + 孤立森林 + CUSUM 接进哨兵监控
=================================================================

数据流：
  sentinel_metric_sample ──读─▶ 按 task_id + metric 聚合时序
          │
          ▼
     STL 分解（24 小时周期）
          │
          ▼
     残差 → Isolation Forest 打分（污染率 0.02）
          │                              │
          ├─── 异常判定 ───▶ 写回 abnormal 字段    ← Java 端 SentinelThreshold 读取
          │
          └─── CUSUM 变点 ──▶ 建议阈值写 sentinel_learning_profile  ← Guardian 建议链路

脚本**零侵入 Java**：只写 sentinel_metric_sample.abnormal 和 sentinel_learning_profile。
SentinelPoller 轮询到 abnormal=1 的样本时，走现有 SentinelThreshold.debounce 触发告警，
和固定阈值的判定路径完全一样，只是数据源升级了。

用法：
  # 默认：对所有启用中的哨兵任务跑一次完整链路，写回 DB
  python scripts/sentinel_modeling_plan1.py

  # 只看效果不写 DB（dry-run）
  python scripts/sentinel_modeling_plan1.py --dry-run

  # 只跑某个任务
  python scripts/sentinel_modeling_plan1.py --task-id 42

  # 扫描过去 N 天数据
  python scripts/sentinel_modeling_plan1.py --days 90

  # 连接参数（默认读 application-local.yml 里的 localhost/root/root/smartops）
  python scripts/sentinel_modeling_plan1.py --host 127.0.0.1 --port 3306 --user root --password root --db smartops
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# 抑制 MLPRegressor 的 ConvergenceWarning（哨兵时序只有几百样本，收敛警告不影响结论）
warnings.filterwarnings("ignore", category=UserWarning,
                        message=".*Maximum iterations.*optimization hasn't converged.*")

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# 确保输出不乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# matplotlib 只在需要画图时导入（避免无显示环境崩溃）
HAS_STTS = False
HAS_SKL = False
try:
    from statsmodels.tsa.seasonal import STL
    HAS_STTS = True
except ImportError:
    print("⚠️  statsmodels 未安装，将跳过 STL 分解", file=sys.stderr)
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    HAS_SKL = True
except ImportError:
    print("⚠️  scikit-learn 未安装，将跳过孤立森林 + Autoencoder", file=sys.stderr)


# ───────────────────────────── 数学建模核心 ─────────────────────────────

def infer_period(series: pd.Series, default: int = 24) -> int:
    """
    从时间序列的采样间隔推断 STL period（每天多少个采样点）。
    采样间隔用相邻时间戳的众数，然后 86400 / 间隔秒数 = 每天采样点。
    样本太少或间隔异常时回退到 default。
    """
    if len(series.index) < 2:
        return default
    try:
        diffs = series.index.to_series().diff().dropna().dt.total_seconds().to_numpy()
        if len(diffs) == 0 or np.all(diffs <= 0):
            return default
        # 众数
        median_diff = float(np.median(diffs))
        if median_diff <= 0:
            return default
        daily = int(round(86400.0 / median_diff))
        # 合理范围：每小时 1 次 ~ 每秒 1 次
        return max(24, min(86400, daily))
    except Exception:
        return default


def run_stl_iforest(series: pd.Series, period: int = 24, contamination: float = 0.02) -> dict:
    """
    STL 分解 + 孤立森林异常检测。

    返回 dict: {
        'stl_available': bool,
        'residual': np.ndarray | None,
        'iforest_score': np.ndarray | None,        # 原始 anomaly score（越小越异常）
        'abnormal_by_iforest': np.ndarray,         # 0/1 数组
        'abnormal_threshold': float,                # 判定阈值（iforest_score 低于它则异常）
        'trend_strength': float | None,             # 趋势方差占比
        'season_strength': float | None,            # 季节方差占比
        'constant_series': bool,                    # 序列方差为零（哨兵刚上线）
    }
    """
    n = len(series)
    values = series.to_numpy(dtype=float)
    out = {
        "stl_available": False,
        "residual": None,
        "iforest_score": None,
        "abnormal_by_iforest": np.zeros(n, dtype=np.int8),
        "abnormal_threshold": -0.5,
        "trend_strength": None,
        "season_strength": None,
        "constant_series": False,
    }

    # 常量序列：跳过所有检测（std=0 时孤立森林无法区分，CUSUM 也没意义）
    if n >= 2 and float(np.std(values)) < 1e-9:
        out["constant_series"] = True
        return out

    if n < period * 2 + 5 or not HAS_STTS:
        # 样本太少，跳过 STL，直接对原值跑孤立森林
        values = series.to_numpy(dtype=float).reshape(-1, 1)
        if HAS_SKL and n >= 10:
            try:
                model = IsolationForest(
                    n_estimators=100, contamination=contamination, random_state=42
                )
                model.fit(values)
                scores = model.decision_function(values)
                out["iforest_score"] = scores
                threshold = np.quantile(scores, contamination)
                out["abnormal_threshold"] = float(threshold)
                out["abnormal_by_iforest"] = (scores <= threshold).astype(np.int8)
            except Exception as exc:
                print(f"  ⚠️  孤立森林失败：{exc}", file=sys.stderr)
        return out

    # STL 分解
    # seasonal 参数必须是奇数 >= 3（Loess 窗口要求对称）
    # 取 ≈ period/7 向下取奇数（经验值）
    seasonal = max(3, period // 7)
    if seasonal % 2 == 0:
        seasonal += 1  # 确保奇数
    # 如果 period 本身就是偶数，STL 会自动处理，不强制要求
    try:
        stl = STL(series, period=period, seasonal=seasonal, robust=True)
        res = stl.fit()
        trend = res.trend.to_numpy()
        season = res.seasonal.to_numpy()
        resid = res.resid.to_numpy()
        observed = series.to_numpy()

        total_var = np.var(observed) + 1e-9
        out["trend_strength"] = float(np.var(trend) / total_var)
        out["season_strength"] = float(np.var(season) / total_var)
        out["residual"] = resid
        out["stl_available"] = True
    except Exception as exc:
        print(f"  ⚠️  STL 失败：{exc}", file=sys.stderr)
        values = series.to_numpy(dtype=float).reshape(-1, 1)
        if HAS_SKL and n >= 10:
            try:
                model = IsolationForest(
                    n_estimators=100, contamination=contamination, random_state=42
                )
                model.fit(values)
                scores = model.decision_function(values)
                out["iforest_score"] = scores
                threshold = np.quantile(scores, contamination)
                out["abnormal_threshold"] = float(threshold)
                out["abnormal_by_iforest"] = (scores <= threshold).astype(np.int8)
            except Exception as e:
                print(f"  ⚠️  孤立森林失败：{e}", file=sys.stderr)
        return out

    # 对残差跑孤立森林
    if not HAS_SKL:
        return out

    # 多维：原值 + 残差 + 时间戳正弦编码（捕获周周期）
    values = np.column_stack([
        observed.reshape(-1, 1),
        resid.reshape(-1, 1),
        np.sin(np.arange(n) * 2 * np.pi / period).reshape(-1, 1),
        np.cos(np.arange(n) * 2 * np.pi / period).reshape(-1, 1),
    ])

    try:
        model = IsolationForest(
            n_estimators=200, contamination=contamination, random_state=42, n_jobs=-1
        )
        model.fit(values)
        scores = model.decision_function(values)
        out["iforest_score"] = scores
        threshold = np.quantile(scores, contamination)
        out["abnormal_threshold"] = float(threshold)
        out["abnormal_by_iforest"] = (scores <= threshold).astype(np.int8)
    except Exception as exc:
        print(f"  ⚠️  孤立森林失败：{exc}", file=sys.stderr)

    return out


def cusum_changepoints(series: pd.Series, delta: float = 0.5, h: float = 5.0) -> dict:
    """
    双侧 CUSUM 变点检测。

    返回 {'changepoints': list[int], 'delays_hours': list[float]}
    每个变点 = 触发告警的样本索引；delta 是允许漂移量（标准差倍数），h 是判决门限。
    """
    n = len(series)
    if n < 30:
        return {"changepoints": [], "delays_hours": []}

    values = series.to_numpy(dtype=float)
    mean = np.mean(values)
    std = max(np.std(values), 1e-6)
    z = (values - mean) / std  # 标准化

    # 正向累积和
    s_pos = np.zeros(n)
    for i in range(1, n):
        s_pos[i] = max(0.0, s_pos[i - 1] + z[i] - delta)

    # 负向累积和
    s_neg = np.zeros(n)
    for i in range(1, n):
        s_neg[i] = max(0.0, s_neg[i - 1] - z[i] - delta)

    changepoints = []
    for i in range(10, n):  # 跳过前 10 个，等累积稳定
        if s_pos[i] > h and s_pos[i - 1] <= h:
            changepoints.append(i)
        if s_neg[i] > h and s_neg[i - 1] <= h:
            changepoints.append(i)

    # 合并太近的变点（3 个样本内合并）
    merged = []
    for cp in sorted(changepoints):
        if not merged or cp - merged[-1] > 3:
            merged.append(cp)

    # 延迟估算：从第一个越界样本到触发点的距离
    delays = []
    for cp in merged:
        # 回溯找第一个残差显著偏离均值的样本
        lookback = max(0, cp - 20)
        for j in range(cp - 1, lookback - 1, -1):
            if abs(z[j]) > 1.5:  # 偏离均值 1.5σ 以上
                delays.append(cp - j)
                break
        else:
            delays.append(0)

    return {"changepoints": merged, "delays_hours": delays}


# ───────────────────────────── DB 交互 ─────────────────────────────

@dataclass
class DBCfg:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = "password"
    database: str = "smartops"


def connect(cfg: DBCfg):
    import pymysql
    return pymysql.connect(
        host=cfg.host, port=cfg.port, user=cfg.user, password=cfg.password,
        database=cfg.database, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def fetch_tasks(conn, task_id: Optional[int] = None):
    """拉启用中的哨兵任务（带阈值模板 rules_json，供 TTC 预测用）。"""
    with conn.cursor() as cur:
        if task_id:
            cur.execute(
                """SELECT t.id, t.user_id, t.name, t.template_id, p.rules_json
                     FROM sentinel_task t
                     LEFT JOIN sentinel_threshold_template p ON p.id = t.template_id
                    WHERE t.id=%s AND t.enabled=1""",
                (task_id,)
            )
        else:
            cur.execute(
                """SELECT t.id, t.user_id, t.name, t.template_id, p.rules_json
                     FROM sentinel_task t
                     LEFT JOIN sentinel_threshold_template p ON p.id = t.template_id
                    WHERE t.enabled=1 AND t.template_id IS NOT NULL ORDER BY t.id"""
            )
        return cur.fetchall()


def parse_rules(rules_json: str | None) -> dict[str, dict]:
    """解析阈值模板 rules_json → {metric: {operator, value}}。"""
    if not rules_json:
        return {}
    try:
        items = json.loads(rules_json)
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for item in items if isinstance(items, list) else []:
        try:
            m = str(item.get("metric", "")).strip()
            v = float(item.get("value"))
            op = str(item.get("operator", "gt")).strip()
            if m:
                out[m] = {"operator": op, "value": v}
        except Exception:
            continue
    return out


def fetch_samples(conn, task_id: int, days: int = 90) -> dict[str, pd.Series]:
    """
    把某个 task_id 的所有 metric 按时间升序拉出来，返回 {metric: pd.Series(sampled_at, value_num)}。
    """
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, metric, sampled_at, value_num, abnormal
                 FROM sentinel_metric_sample
                WHERE task_id=%s AND sampled_at >= %s AND value_num IS NOT NULL
                ORDER BY sampled_at ASC""",
            (task_id, since)
        )
        rows = cur.fetchall()

    if not rows:
        return {}

    # 按 metric 分组
    groups: dict[str, list] = {}
    for r in rows:
        m = r["metric"]
        groups.setdefault(m, []).append(r)

    out: dict[str, pd.Series] = {}
    for metric, items in groups.items():
        times = pd.to_datetime([x["sampled_at"] for x in items])
        values = np.array([float(x["value_num"]) for x in items])
        out[metric] = pd.Series(values, index=times, name=f"task{task_id}:{metric}")
    return out


def update_abnormal(conn, task_id: int, metric: str, new_values: list[int],
                    sampled_ats: list[datetime]) -> int:
    """
    批量更新 sentinel_metric_sample.abnormal 字段。
    用 CASE WHEN 按 (sampled_at, task_id, metric) 定位；未匹配到的行保持原值不变。
    """
    if not new_values:
        return 0
    BATCH = 500
    changed = 0
    tuples = list(zip(sampled_ats, new_values))
    for start in range(0, len(tuples), BATCH):
        batch = tuples[start:start + BATCH]
        with conn.cursor() as cur:
            # 先删这个 task+metric 的旧 abnormal 标记（避免旧残留）
            # 用 CASE WHEN 逐个更新，ELSE 保持原值
            when_clauses = []
            params = []
            sampled_at_list = []
            for sampled_at, val in batch:
                when_clauses.append("WHEN sampled_at = %s THEN %s")
                params.extend([sampled_at, int(val)])
                sampled_at_list.append(sampled_at)
            params.extend([task_id, metric])
            sql = (
                "UPDATE sentinel_metric_sample "
                "SET abnormal = CASE "
                + " ".join(when_clauses)
                + " ELSE abnormal END "
                "WHERE task_id = %s AND metric = %s AND sampled_at IN ("
                + ", ".join(["%s"] * len(batch)) + ")"
            )
            params.extend(sampled_at_list)
            try:
                cur.execute(sql, params)
                changed += cur.rowcount
            except Exception as exc:
                print(f"  ⚠️  abnormal 更新失败：{exc}", file=sys.stderr)
                conn.rollback()
                return 0
    return changed


def upsert_profile(conn, user_id: int, task_id: int, task_name: str, metric: str,
                   sample_count: int, mean: float, std_val: float, p95: float, p05: float,
                   suggested_threshold: float,
                   iforest_abnormal_count: int):
    """
    写一条 sentinel_learning_profile。只使用表中已有的字段，
    STL / CUSUM 等更细的分析结果由脚本独立的 JSON 报告承载。
    """
    ts = datetime.now()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM sentinel_learning_profile WHERE task_id=%s AND metric=%s LIMIT 1",
            (task_id, metric)
        )
        existing = cur.fetchone()

        # status 逻辑：IForest 检出的异常数为 0 → STABLE；有异常 → SUGGESTED
        # 给 Guardian 一个合理的语义（它会把 SUGGESTED 呈给用户确认）
        status = "STABLE" if iforest_abnormal_count == 0 else "SUGGESTED"

        if existing:
            cur.execute(
                """UPDATE sentinel_learning_profile
                      SET sample_count=%s, avg_value=%s, p95_value=%s,
                          min_value=%s, max_value=%s,
                          suggested_threshold=%s, status=%s, updated_at=%s
                    WHERE id=%s""",
                (sample_count, mean, p95, p05, mean + std_val,
                 suggested_threshold, status, ts, existing["id"])
            )
        else:
            cur.execute(
                """INSERT INTO sentinel_learning_profile
                      (user_id, task_id, task_name, metric, operator,
                       sample_count, avg_value, p95_value, min_value, max_value,
                       suggested_threshold, status, learned_at, updated_at)
                   VALUES(%s,%s,%s,%s,'gt',%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (user_id, task_id, task_name, metric, sample_count, mean, p95,
                 p05, mean + std_val, suggested_threshold, status, ts, ts)
            )
        conn.commit()


# ───────────────────────────── 主流程 ─────────────────────────────

def huber_baseline(values: np.ndarray) -> dict:
    """
    Huber 鲁棒基线：RLM（HuberT 损失）拟合稳健中心 + MAD 稳健尺度。

    对比均值/P95 的问题：尖峰样本会同时拉偏两者。
    Huber 对大残差线性降权，离群点不再污染基线；
    MAD×1.4826 是高斯分布下 σ 的稳健估计。
    失败时降级回均值/标准差。
    """
    center, scale = float(np.mean(values)), float(np.std(values))
    try:
        from statsmodels.robust.robust_linear_model import RLM
        from statsmodels.robust.norms import HuberT
        X = np.ones((len(values), 1))
        rlm = RLM(values, X, M=HuberT()).fit()
        center = float(rlm.params[0])
        resid = values - center
        mad = float(np.median(np.abs(resid - np.median(resid))))
        robust_scale = 1.4826 * mad
        if robust_scale > 1e-9:
            scale = robust_scale
    except Exception:
        pass  # 降级：保持均值/标准差
    return {"center": center, "scale": scale}


def predict_ttc(series: pd.Series, rule: dict | None, horizon_hours: float = 48.0,
                window_hours: float = 2.0, min_points: int = 40) -> dict:
    """
    TTC（Time-To-Impact）预测：Huber 鲁棒线性趋势外推到配置阈值。

    借鉴自动驾驶 AEB 的碰撞时间思想：不问"现在是否越界"，
    而问"按当前趋势还有几小时越界"。磁盘写满、内存泄漏这类
    缓慢漂移故障会在越界前 horizon_hours 内触发预警。

    返回 {
        'breaching': 已在阈值上（越界态）,
        'ttc_hours': 预计几小时后越界（None = 无趋势或不适用）,
        'slope_per_hour': 鲁棒趋势斜率,
        'target'/'operator': 使用的配置阈值,
        'trigger': TTC 落入预警窗口内（应触发告警）,
    }
    """
    out = {"breaching": False, "ttc_hours": None, "slope_per_hour": 0.0,
           "target": None, "operator": None, "trigger": False}
    if rule is None:
        return out
    op = rule.get("operator", "gt")
    target = float(rule["value"])
    out["target"] = target
    out["operator"] = op

    values = series.to_numpy(dtype=float)
    times = series.index

    # 当前已越界：硬编码阈值通道自己会告警，TTC 不重复触发
    current = float(values[-1])
    if (op in ("gt", "gte") and current >= target) or (op in ("lt", "lte") and current <= target):
        out["breaching"] = True
        out["ttc_hours"] = 0.0
        return out

    # 取最近 window_hours 样本拟合鲁棒趋势
    cutoff = times[-1] - pd.Timedelta(hours=window_hours)
    mask = times >= cutoff
    w_values = values[mask]
    w_times = times[mask]
    if len(w_values) < min_points:
        return out

    x = np.asarray((w_times - w_times[0]).total_seconds() / 3600.0, dtype=float)
    y = w_values.astype(float)
    try:
        from sklearn.linear_model import HuberRegressor
        model = HuberRegressor(epsilon=1.35, alpha=0.0, max_iter=300)
        model.fit(x.reshape(-1, 1), y)
        slope = float(model.coef_[0])
        intercept = float(model.intercept_)
    except Exception:
        return out
    out["slope_per_hour"] = round(slope, 6)

    # 方向性：gt 只关心上升穿阈，lt 只关心下降穿阈
    if op in ("gt", "gte") and slope <= 1e-9:
        return out
    if op in ("lt", "lte") and slope >= -1e-9:
        return out

    t_cross = (target - intercept) / slope
    elapsed = float(x[-1])
    ttc = max(0.0, t_cross - elapsed)
    out["ttc_hours"] = round(ttc, 2)
    out["trigger"] = 0.0 < ttc <= horizon_hours
    return out


def autoencoder_multivariate(series_dict: dict[str, pd.Series],
                              contamination: float = 0.02,
                              hidden_layer_size: int | None = None) -> dict:
    """
    Autoencoder 第三通道：多变量重构异常检测。

    思想：把 task 的所有 metric 拼成 N×M 矩阵（M=metric 数，N=时间点），
    用 MLPRegressor 训练一个"输入=输出"的 Autoencoder，瓶颈层压缩到
    hidden_layer_size。正常模式能被低维表示重构，异常组合（如 CPU 正常
    但 CPU×IO 同时飙）重构误差高 → 标为异常。

    对比单变量 IForest 的优势：抓**组合异常**——每个指标单独看都正常，
    但联合分布偏离了正常模式。论文清单里的经典架构 Autoencoder 条目。

    返回 {
        'abnormal_indices': list[int],   # 异常时间点的 index
        'reconstruction_error': np.ndarray,  # 每个时间点的重构误差（加权 RMS）
        'threshold': float,              # 误差阈值
        'latent_dim': int,               # 瓶颈层维度
        'samples': int,
        'features': int,
    }
    """
    out = {
        "abnormal_indices": [],
        "reconstruction_error": np.array([]),
        "threshold": 0.0,
        "latent_dim": 0,
        "samples": 0,
        "features": 0,
    }

    if not HAS_SKL:
        return out

    # 对齐所有 metric 的时间索引（取交集），拼成矩阵
    common_idx = None
    for s in series_dict.values():
        if common_idx is None:
            common_idx = s.index
        else:
            common_idx = common_idx.intersection(s.index)
    if common_idx is None or len(common_idx) < 60:   # 至少 60 个样本
        return out

    feature_names = sorted(series_dict.keys())
    n, m = len(common_idx), len(feature_names)
    X = np.zeros((n, m), dtype=float)
    for j, name in enumerate(feature_names):
        X[:, j] = series_dict[name].reindex(common_idx).to_numpy(dtype=float)

    # 常量列跳过（比如 disk 一直是 39.00）
    variance = X.var(axis=0)
    valid_cols = variance > 1e-9
    if valid_cols.sum() < 2:   # 至少 2 个有方差的 metric 才值得多变量分析
        X = X[:, valid_cols]
        feature_names = [feature_names[i] for i in range(m) if valid_cols[i]]
        if X.shape[1] < 2:
            return out

    m = X.shape[1]

    # StandardScaler 标准化，让各 metric 误差可比
    try:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
    except Exception:
        return out

    # Autoencoder 瓶颈层：压缩到 ceil(m/2)，至少 2
    latent = max(2, (hidden_layer_size or int(np.ceil(m / 2))))

    # MLPRegressor 当 Autoencoder：输入=输出，瓶颈层就是 latent
    try:
        ae = MLPRegressor(
            hidden_layer_sizes=(latent, m),   # 瓶颈层 latent → 解码回 m
            activation="relu",
            solver="adam",
            max_iter=300,
            early_stopping=True,
            random_state=42,
            learning_rate_init=1e-3,
        )
        ae.fit(X_scaled, X_scaled)
    except Exception as exc:
        print(f"    AE 训练失败：{exc}", file=sys.stderr)
        return out

    # 重构误差：逐样本 RMS（加权——各 metric 误差等权）
    X_recon = ae.predict(X_scaled)
    errors = np.sqrt(np.mean((X_scaled - X_recon) ** 2, axis=1))

    # 阈值：mean + k × MAD（和 Huber 口径一致，稳健抗极端值）
    mad = float(np.median(np.abs(errors - np.median(errors))))
    threshold = float(np.mean(errors) + 1.5 * 1.4826 * max(mad, 1e-9))
    # 保底：至少有 contamination 比例的样本被标异常
    sorted_errors = np.sort(errors)
    floor_idx = int(np.ceil((1 - contamination) * len(errors))) - 1
    floor_threshold = float(sorted_errors[max(0, floor_idx)])
    threshold = min(threshold, floor_threshold)   # 取更紧的那个，避免漏报

    abnormal = np.where(errors > threshold)[0].tolist()

    out["abnormal_indices"] = abnormal
    out["reconstruction_error"] = errors
    out["threshold"] = threshold
    out["latent_dim"] = latent
    out["samples"] = n
    out["features"] = m
    out["feature_names"] = feature_names
    return out


def process_one_task(conn, task: dict, period: int, contamination: float,
                     dry_run: bool, days: int, ttc_horizon: float) -> dict:
    """处理一个哨兵任务的全流程。"""
    tid = task["id"]
    tname = task["name"]
    uid = task["user_id"]
    rules = parse_rules(task.get("rules_json"))

    samples_by_metric = fetch_samples(conn, tid, days=days)
    if not samples_by_metric:
        print(f"  [{tid}] {tname}: 无数据，跳过")
        return {"task_id": tid, "task_name": tname, "metrics": 0, "skip_reason": "no_data"}

    task_result = {
        "task_id": tid,
        "task_name": tname,
        "user_id": uid,
        "metrics": {},
    }

    # ── 逐 metric 处理：IForest + TTC + CUSUM + Huber ──
    # 同时收集每个 metric 的 abnormal_arr 和 index，供 Autoencoder 合并
    per_metric_abnormal: dict[str, np.ndarray] = {}
    per_metric_index: dict[str, pd.DatetimeIndex] = {}
    per_metric_samples: dict[str, int] = {}

    for metric, series in samples_by_metric.items():
        n = len(series)
        print(f"  [{tid}] {tname} / {metric}: {n} 个样本 ... ", end="", flush=True)

        # 自动推断 STL period（每天多少个采样点）
        inferred_period = infer_period(series, default=period)

        res = run_stl_iforest(series, period=inferred_period, contamination=contamination)
        cps = cusum_changepoints(series)

        # 计算统计量
        values = series.to_numpy(dtype=float)
        mean_val = float(np.mean(values))
        p95_val = float(np.percentile(values, 95))
        p05_val = float(np.percentile(values, 5))
        std_val = float(np.std(values))

        # ── Huber 鲁棒基线（替代被尖峰污染的均值/P95 口径）──
        hub = huber_baseline(values)

        # 建议阈值 = Huber 稳健中心 ± k × 稳健尺度（k=1.5，与论文寻优一致）
        # 尾部保底：gt 不低于 P95 / lt 不高于 P05 —— MAD 尺度对重尾震荡指标
        # （如 tcp）偏窄，纯 Huber 会给出比 P95 更紧的阈值造成告警风暴
        rule = rules.get(metric)
        is_lower = bool(rule and rule["operator"] in ("lt", "lte"))
        if is_lower:
            suggested_threshold = min(p05_val, hub["center"] - 1.5 * hub["scale"])
        else:
            suggested_threshold = max(p95_val, hub["center"] + 1.5 * hub["scale"])

        # ── TTC 预测：按当前趋势还有几小时越界 ──
        ttc = predict_ttc(series, rule, horizon_hours=ttc_horizon)

        # CUSUM 变点时间
        changepoint_at = None
        if cps["changepoints"]:
            last_idx = cps["changepoints"][-1]
            if last_idx < len(series.index):
                changepoint_at = series.index[last_idx].to_pydatetime()

        # 统计异常数
        iforest_abn_count = int(res["abnormal_by_iforest"].sum())

        # TTC 预警合并进 abnormal 标记：只标最新 1 个样本，
        # Java hasModelAnomaly 的 60 秒窗口就能读到并走既有告警链
        abnormal_arr = res["abnormal_by_iforest"].copy()
        ttc_triggered = bool(ttc["trigger"])
        if ttc_triggered and n > 0:
            abnormal_arr[-1] = 1

        # 暂存，等 Autoencoder 第三通道跑完再合并写 DB
        per_metric_abnormal[metric] = abnormal_arr
        per_metric_index[metric] = series.index
        per_metric_samples[metric] = n

        metric_result = {
            "samples": n,
            "mean": round(mean_val, 4),
            "p95": round(p95_val, 4),
            "p05": round(p05_val, 4),
            "std": round(std_val, 4),
            "huber_center": round(hub["center"], 4),
            "huber_scale": round(hub["scale"], 4),
            "stl_available": res["stl_available"],
            "stl_trend_strength": res["trend_strength"],
            "stl_season_strength": res["season_strength"],
            "iforest_abnormal_count": iforest_abn_count,
            "iforest_contamination": contamination,
            "abnormal_threshold": res["abnormal_threshold"],
            "cusum_changepoints": len(cps["changepoints"]),
            "changepoint_at": changepoint_at.isoformat() if changepoint_at else None,
            "suggested_threshold": round(suggested_threshold, 4),
            "stl_residual_std": round(float(np.std(res["residual"])), 4) if res["residual"] is not None else round(std_val, 4),
            "ttc_hours": ttc["ttc_hours"],
            "ttc_target": ttc["target"],
            "ttc_operator": ttc["operator"],
            "ttc_slope_per_hour": ttc["slope_per_hour"],
            "ttc_breaching": ttc["breaching"],
            "ttc_trigger": ttc_triggered,
        }
        task_result["metrics"][metric] = metric_result

        # TTC 预警打印
        if ttc["breaching"]:
            ttc_note = " · TTC:已越界"
        elif ttc["ttc_hours"] is not None:
            ttc_note = f" · TTC:{ttc['ttc_hours']}h 后触及 {ttc['target']}"
            if ttc_triggered:
                ttc_note += " ⏱预警"
        else:
            ttc_note = ""
        print(f"[huber μ={hub['center']:.2f} σ={hub['scale']:.2f} → 建议 {suggested_threshold:.2f}]{ttc_note}", end="")
        print()  # 换行

    # ── Autoencoder 第三通道：多变量组合异常 ──
    # 所有 metric 循环跑完后，用整个 task 的时序矩阵做 AE 重构
    ae_result = autoencoder_multivariate(samples_by_metric, contamination=contamination)
    ae_abn_indices = set(ae_result.get("abnormal_indices", []))
    ae_feat_names = ae_result.get("feature_names", [])
    ae_abn_count = len(ae_abn_indices)

    if ae_abn_indices:
        # AE 的 abnormal_indices 是对齐后的时间索引（按时间交集排序），
        # 但 per_metric_abnormal 里是各自原始 index（可能没对齐）。
        # 解法：把 AE 异常点转成时间戳，再映射回各 metric 的 index
        common_idx = None
        for s in samples_by_metric.values():
            common_idx = s.index if common_idx is None else common_idx.intersection(s.index)
        ae_abn_times = set(common_idx[list(ae_abn_indices)].to_pydatetime()) if common_idx is not None and ae_abn_indices else set()
    else:
        ae_abn_times = set()

    if ae_abn_count > 0:
        print(f"  └─ Autoencoder: {ae_abn_count} 个组合异常点（瓶颈 {ae_result.get('latent_dim')}D，特征 {ae_feat_names}）")

    task_result["ae_abnormal_count"] = ae_abn_count
    task_result["ae_features"] = ae_feat_names
    task_result["ae_latent_dim"] = ae_result.get("latent_dim", 0)

    # ── 统一写回 DB（IForest 异常 + TTC 预警 + AE 组合异常）──
    for metric, series in samples_by_metric.items():
        n = per_metric_samples[metric]
        abnormal_arr = per_metric_abnormal[metric].copy()

        # AE 合并：如果 AE 时间点在这个 metric 里也有对应时间戳 → 置 1
        if ae_abn_times:
            for idx, ts in enumerate(per_metric_index[metric]):
                if ts.to_pydatetime() in ae_abn_times:
                    abnormal_arr[idx] = 1

        ae_metric_hit = int(abnormal_arr.sum() - per_metric_abnormal[metric].sum())

        if not dry_run:
            try:
                new_vals = abnormal_arr.tolist()
                sampled_ats = [ts.to_pydatetime() for ts in per_metric_index[metric]]
                changed = update_abnormal(conn, tid, metric, new_vals, sampled_ats)

                # learning profile（Guardian 会读 suggested_threshold + status）
                mr = task_result["metrics"][metric]
                upsert_profile(
                    conn, user_id=uid, task_id=tid, task_name=tname,
                    metric=metric, sample_count=n,
                    mean=mr["huber_center"], std_val=mr["huber_scale"],
                    p95=mr["p95"], p05=mr["p05"],
                    suggested_threshold=mr["suggested_threshold"],
                    iforest_abnormal_count=mr["iforest_abnormal_count"],
                )

                conn.commit()
                ae_note = f" +AE{ae_metric_hit}" if ae_metric_hit > 0 else ""
                print(f"  ✓ {metric}: 更新 {changed}/{n} 条 abnormal + profile{ae_note}")
            except Exception as exc:
                conn.rollback()
                print(f"  写入失败：{exc}", end="", file=sys.stderr)

    return task_result


def main():
    parser = argparse.ArgumentParser(description="哨兵建模方案一对接脚本")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="password")
    parser.add_argument("--db", default="smartops")
    parser.add_argument("--task-id", type=int, default=None, help="只跑某个任务")
    parser.add_argument("--days", type=int, default=90, help="训练窗口天数")
    parser.add_argument("--period", type=int, default=24, help="STL 周期（小时）")
    parser.add_argument("--contamination", type=float, default=0.02, help="孤立森林污染率")
    parser.add_argument("--ttc-horizon-hours", type=float, default=48.0,
                        help="TTC 预警窗口（小时）：预计越界时间落在此窗口内则触发告警")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写 DB")
    parser.add_argument("--report-dir", default="data/modeling-output/plan1", help="报告输出目录")
    args = parser.parse_args()

    cfg = DBCfg(args.host, args.port, args.user, args.password, args.db)

    print(f"=== 方案一对接脚本开始 ===")
    print(f"DB: {cfg.host}:{cfg.port}/{cfg.database}  user={cfg.user}")
    print(f"窗口: 过去 {args.days} 天  STL 周期={args.period} 污染率={args.contamination}  "
          f"TTC 预警窗口={args.ttc_horizon_hours}h")
    if args.dry_run:
        print("⚠️  DRY-RUN 模式：不会写数据库")
    print()

    # 连接
    try:
        conn = connect(cfg)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        print("✅ DB 连接成功")
    except Exception as exc:
        print(f"❌ DB 连接失败：{exc}")
        print("   请确认 MySQL 在跑，且 sentinel 相关表已由 Flyway 迁移创建。")
        sys.exit(1)

    # 拉任务列表
    tasks = fetch_tasks(conn, args.task_id)
    if not tasks:
        print("⚠️  没有启用中的哨兵任务。先在前端创建一个 CPU/内存监控任务再跑本脚本。")
        sys.exit(0)
    print(f"📋 待处理任务：{len(tasks)} 个\n")

    # 逐个处理
    report = {
        "generated_at": datetime.now().isoformat(),
        "window_days": args.days,
        "period": args.period,
        "contamination": args.contamination,
        "ttc_horizon_hours": args.ttc_horizon_hours,
        "dry_run": args.dry_run,
        "tasks": [],
    }

    t0 = time.time()
    for i, task in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] task_id={task['id']}  {task['name']}")
        try:
            result = process_one_task(
                conn, task,
                period=args.period,
                contamination=args.contamination,
                dry_run=args.dry_run,
                days=args.days,
                ttc_horizon=args.ttc_horizon_hours,
            )
            report["tasks"].append(result)
        except Exception as exc:
            print(f"  ❌ 异常：{exc}", file=sys.stderr)
            import traceback; traceback.print_exc()
            report["tasks"].append({"task_id": task["id"], "error": str(exc)})
        print()

    elapsed = time.time() - t0
    print(f"=== 完成，耗时 {elapsed:.1f}s ===")

    # 写 JSON 报告
    out_dir = ROOT / args.report_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "sentinel_modeling_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"📊 完整报告：{report_path}")

    # 汇总统计
    total_samples = sum(
        m.get("samples", 0)
        for t in report["tasks"]
        for m in t.get("metrics", {}).values()
    )
    total_iforest_abn = sum(
        m.get("iforest_abnormal_count", 0)
        for t in report["tasks"]
        for m in t.get("metrics", {}).values()
    )
    total_changepoints = sum(
        m.get("cusum_changepoints", 0)
        for t in report["tasks"]
        for m in t.get("metrics", {}).values()
    )
    total_profiles = len([
        t for t in report["tasks"]
        for m in t.get("metrics", {}).values()
        if "suggested_threshold" in m
    ])
    total_ae_abn = sum(t.get("ae_abnormal_count", 0) for t in report["tasks"] if "ae_abnormal_count" in t)
    total_ae_tasks = sum(1 for t in report["tasks"] if "ae_abnormal_count" in t and t["ae_abnormal_count"] > 0)
    ttc_rows = [
        (t.get("task_name"), name, m)
        for t in report["tasks"]
        for name, m in t.get("metrics", {}).items()
    ]
    ttc_triggered = [(tn, name, m) for tn, name, m in ttc_rows if m.get("ttc_trigger")]
    ttc_breaching = [(tn, name, m) for tn, name, m in ttc_rows if m.get("ttc_breaching")]
    breaching_txt = ", ".join(f"{tn}/{n}" for tn, n, _ in ttc_breaching[:5])
    trigger_txt = ", ".join(f"{tn}/{n} {m.get('ttc_hours')}h" for tn, n, m in ttc_triggered[:5])
    print(f"   扫描样本：{total_samples}")
    print(f"   孤立森林异常：{total_iforest_abn} 条")
    print(f"   CUSUM 变点：{total_changepoints} 处")
    print(f"   TTC 已越界：{len(ttc_breaching)} 个指标" + (f"（{breaching_txt}）" if ttc_breaching else ""))
    print(f"   TTC 预警触发：{len(ttc_triggered)} 个指标" + (f"（{trigger_txt}）" if ttc_triggered else ""))
    print(f"   Autoencoder 组合异常：{total_ae_abn} 个时间点（{total_ae_tasks} 个 task）")
    if not args.dry_run:
        print(f"   Learning Profile 写回：{total_profiles} 条（Huber 鲁棒基线）")


if __name__ == "__main__":
    main()
