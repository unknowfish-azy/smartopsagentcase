"""Read-only metadata, README and root LICENSE evidence for ops/AI data projects."""
from __future__ import annotations
import argparse, base64, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener
from urllib.parse import quote

CANDIDATES = (
    "logpai/loghub",
    "logpai/logparser",
    "openai/evals",
    "EleutherAI/lm-evaluation-harness",
    "explodinggradients/ragas",
    "beir-cellar/beir",
    "huggingface/datasets",
    "open-telemetry/opentelemetry-demo",
    "grafana/loki",
    "prometheus/prometheus",
    "sierra-research/tau-bench",
    "ServiceNow/WorkArena",
)

def fetch(opener, url, limit=2*1024*1024):
    req = Request(url, headers={"Accept":"application/vnd.github+json", "User-Agent":"SmartOpsAgent-ReadOnly-Research/1.0", "X-GitHub-Api-Version":"2022-11-28"})
    with opener.open(req, timeout=20) as response:
        body=response.read(limit+1)
    if len(body)>limit: raise ValueError("response_size_limit")
    return json.loads(body)

def collect_repository(opener, name, output_dir, fetcher=fetch):
    row = {"repository": name, "url": f"https://github.com/{name}",
           "status": "pending", "data_license_status": "manual_review_required"}
    try:
        api = f"https://api.github.com/repos/{name}"
        meta = fetcher(opener, api)
        row["metadata"] = meta
        row.update({k: meta.get(k) for k in ("full_name", "description", "default_branch", "pushed_at", "license")})
        commit = fetcher(opener, api + "/commits/" + quote(meta["default_branch"], safe=""))
        row["commit_sha"] = commit["sha"]
        repo_dir = output_dir / name.replace("/", "--")
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (repo_dir / "commit.json").write_text(json.dumps(commit, ensure_ascii=False, indent=2), encoding="utf-8")
        for endpoint, filename in (("readme", "README.md"), ("license", "LICENSE.txt")):
            try:
                item = fetcher(opener, api + "/" + endpoint + "?ref=" + row["commit_sha"])
                content = base64.b64decode(item["content"], validate=False)
                path = repo_dir / filename
                path.write_bytes(content)
                evidence = {"status": "saved", "path": item.get("path"), "blob_sha": item.get("sha"),
                            "sha256": hashlib.sha256(content).hexdigest(), "local_path": str(path),
                            "html_url": item.get("html_url"), "license": item.get("license")}
                row["readme" if endpoint == "readme" else "license_file"] = evidence
            except Exception as exc:
                if endpoint == "readme":
                    raise
                row["license_file"] = {"status": "unavailable", "error_type": type(exc).__name__, "error": str(exc)}
        row["status"] = "fetched_review_required"
    except Exception as exc:
        row.update({"status": "fetch_failed", "error_type": type(exc).__name__, "error": str(exc)})
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    opener = build_opener()
    report = {"fetched_at": datetime.now(timezone.utc).isoformat(), "candidate_count": len(CANDIDATES), "repositories": []}
    for name in CANDIDATES:
        row = collect_repository(opener, name, args.output.parent)
        report["repositories"].append(row)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(name + ": " + row["status"], flush=True)
    return 0 if all(r["status"] == "fetched_review_required" for r in report["repositories"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
