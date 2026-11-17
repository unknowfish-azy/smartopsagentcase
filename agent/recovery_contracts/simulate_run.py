"""模拟 Agent 全链路恢复求值：签发 → 登记 → 采集观测 → 求值 → 产出回执。

用法（在仓库根目录执行）：

    # 演示：内置草案，全链路本地模拟，不发起网络请求
    python -m agent.recovery_contracts.simulate_run --demo

    # 用平台导出的草案 JSON 走完整链路（dry-run 默认开启）
    python -m agent.recovery_contracts.simulate_run --draft draft.json

    # 真实上报：登记契约 + 追加观测 + 产出回执
    python -m agent.recovery_contracts.simulate_run --draft draft.json \\
        --owner-user-id 1 --run-id 1 --no-dry-run

职责边界：
- 复用 simulate_issuance 的真实签发校验（digest + RecoveryContract.from_dict）；
- 观测是模拟探针硬编码 ``status=UP``，只演示证据结构与窗口合规，不代表真实采集；
- 回执由本地求值器产出（service-health-ok 谓词模拟），verdict 不经过任何修饰；
- "登记成功"只代表平台受理写入；回执是否被采信由平台复核逻辑决定。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import (
    EvidenceObservation,
    ObligationResult,
    VerificationReceipt,
    add_ms,
    digest_of,
    format_time,
    payload_digest,
)
from .publisher import (
    PublisherConfigError,
    RecoveryPublisher,
    RecoveryPublisherError,
)
from .simulate_issuance import build_claim, issue, load_draft

COLLECTOR_ID = "metric-collector"
COLLECTOR_VERSION = "1.0.0"
PROBE_ID = "service-health-ok"
RUN_IDENT = "run-sim-0001"
POLICY_VERSION = "v1"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def collect_observations(contract, round_no: int = 1) -> list[EvidenceObservation]:
    """模拟探针采样：按窗口冻结常量生成 3 组样本，组间隔恰为 max_adjacent_gap_ms。

    窗口合规自检（window 为冻结常量，不得改）：
    - sample_groups=3 → 恰好 3 组；
    - 组间隔 4000ms ≥ min_next_group_gap_ms(2000) 且 ≤ max_adjacent_gap_ms(4000)；
    - 首尾总跨度 8000ms ≥ min_first_last_gap_ms(4000)；
    - 每组单条观测，组内偏移 0 ≤ max_intra_group_skew_ms(1250)。
    """
    base = add_ms(now_utc(), -8000)
    gap = contract.window.max_adjacent_gap_ms
    rotations = contract.source_groups
    observations: list[EvidenceObservation] = []
    for index in range(contract.window.sample_groups):
        source_group = rotations[index % len(rotations)]
        payload = {
            "service": contract.obligations[0].predicate_params.get("service"),
            "status": "UP",
            "latency_ms": 11 + index,
            "sample_group": index + 1,
        }
        observed_at = add_ms(base, index * gap)
        observations.append(
            EvidenceObservation(
                id=f"{contract.id}-obs-r{round_no}-g{index + 1}",
                run_id=RUN_IDENT,
                verification_round=round_no,
                collector_id=COLLECTOR_ID,
                collector_version=COLLECTOR_VERSION,
                probe_id=PROBE_ID,
                scope=contract.scope,
                target=contract.target,
                binding_revision=contract.expected_revision,
                observed_revision="rev-sim-1",
                source_group=source_group,
                sequence=0,
                observed_at=observed_at,
                elapsed_ms=8,
                artifact_digest=payload_digest(payload),
                payload=payload,
            )
        )
    return observations


def evaluate(contract, observations: list[EvidenceObservation]):
    """模拟谓词求值：service-health-ok = 所有探针 UP。

    全 TRUE → 无原因码、verdict=VERIFIED、回执 ACTIVE。
    若把探针 status 改成 DOWN，这里会如实产出 FALSE/CONTRADICTED——
    本脚本保留该语义但不实现 DOWN 采样，避免"假装有故障样本"。
    """
    all_up = all(
        isinstance(item.payload, dict) and item.payload.get("status") == "UP"
        for item in observations
    )
    checked_at = now_utc()
    result = ObligationResult(
        obligation_id=contract.obligations[0].obligation_id,
        value="TRUE" if all_up else "FALSE",
        reason_codes=(),
        used_evidence_ids=tuple(item.id for item in observations),
        rejected_evidence=(),
        checked_at=checked_at,
    )
    verdict = "VERIFIED" if all_up else "CONTRADICTED"
    return result, verdict


def build_receipt(contract, claim_digest: str, result: ObligationResult,
                  verdict: str, round_no: int = 1) -> VerificationReceipt:
    snapshot = f"evidence-snapshot-r{round_no}"
    issued_at = now_utc()
    return VerificationReceipt(
        id=f"{contract.id}-receipt-r{round_no}",
        contract_digest=contract.digest,
        claim_digest=claim_digest,
        evidence_snapshot_digest=digest_of(snapshot),
        policy_version=POLICY_VERSION,
        collector_versions={COLLECTOR_ID: COLLECTOR_VERSION},
        run_id=RUN_IDENT,
        verification_round=round_no,
        target=contract.target,
        binding_revision=contract.expected_revision,
        observed_revision="rev-sim-1",
        obligation_results=(result,),
        verdict=verdict,
        receipt_state="ACTIVE",
        issued_at=issued_at,
        valid_until=add_ms(issued_at, contract.expires_after),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="模拟 Agent 全链路恢复求值（签发→登记→观测→回执，默认 dry-run）"
    )
    parser.add_argument("--draft", help="平台导出的草案 JSON 文件路径")
    parser.add_argument("--demo", action="store_true", help="使用内置示例草案")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                        help="真实上报：登记契约 + 追加观测 + 产出回执")
    parser.add_argument("--owner-user-id", type=int, default=1)
    parser.add_argument("--run-id", type=int, default=0, help="平台侧运行 ID（数据库主键）")
    parser.add_argument("--backend-url", default=None, help="覆盖 SMARTOPS_BACKEND_URL")
    parser.add_argument("--internal-token", default=None, help="覆盖 SMARTOPS_INTERNAL_TOKEN")
    args = parser.parse_args(argv)

    draft = load_draft(args.draft, args.demo)
    print(f"[1/5] 载入草案：{draft.get('id')}")

    contract = issue(draft)
    claim = build_claim(contract, source_incident_id=None)
    claim_digest = digest_of(claim.to_dict())
    print(f"[2/5] 签发完成：digest={contract.digest} · claim_digest={claim_digest}")

    observations = collect_observations(contract)
    print(f"[3/5] 采集观测：{len(observations)} 组样本（窗口合规）")
    for item in observations:
        print(f"      - {item.id} @ {format_time(item.observed_at)} "
              f"group={item.source_group} payload={json.dumps(item.payload, ensure_ascii=False)}")

    result, verdict = evaluate(contract, observations)
    receipt = build_receipt(contract, claim_digest, result, verdict)
    print(f"[4/5] 求值：{result.obligation_id}={result.value}（证据 {len(result.used_evidence_ids)} 条）"
          f" → verdict={verdict} · state=ACTIVE · 有效至 {format_time(receipt.valid_until)}")

    print("\n=== 回执 JSON ===")
    print(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2))

    if args.dry_run:
        print("\n[dry-run] 未上报。真实登记请追加 --no-dry-run 并配置"
              " SMARTOPS_BACKEND_URL / SMARTOPS_INTERNAL_TOKEN。")
        return 0

    print("\n=== 上报 Backend ===")
    try:
        publisher = RecoveryPublisher(args.backend_url, args.internal_token)
        registered = publisher.create_contract(
            contract, claim,
            owner_user_id=args.owner_user_id, run_id=args.run_id,
        )
        record_id = registered.get("id") or registered.get("contractId")
        print(f"[a] 契约已登记：record={record_id} · idempotentReplay={registered.get('idempotentReplay')}")

        observation_data = publisher.append_observations(record_id, observations)
        print(f"[b] 观测已追加：{json.dumps(observation_data, ensure_ascii=False)}")

        receipt_data = publisher.append_receipt(record_id, receipt)
        print(f"[c] 回执已登记：{json.dumps(receipt_data, ensure_ascii=False)}")
    except PublisherConfigError as error:
        print(f"[x] 配置缺失：{error}")
        return 1
    except RecoveryPublisherError as error:
        print(f"[x] 上报失败：{error}")
        return 1

    print("\n提醒：回执已产出但恢复是否成功，以平台复核与后续回放包为准；"
          "本脚本的观测是模拟探针，真实接入请替换 collect_observations 的采样源。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
