"""Truthful hardware and storage checks; no training is started."""

from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any


def check_hardware(output_dir: str | Path) -> dict[str, Any]:
    torch_available = bool(importlib.util.find_spec("torch"))
    cuda_available = False
    gpu_count = 0
    gpu_names: list[str] = []
    if torch_available:
        try:
            import torch  # type: ignore

            cuda_available = bool(torch.cuda.is_available())
            gpu_count = int(torch.cuda.device_count()) if cuda_available else 0
            gpu_names = [str(torch.cuda.get_device_name(i)) for i in range(gpu_count)]
        except Exception:
            cuda_available = False
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target)
    return {
        "status": "READY" if usage.free > 0 else "BLOCKED",
        "python": True,
        "torch_available": torch_available,
        "cuda_available": cuda_available,
        "gpu_count": gpu_count,
        "gpu_names": gpu_names,
        "gpu_memory": "NOT_AVAILABLE" if not cuda_available else "AVAILABLE",
        "disk_free_bytes": usage.free,
        "output_directory": str(target),
        "output_directory_writable": os.access(target, os.W_OK),
        "reason": "storage is available; GPU availability is reported separately",
    }
