# -*- coding: utf-8 -*-
"""PERF-07 验收实验——同一故障集对比：基线 / 上下文预算 / 模型路由（+检索缓存）。

清单验收口径：用同一故障集比较正确率、假成功率、token、首响应及总耗时；
先验证质量，再采用降本方案。

诚实红线：
- 检索全部走真实知识服务（/api/search），生成全部走真实 Ollama 推理；
- 无 mock、无伪造，任何一项失败如实标记 failed；
- 判分器为确定性启发式（定义见 print 输出），不使用主观打分。

用法：py -3.14 scripts/bench_perf07_faultset.py [--smoke]
输出：reports/perf07_faultset_results.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 真实推理环境：本机 Ollama + 两个真实模型（qwen3:1.7b 文本 / qwen2.5vl:3b 视觉-较大）
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:11434")
os.environ.setdefault("LLM_MODEL", "qwen3:1.7b")
os.environ.setdefault("LLM_MODEL_SIMPLE", "qwen3:1.7b")
os.environ.setdefault("LLM_MODEL_COMPLEX", "qwen2.5vl:3b")
os.environ.setdefault("KNOWLEDGE_API_KEY", "local-dev-70869b4bfaac35d7a16feff0e732208a")

from app.core.config import settings  # noqa: E402
from app.core.context_budget import ContextBudget, ModelRouter, RagQueryCache  # noqa: E402
from app.services.chat import SYSTEM_PROMPT, ChatService  # noqa: E402
from app.services.llm import LLMService  # noqa: E402

KNOW_URL = settings.knowledge_service_url
OUT_PATH = ROOT.parent / "reports" / "perf07_faultset_results.json"

N_VERBATIM = 5
N_PARAPHRASE = 5
N_NO_EVIDENCE = 3
SEED = 20261116

STOPWORDS = set("的了是在和与或及怎么操作如何进行使用一般处理正确步骤如果请尽量应该不要可以需要设置点击输入选择打开支持免费软件版本工具服务管理数据笔记系统使用指南详细教程介绍说明哪些什么以及通过对于关于这样那样一个一些非常".split())


def retrieve(query: str, top_k: int = 4) -> dict:
    body = json.dumps({"query": query, "top_k": top_k, "version": "reference"}).encode()
    req = urllib.request.Request(
        f"{KNOW_URL}/api/search", data=body, method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": os.environ["KNOWLEDGE_API_KEY"]},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return {"results": data.get("results", []), "ms": (time.perf_counter() - t0) * 1000}


def ollama_stream(model: str, prompt: str) -> dict:
    """真实流式推理：返回 TTFT / token 计数 / 总耗时 / 全文。"""
    payload = LLMService._payload(prompt, SYSTEM_PROMPT, stream=True, model=model)
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{settings.llm_base_url}/api/generate", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    ttft = None
    chunks = []
    counts = {}
    with urllib.request.urlopen(req, timeout=180) as resp:
        for line in resp:
            obj = json.loads(line.decode("utf-8", "replace"))
            if obj.get("response"):
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
                chunks.append(obj["response"])
            if obj.get("done"):
                counts = {k: obj.get(k) for k in ("prompt_eval_count", "eval_count")}
    total_ms = (time.perf_counter() - t0) * 1000
    return {
        "answer": "".join(chunks), "ttft_ms": ttft, "total_ms": total_ms,
        "prompt_tokens": counts.get("prompt_eval_count"), "gen_tokens": counts.get("eval_count"),
        "failed": ttft is None,
    }


def build_prompt(message: str, context: str) -> str:
    svc = ChatService()
    return svc._build_prompt(message=message, context=context, images=None)


def distinctive_terms(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[\w\u4e00-\u9fff]{2,}", text)
    seen, out = set(), []
    for w in words:
        w = w.lower()
        if w in STOPWORDS or w in seen or len(w) < 2:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def grade(question: dict, results: list[dict], answer: str) -> dict:
    expected = question.get("expected_sources") or []
    srcs = {r.get("source", "") for r in results}
    retrieval_hit = any(any(e in s for s in srcs) for e in expected) if expected else None
    grounded = None
    if expected:
        ev_text = " ".join(r.get("content", "") for r in results)
        terms = distinctive_terms(ev_text)
        grounded = any(t in answer for t in terms) if terms else None
    return {"retrieval_hit": retrieval_hit, "answer_grounded": grounded}


HEDGES = ("无法确认", "没有足够", "未找到", "知识库", "不能确定", "无法提供", "没有相关", "未提供", "不确定", "抱歉", "没有找到")


def false_success(answer: str) -> bool:
    """无证据题判假成功：回答缺乏对冲且给出具体动作指令（自信地编造）。"""
    if any(h in answer for h in HEDGES):
        return False
    concrete = re.search(r"(执行|运行|修改|配置|设置为|命令|第一步|步骤\d|\.conf|systemctl|nginx|mysql)", answer, re.I)
    return bool(concrete and len(answer) > 40)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="每条件只跑 2 题，验证链路")
    args = ap.parse_args()

    golden = json.load(open(ROOT.parent / "knowledge" / "evaluation" / "golden_set.json", encoding="utf-8"))
    verbatim = [c for c in golden if c.get("style") == "verbatim"]
    paraphrase = [c for c in golden if c.get("style") == "paraphrase"]
    n_v, n_p = (2, 2) if args.smoke else (N_VERBATIM, N_PARAPHRASE)
    step = (len(verbatim) + 6) // max(n_v, 1)
    picked = verbatim[::step][:n_v]
    step = (len(paraphrase) + 6) // max(n_p, 1)
    picked += paraphrase[::step][:n_p]
    no_ev = [
        {"question": "如何给宠物猫剪指甲才不会伤到它", "expected_sources": [], "style": "no-evidence"},
        {"question": "酸菜鱼的正宗做法步骤", "expected_sources": [], "style": "no-evidence"},
        {"question": "手机贴膜怎么避免气泡", "expected_sources": [], "style": "no-evidence"},
    ]
    cases = picked + no_ev
    print(f"故障集：{len(picked)} 知识题（{n_v} verbatim + {n_p} paraphrase）+ {N_NO_EVIDENCE} 无证据题")

    # ── 快照检索：同一故障集、同一证据，跨条件严格一致 ──────────────
    snapshot = {}
    for c in cases:
        r = retrieve(c["question"])
        snapshot[c["question"]] = {"results": r["results"], "retrieval_ms": round(r["ms"], 1)}
        exp = c.get("expected_sources") or []
        hit = "✓" if exp and any(any(e in x.get("source", "") for x in r["results"]) for e in exp) else ("-" if not exp else "✗")
        print(f"  检索 {hit} [{r['ms']:.0f}ms, {len(r['results'])}条] {c['question'][:30]}")

    # ── 检索缓存验证（RagQueryCache 生产键） ─────────────────────
    cache = RagQueryCache(ttl_sec=60, max_entries=128)
    cache_rows = []
    svc = ChatService()
    for c in cases[:5]:
        q = c["question"]
        key = cache.make_key(
            tenant="bench", user="bench", role="ops", version="reference", query=q,
            top_k=4, source=None, score_threshold=None, vector_weight=None, bm25_weight=None,
        )
        t0 = time.perf_counter()
        if cache.get(key) is None:
            cache.put(key, {"results": snapshot[q]["results"]})
            first = snapshot[q]["retrieval_ms"]
            second_ms = (time.perf_counter() - t0) * 1000 + first  # 首次=真实检索
            cache_rows.append({"question": q[:24], "first_ms": round(first, 1), "repeat_ms": 0.0, "hit": False})
        else:
            cache.get(key)
            cache_rows.append({"question": q[:24], "first_ms": first, "repeat_ms": round((time.perf_counter() - t0) * 1000, 3), "hit": True})
    # 第二轮：全部命中
    for row in cache_rows:
        q = row["question"]
        key = cache.make_key(tenant="bench", user="bench", role="ops", version="reference", query=q,
                             top_k=4, source=None, score_threshold=None, vector_weight=None, bm25_weight=None)
        t0 = time.perf_counter()
        hit = cache.get(key) is not None
        row["repeat_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        row["hit"] = hit

    # ── 条件 ────────────────────────────────────────────────────
    budget_default = ContextBudget(budget_chars=settings.context_budget_chars)
    budget_tight = ContextBudget(budget_chars=2000)
    router = ModelRouter(
        default_model=settings.llm_model,
        simple_model=settings.llm_model_simple,
        complex_model=settings.llm_model_complex,
    )
    conditions = [
        ("A_base", None, settings.llm_model),          # 全量证据、默认模型
        ("B_budget12k", budget_default, settings.llm_model),
        ("B2_budget2k", budget_tight, settings.llm_model),
        ("C_route", budget_default, None),             # 路由决定模型
    ]

    all_results = []
    for cond_name, budget, fixed_model in conditions:
        print(f"\n== 条件 {cond_name} ==")
        for c in cases:
            snap = snapshot[c["question"]]
            results = snap["results"]
            stats_d = None
            model_used = fixed_model
            if budget is not None:
                results, stats = budget.apply(results)
                stats_d = budget.stats_dict(stats)
            if fixed_model is None:
                d = router.route(c["question"], images=None, evidence_count=len(results), verification_required=False)
                model_used = d.model
                stats_d = {**(stats_d or {}), "routed": d.routed}
            context = svc.rag.build_context(results)
            prompt = build_prompt(c["question"], context)
            r = ollama_stream(model_used, prompt)
            g = grade(c, snapshot[c["question"]]["results"], r["answer"])
            row = {
                "condition": cond_name, "question": c["question"], "style": c["style"],
                "model": model_used, **g,
                "false_success": false_success(r["answer"]) if c["style"] == "no-evidence" else None,
                "ttft_ms": round(r["ttft_ms"], 1) if r["ttft_ms"] else None,
                "total_ms": round(r["total_ms"], 1),
                "prompt_tokens": r["prompt_tokens"], "gen_tokens": r["gen_tokens"],
                "budget_stats": stats_d, "failed": r["failed"],
                "answer_head": r["answer"][:120],
            }
            all_results.append(row)
            flag = "FAILED" if r["failed"] else f"{r['total_ms']:.0f}ms"
            print(f"  [{cond_name}] {flag} tokens={r['prompt_tokens']}+{r['gen_tokens']} hit={g['retrieval_hit']} grounded={g['answer_grounded']} | {c['question'][:26]}")

    # ── 汇总 ────────────────────────────────────────────────────
    summary = {}
    for cond_name, _, _ in conditions:
        rows = [r for r in all_results if r["condition"] == cond_name and not r["failed"]]
        know = [r for r in rows if r["style"] != "no-evidence"]
        noev = [r for r in rows if r["style"] == "no-evidence"]
        summary[cond_name] = {
            "n_ok": len(rows), "n_failed": len(rows) and len([r for r in all_results if r["condition"] == cond_name]) - len(rows),
            "retrieval_hit_rate": round(sum(1 for r in know if r["retrieval_hit"]) / max(len(know), 1), 3),
            "grounded_rate": round(sum(1 for r in know if r["answer_grounded"]) / max(len(know), 1), 3),
            "false_success_rate": round(sum(1 for r in noev if r["false_success"]) / max(len(noev), 1), 3) if noev else None,
            "median_ttft_ms": round(statistics.median([r["ttft_ms"] for r in rows if r["ttft_ms"]]), 1) if rows else None,
            "median_total_ms": round(statistics.median([r["total_ms"] for r in rows]), 1) if rows else None,
            "median_prompt_tokens": round(statistics.median([r["prompt_tokens"] for r in rows if r["prompt_tokens"]]), 1) if rows else None,
            "median_gen_tokens": round(statistics.median([r["gen_tokens"] for r in rows if r["gen_tokens"]]), 1) if rows else None,
        }

    out = {
        "meta": {
            "date": "2026-11-16", "llm_base_url": settings.llm_base_url,
            "models": {"default": settings.llm_model, "simple": settings.llm_model_simple, "complex": settings.llm_model_complex},
            "knowledge_url": KNOW_URL, "n_cases": len(cases),
            "graders": {
                "retrieval_hit": "expected_sources 命中真实检索结果 source（确定性）",
                "answer_grounded": "回答包含期望证据的≥1个特征词（确定性启发式）",
                "false_success": "无证据题：回答无对冲词且给出具体动作指令（确定性启发式）",
            },
        },
        "cache_rows": cache_rows, "summary": summary, "rows": all_results,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n== 汇总 ==")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"缓存行：{json.dumps(cache_rows, ensure_ascii=False)}")
    print(f"已写入 {OUT_PATH}")


if __name__ == "__main__":
    main()
