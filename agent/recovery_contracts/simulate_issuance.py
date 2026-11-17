"""模拟 Agent 侧签发恢复契约：把工单详情页导出的草案变成可登记的正式契约。

用法（在仓库根目录执行）：

    # 演示：内置示例草案，只做本地签发校验，不发起网络请求
    python -m agent.recovery_contracts.simulate_issuance --demo

    # 用平台导出的草案 JSON 文件签发（dry-run 默认开启）
    python -m agent.recovery_contracts.simulate_issuance --draft draft.json

    # 真实上报到 Backend 内部端点（需要配置并显式关闭 dry-run）
    python -m agent.recovery_contracts.simulate_issuance --draft draft.json \\
        --owner-user-id 1 --run-id 1 --no-dry-run

职责边界（与 publisher/evaluator 一致）：
- 本脚本演示的是 Agent 侧签发动作：核对草案 → 计算 canonical digest → 结构校验 → 组装 Claim；
- 不代表恢复已成功："登记成功"只说明平台受理了写入；
- 默认 dry-run，真实上报必须显式 ``--no-dry-run`` 并配置
  ``SMARTOPS_BACKEND_URL`` / ``SMARTOPS_INTERNAL_TOKEN``。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .models import (
    Claim,
    ContractError,
    RecoveryContract,
    object_digest,
)
from .publisher import (
    PublisherConfigError,
    RecoveryPublisher,
    RecoveryPublisherError,
)

DEMO_DRAFT: dict[str, Any] = {
    "schema_version": "recovery-contract/v1",
    "id": "incident-1-20261117120000",
    "version": "v1",
    "scope": "order-service",
    "target": {"target_id": "order-service-primary", "target_kind": "SERVICE"},
    "expected_revision": "unspecified",
    "template_id": "incident-reactive",
    "template_version": "v1",
    "obligations": [
        {
            "obligation_id": "service-health-observed",
            "predicate_id": "service-health-ok",
            "predicate_version": "v1",
            "required": True,
            "weight": 1,
            "collector_ids": ["metric-collector"],
            "source_groups": ["incident-evidence"],
            "binding_revision": "unspecified",
            "scope": "order-service",
            "target": {"target_id": "order-service-primary", "target_kind": "SERVICE"},
            "predicate_params": {"service": "order-service"},
        }
    ],
    "source_groups": ["incident-evidence", "sentinel-metrics"],
    "window": {
        "sample_groups": 3,
        "min_first_last_gap_ms": 4000,
        "max_adjacent_gap_ms": 4000,
        "max_intra_group_skew_ms": 1250,
        "min_next_group_gap_ms": 2000,
    },
    "budgets": {
        "max_probe_calls": 12,
        "per_probe_timeout_ms": 1000,
        "run_deadline_ms": 30000,
        "evidence_ttl_ms": 15000,
        "receipt_ttl_ms": 8000,
    },
    "expires_after": 3600000,
    "digest": "",
}


def load_draft(path: str | None, demo: bool) -> dict[str, Any]:
    """读草案：--draft 指定文件，--demo 用内置示例；两者互斥，都不给则报错退出。"""
    if demo:
        return json.loads(json.dumps(DEMO_DRAFT))
    if not path:
        raise SystemExit("缺少草案：用 --draft <file> 或 --demo（内置示例草案）")
    raw = Path(path).read_text(encoding="utf-8")
    draft = json.loads(raw)
    if not isinstance(draft, Mapping):
        raise SystemExit("草案文件必须是 JSON 对象")
    return dict(draft)


def issue(draft: Mapping[str, Any]) -> RecoveryContract:
    """Agent 侧签发：digest 回填 → RecoveryContract.from_dict 全量结构校验。

    from_dict 会重算 canonical 摘要并要求与 digest 一致（models.L394），
    所以这一步等于完整的签发校验，通过即代表契约结构可登记。
    """
    body = {key: value for key, value in draft.items() if key != "digest"}
    body["digest"] = object_digest(body)
    return RecoveryContract.from_dict(body)


def build_claim(contract: RecoveryContract, *, source_incident_id: str | None) -> Claim:
    """按 V1 规则组装业务恢复声明（claim_type 只能是 BUSINESS_RECOVERY）。"""
    extensions: dict[str, Any] = {
        "issued_by": "simulate-issuance",
        "issued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if source_incident_id:
        extensions["source_incident_id"] = source_incident_id
    return Claim(
        id=contract.id,
        contract_digest=contract.digest,
        scope=contract.scope,
        target=contract.target,
        expected_revision=contract.expected_revision,
        claim_type="BUSINESS_RECOVERY",
        extensions=extensions,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="模拟 Agent 侧签发恢复契约（默认 dry-run，不发起网络请求）"
    )
    parser.add_argument("--draft", help="平台导出的草案 JSON 文件路径")
    parser.add_argument("--demo", action="store_true", help="使用内置示例草案")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                        help="只做本地签发校验与打印（默认）")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                        help="真实上报到 Backend 内部端点")
    parser.add_argument("--owner-user-id", type=int, default=1, help="契约归属用户 ID")
    parser.add_argument("--run-id", type=int, default=0, help="关联运行 ID")
    parser.add_argument("--backend-url", default=None, help="覆盖 SMARTOPS_BACKEND_URL")
    parser.add_argument("--internal-token", default=None, help="覆盖 SMARTOPS_INTERNAL_TOKEN")
    args = parser.parse_args(argv)

    draft = load_draft(args.draft, args.demo)
    draft_id = draft.get("id", "(无 id)")
    print(f"[1/3] 载入草案：{draft_id}（schema={draft.get('schema_version')}）")

    try:
        contract = issue(draft)
    except ContractError as error:
        # 草案不合法是有效结论：如实退出码 1，不静默降级
        print(f"[x] 签发校验未通过：{error}")
        return 1
    print(f"[2/3] 签发校验通过，digest={contract.digest}")
    print(f"      目标 {contract.target.to_dict()} · 义务 {len(contract.obligations)} 条 · "
          f"source_groups={list(contract.source_groups)}")

    claim = build_claim(contract, source_incident_id=_demo_incident_id(draft, args.demo))
    print(f"[3/3] 组装声明：{claim.to_dict()['id']}（{claim.claim_type}）")

    print("\n=== 签发后的契约 JSON（可直接登记） ===")
    print(json.dumps(contract.to_dict(), ensure_ascii=False, indent=2))
    print("\n=== 声明 JSON ===")
    print(json.dumps(claim.to_dict(), ensure_ascii=False, indent=2))

    if args.dry_run:
        print("\n[dry-run] 未上报。真实登记请追加 --no-dry-run 并配置"
              " SMARTOPS_BACKEND_URL / SMARTOPS_INTERNAL_TOKEN。")
        return 0

    print("\n=== 上报 Backend 内部端点 ===")
    try:
        publisher = RecoveryPublisher(args.backend_url, args.internal_token)
        data = publisher.create_contract(
            contract,
            claim,
            owner_user_id=args.owner_user_id,
            run_id=args.run_id,
        )
    except PublisherConfigError as error:
        print(f"[x] 配置缺失：{error}")
        return 1
    except RecoveryPublisherError as error:
        print(f"[x] 上报失败：{error}")
        return 1

    print(f"[ok] 平台已受理：{json.dumps(data, ensure_ascii=False)}")
    print("提醒：登记成功 ≠ 恢复成功。后续观测/回执由 Agent 求值器产出。")
    return 0


def _demo_incident_id(draft: Mapping[str, Any], demo: bool) -> str | None:
    """从草案 id（形如 incident-1-<时间戳>）反解工单号，便于回链。"""
    raw = str(draft.get("id", ""))
    if raw.startswith("incident-"):
        return raw.split("-")[1] if not demo else "1"
    return None


if __name__ == "__main__":
    sys.exit(main())
