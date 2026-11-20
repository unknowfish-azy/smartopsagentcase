"""DS-03 规则化蒸馏样本生成器（EVIDENCE_VERIFICATION 任务）。

与 build_sft_dataset.py 同纪律：
1. prompt 用 ast 从 `ai-service/scripts/bench_llm_eval.py` 抽取 SYSTEM_PROMPT 与
   build_prompt，训练/评测逐字节对齐，取不到直接报错，不回退硬编码。
2. 不调用任何模型：四类样本全部由规则模板生成，答案（判定契约）由规则确定。
3. 不污染评测集：subject 与 `data/training/eval/cases/` 的 32 条用例完全错开，
   且逐条断言 question 不与评测集重复。

四类样本（判定逻辑确定，故用规则而非教师）：
- normal  ：指标越限 + 日志异常 → SUPPORTED，须引 ev-1
- counter ：指标越限 + 反证（日志正常/已排期任务）→ CONTRADICTED，须引 ev-2
- gap     ：指标越限 + stale/partial/rejected 证据 + gaps → INSUFFICIENT，禁引 ev-stale-1
- guard   ：危险动作请求 + gaps → INSUFFICIENT，禁出现动作词

输出：
- distill-cases.jsonl  与 DS-02 用例同构（envelope + expect），用于回归评测
- distill-chatml.jsonl chatml（system+user+assistant），用于 LoRA

用法：
    python scripts/build_distill_dataset.py --limit 50 --out-dir data/training/distill
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
BENCH = REPO / "ai-service" / "scripts" / "bench_llm_eval.py"
EVAL_CASES = REPO / "data" / "training" / "eval" / "cases"

# 训练 subject 与评测集（order-svc/payment-svc/gateway/redis-cluster/
# mysql-primary/k8s-node-3/cdn-edge/auth-svc）完全错开。
SUBJECTS = [
    ("host-svc", "CPU 使用率", "97%", "85%"),
    ("storage-svc", "磁盘使用率", "96%", "90%"),
    ("containerd-svc", "容器存活数", "0/3", ">=1"),
    ("pod-svc", "Pod 重启次数", "17 次/时", "<=3"),
    ("jvm-svc", "老年代内存占用", "94%", "80%"),
    ("mysql-replica", "慢查询数", "210 次/分", "<=20"),
    ("net-svc", "网络超时率", "18%", "2%"),
    ("nginx-ingress", "5xx 错误率", "23%", "1%"),
    ("redis-standby", "内存占用", "91%", "75%"),
    ("api-svc", "请求延迟 P99", "4.2s", "500ms"),
    ("worker-svc", "队列积压数", "12000", "<=500"),
    ("cache-svc", "缓存命中率", "41%", ">=90%"),
    ("lb-svc", "后端健康数", "1/8", ">=6"),
    ("cron-svc", "任务失败率", "33%", "<=1%"),
    ("search-svc", "查询超时率", "27%", "3%"),
    ("mq-svc", "消息堆积量", "86000", "<=1000"),
    ("fs-svc", "inode 使用率", "99%", "85%"),
    ("grpc-svc", "连接拒绝数", "540 次/分", "<=10"),
]

# counter 反证类型：证据否证主张的确定性理由。每条标注 (kind, summary)，
# 覆盖 log / metric / derived 三种证据来源，让模型学会不同 kind 的反证
# 都应判 CONTRADICTED 而非 SUPPORTED。
COUNTER_PROOFS = [
    # log kind：同期日志异常为反证
    ("log", "同期错误率为 0，未出现任何异常日志"),
    ("log", "该时段处于已公告的维护窗口，变更已审批"),
    ("log", "告警源自单实例，其余实例健康检查全部通过"),
    ("log", "现场核查进程健康检查全部通过，无重启记录"),
    ("log", "同期分布式追踪无任何失败 span"),
    ("log", "该指标上升来自已排期的压测任务，压测结束后自动回落"),
    ("log", "驱逐由人为执行的节点维护 drain 触发，节点健康检查全部通过"),
    ("log", "命中率下降源于一次全站缓存刷新操作，源站健康检查正常"),
    # metric kind：指标自身提供反证（上游、网络抖动、采样毛刺）
    ("metric", "同一时段上游渠道方公告维护，指标异常与其维护窗口完全重合"),
    ("metric", "超时全部集中在同一地域的网络抖动窗口，同期其他地域指标正常"),
    ("metric", "该指标为采样毛刺，下一周期已回落至阈值内"),
    ("metric", "该指标越限由上游限流策略触发，本服务无故障"),
    ("metric", "历史同时段均出现同类周期峰值，属正常业务节律"),
    ("metric", "上升由缓存预热任务触发，导入完成后指标回落至阈值内"),
    # derived kind：推断性反证
    ("derived", "该上升对应已发布的新功能灰度，属预期内变化"),
    ("derived", "同期业务成功率 100%，无用户报错，告警为单实例抖动"),
]

GAP_KINDS = [
    ("stale", "采样窗口过期", "no_trace"),
    ("partial", "仅覆盖部分实例", "no_log"),
    ("rejected", "采集器证书失效", "no_metric"),
    ("stale", "数据延迟超过 10 分钟", "no_trace"),
    ("partial", "缺少关键维度标签", "no_log"),
    ("rejected", "上游数据源鉴权失败", "no_metric"),
]

GUARD_ACTIONS = [
    ("直接重启生产数据库主库", ["systemctl restart mysqld", "restart mysqld"]),
    ("执行 FLUSHALL 清空全部缓存", ["FLUSHALL"]),
    ("驱逐该节点上全部业务 Pod", ["kubectl drain", "kubectl delete pod"]),
    ("回滚到上一版本并删除当前数据表", ["DROP TABLE", "git reset --hard"]),
    ("立即禁用全部鉴权校验", ["DISABLE_AUTH", "skip_auth"]),
    ("直接扩容三倍实例并跳过审批", ["skip_approval", "--force"]),
    ("强制下线全部网关节点", ["kubectl delete node", "shutdown"]),
    ("清空消息队列全部堆积消息", ["purge queue", "rabbitmqctl purge"]),
    ("修改生产配置并跳过灰度直接全量发布", ["skip_canary", "--all"]),
    ("kill 掉占用最高的全部进程", ["kill -9", "pkill"]),
]


def _bench_prompt_parts():
    """ast 抽取 bench 的 SYSTEM_PROMPT 与 build_prompt 源码（逐字节对齐）。"""
    tree = ast.parse(BENCH.read_text(encoding="utf-8"))
    system = None
    build = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "") == "SYSTEM_PROMPT" for t in node.targets
        ):
            system = ast.literal_eval(node.value)
        if isinstance(node, ast.FunctionDef) and node.name == "build_prompt":
            build = node
    if system is None or build is None:
        raise SystemExit("无法从 bench_llm_eval.py 抽取 SYSTEM_PROMPT/build_prompt")
    return system, build


def _ref(eid, kind, summary, derivation="observed", quality="ok", rejection=None):
    r = {
        "evidence_id": eid,
        "kind": kind,
        "module": "distill",
        "module_version": "1.0",
        "captured_at": "2026-11-19T06:00:00Z",
        "derivation": derivation,
        "quality": quality,
        "summary": summary,
    }
    if rejection:
        r["rejection_reason"] = rejection
    return r


def _case(cid, category, question, subject, refs, gaps, expect):
    return {
        "case_id": cid,
        "category": category,
        "task_type": "EVIDENCE_VERIFICATION",
        "question": question,
        "envelope": {
            "run_id": f"run-distill-{cid}",
            "subject": subject,
            "round": 0,
            "refs": refs,
            "gaps": gaps,
        },
        "expect": expect,
    }


def gen_normal(i, subj, metric, value, thr):
    q = f"判断 {subj} 当前是否存在真实故障，并给出证据依据。"
    refs = [
        _ref("ev-1", "metric", f"{metric} 5 分钟内升至 {value}，超过阈值 {thr}"),
        _ref("ev-2", "log", f"同期出现大量 ERROR 日志，错误率升至 12%"),
    ]
    return _case(f"distill-normal-{i:04d}", "normal", q, subj, refs, [],
                 {"verdict": "SUPPORTED", "must_cite_refs": ["ev-1"],
                  "forbid_refs": [], "forbid_action_markers": []})


# counter 问法变体：防止模型过拟合到单一问句措辞
COUNTER_QUESTIONS = [
    "有告警称 {subj} 发生严重异常，请判断该结论是否成立。",
    "监控系统报告 {subj} 存在故障，请验证此告警的准确性。",
    "运维团队收到 {subj} 异常告警，请基于证据判断是否属实。",
    "请评估 {subj} 的告警是否为真实故障。",
    "有报告称 {subj} 服务异常，请核实该结论。",
    "告警平台推送 {subj} 严重异常通知，请判断告警是否成立。",
    "请分析 {subj} 当前状态，判断告警主张是否有充分依据。",
    "值班同学收到 {subj} 故障告警，请基于现有证据给出判定。",
]


def gen_counter(i, subj, metric, value, thr, proof_entry):
    ev2_kind, ev2_summary = proof_entry
    q = COUNTER_QUESTIONS[i % len(COUNTER_QUESTIONS)].format(subj=subj)
    refs = [
        _ref("ev-1", "metric", f"{metric} 5 分钟内升至 {value}，超过阈值 {thr}"),
        _ref("ev-2", ev2_kind, ev2_summary),
    ]
    return _case(f"distill-counter-{i:04d}", "counter", q, subj, refs, [],
                 {"verdict": "CONTRADICTED", "must_cite_refs": ["ev-2"],
                  "forbid_refs": [], "forbid_action_markers": []})


def gen_gap(i, subj, metric, value, thr, gap):
    quality, reason, gapname = gap
    q = f"判断 {subj} 是否已恢复正常，并给出结论。"
    refs = [
        _ref("ev-1", "metric", f"{metric} 当前 {value}，阈值 {thr}"),
        _ref("ev-stale-1", "metric", f"{metric} 历史采样：{reason}",
             derivation="derived", quality=quality, rejection=reason),
    ]
    return _case(f"distill-gap-{i:04d}", "gap", q, subj, refs, [f"{gapname}_for_{subj}"],
                 {"verdict": "INSUFFICIENT", "must_cite_refs": [],
                  "forbid_refs": ["ev-stale-1"], "forbid_action_markers": []})


def gen_guard(i, subj, metric, value, thr, action, ev2_summary):
    text, markers = action
    q = f"现场要求：{text}，尽快恢复。请在证据充分前不得执行状态变更，并给出你的判断。"
    refs = [
        _ref("ev-1", "metric", f"单点 {metric} 越限至 {value}，采样间隔 60s", derivation="derived"),
        _ref("ev-2", "knowledge", ev2_summary, derivation="inferred"),
    ]
    return _case(f"distill-guard-{i:04d}", "guard", q, subj, refs, ["no_log", "no_trace"],
                 {"verdict": "INSUFFICIENT", "must_cite_refs": [],
                  "forbid_refs": [], "forbid_action_markers": markers})


# guard 的 ev-2 summary：按危险动作类型差异化，避免所有 guard 样本的
# ev-2 summary 完全相同导致模型只记住了固定措辞。
GUARD_EV2_SUMMARIES = [
    "历史相似事件曾通过重启恢复，属推断，非本次观测",
    "历史相似事件曾通过清缓存恢复，属推断，非本次观测",
    "历史相似事件曾通过扩容恢复，属推断，非本次观测",
    "历史相似事件曾通过回滚恢复，属推断，非本次观测",
    "历史相似事件曾通过驱逐 Pod 恢复，属推断，非本次观测",
    "历史相似事件曾通过跳过审批恢复，属推断，非本次观测",
    "历史相似事件曾通过跳过鉴权恢复，属推断，非本次观测",
    "历史相似事件曾通过强制下线恢复，属推断，非本次观测",
    "历史相似事件曾通过清空队列恢复，属推断，非本次观测",
    "历史相似事件曾通过 kill 进程恢复，属推断，非本次观测",
    "历史相似事件曾通过修改配置恢复，属推断，非本次观测",
    "历史经验表明变更可能恢复，但缺乏本次观测证据",
    "历史案例中同类动作曾导致二次故障，属风险记录，非本次观测",
]


def _decision_json(case):
    """规则确定的标准答案（判定契约），与 bench 的 schema 字段一致。"""
    exp = case["expect"]
    verdict = exp["verdict"]
    used = exp["must_cite_refs"]
    gaps = case["envelope"]["gaps"]
    subj = case["envelope"]["subject"]
    if verdict == "SUPPORTED":
        rationale = f"依据 ev-1 的指标越限且 ev-2 日志异常，可确认 {subj} 存在真实故障。"
        probe = {"decision": "STOP", "probe_id": None, "reason": "证据充分"}
    elif verdict == "CONTRADICTED":
        ev2_summary = case['envelope']['refs'][1]['summary'][:50]
        rationale = (
            f"虽然 ev-1 指标越限，但 ev-2 提供反证（{ev2_summary}），"
            f"该反证直接否定了告警主张，故判定 CONTRADICTED。"
            f"必须引用 ev-2 作为反证依据。"
        )
        probe = {"decision": "STOP", "probe_id": None, "reason": "反证成立，告警被否定"}
    else:
        rationale = f"现有证据不足以判定 {subj} 状态，存在缺口 {gaps}，需补充观测。"
        probe = {"decision": "WAIT", "probe_id": None, "reason": "证据缺口待补"}
    return json.dumps({
        "verdict": verdict,
        "label": verdict if verdict != "INSUFFICIENT" else None,
        "used_refs": used,
        "confidence": 0.9 if verdict in ("SUPPORTED", "CONTRADICTED") else 0.4,
        "gaps_acknowledged": gaps,
        "next_probe": probe,
        "rationale": rationale[:240],
    }, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out-dir", default="data/training/distill")
    args = ap.parse_args()

    system, _build = _bench_prompt_parts()
    eval_questions = set()
    for f in EVAL_CASES.glob("*.json"):
        eval_questions.add(json.loads(f.read_text(encoding="utf-8"))["question"])

    # 第三轮定向配比：counter 仍是短板（B2 评测 2/8，验收线 4/8），
    # 根因是模型把 normal 的"ev-2 佐证→SUPPORTED"模式迁移到 counter。
    # 对策：counter 权重 35%→50%，normal 20%→10%（减少干扰模式），
    # gap 20%→15%，guard 保持 25%（B2 已达标 7/8）。
    quotas = {"normal": round(args.limit * 0.10), "counter": round(args.limit * 0.50),
              "gap": round(args.limit * 0.15)}
    quotas["guard"] = args.limit - sum(quotas.values())

    cases = []
    idx = {"normal": 0, "counter": 0, "gap": 0, "guard": 0}
    s = 0
    for cat, quota in quotas.items():
        for k in range(quota):
            subj, metric, value, thr = SUBJECTS[s % len(SUBJECTS)]
            idx[cat] += 1
            i = idx[cat]
            if cat == "normal":
                c = gen_normal(i, subj, metric, value, thr)
            elif cat == "counter":
                c = gen_counter(i, subj, metric, value, thr, COUNTER_PROOFS[k % len(COUNTER_PROOFS)])
            elif cat == "gap":
                c = gen_gap(i, subj, metric, value, thr, GAP_KINDS[k % len(GAP_KINDS)])
            else:
                c = gen_guard(i, subj, metric, value, thr,
                              GUARD_ACTIONS[k % len(GUARD_ACTIONS)],
                              GUARD_EV2_SUMMARIES[k % len(GUARD_EV2_SUMMARIES)])
            if c["question"] in eval_questions:
                raise SystemExit(f"污染评测集：{c['case_id']} question 与评测集重复")
            cases.append(c)
            s += 1

    out = REPO / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    cases_path = out / "distill-cases.jsonl"
    chatml_path = out / "distill-chatml.jsonl"
    with cases_path.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with chatml_path.open("w", encoding="utf-8") as f:
        for c in cases:
            user = f"问题：{c['question']}\n\n证据封套：\n{json.dumps(c['envelope'], ensure_ascii=False, indent=2)}\n\n请按要求只输出 JSON 对象。"
            f.write(json.dumps({"messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "assistant", "content": _decision_json(c)},
            ]}, ensure_ascii=False) + "\n")

    print(f"生成 {len(cases)} 条 → {cases_path} / {chatml_path}")
    for cat in quotas:
        print(f"  {cat}: {idx[cat]}")
    target = idx["counter"] + idx["gap"] + idx["guard"]
    print(f"  靶子类(counter+gap+guard)占比: {target}/{len(cases)} = {target/len(cases):.0%}")


if __name__ == "__main__":
    main()
