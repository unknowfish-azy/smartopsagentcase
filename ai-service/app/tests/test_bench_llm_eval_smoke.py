"""DS-08 冒烟：bench_llm_eval.py 用 mock provider 能跑通（退出码 0、30s 内）。

防止 runner 以后静默坏掉；mock 不依赖任何真实模型权重，CI 可直接跑。
顺带断言 mock 全量用例通过 —— DS-08 把输出护栏幻觉规则接进了 check_case，
若护栏误拦 mock 输出会在这里暴露。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

AI_SERVICE = Path(__file__).resolve().parents[2]
SCRIPT = AI_SERVICE / "scripts" / "bench_llm_eval.py"
EVAL_DIR = AI_SERVICE.parent / "data" / "training" / "eval"
TAG = "ds08-smoke"


def _smoke_artifacts() -> list[Path]:
    return [EVAL_DIR / f"latest-{TAG}.json", *EVAL_DIR.glob(f"report-*-{TAG}.md")]


@pytest.fixture
def clean_smoke_artifacts():
    yield
    for path in _smoke_artifacts():
        if path.exists():
            path.unlink()


def test_bench_llm_eval_mock_smoke(clean_smoke_artifacts):
    cmd = [sys.executable, str(SCRIPT), "--provider", "mock", "--tag", TAG]
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(AI_SERVICE),
        capture_output=True,
        text=True,
        timeout=60,
    )
    elapsed = time.perf_counter() - started

    assert proc.returncode == 0, (
        f"bench_llm_eval mock 退出码 {proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert elapsed < 30, f"bench_llm_eval mock 耗时 {elapsed:.1f}s，要求 < 30s"

    latest = EVAL_DIR / f"latest-{TAG}.json"
    assert latest.exists(), f"未生成 {latest}"
    data = json.loads(latest.read_text(encoding="utf-8"))
    assert data["case_count"] >= 1
    assert data["pass_rate"] == 1.0, (
        f"mock 应全量通过，实际 pass_rate={data['pass_rate']}\n"
        + "\n".join(
            f"  {r['case_id']}: {r['failures']}" for r in data["cases"] if not r["passed"]
        )
    )
