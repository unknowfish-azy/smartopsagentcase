# -*- coding: utf-8 -*-
"""演示动线（方案 #3）验证脚本——模拟连续问答 vs 分散提问的 KV 命中差异。

=================================================================
背景（2026-11-16 实测结论，见 bench_heartbeat.py / config.py）：
=================================================================
Ollama 0.40.8 每次请求后槽位缓存只保留 system+模板头部（~101 tokens），
完整前缀复用仅在请求间隔 <=5s 时可靠出现：
  - 间隔 2-5s：预填充 15-73ms（FA+q8_0 下命中更深）
  - 间隔 30s+：预填充 230-513ms（接近冷启动）

答辩策略（演示动线）：把同类问题编排到时间上邻近的段落连续演示，
让相邻请求间隔落在 2-5s 窗口内，预填充省 77-95%。

=================================================================
实验设计
=================================================================
模拟真实 RAG 问答：每个问题有独立证据块（模拟检索结果），共享
固定头部（system + 要求段）。两种节奏各跑 6 个问题：
  - 连排动线（sequential）：每题结束后 2s 即问下一题（答辩连排节奏）
  - 分散节奏（scattered） ：每题结束后 35s 再问下一题（翻页/讲解节奏）

指标：prompt_eval_ms（预填充耗时，TTFT 的主要波动项）+ total_ms。

用法：
  python bench_demo_flow.py                 # 两种模式都跑
  python bench_demo_flow.py --mode sequential   # 只跑连排（快速冒烟）
  python bench_demo_flow.py --mode scattered    # 只跑分散
"""

import argparse
import sys
import time
import urllib.request
import json

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

# ====== 业务 prompt 模板（与 chat._build_prompt 一致，含前导 \n）======
PROMPT_TEMPLATE = """
请回答下面的用户问题。

要求：
- 优先使用知识库证据。
- 不要把没有证据支持的内容说成确定事实。
- 如果知识库没有足够证据，请明确说明。
- 如果涉及执行操作，只给出建议，不声称已经执行。

知识库证据：
{evidence}

用户问题：
{question}
"""

# ====== 演示题单：6 个真实知识库问题（来源：Docker运维课/Docker重点背诵卡.md）======
# 每题独立证据块（模拟 RAG 检索结果），证据引用背诵卡原文，共享固定头部。
DEMO_QUESTIONS = [
    ("CentOS 7 换 yum 源的完整步骤是什么？",
     "证据一：换源四步：先备份原有源（mkdir -p /etc/yum.repos.d/bak 并 mv *.repo 到备份目录），再下载阿里云基础源 Centos-7.repo 和 EPEL 源 epel-7.repo。\n"
     "证据二：然后 yum clean all 清缓存，yum makecache 建缓存（顺序固定），最后 yum repolist 验证。"),
    ("Docker CE 的安装步骤有哪些？",
     "证据一：安装五步：yum 安装依赖（yum-utils、device-mapper-persistent-data、lvm2）→ yum-config-manager 添加 docker-ce 阿里云源 → yum -y install docker-ce。\n"
     "证据二：systemctl enable --now docker 启动并设开机自启，docker version 和 docker info 验证（Client 和 Server 两段都有内容才正常）。"),
    ("修改 daemon.json 后为什么没有生效？",
     "证据一：daemon.json 四铁律：JSON 里不能写注释、最后一个字段不能有尾逗号、改前先备份、改完必须 systemctl daemon-reload 加 systemctl restart docker。\n"
     "证据二：生效三连：systemctl daemon-reload && systemctl restart docker && docker info，验证生效看 docker info 里的 Registry Mirrors 段。"),
    ("Docker 镜像名的完整格式是什么？省略部分默认值是什么？",
     "证据一：镜像名全称格式：网址或IP[:端口]/名称/镜像名[:标签]。\n"
     "证据二：省略默认值：网址省略看 docker info 的仓库地址（默认 Docker Hub），端口默认 80，名称省略是官方 library，标签省略是 latest；latest 只是默认标签名，不保证最新，生产要显式写版本。"),
    ("容器和虚拟机有什么区别？",
     "证据一：容器秒级启动（只启动进程）、硬盘 MB 级、单机可跑上千个、资源几乎无损耗；虚拟机分钟级启动、GB 级硬盘、单机几十个、系统本身吃约 50% 资源。\n"
     "证据二：根因：容器 = namespace（隔离视野）+ cgroups（限制用量）+ UnionFS/overlay2（分层文件系统），共享宿主机内核，软隔离；虚拟机靠 Hypervisor 硬隔离。"),
    ("Dockerfile 怎么写能减小镜像体积？",
     "证据一：分层实验结论（v10~v14 实测）：多个 RUN 各自成层，yum 缓存被永久留在层里，镜像 791MB；合并成一个 RUN 用 && 连接后镜像 539MB。\n"
     "证据二：结论：相关操作合并 RUN + 行尾 &&，能显著减小镜像；Dockerfile 四段结构为 FROM 基础镜像、LABEL 维护者、RUN 镜像操作、CMD 默认命令。"),
]


