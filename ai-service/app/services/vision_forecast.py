"""巡检视觉事件预测：多目标跟踪 + 恒速轨迹外推 + 区域事件研判。

定位：**几何基线**，不是学习型轨迹模型。借鉴多智能体轨迹预测的建模思路
（实体集合 + 历史轨迹 → 未来轨迹 → 事件），但在机房巡检场景重写：

* 输入是模型无关的归一化检测框序列，先保证可复现、可解释；
* 输出结构化证据（轨迹、ETA、区域事件、不确定半径），决策权仍在 Agent；
* probability 由几何穿透深度与轨迹拟合残差构成，**未经概率校准**，
  不能当作故障概率或告警级别使用；
* 学习型后端只保留接入点：权重不可用时显式标 geometry_only，绝不伪造
  model_status。

刻意不做的事：不读图片、不做检测、不写库、不自动改权重。检测由
vision/grounding.py 负责，这里只消费检测结果，避免感知与预测耦合。
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Sequence

import numpy as np

# 只用最近若干帧拟合速度：机房目标速度快、轨迹短，历史越长越容易把转向抹平
TRACK_HISTORY = 8
# 关联门限：IoU 太低但中心足够近时仍认为是同一目标（小目标框抖动大）
MIN_IOU = 0.05
MAX_CENTER_DISTANCE = 0.12
# 区域类型对风险分的权重：danger 才是真正的禁入约束
ZONE_RISK_WEIGHT = {"danger": 1.0, "inspect": 0.6, "normal": 0.0}


@dataclass
class _Track:
    track_id: str
    label: str
    positions: list[tuple[float, float, float]] = field(default_factory=list)  # (t_ms, cx, cy)
    bboxes: list[list[float]] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)
    missing: int = 0
    dropped: bool = False

    @property
    def hits(self) -> int:
        return len(self.positions)

    @property
    def mean_confidence(self) -> float:
        return float(np.mean(self.confidences)) if self.confidences else 0.0


# ---------------------------------------------------------------------------
# 几何工具
# ---------------------------------------------------------------------------


def _center(bbox: Sequence[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = width * height
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection
    return intersection / union if union > 0 else 0.0


def _center_distance(a: Sequence[float], b: Sequence[float]) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _inside(px: float, py: float, box: Sequence[float]) -> bool:
    return box[0] <= px <= box[2] and box[1] <= py <= box[3]


def _rect_distance(px: float, py: float, box: Sequence[float]) -> float:
    """点到矩形边框的距离：框内返回最近边距离，框外返回欧氏距离。"""
    x1, y1, x2, y2 = box
    if _inside(px, py, box):
        return min(px - x1, x2 - px, py - y1, y2 - py)
    dx = max(x1 - px, 0.0, px - x2)
    dy = max(y1 - py, 0.0, py - y2)
    return math.hypot(dx, dy)


# ---------------------------------------------------------------------------
# 时间轴
# ---------------------------------------------------------------------------


def _resolve_dt(frames: Sequence[Any], fallback: float) -> tuple[float, list[str]]:
    """优先使用真实采集间隔；时间戳不可用时回退到 frame_interval_ms。"""
    reasons: list[str] = []
    stamps = [frame.captured_at_ms for frame in frames]
    if any(stamp is None for stamp in stamps):
        return float(fallback), reasons
    diffs = [b - a for a, b in zip(stamps, stamps[1:]) if b > a]
    if not diffs:
        reasons.append("采集时间戳无正向间隔，已回退到 frame_interval_ms")
        return float(fallback), reasons
    return float(np.median(diffs)), reasons


def _order_frames(frames: Sequence[Any]) -> tuple[list[Any], list[str]]:
    """时间戳齐全时按采集时间排序，保证速度方向不被乱序帧带反。"""
    stamps = [frame.captured_at_ms for frame in frames]
    if any(stamp is None for stamp in stamps):
        return list(frames), []
    if all(b > a for a, b in zip(stamps, stamps[1:])):
        return list(frames), []
    ordered = sorted(frames, key=lambda frame: frame.captured_at_ms)
    return ordered, ["帧时间戳非严格递增，已按 captured_at_ms 重排后再做关联"]


# ---------------------------------------------------------------------------
# 跟踪
# ---------------------------------------------------------------------------


def _track(frames: Sequence[Any], dt_ms: float, lost_after: int, labels: set[str]) -> list[_Track]:
    active: list[_Track] = []
    created: list[_Track] = []
    next_id = 1

    for index, frame in enumerate(frames):
        t_ms = frame.captured_at_ms if frame.captured_at_ms is not None else index * dt_ms
        detections = [d for d in frame.detections if not labels or d.label in labels]

        pairs: list[tuple[float, float, int, int]] = []
        for track_index, track in enumerate(active):
            last = track.bboxes[-1]
            for det_index, det in enumerate(detections):
                if det.label != track.label:
                    continue
                iou = _iou(last, det.bbox)
                distance = _center_distance(last, det.bbox)
                if iou >= MIN_IOU or distance <= MAX_CENTER_DISTANCE:
                    pairs.append((iou, -distance, track_index, det_index))
        # 先匹配 IoU 高的，再匹配中心更近的
        pairs.sort(key=lambda item: (item[0], item[1]), reverse=True)

        used_tracks: set[int] = set()
        used_dets: set[int] = set()
        for _, _, track_index, det_index in pairs:
            if track_index in used_tracks or det_index in used_dets:
                continue
            used_tracks.add(track_index)
            used_dets.add(det_index)
            track = active[track_index]
            det = detections[det_index]
            track.positions.append((float(t_ms), *_center(det.bbox)))
            track.bboxes.append(list(det.bbox))
            track.confidences.append(float(det.confidence))
            track.missing = 0

        survivors: list[_Track] = []
        for track_index, track in enumerate(active):
            if track_index in used_tracks:
                survivors.append(track)
            elif track.missing + 1 <= lost_after:
                track.missing += 1
                survivors.append(track)
            else:
                track.missing += 1
                track.dropped = True

        for det_index, det in enumerate(detections):
            if det_index in used_dets:
                continue
            track = _Track(track_id=f"T{next_id}", label=det.label)
            next_id += 1
            track.positions.append((float(t_ms), *_center(det.bbox)))
            track.bboxes.append(list(det.bbox))
            track.confidences.append(float(det.confidence))
            survivors.append(track)
            created.append(track)

        active = survivors

    return created


# ---------------------------------------------------------------------------
# 速度拟合与轨迹外推
# ---------------------------------------------------------------------------


def _fit_velocity(track: _Track) -> tuple[float, float, float]:
    """最小二乘拟合最近轨迹，返回 (vx, vy, 残差)，单位为归一化坐标/秒。"""
    points = track.positions[-TRACK_HISTORY:]
    if len(points) < 2:
        return 0.0, 0.0, 0.0
    stamps = np.asarray([point[0] for point in points], dtype=np.float64)
    xs = np.asarray([point[1] for point in points], dtype=np.float64)
    ys = np.asarray([point[2] for point in points], dtype=np.float64)
    # 相对化时间轴：绝对毫秒时间戳直接 polyfit 会丢精度
    stamps = stamps - stamps[0]
    if float(np.ptp(stamps)) <= 0.0:
        return 0.0, 0.0, 0.0
    vx = float(np.polyfit(stamps, xs, 1)[0]) * 1000.0
    vy = float(np.polyfit(stamps, ys, 1)[0]) * 1000.0
    fitted_x = np.polyval(np.polyfit(stamps, xs, 1), stamps)
    fitted_y = np.polyval(np.polyfit(stamps, ys, 1), stamps)
    residual = float(np.sqrt(np.mean((xs - fitted_x) ** 2 + (ys - fitted_y) ** 2)))
    return vx, vy, residual


def _predict_path(
    track: _Track, vx: float, vy: float, residual: float, horizon: int, dt_ms: float,
) -> list[dict[str, Any]]:
    _, last_x, last_y = track.positions[-1]
    points: list[dict[str, Any]] = []
    for step in range(1, horizon + 1):
        seconds = step * dt_ms / 1000.0
        cx = min(1.0, max(0.0, last_x + vx * seconds))
        cy = min(1.0, max(0.0, last_y + vy * seconds))
        # 不确定半径随步数增长；残差是拟合噪声，不是统计置信区间
        radius = min(0.5, max(0.005, residual + 0.004 * math.sqrt(step)))
        points.append({
            "step": step,
            "t_ms": round(seconds * 1000.0, 3),
            "cx": round(cx, 6),
            "cy": round(cy, 6),
            "radius": round(radius, 6),
        })
    return points


def _dwell_ms(track: _Track, box: Sequence[float]) -> float:
    """从最后一帧向前累计连续位于区域内的时长。"""
    total = 0.0
    for index in range(len(track.positions) - 1, 0, -1):
        _, px, py = track.positions[index]
        _, qx, qy = track.positions[index - 1]
        if not (_inside(px, py, box) and _inside(qx, qy, box)):
            break
        total += track.positions[index][0] - track.positions[index - 1][0]
    return total


def _event_probability(
    px: float,
    py: float,
    zone_box: Sequence[float],
    speed: float,
    residual: float,
    dt_seconds: float,
    confidence: float,
) -> float:
    """几何启发式概率：穿透越深、拟合越稳、检测越可信，分数越高。

    这不是校准概率：没有真实标签、没有可靠性曲线，只是排序用的证据强度。
    """
    zone_size = max(1e-6, min(zone_box[2] - zone_box[0], zone_box[3] - zone_box[1]))
    depth = min(1.0, 2.0 * _rect_distance(px, py, zone_box) / zone_size)
    travel = speed * dt_seconds
    uncertainty = min(1.0, residual / max(1e-6, travel)) if travel > 0 else 1.0
    score = 0.85 * depth + 0.15 * (1.0 - uncertainty)
    score *= 0.5 + 0.5 * confidence
    return round(min(0.95, max(0.05, score)), 4)


def _zone_events(
    track: _Track,
    zones: Sequence[Any],
    path: Sequence[dict[str, Any]],
    speed: float,
    residual: float,
    dt_ms: float,
    dwell_threshold_ms: float | None,
) -> list[dict[str, Any]]:
    if track.dropped or not path:
        return []
    _, last_x, last_y = track.positions[-1]
    confidence = track.mean_confidence
    events: list[dict[str, Any]] = []

    for zone in zones:
        if zone.kind == "normal":
            continue
        currently_inside = _inside(last_x, last_y, zone.bbox)

        if currently_inside:
            if dwell_threshold_ms is not None:
                dwelled = _dwell_ms(track, zone.bbox)
                if dwelled >= dwell_threshold_ms:
                    events.append({
                        "track_id": track.track_id,
                        "label": track.label,
                        "zone_id": zone.zone_id,
                        "zone_kind": zone.kind,
                        "event": "dwell_exceeded",
                        "step": None,
                        "eta_ms": 0.0,
                        "probability": 0.95,
                        "basis": [
                            f"目标已在 {zone.zone_id} 连续停留 {dwelled:.0f}ms",
                            f"停留阈值 {dwell_threshold_ms:.0f}ms",
                            "停留时长来自历史帧实测，不是外推",
                        ],
                    })
                    continue
            exit_point = next(
                (point for point in path if not _inside(point["cx"], point["cy"], zone.bbox)),
                None,
            )
            if exit_point is not None:
                events.append({
                    "track_id": track.track_id,
                    "label": track.label,
                    "zone_id": zone.zone_id,
                    "zone_kind": zone.kind,
                    "event": "predicted_exit",
                    "step": exit_point["step"],
                    "eta_ms": exit_point["t_ms"],
                    "probability": _event_probability(
                        exit_point["cx"], exit_point["cy"], zone.bbox,
                        speed, residual, dt_ms / 1000.0, confidence,
                    ),
                    "basis": [
                        f"当前位于 {zone.zone_id} 内",
                        f"按恒速外推第 {exit_point['step']} 步离开区域",
                        "概率为几何启发式，未经校准",
                    ],
                })
            continue

        enter_point = next(
            (point for point in path if _inside(point["cx"], point["cy"], zone.bbox)),
            None,
        )
        if enter_point is not None:
            events.append({
                "track_id": track.track_id,
                "label": track.label,
                "zone_id": zone.zone_id,
                "zone_kind": zone.kind,
                "event": "predicted_enter",
                "step": enter_point["step"],
                "eta_ms": enter_point["t_ms"],
                "probability": _event_probability(
                    enter_point["cx"], enter_point["cy"], zone.bbox,
                    speed, residual, dt_ms / 1000.0, confidence,
                ),
                "basis": [
                    f"当前位于 {zone.zone_id} 外",
                    f"按恒速外推第 {enter_point['step']} 步进入区域",
                    f"拟合残差 {residual:.4f}，速度 {speed:.4f}/s",
                    "概率为几何启发式，未经校准",
                ],
            })
    return events


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def _data_quality(frames: Sequence[Any], reasons: list[str]) -> dict[str, Any]:
    with_detections = sum(1 for frame in frames if frame.detections)
    coverage = with_detections / len(frames) if frames else 0.0
    confidences = [det.confidence for frame in frames for det in frame.detections]
    mean_confidence = float(np.mean(confidences)) if confidences else 0.0

    problems = list(reasons)
    if len(frames) < 3:
        problems.append(f"帧数 {len(frames)} 少于 3，速度拟合不可靠")
    if coverage < 0.5:
        problems.append(f"仅 {coverage:.0%} 的帧有检测结果，轨迹可能断裂")
    if mean_confidence < 0.35:
        problems.append(f"平均检测置信度 {mean_confidence:.2f} 偏低")

    return {
        "frames": len(frames),
        "frames_with_detections": with_detections,
        "detection_coverage": round(coverage, 4),
        "mean_confidence": round(mean_confidence, 4),
        "status": "DEGRADED" if problems else "OK",
        "reasons": problems,
    }


def forecast(request) -> dict[str, Any]:
    frames, order_reasons = _order_frames(request.frames)
    dt_ms, dt_reasons = _resolve_dt(frames, request.frame_interval_ms)
    labels = set(request.labels)
    tracks = _track(frames, dt_ms, request.lost_after_frames, labels)

    track_models: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for track in tracks:
        vx, vy, residual = _fit_velocity(track)
        speed = math.hypot(vx, vy)
        path = [] if track.dropped else _predict_path(track, vx, vy, residual, request.horizon, dt_ms)
        if track.dropped:
            status = "lost"
        elif track.hits >= 3 and track.missing == 0:
            status = "confirmed"
        else:
            status = "tentative"
        track_models.append({
            "track_id": track.track_id,
            "label": track.label,
            "status": status,
            "hits": track.hits,
            "missing_frames": track.missing,
            "last_bbox": track.bboxes[-1],
            "velocity": [round(vx, 6), round(vy, 6)],
            "speed": round(speed, 6),
            "predicted_path": path,
        })
        events.extend(_zone_events(
            track, request.zones, path, speed, residual, dt_ms, request.dwell_ms,
        ))

    quality = _data_quality(frames, order_reasons + dt_reasons)
    events.sort(
        key=lambda item: (ZONE_RISK_WEIGHT.get(item["zone_kind"], 0.0), item["probability"]),
        reverse=True,
    )

    risk_basis: list[str] = []
    risk_score = 0.0
    if events:
        weighted = [
            event["probability"] * ZONE_RISK_WEIGHT.get(event["zone_kind"], 0.0)
            for event in events
        ]
        risk_score = round(max(weighted), 4)
        top = events[0]
        risk_basis.append(
            f"最高风险事件：{top['label']} {top['event']} → {top['zone_id']}"
            f"（第 {top['step']} 步，约 {top['eta_ms']:.0f}ms）"
        )
    else:
        risk_basis.append("未来窗口内未预测到区域进入/离开事件")
    risk_basis.append("风险分由几何外推与检测置信度构成，未经概率校准，不代表故障概率")

    if quality["status"] != "OK":
        risk_basis.append("数据质量不足，外推结论需人工复核：" + "；".join(quality["reasons"]))
    lost = [track["track_id"] for track in track_models if track["status"] == "lost"]
    if lost:
        risk_basis.append(f"{len(lost)} 条轨迹已丢失，不输出未来轨迹：{', '.join(lost)}")

    risk_level = "high" if risk_score >= 0.67 else "medium" if risk_score >= 0.33 else "low"
    degraded = quality["status"] != "OK"
    explanation = (
        f"[geometric] {quality['frames']} 帧、{len(track_models)} 条轨迹、"
        f"{len(events)} 个区域事件；预测窗口 {request.horizon} 步 × {dt_ms:.0f}ms。"
        f"风险 {risk_level}（{risk_score:.2f}，几何启发式）。"
    )
    if degraded:
        explanation += " 数据质量不足，结论为降级输出。"

    return {
        "ok": True,
        "mode": "geometric",
        "model_status": "degraded" if degraded else "geometry_only",
        "model_status_detail": (
            "；".join(quality["reasons"]) if degraded else
            "未加载学习型轨迹模型，使用恒速几何基线"
        ),
        "frame_count": len(frames),
        "dt_ms": round(dt_ms, 3),
        "tracks": track_models,
        "events": events,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_basis": risk_basis,
        "data_quality": quality,
        "explanation": explanation,
    }


def get_model_info() -> dict[str, Any]:
    learned = [name for name in ("boxmot", "torch") if find_spec(name) is not None]
    return {
        "available": True,
        "kind": "geometric",
        "learned_backend": learned,
        "reason": (
            "当前为恒速几何基线；"
            + (f"检测器可选用 {', '.join(learned)}" if learned else "未安装可选学习型依赖")
        ),
        "supports": ["multi_object_tracking", "trajectory_extrapolation", "zone_event_forecast"],
        "probability_calibrated": False,
        "min_frames": 2,
        "max_horizon": 30,
    }


# ---------------------------------------------------------------------------
# 学习闭环：只做样本回流，不自动改权重
# ---------------------------------------------------------------------------


def _feedback_dir() -> Path:
    configured = os.getenv("SMARTOPS_VISION_FEEDBACK_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "vision_feedback"


def record_feedback(payload: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    """把人工复核结果追加到 JSONL，供离线训练使用。

    在线只收集标签，**不触发训练、不改阈值**；模型晋升必须走离线评测与注册。
    """
    target = directory or _feedback_dir()
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"vision_feedback_{datetime.now(timezone.utc):%Y%m%d}.jsonl"
    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "smartops.vision_feedback.v1",
        **payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"ok": True, "stored": str(path), "schema_version": "smartops.vision_feedback.v1"}
