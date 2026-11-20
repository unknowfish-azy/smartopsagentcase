"""P3 任务分解器：从 goal 拆出 SubTask 列表。

最小化规则实现，不依赖 LLM：
  - 关键词匹配 → 决定调哪些子 Agent
  - 依赖关系硬编码（anomaly sleuth 先于 rootcause hunter）
  - priority 按关键词权重

设计目标：不管 goal 怎么写，至少能触发"异常检测 → 根因 → 案例 → 处置"这条基础链路。
"""

from __future__ import annotations

from typing import Any

from .models import SubTask, AgentSpecialty


# ---------------------------------------------------------------------------
# 关键词 → 专长映射
# ---------------------------------------------------------------------------

_KEYWORD_TO_SPECIALTY: list[tuple[list[str], AgentSpecialty, int]] = [
    # (触发关键词, 子 Agent, priority)
    (
        ["异常", "报警", "告警", "监控", "指标", "metric", "anomaly", "spike", "尖峰", "波动"],
        AgentSpecialty.ANOMALY_SLEUTH, 1,
    ),
    (
        ["根因", "原因", "root cause", "rootcause", "归因", "定位"],
        AgentSpecialty.ROOTCAUSE_HUNTER, 1,
    ),
    (
        ["日志", "log", "error", "堆栈", "stack", "traceback", "oops"],
        AgentSpecialty.LOG_INTERPRETER, 2,
    ),
    (
        ["历史", "类似", "以前", "参考案例", "case", "检索"],
        AgentSpecialty.CASE_RETRIEVER, 2,
    ),
    (
        ["处置", "建议", "怎么办", "action", "restart", "扩容", "重启", "回滚", "rollback", "scale"],
        AgentSpecialty.ACTION_ADVISOR, 1,
    ),
    (
        ["仿真", "模拟", "simulate", "演练", "注入", "fault injection"],
        AgentSpecialty.SIMULATOR, 3,
    ),
    (
        ["反思", "教训", "lesson", "复盘", "沉淀", "学习", "learn"],
        AgentSpecialty.REFLECTION, 3,
    ),
]

# "故障/问题/down/挂了" 触发基础链路
_GENERAL_INCIDENT_KEYWORDS = [
    "故障", "问题", "down", "挂了", "崩了", "crash", "oops", "outage",
    "紧急", "P0", "P1", "严重",
]

# 基础链路：anomaly → rootcause → case → action（顺序有依赖）
_BASE_CHAIN = [
    (AgentSpecialty.ANOMALY_SLEUTH, []),
    (AgentSpecialty.ROOTCAUSE_HUNTER, [AgentSpecialty.ANOMALY_SLEUTH]),
    (AgentSpecialty.LOG_INTERPRETER, []),  # log 可以并行
    (AgentSpecialty.CASE_RETRIEVER, [AgentSpecialty.ANOMALY_SLEUTH, AgentSpecialty.ROOTCAUSE_HUNTER]),
    (AgentSpecialty.ACTION_ADVISOR, [AgentSpecialty.ROOTCAUSE_HUNTER, AgentSpecialty.CASE_RETRIEVER]),
]

# ---------------------------------------------------------------------------
# 机器人域链路：巡检调度 / 设备诊断并行，合规审计在两者之后
# ---------------------------------------------------------------------------

_ROBOT_KEYWORD_TO_SPECIALTY: list[tuple[list[str], AgentSpecialty]] = [
    (
        ["巡检", "巡查", "巡逻", "排班", "路线规划", "任务下发", "调度", "patrol", "route"],
        AgentSpecialty.PATROL_PLANNER,
    ),
    (
        ["诊断", "设备状态", "遥测", "离线", "电量", "障碍", "健康度", "故障设备", "telemetry", "diagnose"],
        AgentSpecialty.DEVICE_DIAGNOSTICIAN,
    ),
    (
        ["合规", "审计", "越权", "违规", "安全约束", "compliance", "audit"],
        AgentSpecialty.COMPLIANCE_AUDITOR,
    ),
]

_ROBOT_CHAIN: list[tuple[AgentSpecialty, list[AgentSpecialty]]] = [
    (AgentSpecialty.PATROL_PLANNER, []),
    (AgentSpecialty.DEVICE_DIAGNOSTICIAN, []),
    (
        AgentSpecialty.COMPLIANCE_AUDITOR,
        [AgentSpecialty.PATROL_PLANNER, AgentSpecialty.DEVICE_DIAGNOSTICIAN],
    ),
]


