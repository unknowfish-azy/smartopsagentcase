"""计划 DAG 校验与拓扑分波（P3，蒸馏 AgentForge 的"规划师生成 DAG + 逐条校验"）。

AgentForge 机制：Planner 产出 DAG → 逐条校验 → 不合格修复一次 → 再失败退回简单形态。
本模块提供：
* ``validate_dag``        依赖合法性检查（未知依赖 / 自依赖 / 环）；
* ``repair_dag``          修复一次：剔除非法依赖边（保留步骤本身）；
* ``topological_waves``   Kahn 分波：同波步骤无依赖关系，可并行执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .steps import PlanStep


@dataclass
class DagValidation:
    """DAG 校验结果。"""

    ok: bool
    problems: list[str] = field(default_factory=list)
    # 非法依赖边 {(step_id, bad_dep)}，供修复使用
    illegal_edges: list[tuple[int, int]] = field(default_factory=list)


def validate_dag(steps: list[PlanStep]) -> DagValidation:
    """检查依赖引用与环路。step_id 重复也视为非法。"""

    problems: list[str] = []
    illegal: list[tuple[int, int]] = []

    ids = [s.step_id for s in steps]
    if len(ids) != len(set(ids)):
        problems.append("step_id 重复")
        return DagValidation(ok=False, problems=problems)

    id_set = set(ids)
    for step in steps:
        for dep in step.depends_on:
            if dep == step.step_id:
                problems.append(f"步骤 {step.step_id} 依赖自身")
                illegal.append((step.step_id, dep))
            elif dep not in id_set:
                problems.append(f"步骤 {step.step_id} 依赖不存在的步骤 {dep}")
                illegal.append((step.step_id, dep))

    if _find_cycle(steps):
        problems.append(f"依赖构成环: {' -> '.join(map(str, _find_cycle(steps)))}")
        return DagValidation(ok=False, problems=problems, illegal_edges=illegal)

    return DagValidation(ok=not problems, problems=problems, illegal_edges=illegal)


def repair_dag(steps: list[PlanStep]) -> list[PlanStep] | None:
    """修复一次：剔除非法依赖边，保留全部步骤。

    修复后仍存在环（环无法靠删边保语义）→ 返回 None，由上层退回线性执行。
    """

    validation = validate_dag(steps)
    if validation.ok:
        return steps

    illegal = set(validation.illegal_edges)
    repaired: list[PlanStep] = []
    for step in steps:
        cleaned = [d for d in step.depends_on if (step.step_id, d) not in illegal]
        if cleaned != step.depends_on:
            step = PlanStep(
                step_id=step.step_id,
                action=step.action,
                tool_name=step.tool_name,
                arguments=step.arguments,
                description=step.description,
                requires_approval=step.requires_approval,
                depends_on=cleaned,
            )
        repaired.append(step)

    # 环不在 illegal_edges 里（validate 对环直接失败），修复后复查
    if _find_cycle(repaired):
        return None
    return repaired


def topological_waves(steps: list[PlanStep]) -> list[list[PlanStep]] | None:
    """Kahn 分波：波次内步骤互相无依赖，可并行。

    存在环时返回 None。波内按 step_id 排序，保证确定性。
    """

    by_id = {s.step_id: s for s in steps}
    if len(by_id) != len(steps):
        return None

    indegree = {s.step_id: 0 for s in steps}
    dependents: dict[int, list[int]] = {s.step_id: [] for s in steps}
    for step in steps:
        for dep in step.depends_on:
            if dep in by_id:
                indegree[step.step_id] += 1
                dependents[dep].append(step.step_id)

    waves: list[list[PlanStep]] = []
    ready = sorted(sid for sid, deg in indegree.items() if deg == 0)
    done = 0
    while ready:
        waves.append([by_id[sid] for sid in ready])
        done += len(ready)
        next_ready: list[int] = []
        for sid in ready:
            for follower in dependents[sid]:
                indegree[follower] -= 1
                if indegree[follower] == 0:
                    next_ready.append(follower)
        ready = sorted(next_ready)

    if done != len(steps):
        return None  # 有环
    return waves


def _find_cycle(steps: list[PlanStep]) -> list[int] | None:
    """DFS 找一个依赖环（返回环上的 step_id 序列），无环返回 None。"""

    by_id = {s.step_id: s for s in steps}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {sid: WHITE for sid in by_id}
    stack: list[int] = []

    def dfs(sid: int) -> list[int] | None:
        color[sid] = GRAY
        stack.append(sid)
        for dep in by_id[sid].depends_on:
            if dep not in by_id:
                continue
            if color[dep] == GRAY:
                idx = stack.index(dep)
                return stack[idx:]
            if color[dep] == WHITE:
                found = dfs(dep)
                if found:
                    return found
        color[sid] = BLACK
        stack.pop()
        return None

    for sid in by_id:
        if color[sid] == WHITE:
            found = dfs(sid)
            if found:
                return found
    return None


__all__ = [
    "DagValidation",
    "validate_dag",
    "repair_dag",
    "topological_waves",
]
