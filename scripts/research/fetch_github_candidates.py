"""Collect public GitHub metadata/docs only; never execute downloaded content."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

CANDIDATES = (
    "langchain-ai/langgraph",
    "run-llama/llama_index",
    "qdrant/qdrant",
    "Arize-ai/phoenix",
    "open-telemetry/opentelemetry-collector",
    "stackstorm/st2",
    "rundeck/rundeck",
    "prometheus/alertmanager",
    "promptfoo/promptfoo",
    "microsoft/playwright",
)
MAX_BYTES = 2 * 1024 * 1024


def fetch_json(opener, url):
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "SmartOpsAgent-ReadOnly-Research/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with opener.open(request, timeout=20) as response:
        payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("response_size_limit")
        return json.loads(payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".runtime/github-research/github-repositories.json"))
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    documents = args.output.parent / "readmes"
    documents.mkdir(exist_ok=True)
    opener = build_opener(ProxyHandler({}))
    report = {"fetched_at": datetime.now(timezone.utc).isoformat(), "repositories": []}
    failed = 0
    for name in CANDIDATES:
        row = {"repository": name, "url": f"https://github.com/{name}", "status": "pending"}
        try:
            api = f"https://api.github.com/repos/{name}"
            metadata = fetch_json(opener, api)
            row.update({key: metadata.get(key) for key in (
                "full_name", "description", "default_branch", "pushed_at", "updated_at",
                "archived", "disabled", "stargazers_count", "open_issues_count", "license",
            )})
            # Metadata's SPDX label is evidence to review, not a license compatibility verdict.
            readme = fetch_json(opener, api + "/readme")
            if readme.get("encoding") != "base64":
                raise ValueError("unsupported_readme_encoding")
            content = base64.b64decode(readme["content"])
            path = documents / (name.replace("/", "--") + ".md")
            path.write_bytes(content)
            row.update({"readme_path": str(path), "readme_blob_sha": readme.get("sha"), "readme_sha256": hashlib.sha256(content).hexdigest()})
            try:
                license_file = fetch_json(opener, api + "/license")
                row["license_file"] = {key: license_file.get(key) for key in ("path", "sha", "html_url", "license")}
            except HTTPError as exc:
                if exc.code != 404:
                    raise
                row["license_file"] = None
            row["status"] = "fetched_review_required"
        except (HTTPError, URLError, OSError, ValueError, KeyError) as exc:
            failed += 1
            row["status"] = "fetch_failed"
            row["error_type"] = type(exc).__name__
            if isinstance(exc, HTTPError):
                row["http_status"] = exc.code
        report["repositories"].append(row)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{name}: {row['status']}")
        if failed == len(report["repositories"]) and failed >= 2:
            print("Repeated network failures; partial report saved, remaining candidates not fetched.")
            return 1
        time.sleep(1)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
