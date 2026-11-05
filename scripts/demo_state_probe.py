"""现场演示：L4 状态核验的主动探活。

对一组真实目标执行 TCP / HTTP / 进程三类探测，把原始观测喂给
resolve_from_probes() 推导 resolved，再结合 agent_claim 判定
成功 / 假成功 / 存疑 / 失败。

不依赖任何服务在跑：探测不通就如实输出 closed / refused，
这本身就是演示的一部分（系统对"探测不到"是诚实的）。

用法：
    python scripts/demo_state_probe.py                     # 默认目标
    python scripts/demo_state_probe.py --claim "服务已恢复"  # 指定 agent 结论
    python scripts/demo_state_probe.py --url http://127.0.0.1:8001/docs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agent.inspector.verifiers.state_verifier import (  # noqa: E402
    StateVerifier,
    http_probe,
    port_probe,
    process_probe,
    resolve_from_probes,
)

DEFAULTS = {
    "ports": [("127.0.0.1", 80), ("127.0.0.1", 8080), ("127.0.0.1", 11434)],
    "urls": ["http://127.0.0.1:8001/docs"],
    "processes": ["python", "ollama", "nginx"],
}


def run(claim: str, ports, urls, processes) -> int:
    probes: list[dict] = []

    for host, port in ports:
        probe = port_probe(host, port, timeout=1.5)
        probes.append(probe)
        print(f"  [port   ] {host}:{port:<6} -> {probe['status']:<10} {probe.get('latency_ms', '')}ms")

    for url in urls:
        probe = http_probe(url, timeout=3.0)
        probes.append(probe)
        print(f"  [http   ] {url:<38} -> {probe.get('status_code', probe.get('status'))}")

    for name in processes:
        probe = process_probe(name)
        probes.append(probe)
        print(f"  [process] {name:<38} -> {probe['status']} (match {probe.get('match_count', 0)})")

    print("\n--- 判定 ---")
    resolved = resolve_from_probes(probes)
    verdict = StateVerifier().verify(claim, {"probes": probes})

    rows = [
        ("agent_claim", claim or "(空)"),
        ("探针推导 resolved", resolved),
        ("claim 分类", verdict.get("claim_state", "unknown")),
        ("判定", {
            True: "假成功（REJECTED）——声称成功但探针显示未恢复",
            False: "通过（PASS）——结论与观测一致",
        }.get(verdict.get("false_success"),
              "存疑（需人工复核）" if verdict.get("uncertain") else "未核验/证据不足"),
        ),
        ("reason", verdict.get("reason", "")),
    ]
    width = max(len(str(k)) for k, _ in rows)
    for key, value in rows:
        print(f"  {str(key):<{width}} : {value}")

    print("\n--- 原始探针（可直接复用为评测样本） ---")
    print(json.dumps(probes, ensure_ascii=False, indent=2)[:1200])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim", default="服务已恢复",
                        help="agent 给出的结论，用于判定是否假成功")
    parser.add_argument("--ports", default=",".join(f"{h}:{p}" for h, p in DEFAULTS["ports"]))
    parser.add_argument("--urls", default=",".join(DEFAULTS["urls"]))
    parser.add_argument("--processes", default=",".join(DEFAULTS["processes"]))
    args = parser.parse_args(argv)

    ports = []
    for item in filter(None, args.ports.split(",")):
        host, _, port = item.rpartition(":")
        ports.append((host or "127.0.0.1", int(port)))

    return run(
        args.claim,
        ports,
        filter(None, args.urls.split(",")),
        filter(None, args.processes.split(",")),
    )


if __name__ == "__main__":
    raise SystemExit(main())
