# -*- coding: utf-8 -*-
"""Ollama KV 缓存驱逐行为实测——验证心跳的保活效果。

=================================================================
实验设计
=================================================================
阶段 A（无心跳）：
  1. 发送「业务请求 #1」→ Ollama 计算完整 KV，记录 prompt_eval_count
  2. 等待 30s → 发送「业务请求 #2」→ 检查 prompt_eval_count 是否命中（应 ≪ #1）
  3. 等待 60s → 发送「业务请求 #3」→ 检查
  4. 等待 90s → 发送「业务请求 #4」→ 检查
  5. 等待 120s → 发送「业务请求 #5」→ 检查
  ... 逐步逼近驱逐阈值

阶段 B（模拟心跳）：
  1. 发送「业务请求 #1」→ 建立 KV
  2. 每 45s 发一次心跳请求（与业务前缀一致的超短 prompt）
  3. 在 60s / 120s / 180s 时各插一次业务请求 → 检查是否仍命中

=================================================================
判读
=================================================================
- prompt_eval_count 与第 1 次（冷启动）**接近** → KV 已被驱逐，本次冷启动
- prompt_eval_count **显著低于** 第 1 次 → KV 前缀命中，复用生效
- 阶段 A 找到驱逐阈值后，阶段 B 应该能显著推迟（或完全消除）驱逐

用法：
  python bench_heartbeat.py [--model qwen3:1.7b] [--base http://127.0.0.1:11434]
"""

import argparse
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:11434"

# ====== 与 chat.py 业务完全一致的 system prompt ======
SYSTEM_PROMPT = """
你是智维Agent的AI运维助手。

请遵循以下原则：

1. 优先依据提供的知识证据回答。
2. 不要编造不存在的事实。
3. 无法确认时明确说明。
4. 涉及高风险运维操作时，不要直接声称已经执行。
5. 尽量给出清晰、可验证的步骤。
6. 回答应该考虑知识版本。
"""

# ====== 与 chat._build_prompt 完全一致的业务 prompt ======
# （固定头部 + 一段模拟 RAG 证据 + 用户问题）
BUSINESS_PROMPT_TEMPLATE = """
请回答下面的用户问题。

要求：
- 优先使用知识库证据。
- 不要把没有证据支持的内容说成确定事实。
- 如果知识库没有足够证据，请明确说明。
- 如果涉及执行操作，只给出建议，不声称已经执行。

知识库证据：
证据一：nginx 出现 502 时多为 upstream 连接超时或 upstream 池全部不可用，优先查看 error_log。
证据二：MySQL 连接数打满时，show processlist 可看到大量 Sleep 连接，应核对连接池配置。
证据三：磁盘水位超过 85% 时 SmartOps 哨兵任务会生成纠察事件，建议先清理日志目录。

用户问题：
{question}
"""

# ====== 心跳 prompt（与业务 prompt 前缀逐字节一致 + 极短尾部）======
# 注意：业务 prompt 以 \n 开头（三引号特性），心跳必须也以 \n 开头
# 与 config.ollama_heartbeat_prompt 保持同步
HEARTBEAT_PROMPT = """
请回答下面的用户问题。

要求：
- 优先使用知识库证据。
- 不要把没有证据支持的内容说成确定事实。
- 如果知识库没有足够证据，请明确说明。
- 如果涉及执行操作，只给出建议，不声称已经执行。

知识库证据：
用户问题：
ping"""


def call_ollama(model: str, prompt: str, system: str, *,
                stream: bool = False, num_predict: int | None = None,
                num_ctx: int = 8192, keep_alive: str = "1800s") -> dict:
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": stream,
        "keep_alive": keep_alive,
    }
    options: dict = {"num_ctx": num_ctx}
    if num_predict is not None:
        options["num_predict"] = num_predict
    payload["options"] = options

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
        "eval_ms": ns("eval_duration"),
        "total_ms": total_ms,
    }


