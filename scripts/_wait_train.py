"""等待训练完成并定期打印状态"""
import time, json, os
from pathlib import Path

LOG = Path(r"d:\SmartOpsAgent\data\models\distill\qwen3-1.7b-lora-exp-20261119b\train.log")
ADAPTER = Path(r"d:\SmartOpsAgent\data\models\distill\qwen3-1.7b-lora-exp-20261119b\adapter")
METRICS = Path(r"d:\SmartOpsAgent\data\models\distill\qwen3-1.7b-lora-exp-20261119b\training-metrics.json")
COMPLETE = False

for i in range(120):  # 最多等 2 小时 (120 * 60s)
    time.sleep(60)
    if COMPLETE:
        break
    tail = ""
    if LOG.exists():
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-3:] if len(lines) >= 3 else lines
    adapter_exists = ADAPTER.exists() and (ADAPTER / "adapter_model.safetensors").exists()
    metrics_exists = METRICS.exists()
    
    # 检查进程
    alive = False
    try:
        import subprocess
        out = subprocess.run(["powershell", "-Command", 
            "Get-Process python -ErrorAction SilentlyContinue | Where-Object {$_.WorkingSet64 -gt 100MB} | Select-Object -First 1"],
            capture_output=True, text=True, timeout=5)
        alive = bool(out.stdout.strip())
    except: pass
    
    status = "RUNNING" if alive else "IDLE"
    print(f"[{i+1:3d}m] {status} | adapter={adapter_exists} | metrics={metrics_exists} | tail={tail[-1] if tail else '(no log)'}", flush=True)
    
    if metrics_exists:
        m = json.loads(METRICS.read_text())
        print(f"  TRAINING COMPLETE: {m}", flush=True)
        COMPLETE = True
    elif not alive and i > 3:
        print(f"  PROCESS DIED, checking if checkpoint saved...", flush=True)
        # 打印完整日志看错误
        if LOG.exists():
            full = LOG.read_text(encoding="utf-8", errors="replace")
            if "Traceback" in full or "Error" in full[-2000:]:
                print(f"  ERROR: {full[-2000:]}", flush=True)
            elif "TRAINING_COMPLETE" in full or "ADAPTER=" in full:
                print(f"  DONE (but metrics not written?)", flush=True)
                COMPLETE = True
        break

print("EXIT")
