import json

from training.readiness import run_readiness_check


if __name__ == "__main__":
    print(json.dumps(run_readiness_check(), ensure_ascii=False, indent=2))