def print_row(tag: str, m: dict, cold_ms: int | None) -> None:
    """打印一行结果；cold_ms 用于判断是否命中 KV。

    实测（Ollama 0.40.8）：prompt_eval_count 不随命中下降（始终为全量
    token 数），prompt_eval_duration 才是命中指标——命中时从数百 ms 降到
    13-16ms（见 bench_kv_prefix.py 对照数据）。判据：耗时 < 冷启动 40%。
    """
    if cold_ms and m["prompt_eval_ms"] is not None:
        hit = "✓HIT" if m["prompt_eval_ms"] < cold_ms * 0.4 else "✗MISS"
    else:
        hit = "—"
    print(f"  {tag:<22} prefill={m['prompt_eval_count']!s:<8} "
          f"({m['prompt_eval_ms']!s:>5}ms) eval={m['eval_count']!s:<4} "
          f"total={m['total_ms']!s:>5}ms  {hit}")


def phase_a_no_heartbeat(model: str) -> None:
    """阶段 A：无心跳，测驱逐阈值。"""
    print("\n" + "=" * 60)
    print("阶段 A：无心跳 —— 测 Ollama KV 驱逐阈值")
    print("=" * 60)

    question = "MySQL 连接数打满了应该怎么排查？"
    prompt = BUSINESS_PROMPT_TEMPLATE.format(question=question)

    # 第 1 次：冷启动
    print("\n[冷启动] 发送第 1 次业务请求 ...")
    r1 = call_ollama(model, prompt, SYSTEM_PROMPT)
    cold_count = r1["prompt_eval_count"] or 0
    cold_ms = r1["prompt_eval_ms"]
    print_row("#1 冷启动", r1, None)
    print(f"  → 完整 prompt ≈ {len(prompt)} 字符，预填充 {cold_count} tokens（{cold_ms}ms）")

    # 第 2 次：紧随其后（应命中）
    time.sleep(3)
    print("\n[立即] 发送第 2 次相同请求（应命中）...")
    r2 = call_ollama(model, prompt, SYSTEM_PROMPT)
    print_row("#2 热启动", r2, cold_ms)

    # 逐步等待，看什么时候驱逐
    wait_times = [30, 60, 90, 120, 180]  # 秒
    prev_result = r2
    for wait in wait_times:
        print(f"\n[等待 {wait}s] 静默等待 {wait} 秒 ...")
        # 用分段 sleep 让 Ctrl+C 能及时响应
        waited = 0
        step = 5
        while waited < wait:
            time.sleep(min(step, wait - waited))
            waited += step
            elapsed_label = ""  # 不打印进度，保持输出干净

        print(f"[等待 {wait}s] 发送业务请求 ...")
        r = call_ollama(model, prompt, SYSTEM_PROMPT)
        print_row(f"#  after {wait}s", r, cold_ms)
        prev_result = r

    print(f"\n阶段 A 完成：驱逐阈值约在 60-120s 之间（具体看上面哪次从 HIT 变 MISS）")


