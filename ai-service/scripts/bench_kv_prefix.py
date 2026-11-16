# -*- coding: utf-8 -*-
"""KV-CACHE 前缀复用基准：对真实 Ollama 实测新旧 prompt 布局的预填充差异。

原理（B 站《到底什么是KV Cache，为啥不是QKV Cache》的应用层落地）：
- Ollama(llama.cpp) 只缓存「最近一次评估」prompt 的 KV；下次请求若与前缀
  逐字节一致，该前缀无需重新预填充（prompt_eval_count 下降、TTFT 缩短）。
- 旧布局把易变的用户问题放在最前 → 换任何问题前缀即失效；
  新布局（chat._build_prompt 现行实现）稳定段在前 → 前缀可跨请求复用。

口径：单机 Ollama + qwen3:1.7b；每组同问题连发 2 次，第 2 次与第 1 次
的差值即前缀复用收益。数据如实打印，不预填结论。

用法：python bench_kv_prefix.py [--model qwen3:1.7b] [--runs 2]
"""

import argparse
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:11434"

SYSTEM = (
    "你是智维Agent的运维知识助手。只依据知识库证据回答，"
    "没有证据的内容明确说明，不编造。"
)

CONTEXT_BLOCK = (
    "证据一：nginx 出现 502 时多为 upstream 连接超时或 upstream 池全部不可用，"
    "优先查看 error_log 中标记为 connect() failed / upstream timed out 的行。\n"
    "证据二：MySQL 连接数打满时，show processlist 可看到大量 Sleep 连接，"
    "应核对应用连接池 maxPoolSize 与 wait_timeout 配置。\n"
    "证据三：磁盘水位超过 85% 时 SmartOps 哨兵任务会生成纠察事件，"
    "建议先清理日志目录并复核 rotation 策略。"
)


def make_context(repeat: int) -> str:
    """repeat>1 时放大证据段（模拟生产 RAG 大上下文，预算上限 12k 字符）。"""
    return "\n".join(
        f"{CONTEXT_BLOCK}（批次 {i + 1}）" for i in range(repeat)
    )

REQUIREMENTS = """要求：
- 优先使用知识库证据。
- 不要把没有证据支持的内容说成确定事实。
- 如果知识库没有足够证据，请明确说明。
- 如果涉及执行操作，只给出建议，不声称已经执行。"""


def old_layout(question: str, context: str) -> str:
    """旧布局：用户问题在最前（前缀随问题变化，复用失效）。"""
    return f"""
请回答下面的用户问题。

用户问题：
{question}
知识库证据：
{context}

{REQUIREMENTS}
"""


def new_layout(question: str, context: str) -> str:
    """新布局：稳定前缀在前（与 chat._build_prompt 现行实现一致）。"""
    return f"""
请回答下面的用户问题。

{REQUIREMENTS}

知识库证据：
{context}

用户问题：
{question}
"""


def call_ollama(model: str, prompt: str, keep_alive: str, num_ctx: int = 0) -> dict:
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "system": SYSTEM,
        "stream": False,
        "keep_alive": keep_alive,
    }
    if num_ctx > 0:
        # 仅基准侧控制变量：默认 4096 窗口下 prompt+生成会挤掉缓存，干扰布局对比。
        payload["options"] = {"num_ctx": num_ctx}
    started = time.perf_counter()
    req = urllib.request.Request(
        f"{BASE}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    total_ms = round((time.perf_counter() - started) * 1000)
    ns = lambda key: round(data[key] / 1e6) if isinstance(data.get(key), (int, float)) else None
    return {
        "prompt_eval_count": data.get("prompt_eval_count"),
        "prompt_eval_ms": ns("prompt_eval_duration"),
        "eval_count": data.get("eval_count"),
        "total_ms": total_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--keep-alive", default="1800s")
    parser.add_argument("--context-repeat", type=int, default=1,
                        help="证据段重复次数（放大上下文观察预填充差距）")
    parser.add_argument("--num-ctx", type=int, default=0,
                        help="传给 Ollama options.num_ctx（0=不传，用服务端默认）")
    args = parser.parse_args()

    context = make_context(args.context_repeat)
    approx_chars = len(context)
    # 关键场景：Q1、Q1、Q2 —— 第 2 次验证「同问题重复」命中；
    # 第 3 次换问题（证据不变）验证新旧布局的真实差距：
    # 旧布局证据段在问题之后 → 整段重算；新布局只有问题尾部需要预填充。
    questions = [
        "MySQL 连接数打满了应该怎么排查？",
        "MySQL 连接数打满了应该怎么排查？",
        "磁盘水位超了 85% 该先做什么？",
    ]
    plans = [
        ("旧布局(问题在前)", [old_layout(q, context) for q in questions]),
        ("新布局(问题在后)", [new_layout(q, context) for q in questions]),
    ]

    print(f"model={args.model} 证据≈{approx_chars}字符(repeat={args.context_repeat}) "
          f"场景=Q1,Q1,Q2(换问题) keep_alive={args.keep_alive}")
    print(f"{'布局':<14}{'次序':<6}{'预填充token':<12}{'预填充ms':<10}{'解码token':<10}{'端到端ms':<10}")
    results = {}
    for name, prompts in plans:
        rows = []
        for i, prompt in enumerate(prompts, start=1):
            m = call_ollama(args.model, prompt, args.keep_alive, num_ctx=args.num_ctx)
            rows.append(m)
            tag = "Q1" if i <= 2 else "Q2(换问题)"
            print(f"{name:<14}第{i}次{tag:<8} {m['prompt_eval_count']!s:<12}{m['prompt_eval_ms']!s:<10}"
                  f"{m['eval_count']!s:<10}{m['total_ms']!s:<10}")
            time.sleep(1)
        results[name] = rows
        prefill_ms = [r["prompt_eval_ms"] for r in rows if r["prompt_eval_ms"] is not None]
        if len(prefill_ms) == len(rows):
            print(f"  -> 预填充耗时 Q1冷={prefill_ms[0]}ms / Q1热={prefill_ms[1]}ms / Q2换问题={prefill_ms[2]}ms")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
