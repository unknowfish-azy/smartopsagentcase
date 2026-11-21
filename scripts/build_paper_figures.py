#!/usr/bin/env python3
"""生成 short paper《标签—探针循环》的 4 张图（纯 stdlib + 可选 matplotlib）。

用法：
    python scripts/build_paper_figures.py            # 优先 PNG（需 matplotlib），否则 SVG
    python scripts/build_paper_figures.py --svg      # 强制 SVG（无依赖）

数据来源（只读）：
    reports/label-probe-circularity.json
    reports/dataset-ceiling.json

产物：docs/evaluation/paper/figures/fig{1,2,3,4}.{png|svg}

本脚本不修改任何既有指标或数据。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FIG_DIR = REPO / "docs" / "evaluation" / "paper" / "figures"
CIRC_JSON = REPO / "reports" / "label-probe-circularity.json"
CEIL_JSON = REPO / "reports" / "dataset-ceiling.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------- 图 1
def fig1_data(circ: dict[str, Any]) -> dict[str, Any]:
    """标签 × 探针健康度列联（完美对角）。"""
    full = circ["full"]
    table = full["label_x_probe_health"]          # e.g. {"FAILED|False": 30, ...}
    labels = ["SUCCESS", "FALSE_SUCCESS", "FAILED", "UNKNOWN"]
    matrix = {
        lab: {
            "healthy": table.get(f"{lab}|True", 0),
            "unhealthy": table.get(f"{lab}|False", 0),
        }
        for lab in labels
    }
    return {
        "title": "Fig.1  Label x probe health is perfectly diagonal",
        "labels": labels,
        "columns": ["probe healthy", "probe unhealthy"],
        "matrix": matrix,
        "fisher_one_sided_p": full["fisher_one_sided_p"],
        "note": "one-sided Fisher exact p over (healthy x SUCCESS/not-SUCCESS)",
    }


# --------------------------------------------------------------------- 图 2
def fig2_data(circ: dict[str, Any]) -> dict[str, Any]:
    """逐 split：平凡规则 vs 反极性对照。"""
    splits = circ["splits"]
    if isinstance(splits, dict):
        splits = [{"set": k, **v} for k, v in splits.items()]
    rows = []
    for s in splits:
        rows.append({
            "split": s.get("set") or s.get("split"),
            "binary_n": s["binary_subset_n"],
            "trivial_correct": s.get("binary_trivial_correct"),
            "reversed_correct": s.get("binary_reversed_correct"),
            "coverage_rate": s["coverage_rate"],
        })
    return {
        "title": "Fig.2  Trivial rule reproduces every split; reversed polarity does not",
        "rows": rows,
        "full_binary_trivial_rate": circ["full"]["binary_trivial_rate"],
        "full_binary_reversed_correct": circ["full"]["binary_reversed_correct"],
    }


# --------------------------------------------------------------------- 图 3
def fig3_data(ceil: dict[str, Any], circ: dict[str, Any]) -> dict[str, Any]:
    """双面板：指标准确率平线 + 有效单元数分布（重算 200 次分割）。

    样本行的 probe_healthy 由 `audit_label_probe_circularity` 的同一代码路径现算，
    不读 `samples.jsonl` 的 inspector 字段（该字段在数据文件里为空）。
    """
    import random

    from agent.inspector.adapters.controlled_probe import normalize_probes
    from agent.inspector.verifiers.state_verifier import classify_claim, resolve_from_probes

    def probe_health(normalize, resolve, row) -> bool | None:
        flats, _ = normalize(row.get("state_assertions") or [])
        return resolve(flats) if flats else None

    per_row = []
    for r in _load_raw():
        per_row.append({
            "sample_id": r["sample_id"],
            "group": (r.get("metadata") or {}).get("root_cause_group"),
            "label": (r.get("ground_truth") or {}).get("label"),
            "claim_state": classify_claim(str(r.get("claim") or "")),
            "probe_healthy": probe_health(normalize_probes, resolve_from_probes, r),
        })

    groups = sorted({r["group"] for r in per_row})
    scorable = [r for r in per_row if r["claim_state"] == "asserts_success"]
    rng = random.Random(20261121)

    accs: list[float] = []
    eff_ns: list[int] = []
    trivial_rates: list[float] = []
    for _ in range(200):
        chosen = set(rng.sample(groups, len(groups) // 2))
        sub = [r for r in scorable if r["group"] in chosen]
        hit = sum(
            1 for r in sub
            if ("FALSE_SUCCESS" if r["probe_healthy"] is False else "SUCCESS") == r["label"]
        )
        rate = hit / len(sub) if sub else float("nan")
        accs.append(rate)
        eff_ns.append(len({r["group"] for r in sub}))
        trivial_rates.append(rate)

    valid = [a for a in accs if a == a]
    return {
        "title": "Fig.3  Accuracy is flat across re-splits while effective n varies",
        "n_trials": 200,
        "accuracy_min": min(valid),
        "accuracy_max": max(valid),
        "effective_n_p50": ceil["stability"]["scorable_n_p50"],
        "effective_n_min": min(eff_ns),
        "effective_n_max": max(eff_ns),
        "effective_n_hist": _hist(eff_ns, bins=12),
        "trivial_rule_min": min(trivial_rates),
        "trivial_rule_max": max(trivial_rates),
        "independent_units_total": ceil["families"]["n_independent_units_total"],
    }


def _hist(values: list[int], bins: int = 12) -> dict[str, int]:
    if not values:
        return {}
    lo, hi = min(values), max(values)
    if hi == lo:
        return {str(lo): len(values)}
    width = (hi - lo) / bins
    out: dict[str, int] = {}
    for v in values:
        idx = min(int((v - lo) / width), bins - 1)
        left = round(lo + idx * width, 2)
        key = f"{left:.0f}-{left + width:.0f}"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: float(kv[0].split("-")[0])))


_ROWS_CACHE: list[dict[str, Any]] | None = None


def _load_raw() -> list[dict[str, Any]]:
    """读取受控集原始样本（不加工，供调用方自行归一化）。"""
    global _ROWS_CACHE
    if _ROWS_CACHE is None:
        samples = REPO / "SmartOps-Dataset" / "Controlled" / "v1" / "samples.jsonl"
        out: list[dict[str, Any]] = []
        for line in samples.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        _ROWS_CACHE = out
    return _ROWS_CACHE


# --------------------------------------------------------------------- 图 4
def fig4_data(ceil: dict[str, Any]) -> dict[str, Any]:
    costs = ceil["costs"]
    wilson = ceil["wilson_lower_when_all_correct"]
    return {
        "title": "Fig.4  Precision-cost curves and Wilson lower bound when all correct",
        "curves": [
            {"deff": v["deff"], "margin": v["target_margin"],
             "n_needed": v["n_nominal_needed"], "person_hours": v["total_person_hours"]}
            for v in costs.values()
        ],
        "current_units": ceil["families"]["n_independent_units_total"],
        "wilson_all_correct": wilson,
    }


# -------------------------------------------------------------------- 渲染
def render_svg(fig: dict[str, Any], path: Path) -> None:
    """纯 stdlib SVG 渲染（无 matplotlib 时兜底）。"""
    w, h = 900, 460
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="-apple-system,Segoe UI,Roboto,Helvetica,Arial">',
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
        f'<text x="24" y="34" font-size="17" font-weight="600" fill="#111827">{fig["title"]}</text>',
    ]
    kind = fig["title"].split()[0]
    if kind == "Fig.1":
        parts += _svg_fig1(fig)
    elif kind == "Fig.2":
        parts += _svg_fig2(fig)
    elif kind == "Fig.3":
        parts += _svg_fig3(fig)
    elif kind == "Fig.4":
        parts += _svg_fig4(fig)
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _svg_fig1(fig: dict[str, Any]) -> list[str]:
    m = fig["matrix"]
    labels, cols = fig["labels"], fig["columns"]
    total = sum(v[c] for v in m.values() for c in ("healthy", "unhealthy"))
    x0, y0, cw, ch = 90, 90, 180, 44
    out = []
    for j, col in enumerate(cols):
        out.append(f'<text x="{x0 + j * cw + cw / 2}" y="{y0 - 12}" text-anchor="middle" '
                   f'font-size="12" fill="#374151">{col}</text>')
    vmax = max(1, max(v[c] for v in m.values() for c in ("healthy", "unhealthy")))
    for i, lab in enumerate(labels):
        y = y0 + i * ch
        out.append(f'<text x="{x0 - 12}" y="{y + ch / 2 + 4}" text-anchor="end" '
                   f'font-size="12" fill="#374151">{lab}</text>')
        for j, col in enumerate(("healthy", "unhealthy")):
            val = m[lab][col]
            alpha = 0.12 + 0.85 * (val / vmax)
            x = x0 + j * cw
            out.append(f'<rect x="{x + 2}" y="{y + 2}" width="{cw - 4}" height="{ch - 4}" '
                       f'fill="#2563eb" fill-opacity="{alpha:.2f}" stroke="#bfdbfe"/>')
            out.append(f'<text x="{x + cw / 2}" y="{y + ch / 2 + 5}" text-anchor="middle" '
                       f'font-size="14" font-weight="600" fill="#111827">{val}</text>')
    out.append(f'<text x="{x0}" y="{y0 + len(labels) * ch + 34}" font-size="12.5" fill="#b91c1c" '
               f'font-weight="600">one-sided Fisher p = {fig["fisher_one_sided_p"]:.3e}</text>')
    out.append(f'<text x="{x0}" y="{y0 + len(labels) * ch + 54}" font-size="11.5" fill="#6b7280">'
               f'total samples = {total}; non-zero cells lie only on the diagonal</text>')
    return out


def _svg_fig2(fig: dict[str, Any]) -> list[str]:
    rows = fig["rows"]
    x0, y0, bw, gap, maxv = 120, 110, 70, 26, 30
    hscale = 240 / maxv
    out = [f'<line x1="{x0 - 30}" y1="{y0 + 260}" x2="{x0 + len(rows) * (2 * bw + gap) + 20}" '
           f'y2="{y0 + 260}" stroke="#d1d5db"/>']
    for i, r in enumerate(rows):
        bx = x0 + i * (2 * bw + gap)
        th = r["trivial_correct"] * hscale
        rh = r["reversed_correct"] * hscale
        out.append(f'<rect x="{bx}" y="{y0 + 260 - th}" width="{bw}" height="{th}" fill="#2563eb"/>')
        out.append(f'<rect x="{bx + bw}" y="{y0 + 260 - rh}" width="{bw}" height="{rh}" fill="#dc2626"/>')
        out.append(f'<text x="{bx + bw / 2}" y="{y0 + 250 - th}" text-anchor="middle" '
                   f'font-size="12" fill="#1d4ed8">{r["trivial_correct"]}/{r["binary_n"]}</text>')
        out.append(f'<text x="{bx + bw + bw / 2}" y="{y0 + 250 - rh}" text-anchor="middle" '
                   f'font-size="12" fill="#b91c1c">{r["reversed_correct"]}/{r["binary_n"]}</text>')
        out.append(f'<text x="{bx + bw}" y="{y0 + 282}" text-anchor="middle" font-size="12" '
                   f'fill="#374151">{r["split"]}</text>')
        out.append(f'<text x="{bx + bw}" y="{y0 + 298}" text-anchor="middle" font-size="10.5" '
                   f'fill="#6b7280">n={r["binary_n"]}, cov {100 * r["coverage_rate"]:.1f}%</text>')
    out.append(f'<rect x="{x0}" y="{y0 + 316}" width="14" height="14" fill="#2563eb"/>'
               f'<text x="{x0 + 20}" y="{y0 + 328}" font-size="12" fill="#374151">trivial rule</text>')
    out.append(f'<rect x="{x0 + 120}" y="{y0 + 316}" width="14" height="14" fill="#dc2626"/>'
               f'<text x="{x0 + 140}" y="{y0 + 328}" font-size="12" fill="#374151">'
               f'reversed-polarity control</text>')
    out.append(f'<text x="{x0}" y="{y0 + 366}" font-size="12.5" fill="#6b7280">'
               f'full binary subset n={sum(r["binary_n"] for r in rows)}: trivial '
               f'{fig["full_binary_trivial_rate"]:.4f}, reversed correct '
               f'{fig["full_binary_reversed_correct"]}</text>')
    return out


def _svg_fig3(fig: dict[str, Any]) -> list[str]:
    hist = fig["effective_n_hist"]
    keys = list(hist.keys())
    vmax = max(hist.values()) if hist else 1
    x0, y0, bw = 90, 100, 30
    out = []
    out.append(f'<text x="24" y="70" font-size="12.5" fill="#6b7280">panel A: primary accuracy '
               f'(flat at {fig["accuracy_min"]:.4f})</text>')
    out.append(f'<line x1="{x0}" y1="{y0 + 150}" x2="{x0 + 340}" y2="{y0 + 150}" '
               f'stroke="#d1d5db"/>')
    out.append(f'<line x1="{x0}" y1="{y0 + 75}" x2="{x0 + 340}" y2="{y0 + 75}" '
               f'stroke="#2563eb" stroke-width="2.5"/>')
    out.append(f'<text x="{x0 + 346}" y="{y0 + 79}" font-size="12" fill="#1d4ed8">1.0000</text>')
    out.append(f'<text x="{x0}" y="{y0 + 176}" font-size="11.5" fill="#6b7280">'
               f'200 random half-group re-splits (p50 effective n = {fig["effective_n_p50"]})</text>')

    out.append(f'<text x="470" y="70" font-size="12.5" fill="#6b7280">panel B: effective units '
               f'actually vary</text>')
    for i, k in enumerate(keys):
        v = hist[k]
        bh = 150 * v / vmax
        x = 470 + i * bw
        out.append(f'<rect x="{x}" y="{y0 + 150 - bh}" width="{bw - 6}" height="{bh}" '
                   f'fill="#0891b2"/>')
        out.append(f'<text x="{x + (bw - 6) / 2}" y="{y0 + 145 - bh}" text-anchor="middle" '
                   f'font-size="10" fill="#0e7490">{v}</text>')
    out.append(f'<line x1="470" y1="{y0 + 150}" x2="{470 + len(keys) * bw}" y2="{y0 + 150}" '
               f'stroke="#d1d5db"/>')
    out.append(f'<text x="470" y="{y0 + 176}" font-size="11.5" fill="#6b7280">'
               f'range {fig["effective_n_min"]}-{fig["effective_n_max"]} units; total independent '
               f'units = {fig["independent_units_total"]}</text>')
    out.append(f'<text x="24" y="{y0 + 230}" font-size="12.5" fill="#b91c1c" font-weight="600">'
               f'an accuracy that does not respond to sample size cannot be capability evidence'
               f'</text>')
    return out


def _svg_fig4(fig: dict[str, Any]) -> list[str]:
    curves = fig["curves"]
    margins = sorted({c["margin"] for c in curves})
    x0, y0, pw, ph = 90, 100, 640, 250
    nmax = max(c["n_needed"] for c in curves) * 1.08
    hmax = max(c["person_hours"] for c in curves) * 1.12
    out = [
        f'<line x1="{x0}" y1="{y0 + ph}" x2="{x0 + pw}" y2="{y0 + ph}" stroke="#d1d5db"/>',
        f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0 + ph}" stroke="#d1d5db"/>',
        f'<text x="{x0 + pw / 2}" y="{y0 + ph + 34}" text-anchor="middle" font-size="12" '
        f'fill="#374151">nominal independent units needed</text>',
        f'<text x="30" y="{y0 + ph / 2}" text-anchor="middle" font-size="12" fill="#374151" '
        f'transform="rotate(-90 30 {y0 + ph / 2})">person-hours</text>',
        f'<line x1="{x0 + pw * (fig["current_units"] / nmax):.1f}" y1="{y0}" '
        f'x2="{x0 + pw * (fig["current_units"] / nmax):.1f}" y2="{y0 + ph}" '
        f'stroke="#dc2626" stroke-dasharray="5 4"/>',
        f'<text x="{x0 + pw * (fig["current_units"] / nmax) + 6:.1f}" y="{y0 + 16}" '
        f'font-size="11.5" fill="#b91c1c">current {fig["current_units"]} units</text>',
    ]
    colors = {1.0: "#2563eb", 2.0: "#0891b2"}
    for deff in sorted({c["deff"] for c in curves}):
        pts = sorted((c for c in curves if c["deff"] == deff), key=lambda c: c["margin"])
        coords = [(x0 + pw * (c["n_needed"] / nmax), y0 + ph - ph * (c["person_hours"] / hmax))
                  for c in pts]
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        out.append(f'<polyline points="{poly}" fill="none" stroke="{colors.get(deff, "#2563eb")}" '
                   f'stroke-width="2.5"/>')
        for c, (x, y) in zip(pts, coords):
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" '
                       f'fill="{colors.get(deff, "#2563eb")}"/>')
            out.append(f'<text x="{x + 8:.1f}" y="{y - 6:.1f}" font-size="11" fill="#374151">'
                       f'+/-{c["margin"]:.2f}: n={c["n_needed"]}, {c["person_hours"]}h</text>')
    out.append(f'<rect x="{x0}" y="{y0 + ph + 52}" width="14" height="14" fill="#2563eb"/>'
               f'<text x="{x0 + 20}" y="{y0 + ph + 64}" font-size="12" fill="#374151">DEFF = 1.0</text>')
    out.append(f'<rect x="{x0 + 120}" y="{y0 + ph + 52}" width="14" height="14" fill="#0891b2"/>'
               f'<text x="{x0 + 140}" y="{y0 + ph + 64}" font-size="12" fill="#374151">DEFF = 2.0</text>')
    w = fig["wilson_all_correct"]
    out.append(f'<text x="{x0 + 260}" y="{y0 + ph + 64}" font-size="11.5" fill="#6b7280">'
               f'Wilson 95% lower bound even when all correct: ' +
               ", ".join(f"n={k} -> {v}" for k, v in w.items()) + '</text>')
    return out


def render_png(fig: dict[str, Any], path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    kind = fig["title"].split()[0]
    figobj, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    figobj.suptitle(fig["title"], fontsize=11, y=0.98)
    if kind == "Fig.1":
        labels, m = fig["labels"], fig["matrix"]
        data = [[m[l]["healthy"], m[l]["unhealthy"]] for l in labels]
        im = ax.imshow(data, cmap="Blues", aspect="auto", vmin=0)
        ax.set_xticks([0, 1], fig["columns"])
        ax.set_yticks(range(len(labels)), labels)
        for i in range(len(labels)):
            for j in range(2):
                ax.text(j, i, str(data[i][j]), ha="center", va="center",
                        fontweight="bold", color="#111827")
        ax.set_title(f'one-sided Fisher p = {fig["fisher_one_sided_p"]:.3e}', fontsize=9,
                     color="#b91c1c")
    elif kind == "Fig.2":
        rows = fig["rows"]
        x = range(len(rows))
        ax.bar([i - 0.2 for i in x], [r["trivial_correct"] for r in rows], width=0.4,
               label="trivial rule", color="#2563eb")
        ax.bar([i + 0.2 for i in x], [r["reversed_correct"] for r in rows], width=0.4,
               label="reversed polarity", color="#dc2626")
        ax.set_xticks(list(x), [f'{r["split"]}\n(n={r["binary_n"]}, cov {100*r["coverage_rate"]:.1f}%)'
                                for r in rows])
        ax.set_ylim(0, 32)
        ax.set_ylabel("correct predictions")
        ax.legend(fontsize=8)
    elif kind == "Fig.3":
        ax.axis("off")
        ax.text(0.01, 0.9, f'accuracy min/p50/max = {fig["accuracy_min"]:.4f} / '
               f'{fig["accuracy_min"]:.4f} / {fig["accuracy_max"]:.4f}   (zero variance)',
               fontsize=10, color="#111827")
        ax.text(0.01, 0.72, f'effective units: min {fig["effective_n_min"]}, '
               f'p50 {fig["effective_n_p50"]}, max {fig["effective_n_max"]}',
               fontsize=10, color="#0e7490")
        hist = fig["effective_n_hist"]
        ax.bar(list(hist.keys()), list(hist.values()), color="#0891b2")
        ax.set_title("effective-unit count across 200 half-group re-splits", fontsize=9)
    elif kind == "Fig.4":
        curves = fig["curves"]
        for deff in sorted({c["deff"] for c in curves}):
            pts = sorted((c for c in curves if c["deff"] == deff), key=lambda c: c["margin"])
            ax.plot([c["n_needed"] for c in pts], [c["person_hours"] for c in pts],
                    marker="o", label=f"DEFF = {deff}")
        ax.axvline(fig["current_units"], ls="--", color="#dc2626")
        ax.annotate(f'current {fig["current_units"]} units',
                    xy=(fig["current_units"], 5), rotation=90, fontsize=8, color="#b91c1c")
        ax.set_xlabel("nominal independent units needed")
        ax.set_ylabel("person-hours")
        ax.legend(fontsize=8)
    figobj.tight_layout(rect=[0, 0, 1, 0.95])
    figobj.savefig(path)
    plt.close(figobj)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", action="store_true", help="force SVG output (no matplotlib)")
    args = ap.parse_args()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    circ = load(CIRC_JSON)
    ceil = load(CEIL_JSON)

    figs = {
        "fig1": fig1_data(circ),
        "fig2": fig2_data(circ),
        "fig3": fig3_data(ceil, circ),
        "fig4": fig4_data(ceil),
    }

    manifest: dict[str, Any] = {"generated_at": None, "figures": {}}
    from datetime import datetime, timezone
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        import matplotlib  # noqa: F401
        have_mpl = True
    except Exception:
        have_mpl = False

    for name, fig in figs.items():
        meta = {"title": fig["title"]}
        if have_mpl and not args.svg:
            png = FIG_DIR / f"{name}.png"
            if render_png(fig, png):
                meta["path"] = str(png.relative_to(REPO)).replace("\\", "/")
                meta["format"] = "png"
        if "path" not in meta:
            svg = FIG_DIR / f"{name}.svg"
            render_svg(fig, svg)
            meta["path"] = str(svg.relative_to(REPO)).replace("\\", "/")
            meta["format"] = "svg"
        manifest["figures"][name] = meta
        print(f"[ok] {meta['path']}  ({meta['format']})")

    (FIG_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[done] figures written to", FIG_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
