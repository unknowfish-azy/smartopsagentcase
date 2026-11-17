"""P2-2 simulator smoke test."""
from app.training.simulator import synthesize_series, verify_detectors, FAULT_TEMPLATES

print("=== Simulator 直接调用 smoke ===")
print("supported categories:", list(FAULT_TEMPLATES.keys()))
print()

for cat in FAULT_TEMPLATES.keys():
    r = synthesize_series(category=cat, seed=42, severity=1.0)
    dv = verify_detectors(cat, r)
    if not dv["available"]:
        print(f"[{cat}] verify_detectors UNAVAILABLE — anomaly import 失败？")
        continue
    cov = dv["coverage"]
    expected = dv["expected_hit"]
    metric = r["meta"]["metric"]
    inj = r["meta"]["inject_start"]
    dur = r["meta"]["duration"]
    print(f"[{cat}] metric={metric:14s} inject={inj:3d} dur={dur:2d}  coverage={cov:.2f}  expected_hit={expected}")

print()
print("=== detail: disk_full ===")
r2 = synthesize_series("disk_full", seed=7, severity=1.2)
dv2 = verify_detectors("disk_full", r2)
for n, m in dv2["per_detector"].items():
    print(f"  {n:20s} precision={m['precision']:.3f} recall={m['recall']:.3f} f1={m['f1']:.3f} hit={m['hit']}")

print()
print("=== detail: network_error ===")
r3 = synthesize_series("network_error", seed=99, severity=0.9)
dv3 = verify_detectors("network_error", r3)
for n, m in dv3["per_detector"].items():
    print(f"  {n:20s} precision={m['precision']:.3f} recall={m['recall']:.3f} f1={m['f1']:.3f} hit={m['hit']}")
