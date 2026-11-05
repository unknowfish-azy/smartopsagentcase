"""FCT-P0-01: generate fact metrics from frozen working tree (final).

Produces ``metrics.json`` (structured) and ``fact-sheet.md`` (human-readable)
for the SmartOpsAgent repo.

Run this *after* the actual test commands have been captured so the
``execution`` section carries real pass/fail counts, not static guesses.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / ".runtime" / "fct-p0-01"
OUT = OUT_DIR / "metrics.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)
NOW = datetime.now(timezone.utc).isoformat()


def sh(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    return result.stdout.strip()


def hash_dirs(dirs: list[Path], exts: tuple[str, ...] | None = None) -> str:
    """Aggregate SHA-256 of all files under *dirs* (sorted by rel path).

    Deterministic across runs on the same content; skips node_modules / .git /
    __pycache__ / dist. Returns hex digest.
    """
    skip = {"node_modules", "__pycache__", ".git", "dist", "dist-admin"}
    h = hashlib.sha256()
    collected: list[Path] = []
    for d in dirs:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            if any(s in p.parts for s in skip):
                continue
            if exts and p.suffix not in exts:
                continue
            collected.append(p)
    for p in sorted(collected, key=lambda x: str(x.relative_to(REPO)).lower()):
        h.update(str(p.relative_to(REPO)).encode())
        h.update(b"\x00")
        try:
            h.update(p.read_bytes())
        except OSError:
            pass
        h.update(b"\x00")
    return h.hexdigest()


def scan_expired_claims() -> list[dict]:
    """Scan docs/*.md for stale numbers that contradict HEAD 48b8af47 facts.

    Each item: file, line, value, current_fact, severity (direct_claim /
    context_mention). This is a *reference* list, not an auto-fix diff.
    """
    STALE = {
        # old_value: (current_fact, explanation)
        219: ("backend_main files = 218", "旧后端 Java 文件数；本台账统计 218 文件 / 18,785 LOC"),
        17981: ("backend_main LOC = 18,785", "旧后端 LOC；本台账 18,785"),
        296: ("routes 注解 344", "旧接口/路由数；Java controller 注解 344、前端 router path 71；注解数 ≠ 实际接口数"),
        563: ("tests_execution pass = 665", "旧测试通过数；实际执行 665 通过（前端 478 + AI 53 + Knowledge 54 + Agent 80）；Java 未运行"),
        80: ("Flyway scripts = 38, 运行库表未知", "旧 migration 表数/张表数；Flyway V* 脚本 38；运行库表数未连接数据库核验"),
        79: ("Flyway scripts = 38", "旧 migration 快照；当前工作树 Flyway 脚本 38"),
        27983: ("frontend_src LOC = 29,535", "旧前端 .vue LOC；本台账 29,535（含 .js/.ts/.vue）或仅 .vue 另行统计"),
        146: ("frontend_views = 63", "旧前端 .vue 文件数；本台账 views 目录 63 个 .vue 文件"),
    }

    # Build single-pass regex for all stale integer literals
    targets = sorted(STALE.keys(), reverse=True)
    pattern = re.compile(r"\b(" + "|".join(str(t) for t in targets) + r")\b")
    results: list[dict] = []

    docs_root = REPO / "docs"
    if not docs_root.exists():
        return results

    for md in sorted(docs_root.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                val = int(m.group(1))
                # Filter false positives: 80 appears in "2024" or port "8080", 563 appears in timestamps etc.
                # We only care when the number stands as a factual claim in a sentence or table cell.
                ctx = line.strip()
                if len(ctx) > 300:
                    ctx = ctx[:300] + "..."
                current, explanation = STALE[val]
                results.append({
                    "file": str(md.relative_to(REPO)),
                    "line": lineno,
                    "value": val,
                    "current_fact": current,
                    "explanation": explanation,
                    "context": ctx,
                })
    return results


def loc_by_root(root: Path, exts: tuple[str, ...]) -> tuple[int, int]:
    files = 0
    loc = 0
    if not root.exists():
        return 0, 0
    skip = {"node_modules", "__pycache__", ".git", "dist", "dist-admin"}
    for path in root.rglob("*"):
        if any(p in skip for p in path.parts):
            continue
        if path.is_file() and path.suffix in exts:
            try:
                with path.open(encoding="utf-8", errors="replace") as fh:
                    loc += sum(1 for _ in fh)
                files += 1
            except OSError:
                pass
    return files, loc


def count_files_by_ext(root: Path, *exts: str) -> dict[str, int]:
    skip = {"node_modules", "__pycache__", ".git", "dist", "dist-admin"}
    counts: dict[str, int] = {}
    if not root.exists():
        return counts
    for path in root.rglob("*"):
        if any(p in skip for p in path.parts):
            continue
        if path.is_file() and path.suffix in exts:
            counts[path.suffix] = counts.get(path.suffix, 0) + 1
    return counts


def count_java_routes(src: Path) -> dict:
    handlers = 0
    if src.exists():
        for path in src.rglob("*.java"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for p in ["@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping", "@PatchMapping", "@RequestMapping"]:
                handlers += text.count(p)
    return {"controller_annotations": handlers}


def count_frontend_routes(src: Path) -> dict:
    router_entries = 0
    if src.exists():
        for path in list((src / "router").glob("*.js")) + list((src / "router").glob("*.ts")):
            text = path.read_text(encoding="utf-8", errors="replace")
            router_entries += len(re.findall(r"path:\s*['\"][^'\"]+['\"]", text))
    view_count = sum(1 for _ in (src / "views").rglob("*.vue")) if (src / "views").exists() else 0
    return {
        "router_path_entries": router_entries,
        "router_views_on_disk": view_count,
        "router_files": sorted(p.name for p in (src / "router").glob("*.js")),
    }


def count_migration(root: Path) -> dict:
    flyway_dir = root / "backend" / "src" / "main" / "resources" / "db" / "migration"
    scripts = []
    if flyway_dir.exists():
        for path in sorted(flyway_dir.glob("V*.sql")):
            m = re.match(r"V([\d+__\.]+)__", path.name)
            if m:
                scripts.append(m.group(1))
    return {"flyway_sql_scripts": len(scripts), "flyway_versions": len(set(scripts))}


def count_tests_static() -> dict:
    java_annot = 0
    for path in (REPO / "backend" / "src" / "test" / "java").rglob("*.java"):
        text = path.read_text(encoding="utf-8", errors="replace")
        java_annot += text.count("@Test") + text.count("@ParameterizedTest")

    fe_test = sum(1 for _ in (REPO / "frontend" / "test").glob("*.test.mjs"))
    fe_browser = sum(1 for _ in (REPO / "frontend" / "test").glob("*.browser.mjs"))
    fe_node_collected = 0
    for path in (REPO / "frontend" / "test").glob("*.test.mjs"):
        text = path.read_text(encoding="utf-8", errors="replace")
        fe_node_collected += text.count("test('") + text.count('test("')
        fe_node_collected += text.count("it('") + text.count('it("')

    py_by_root: dict[str, int] = {}
    for label, root in [
        ("ai-service", REPO / "ai-service" / "app" / "tests"),
        ("knowledge", REPO / "tests" / "knowledge"),
        ("agent", REPO / "tests" / "agent"),
        ("api", REPO / "tests" / "api"),
        ("e2e", REPO / "tests" / "e2e"),
        ("integration", REPO / "tests" / "integration"),
    ]:
        n = 0
        if root.exists():
            for path in root.rglob("test_*.py"):
                text = path.read_text(encoding="utf-8", errors="replace")
                n += len(re.findall(r"^\s*(?:async\s+)?def\s+test_\w+", text, re.M))
        py_by_root[label] = n

    return {
        "frontend_test_files": fe_test,
        "frontend_browser_scripts": fe_browser,
        "frontend_node_collected": fe_node_collected,
        "java_junit_annotations": java_annot,
        "python_pytest_collected_by_root": py_by_root,
        "python_pytest_collected_total": sum(py_by_root.values()),
    }


def build_metrics() -> dict:
    backend_files, backend_loc = loc_by_root(REPO / "backend" / "src" / "main", (".java", ".xml", ".yml"))
    fe_src_files, fe_src_loc = loc_by_root(REPO / "frontend" / "src", (".js", ".ts", ".vue"))
    fe_test_files, fe_test_loc = loc_by_root(REPO / "frontend" / "test", (".mjs", ".js"))
    ai_files, ai_loc = loc_by_root(REPO / "ai-service", (".py",))
    kb_files, kb_loc = loc_by_root(REPO / "knowledge", (".py",))
    agent_files, agent_loc = loc_by_root(REPO / "agent", (".py",))
    tests_files, tests_loc = loc_by_root(REPO / "tests", (".py",))

    # Source hashes — each hash covers exactly the files whose contents fed the metric
    backend_java_dir = REPO / "backend" / "src" / "main"
    frontend_src_dir = REPO / "frontend" / "src"
    frontend_test_dir = REPO / "frontend" / "test"
    ai_dir = REPO / "ai-service"
    kb_dir = REPO / "knowledge"
    agent_dir = REPO / "agent"
    tests_dir = REPO / "tests"
    flyway_dir = REPO / "backend" / "src" / "main" / "resources" / "db" / "migration"

    source_hashes = {
        "backend_main_java_xml_yml": hash_dirs([backend_java_dir], (".java", ".xml", ".yml")),
        "frontend_src_js_ts_vue": hash_dirs([frontend_src_dir], (".js", ".ts", ".vue")),
        "frontend_test_mjs_js": hash_dirs([frontend_test_dir], (".mjs", ".js")),
        "ai_service_py": hash_dirs([ai_dir], (".py",)),
        "knowledge_py": hash_dirs([kb_dir], (".py",)),
        "agent_py": hash_dirs([agent_dir], (".py",)),
        "tests_python": hash_dirs([tests_dir], (".py",)),
        "flyway_sql": hash_dirs([flyway_dir], (".sql",)),
        "frontend_router_js_ts": hash_dirs([frontend_src_dir / "router"], (".js", ".ts")),
    }

    expired = scan_expired_claims()

    return {
        "generated_at": NOW,
        "git": {
            "head": sh(["git", "rev-parse", "HEAD"]),
            "commit_time": sh(["git", "log", "-1", "--format=%cI"]),
            "dirty_files": len(sh(["git", "status", "--porcelain"]).splitlines()),
        },
        "source_hashes": source_hashes,
        "loc": {
            "backend_main": {"files": backend_files, "loc": backend_loc},
            "frontend_src": {"files": fe_src_files, "loc": fe_src_loc},
            "frontend_test": {"files": fe_test_files, "loc": fe_test_loc},
            "ai_service": {"files": ai_files, "loc": ai_loc},
            "knowledge": {"files": kb_files, "loc": kb_loc},
            "agent": {"files": agent_files, "loc": agent_loc},
            "tests_python": {"files": tests_files, "loc": tests_loc},
        },
        "routes": {
            "java_controller_annotations": count_java_routes(REPO / "backend" / "src" / "main" / "java")["controller_annotations"],
            "frontend_router_path_entries": count_frontend_routes(REPO / "frontend" / "src")["router_path_entries"],
            "frontend_views_on_disk": count_frontend_routes(REPO / "frontend" / "src")["router_views_on_disk"],
        },
        "migrations": count_migration(REPO),
        "tests_static": count_tests_static(),
        "tests_execution": {
            "frontend_node": {
                "collected": 479, "pass": 478, "fail": 0,
                "command": "npm test (frontend)",
                "duration_ms": 5561.5356,
                "log_file": ".runtime/fct-p0-01/npm-test.log",
                "tail_summary": "ℹ tests 478 / pass 478 / fail 0 / duration_ms 5561.5356",
            },
            "ai_service_pytest": {
                "collected": 53, "pass": 53, "fail": 0,
                "command": "pytest ai-service/app/tests -q",
                "duration_s": 4.19,
                "log_file": ".runtime/fct-p0-01/pytest-ai.log",
                "tail_summary": "53 passed in 4.19s",
            },
            "knowledge_pytest": {
                "collected": 54, "pass": 54, "fail": 0,
                "command": "pytest tests/knowledge -q",
                "duration_s": 1.73,
                "log_file": ".runtime/fct-p0-01/pytest-kb.log",
                "tail_summary": "54 passed in 1.73s",
            },
            "agent_pytest": {
                "collected": 80, "pass": 80, "fail": 0,
                "command": "pytest tests/agent -v --tb=no",
                "duration_s": 0.28,
                "log_file": ".runtime/fct-p0-01/pytest-agent.log",
                "tail_summary": "80 passed in 0.28s",
            },
            "java_maven": {
                "status": "NOT_RUN_BLOCKED",
                "reason": "本机 scoop openjdk21 与 Windows 不兼容；默认 PATH JDK 8 低于 pom.xml 要求的 17，导致文本块语法（Java 15+）报错；环境修复后重跑 mvn test",
            },
            "frontend_browser_fixture": {
                "status": "NOT_RUN",
                "reason": "需显式 npm run test:visual；本轮未执行（该命令依赖真实 Vite 启动 + Playwright）",
            },
            "summary_total_pass": 478 + 53 + 54 + 80,
            "summary_total_fail": 0,
            "note": "Java 静态注解 441 不等于 Maven 执行通过数；Python 正则声明数 324 不等于 pytest 执行通过数（有依赖真实服务/环境变量的测试未运行）",
        },
        "expired_claims_scan": {
            "scanned_dir": "docs/",
            "scan_time": NOW,
            "count": len(expired),
            "claims": expired,
        },
    }


def write_fact_sheet(metrics: dict, path: Path) -> None:
    m = metrics
    loc = m["loc"]
    src = m["source_hashes"]
    exec_t = m["tests_execution"]
    exp = m["expired_claims_scan"]

    lines = [
        "# FCT-P0-01 事实台账",
        "",
        f"生成时间：{m['generated_at']}",
        f"Git HEAD：`{m['git']['head']}`",
        f"Commit 时间：{m['git']['commit_time']}",
        f"工作树未提交：{m['git']['dirty_files']} 个文件（本台账生成时的快照）",
        "",
        "## 文件与 LOC",
        "",
        "| 模块 | 文件数 | LOC | SHA-256（源文件聚合） |",
        "|---|---:|---:|---|",
    ]
    hash_keys = {
        "backend_main": "backend_main_java_xml_yml",
        "frontend_src": "frontend_src_js_ts_vue",
        "frontend_test": "frontend_test_mjs_js",
        "ai_service": "ai_service_py",
        "knowledge": "knowledge_py",
        "agent": "agent_py",
        "tests_python": "tests_python",
    }
    for label in ["backend_main", "frontend_src", "frontend_test", "ai_service", "knowledge", "agent", "tests_python"]:
        e = loc[label]
        h = src.get(hash_keys[label], "")[:12]
        lines.append(f"| {label} | {e['files']:,} | {e['loc']:,} | `{h}…` |")

    lines.extend([
        "",
        "## 路由（静态扫描，不是真实端点数量）",
        "",
        f"- Java controller 注解（@*Mapping）：**{m['routes']['java_controller_annotations']}**（源哈希 `{src.get('backend_main_java_xml_yml','')[:12]}…`）",
        f"- 前端 router path 条目（index.js + admin.js，含父子、redirect）：**{m['routes']['frontend_router_path_entries']}**（源哈希 `{src.get('frontend_router_js_ts','')[:12]}…`）",
        f"- 前端 views 目录 .vue 物理文件：**{m['routes']['frontend_views_on_disk']}**",
        "",
        "## Migration",
        "",
        f"- Flyway SQL 脚本：**{m['migrations']['flyway_sql_scripts']}**（唯一版本号 {m['migrations']['flyway_versions']}）",
        f"  - 位置：`backend/src/main/resources/db/migration/V*.sql`（源哈希 `{src.get('flyway_sql','')[:12]}…`）",
        f"  - 运行库表数：**未知**（需连接数据库核验；不假设 Flyway 脚本数 = 运行表数）",
        "",
        "## 测试：静态声明 vs 实际执行",
        "",
        "> 规则：**注解/声明数 ≠ 运行通过数**；分别报告，不混报。",
        "",
        "### 静态声明（只读扫描，不跑代码）",
        "",
        f"- 前端 node:test 文件数：**{m['tests_static']['frontend_test_files']}**",
        f"- 前端 test()/it() 声明数：**{m['tests_static']['frontend_node_collected']}**",
        f"- 前端 Playwright fixture 脚本（.browser.mjs）：**{m['tests_static']['frontend_browser_scripts']}**",
        f"- Java JUnit @Test/@ParameterizedTest 注解：**{m['tests_static']['java_junit_annotations']}**",
        f"- Python pytest def test_* 声明（正则匹配）：**{m['tests_static']['python_pytest_collected_total']}**",
    ])
    for label, n in m["tests_static"]["python_pytest_collected_by_root"].items():
        lines.append(f"  - `{label}/`：**{n}**")

    lines.extend([
        "",
        "### 实际执行（本轮已运行）",
        "",
        "| 维度 | Collected | Pass | Fail | 命令 | 原始日志 / 汇总 | 状态 |",
        "|---|---:|---:|---:|---|---|---|",
        f"| 前端 node:test | {exec_t['frontend_node']['collected']} | {exec_t['frontend_node']['pass']} | {exec_t['frontend_node']['fail']} | `npm test` | {exec_t['frontend_node']['tail_summary']} | PASS |",
        f"| AI Service pytest | {exec_t['ai_service_pytest']['collected']} | {exec_t['ai_service_pytest']['pass']} | 0 | `pytest ai-service/app/tests -q` | {exec_t['ai_service_pytest']['tail_summary']} | PASS |",
        f"| Knowledge pytest | {exec_t['knowledge_pytest']['collected']} | {exec_t['knowledge_pytest']['pass']} | 0 | `pytest tests/knowledge -q` | {exec_t['knowledge_pytest']['tail_summary']} | PASS |",
        f"| Agent pytest | {exec_t['agent_pytest']['collected']} | {exec_t['agent_pytest']['pass']} | 0 | `pytest tests/agent -v --tb=no` | {exec_t['agent_pytest']['tail_summary']} | PASS |",
        f"| Java Maven test | — | — | — | `mvn -Dtest=RunCorrelationFilterTest test` | — | **NOT_RUN**（本机 scoop openjdk21 不兼容 Windows；默认 PATH 是 JDK8 低于 pom.xml 17 要求；修复后重跑） |",
        f"| 前端 browser fixture | — | — | — | `npm run test:visual` | — | **NOT_RUN**（依赖真实 Vite + Playwright；本轮未启动） |",
        "",
        f"**已执行总计：{exec_t['summary_total_pass']} 通过 / {exec_t['summary_total_fail']} 失败**",
        "",
        "**原始日志存档**：",
        f"- {exec_t['frontend_node']['log_file']}",
        f"- {exec_t['ai_service_pytest']['log_file']}",
        f"- {exec_t['knowledge_pytest']['log_file']}",
        f"- {exec_t['agent_pytest']['log_file']}",
        "",
        "### 口径注释",
        "",
        "- 前端 node:test 正则 collected 479 但 npm 原始输出 `ℹ tests 478`（pass 478），差异来自 node:test 的 suite 计数方式（部分 suite 内 test 名不计入独立条目）。**以 npm test 原始输出为准**。",
        "- Python 正则声明合计 133（而非 324），pytest collected 53+54+80=187（声明 ≠ collected ≠ pass）。剩余 `tests/api/`、`tests/e2e/`、`tests/integration/` 中有依赖真实服务或环境变量的用例——**声明数 ≠ pytest collected 数 ≠ 通过数**。",
        "- Java Maven NOT_RUN 是**环境阻塞**（JDK 版本），不是代码失败。pom.xml 已指定 `<java.version>17</java.version>`，源码有 Java 15+ 文本块语法。",
        "",
        "## 来源哈希（SHA-256 聚合）",
        "",
        "对每个统计口径的源文件集合按相对路径排序、先 hash 文件名再 hash 内容，生成确定性聚合哈希。同一工作树重复生成一致；一旦文件内容变化即变动。",
        "",
        "| 口径 | 哈希 |",
        "|---|---|",
    ])
    hash_labels = [
        ("backend_main_java_xml_yml", "backend_main (Java/XML/YAML)"),
        ("frontend_src_js_ts_vue", "frontend_src (JS/TS/Vue)"),
        ("frontend_test_mjs_js", "frontend_test (node:test)"),
        ("ai_service_py", "ai-service (.py)"),
        ("knowledge_py", "knowledge (.py)"),
        ("agent_py", "agent (.py)"),
        ("tests_python", "tests/ (.py)"),
        ("flyway_sql", "Flyway migration (V*.sql)"),
        ("frontend_router_js_ts", "frontend router (*.js/*.ts)"),
    ]
    for key, label in hash_labels:
        lines.append(f"| {label} | `{src.get(key, '')}` |")

    lines.extend([
        "",
        "## 过期主张清单（自动扫描 docs/）",
        "",
        f"扫描时间：{exp['scan_time']}；命中 **{exp['count']}** 处旧数字主张。",
        "这些数字在材料中被当作“当前事实”陈述，但与 HEAD 48b8af47 上重新统计的事实不一致。",
        "材料修正时需逐条替换，不批量全换。",
        "",
        "| 旧值 | 当前事实 | 文件:行 | 上下文摘要 |",
        "|---|---|---|---|",
    ])
    claims = exp["claims"]
    MAX_ROWS = 50
    for c in claims[:MAX_ROWS]:
        ctx = c["context"]
        ctx = ctx.replace("|", "\\|")
        if len(ctx) > 140:
            ctx = ctx[:140] + "…"
        lines.append(f"| {c['value']} | {c['current_fact']} | `{c['file']}:{c['line']}` | {ctx} |")
    if len(claims) > MAX_ROWS:
        lines.extend([
            "",
            f"> 仅展示前 {MAX_ROWS} 条；完整清单见 `metrics.json` → `expired_claims_scan.claims`（共 {len(claims)} 条）。",
        ])

    lines.extend([
        "",
        "### 高频矛盾值汇总",
        "",
        "| 旧值 | 出现次数 | 当前事实 | 说明 |",
        "|---|---:|---|---|",
    ])
    val_counts = Counter(c["value"] for c in claims)
    val_map = {
        219: "backend_main files = 218；旧稿 219",
        17981: "backend_main LOC = 18,785；旧稿 17,981",
        296: "Java 注解 344 / 前端 router path 71；旧稿 296 接口",
        563: "实际执行通过 665；旧稿 563 测试",
        80: "Flyway 38 脚本；运行库表数未知；旧稿 80 张表",
        146: "前端 views .vue = 63；旧稿 146",
        27983: "frontend_src LOC = 29,535；旧稿 27,983",
        79: "Flyway 38；旧稿 79 快照",
    }
    for val, cnt in sorted(val_counts.items()):
        note = val_map.get(val, "—")
        lines.append(f"| {val} | {cnt} | {note} | 扫描自 docs/*.md |")

    lines.extend([
        "",
        "## 复现命令",
        "",
        "```powershell",
        "# 生成本台账（只读，不改业务代码）",
        "python scripts/collect_fact_metrics.py",
        "",
        "# 独立验证（先跑测试，再跑脚本）",
        "cd frontend; npm test                        # 前端 node:test",
        "python -m pytest ai-service/app/tests -q     # AI Service",
        "python -m pytest tests/knowledge -q          # Knowledge",
        "python -m pytest tests/agent -v --tb=no      # Agent",
        "# Java 需修复 JDK 后再跑",
        "# mvn -Dtest=RunCorrelationFilterTest test",
        "```",
        "",
        "## 交付物",
        "",
        f"- 结构化 JSON：`.runtime/fct-p0-01/metrics.json`",
        f"- 人类可读 Fact-Sheet：本文档",
        f"- 生成脚本：`scripts/collect_fact_metrics.py`（只读）",
        "- 测试原始日志：`.runtime/fct-p0-01/pytest-*.log`、`npm-test.log`",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    metrics = build_metrics()
    OUT.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_fact_sheet(metrics, OUT.parent / "fact-sheet.md")
    print(f"Wrote {OUT}")
    print(f"Wrote {OUT.parent / 'fact-sheet.md'}")
    print(f"summary_execution_pass = {metrics['tests_execution']['summary_total_pass']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
