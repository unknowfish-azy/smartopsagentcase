import os
import sys

# 【已废弃】第二轮校正脚本：会把材料写回 2026-11-05 的旧口径
#   （Python 135 用例 / 后端 428 @Test / 563 项 / 80 张表），与当前冻结快照不符。
# 现行口径见 docs/development/FCT-P0-01-事实台账与材料门禁.md
#   与 docs/development/fct-p0-01-evidence/metrics.json（快照 9f9e7342…）。
# 确需复现历史口径时设置 ALLOW_LEGACY_FIX=1 再运行。
if os.environ.get("ALLOW_LEGACY_FIX") != "1":
    sys.exit("refusing to run: 旧口径替换脚本已废弃，见 FCT-P0-01 报告；确需复现请设 ALLOW_LEGACY_FIX=1")

# 第二轮校正：对齐今日既定权威口径
#   测试：Python 135 用例（111 通过 / 24 跳过）+ 后端 428 @Test = 563
#   建表：80 张
#   纠察：四级（规则→证据→AI→状态核验）
FILES = [
    "defense.md",
    "defense-qa.md",
    "defense-master.md",
    "defense-advanced.md",
    "demo-script.md",
    "adjustment-plan.md",
    "project-plan.md",
    "innovation.md",
    "technical-document.html",
    "项目知识要点手册.md",
    "答辩实战问答手册.md",
]
BASE = os.path.dirname(os.path.abspath(__file__))

REPL = [
    # 测试总数 541 -> 563（含 Python 135）
    ("541 项测试（Python 113 + 后端 428）", "563 项测试（Python 135 + 后端 428）"),
    ("541 项测试", "563 项测试（Python 135 + 后端 428）"),
    ("541 项", "563 项"),
    ("541", "563"),
    # 表数 81 -> 80
    ("81 张表", "80 张表"),
    ("81表", "80表"),
    # Python 用例 113 -> 135，通过数 89 -> 111
    ("Python 113 用例", "Python 135 用例"),
    ("Python 113（89 通过 / 24 跳过）", "Python 135（111 通过 / 24 跳过）"),
    ("113 用例 = 89 通过", "135 用例 = 111 通过"),
    ("89 passed / 24 skipped", "111 passed / 24 skipped"),
    ("89 通过 / 24 跳过", "111 通过 / 24 跳过"),
    ("（Python 113 + 后端 428）", "（Python 135 + 后端 428）"),
]

for f in FILES:
    p = os.path.join(BASE, f)
    if not os.path.exists(p):
        print(f"[skip] {f}")
        continue
    s = open(p, encoding="utf-8").read()
    total = 0
    for pat, rep in REPL:
        n = s.count(pat)
        if n:
            s = s.replace(pat, rep)
            total += n
    open(p, "w", encoding="utf-8").write(s)
    print(f"[ok] {f}: {total} 处")
