"""Write the read-only Phase 7.2 status report."""

from __future__ import annotations

import json

from training.phase_status import write_phase_status


if __name__ == "__main__":
    print(json.dumps(write_phase_status(), ensure_ascii=False, indent=2))