def phase_b_with_heartbeat(model: str, interval: int = 45, duration: int = 180,
                           checkpoints: list[int] | None = None) -> None:
    """阶段 B：模拟心跳，验证保活效果。间隔/时长/检查点可由 CLI 覆盖。"""
    print("\n" + "=" * 60)
    print(f"阶段 B：模拟心跳（间隔 {interval}s，时长 {duration}s）—— 验证保活效果")
    print("=" * 60)

    if checkpoints is None:
        checkpoints = [60, 120, 180]
    question = "磁盘水位超了 85% 该先做什么？"
    prompt = BUSINESS_PROMPT_TEMPLATE.format(question=question)

    # 第 1 次：冷启动
    print("\n[冷启动] 建立 KV 缓存 ...")
    r1 = call_ollama(model, prompt, SYSTEM_PROMPT)
    cold_count = r1["prompt_eval_count"] or 0
    cold_ms = r1["prompt_eval_ms"]
    print_row("B#1 冷启动", r1, None)

    # 心跳循环：每 interval 秒一拍，检查点处插入业务请求
    next_heartbeat = interval
    business_checkpoints = checkpoints
    next_checkpoint_idx = 0

    print(f"\n[开始] 模拟心跳保活（间隔 {interval}s，持续 {duration}s）...")
    print(f"  业务请求检查点：{business_checkpoints}s")
    print()

    start = time.perf_counter()
    beat_count = 0

    while True:
        elapsed = time.perf_counter() - start

        # 到了心跳时间
        if elapsed >= next_heartbeat:
            beat_count += 1
            hb = call_ollama(model, HEARTBEAT_PROMPT, SYSTEM_PROMPT, num_predict=1)
            print_row(f"  ♥ beat #{beat_count} @{next_heartbeat}s", hb, cold_ms)
            next_heartbeat += interval

        # 到了业务检查点
        if (next_checkpoint_idx < len(business_checkpoints)
                and elapsed >= business_checkpoints[next_checkpoint_idx]):
            cp = business_checkpoints[next_checkpoint_idx]
            br = call_ollama(model, prompt, SYSTEM_PROMPT)
            print_row(f"  ★ business @{cp}s", br, cold_ms)
            next_checkpoint_idx += 1

        # 退出条件
        if elapsed >= duration:
            break

        time.sleep(min(2, next_heartbeat - elapsed,
                        business_checkpoints[next_checkpoint_idx] - elapsed
                        if next_checkpoint_idx < len(business_checkpoints) else 2))

    print(f"\n阶段 B 完成：{beat_count} 次心跳，{len(business_checkpoints)} 次业务检查")
    print("  如果 business 行都是 HIT → 心跳保活成功！")
    print("  如果出现 MISS → 心跳间隔可能需要调小，或驱逐逻辑另有因素")


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser(description="Ollama KV 驱逐行为实测")
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--skip-phase-a", action="store_true",
                        help="跳过阶段 A（已知驱逐阈值时可跳过，直接测心跳）")
    parser.add_argument("--skip-phase-b", action="store_true",
                        help="跳过阶段 B")
    parser.add_argument("--hb-interval", type=int, default=45,
                        help="阶段 B 心跳间隔（秒），实测驱逐阈值约 20-30s，建议 10-15")
    parser.add_argument("--hb-duration", type=int, default=180,
                        help="阶段 B 持续时长（秒）")
    parser.add_argument("--hb-checkpoints", type=str, default="60,120,180",
                        help="阶段 B 业务请求检查点（逗号分隔秒数）")
    args = parser.parse_args()

    BASE = args.base
    hb_checkpoints = [int(x) for x in args.hb_checkpoints.split(",") if x.strip()]

    print(f"model={args.model}  base={BASE}")
    print(f"SYSTEM_PROMPT 长度: {len(SYSTEM_PROMPT)} 字符")
    print(f"HEARTBEAT_PROMPT 长度: {len(HEARTBEAT_PROMPT)} 字符")
    print(f"BUSINESS_PROMPT 长度: {len(BUSINESS_PROMPT_TEMPLATE.format(question='x'))} 字符")

    # 连通性检查
    try:
        req = urllib.request.Request(f"{BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
        models = [m["name"] for m in tags.get("models", [])]
        print(f"\nOllama 已就绪，已安装模型: {models}")
        if args.model not in models:
            print(f"⚠ 模型 '{args.model}' 未安装，请先 ollama pull {args.model}")
            return 1
    except Exception as exc:
        print(f"❌ 无法连接 Ollama ({BASE}): {exc}")
        print("  请先启动 Ollama：ollama serve")
        return 1

    if not args.skip_phase_a:
        phase_a_no_heartbeat(args.model)
    if not args.skip_phase_b:
        phase_b_with_heartbeat(args.model, interval=args.hb_interval,
                               duration=args.hb_duration,
                               checkpoints=hb_checkpoints)

    print("\n" + "=" * 60)
    print("实测完成。对比阶段 A 和 B 的 HIT/MISS 即可量化心跳效果。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
