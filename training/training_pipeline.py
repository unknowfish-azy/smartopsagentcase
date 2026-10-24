"""Dry-run training pipeline configuration validation."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class TrainingConfig:
    method: str
    model: str
    dataset: str
    learning_rate: float
    epochs: int
    batch_size: int
    gradient_accumulation: int
    max_length: int
    hardware: str = "CPU"

    def validate(self) -> None:
        if self.method not in {"SFT", "QLORA", "PREFERENCE"}:
            raise ValueError("method must be SFT, QLORA or PREFERENCE")
        if self.hardware not in {"CPU", "CUDA", "GPU"}:
            raise ValueError("hardware must be CPU, CUDA or GPU")
        if self.learning_rate <= 0 or self.epochs <= 0 or self.batch_size <= 0:
            raise ValueError("learning rate, epochs and batch size must be positive")
        if self.gradient_accumulation <= 0 or self.max_length <= 0:
            raise ValueError("gradient accumulation and max length must be positive")


def dry_run(config: TrainingConfig) -> dict[str, Any]:
    config.validate()
    return {
        "status": "NOT RUN",
        "reason": "dry-run only; no GPU/model training was executed",
        "config": asdict(config),
        "loss": None,
        "metrics": None,
        "artifact": None,
    }


__all__ = ["TrainingConfig", "dry_run"]