def call_ollama(model: str, prompt: str) -> dict:
    """发送一次业务请求，返回关键指标。"""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "keep_alive": "1800s",
        "options": {"num_ctx": 8192},
    }
    started = time.perf_counter()
    req = urllib.request.Request(
        f"{BASE}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    total_ms = round((time.perf_counter() - started) * 1000)
    pe_ms = round(data["prompt_eval_duration"] / 1e6) if data.get("prompt_eval_duration") else 0
    return {"prefill_ms": pe_ms, "total_ms": total_ms,
            "eval_count": data.get("eval_count")}


def run_mode(model: str, mode: str, gap: int, cold_ms: int) -> list[dict]:
    """按指定节奏跑完 6 个演示问题，返回逐题指标。"""
    label = "连排动线" if mode == "sequential" else "分散节奏"
    print(f"\n--- {label}（题目间隔 {gap}s）---")
    results = []
    for i, (question, evidence) in enumerate(DEMO_QUESTIONS, 1):
        if i > 1:
            time.sleep(gap)
        prompt = PROMPT_TEMPLATE.format(evidence=evidence, question=question)
        m = call_ollama(model, prompt)
        ratio = m["prefill_ms"] / cold_ms * 100 if cold_ms else 0
        hit = "HIT" if cold_ms and m["prefill_ms"] < cold_ms * 0.4 else "MISS"
        short_q = question[:16]
        print(f"  Q{i} {short_q:<18} prefill={m['prefill_ms']:>4}ms "
              f"({ratio:4.0f}%)  total={m['total_ms']:>5}ms  {hit}")
        results.append({"q": i, **m, "ratio": ratio, "hit": hit})
    return results


def summarize(mode: str, results: list[dict], cold_ms: int) -> dict:
    """打印汇总并返回统计数据。"""
    label = "连排动线" if mode == "sequential" else "分散节奏"
    hits = sum(1 for r in results if r["hit"] == "HIT")
    avg = sum(r["prefill_ms"] for r in results) / len(results)
    saving = (1 - avg / cold_ms) * 100 if cold_ms else 0
    print(f"\n  [{label}] 命中 {hits}/{len(results)}，"
          f"平均预填充 {avg:.0f}ms，相比冷启动({cold_ms}ms)节省 {saving:.0f}%")
    return {"mode": mode, "hits": hits, "avg_prefill": avg, "saving_pct": saving}


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser(description="演示动线方案验证：连续问答 vs 分散提问")
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--mode", choices=["both", "sequential", "scattered"], default="both")
    parser.add_argument("--gap-sequential", type=int, default=2,
                        help="连排动线的题目间隔秒数（模拟答辩连排节奏，默认 2s）")
    parser.add_argument("--gap-scattered", type=int, default=35,
                        help="分散节奏的题目间隔秒数（模拟翻页讲解节奏，默认 35s）")
    args = parser.parse_args()
    BASE = args.base

    print(f"model={args.model}  base={BASE}")
    print(f"题单：{len(DEMO_QUESTIONS)} 个知识库运维问题（各自独立证据块，共享固定头部）")

    # 连通性检查
    try:
        req = urllib.request.Request(f"{BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
        models = [m["name"] for m in tags.get("models", [])]
        print(f"Ollama 已就绪，已安装模型: {models}")
        if args.model not in models:
            print(f"⚠ 模型 '{args.model}' 未安装，请先 ollama pull {args.model}")
            return 1
    except Exception as exc:
        print(f"❌ 无法连接 Ollama ({BASE}): {exc}")
        return 1

    # 冷启动基准（独立证据块的问题，代表"无任何命中"的下限）
    print("\n[基准] 冷启动测量 ...")
    q0, e0 = DEMO_QUESTIONS[0]
    cold = call_ollama(args.model, PROMPT_TEMPLATE.format(evidence=e0, question=q0))
    cold_ms = cold["prefill_ms"]
    print(f"  冷启动 prefill={cold_ms}ms  total={cold['total_ms']}ms")

    summary = []
    if args.mode in ("both", "sequential"):
        r = run_mode(args.model, "sequential", args.gap_sequential, cold_ms)
        summary.append(summarize("sequential", r, cold_ms))
    if args.mode in ("both", "scattered"):
        r = run_mode(args.model, "scattered", args.gap_scattered, cold_ms)
        summary.append(summarize("scattered", r, cold_ms))

    print("\n" + "=" * 60)
    print("结论")
    print("=" * 60)
    for s in summary:
        label = "连排动线" if s["mode"] == "sequential" else "分散节奏"
        print(f"  {label}: 命中 {s['hits']}/6，平均预填充 {s['avg_prefill']:.0f}ms，"
              f"节省 {s['saving_pct']:.0f}%")
    if len(summary) == 2:
        # summary 顺序 = [连排, 分散]，收益 = 分散平均 - 连排平均
        delta = summary[1]["avg_prefill"] - summary[0]["avg_prefill"]
        print(f"\n  动线收益：连排比分散平均每题省 {delta:.0f}ms 预填充。")
        print("  答辩建议：同类问题连排演示，题目间自然间隔即落在命中窗口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