def decompose_goal(goal: str, context: dict[str, Any] | None = None) -> list[SubTask]:
    """从自然语言 goal 拆 SubTask 列表。

    策略：
    1. 先跑关键词匹配——显式提到的专长必进
    2. 有 general incident 关键词 → 进基础链路（anomaly → rootcause → case → action）
    3. 去重 + 依赖排序
    """
    context = context or {}
    goal_lower = goal.lower()

    # 0. 机器人域优先：命中巡检/诊断/合规关键词时，不再落入 AIOps 基础链路。
    robot_tasks = _decompose_robot_goal(goal, goal_lower, context)
    if robot_tasks:
        return robot_tasks

    triggered_specialties: set[AgentSpecialty] = set()

    # 1. 关键词匹配
    for keywords, specialty, _ in _KEYWORD_TO_SPECIALTY:
        for kw in keywords:
            if kw.lower() in goal_lower:
                triggered_specialties.add(specialty)
                break

    # 2. General incident → 基础链路
    has_general_incident = any(kw.lower() in goal_lower for kw in _GENERAL_INCIDENT_KEYWORDS)
    if has_general_incident:
        for spec, _ in _BASE_CHAIN:
            triggered_specialties.add(spec)

    if not triggered_specialties:
        # 没匹配上任何关键词 → 默认基础链路
        for spec, _ in _BASE_CHAIN:
            triggered_specialties.add(spec)

    # 3. 构建 SubTask（带依赖）
    task_map: dict[AgentSpecialty, SubTask] = {}
    for spec, deps in _BASE_CHAIN:
        if spec not in triggered_specialties:
            continue
        task_id = f"t_{spec.value}"
        dep_ids = [f"t_{d.value}" for d in deps if d in triggered_specialties]
        priority = 1 if spec in (AgentSpecialty.ANOMALY_SLEUTH, AgentSpecialty.ROOTCAUSE_HUNTER) else 2
        task_map[spec] = SubTask(
            task_id=task_id,
            description=_default_description(spec, goal),
            required_specialty=spec,
            priority=priority,
            depends_on=dep_ids,
            context=context,
        )

    # 额外关键词触发的 Agent（simulator / reflection）
    for spec in triggered_specialties:
        if spec in task_map:
            continue
        task_id = f"t_{spec.value}"
        task_map[spec] = SubTask(
            task_id=task_id,
            description=_default_description(spec, goal),
            required_specialty=spec,
            priority=3,
            context=context,
        )

    # 排序：priority 低的先；同 priority 按 base chain 顺序
    base_order = {spec.value: i for i, (spec, _) in enumerate(_BASE_CHAIN)}
    extra_order = 100
    def _sort_key(task):
        order = base_order.get(task.required_specialty.value, extra_order)
        return (task.priority, order)

    return sorted(task_map.values(), key=_sort_key)


def _decompose_robot_goal(
    goal: str,
    goal_lower: str,
    context: dict[str, Any],
) -> list[SubTask]:
    """机器人域拆解：命中即返回，未命中返回空列表交给 AIOps 规则。"""
    triggered: set[AgentSpecialty] = set()
    for keywords, specialty in _ROBOT_KEYWORD_TO_SPECIALTY:
        if any(kw.lower() in goal_lower for kw in keywords):
            triggered.add(specialty)

    if not triggered:
        return []

    tasks: list[SubTask] = []
    for spec, deps in _ROBOT_CHAIN:
        if spec not in triggered:
            continue
        task_id = f"t_{spec.value}"
        tasks.append(
            SubTask(
                task_id=task_id,
                description=_default_description(spec, goal),
                required_specialty=spec,
                priority=1 if not deps else 2,
                depends_on=[f"t_{d.value}" for d in deps if d in triggered],
                context=context,
            )
        )
    return tasks


def _default_description(spec: AgentSpecialty, goal: str) -> str:
    goal_short = goal[:80] + ("..." if len(goal) > 80 else "")
    templates: dict[str, str] = {
        AgentSpecialty.ANOMALY_SLEUTH.value: (
            f"对 goal='{goal_short}' 跑多检测器异常检测 + STL 自适应阈值，聚合 consensus span"
        ),
        AgentSpecialty.ROOTCAUSE_HUNTER.value: (
            "基于异常 span 和依赖图做 GCN/GAT 根因定位，输出 top-k 候选"
        ),
        AgentSpecialty.LOG_INTERPRETER.value: (
            f"对 goal='{goal_short}' 做 TinyBERT 日志分类 + noise 过滤，聚合 top-3 类别"
        ),
        AgentSpecialty.CASE_RETRIEVER.value: (
            "用异常 + 根因发现拼 query，从历史案例库检索 top-5 相似案例"
        ),
        AgentSpecialty.ACTION_ADVISOR.value: (
            "对 8 种候选动作跑双任务 MLP 预测，输出 top-3 建议 + risk_score"
        ),
        AgentSpecialty.SIMULATOR.value: (
            "生成故障仿真序列 + 检测器验证 coverage"
        ),
        AgentSpecialty.REFLECTION.value: (
            "反思处置结果 → append 新案例到 faiss"
        ),
        AgentSpecialty.PATROL_PLANNER.value: (
            f"对 goal='{goal_short}' 查机队状态与现有任务，输出巡检任务建议（默认不下发）"
        ),
        AgentSpecialty.DEVICE_DIAGNOSTICIAN.value: (
            "读取设备实时遥测与任务记录，按阈值给出风险等级与证据"
        ),
        AgentSpecialty.COMPLIANCE_AUDITOR.value: (
            "只读核查急停/故障设备任务、并发上限与失败记录，输出违规清单"
        ),
    }
    return templates.get(spec.value, f"Agent {spec.value} 处理 goal")
