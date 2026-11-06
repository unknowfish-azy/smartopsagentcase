// 恢复三卡的展示样例（fixture）。
// 字段按 docs/design/recovery-contract-v1/schema.json 裁剪，只保留三卡需要展示的最小字段。
// 这些数据是静态样例，未接入任何 API，不是运行证据，也不能用来证明某次恢复。

export const DISPLAY_FIXTURE_NOTE = '展示样例（fixture）：静态数据，未接入 API，不是运行证据。'

const CONTRACT_DIGEST = 'sha256:07a69ae519952c7f0cb332f5086a0b988127cba235c10b3c46670aa4d36bb967'

const TARGET = Object.freeze({
  target_id: 'service:edge-nginx',
  target_kind: 'SERVICE',
  endpoint: 'http://127.0.0.1:18081/health'
})

const WINDOW = Object.freeze({
  sample_groups: 3,
  min_first_last_gap_ms: 4000,
  max_adjacent_gap_ms: 4000,
  max_intra_group_skew_ms: 1250,
  min_next_group_gap_ms: 2000
})

const BUDGETS = Object.freeze({
  max_probe_calls: 12,
  per_probe_timeout_ms: 1000,
  run_deadline_ms: 30000,
  evidence_ttl_ms: 15000,
  receipt_ttl_ms: 8000
})

const CLAIM = Object.freeze({
  id: 'claim-business-recovery-1',
  contract_digest: CONTRACT_DIGEST,
  scope: 'tenant:t1/workspace:w1',
  target: TARGET,
  expected_revision: 'r17',
  claim_type: 'BUSINESS_RECOVERY'
})

const HEALTH_OBLIGATION = Object.freeze({
  obligation_id: 'obl-business-health',
  predicate_id: 'business_health_flag',
  predicate_version: '1',
  predicate_params: { field: 'recovery_status', expected: true },
  required: true,
  weight: 1,
  collector_ids: ['col-a', 'col-b'],
  source_groups: ['sg-a', 'sg-b'],
  binding_revision: 'r17',
  scope: 'tenant:t1/workspace:w1',
  target: TARGET
})

const CAPACITY_OBLIGATION = Object.freeze({
  obligation_id: 'obl-downstream-capacity',
  predicate_id: 'downstream_capacity_ratio',
  predicate_version: '1',
  predicate_params: { field: 'capacity_ratio', minimum: 0.6 },
  required: true,
  weight: 2,
  collector_ids: ['col-c'],
  source_groups: ['sg-b'],
  binding_revision: 'r17',
  scope: 'tenant:t1/workspace:w1',
  target: TARGET
})

function buildContract(obligations) {
  return {
    schema_version: 'recovery-contract/v1',
    id: 'rc-edge-nginx-v1',
    version: '1',
    scope: 'tenant:t1/workspace:w1',
    target: TARGET,
    expected_revision: 'r17',
    template_id: 'template:nginx-health',
    template_version: '1',
    obligations,
    source_groups: ['sg-a', 'sg-b'],
    window: WINDOW,
    budgets: BUDGETS,
    expires_after: 3600000,
    digest: CONTRACT_DIGEST
  }
}

function buildBudgetState(callsUsed, callsRemaining) {
  return { calls_used: callsUsed, calls_remaining: callsRemaining, deadline_at: '2026-11-05T02:00:30Z' }
}

// 样例一：VERIFIED 契约。三组 A/B 双路径采样、窗口满足、业务谓词为真，可签发 ACTIVE 回执。
export const VERIFIED_CASE = Object.freeze({
  source: 'fixture',
  note: DISPLAY_FIXTURE_NOTE,
  contract: buildContract([HEALTH_OBLIGATION]),
  claim: CLAIM,
  action: 'NOT_PERFORMED',
  authorization: 'NOT_REQUIRED',
  inspection_passed: true,
  obligation_results: [{
    obligation_id: 'obl-business-health',
    value: 'TRUE',
    reason_codes: [],
    used_evidence_ids: ['obs-g1-sg-a', 'obs-g1-sg-b', 'obs-g2-sg-a', 'obs-g2-sg-b', 'obs-g3-sg-a', 'obs-g3-sg-b'],
    rejected_evidence: [],
    checked_at: '2026-11-05T02:00:06Z'
  }],
  receipt: {
    id: 'vr-edge-nginx-round1',
    contract_digest: CONTRACT_DIGEST,
    claim_digest: CONTRACT_DIGEST,
    evidence_snapshot_digest: 'sha256:6b3d36950ac783d1242e6519b13b36efc82dac93261dc0166b4699bb9763b3eb',
    policy_version: 'policy-v1',
    collector_versions: { 'col-a': '1.0.0', 'col-b': '1.0.0' },
    run_id: 'run-ver-p0-01',
    verification_round: 1,
    target: TARGET,
    binding_revision: 'r17',
    observed_revision: 'r17',
    obligation_results: [{
      obligation_id: 'obl-business-health',
      value: 'TRUE',
      reason_codes: [],
      used_evidence_ids: ['obs-g3-sg-a', 'obs-g3-sg-b'],
      rejected_evidence: [],
      checked_at: '2026-11-05T02:00:06Z'
    }],
    verdict: 'VERIFIED',
    receipt_state: 'ACTIVE',
    issued_at: '2026-11-05T02:00:06Z',
    valid_until: '2026-11-05T02:00:14Z',
    invalidation_event_ids: []
  },
  probe_decision: {
    decision_id: 'pd-round1-final',
    policy_version: 'policy-v1',
    candidates: [],
    score: 0,
    decision: 'STOP',
    selected_probe_id: null,
    next_eligible_at: null,
    stop_reason: 'NO_NEW_INFORMATION',
    budget_before: buildBudgetState(6, 6),
    budget_after: buildBudgetState(6, 6)
  },
  replay_bundle: {
    schema_version: 'recovery-replay/v1',
    bundle_id: 'rb-edge-nginx-verified-1',
    policy_version: 'policy-v1',
    decision_clock: { mode: 'RECORDED', decision_time: '2026-11-05T02:00:06Z', monotonic_origin_id: 'origin-run-ver-p0-01' },
    observation_order: ['obs-g1-sg-a', 'obs-g1-sg-b', 'obs-g2-sg-a', 'obs-g2-sg-b', 'obs-g3-sg-a', 'obs-g3-sg-b'],
    prerecorded_probe_map: { 'probe-a': ['obs-g1-sg-a', 'obs-g2-sg-a', 'obs-g3-sg-a'], 'probe-b': ['obs-g1-sg-b', 'obs-g2-sg-b', 'obs-g3-sg-b'] },
    run_event_refs: ['run-event-1'],
    source_mapping: { 'col-a': 'sg-a', 'col-b': 'sg-b' },
    dependency_versions: { 'policy-v1': '1' },
    parent_bundle_id: null,
    mutation_diff: null,
    is_historical_fact: true
  },
  replay: {
    replay_state: 'COMPLETE',
    diff_codes: [],
    missing_probe_ids: [],
    policy_version: 'policy-v1',
    decision_time: '2026-11-05T02:00:06Z',
    obligation_results: [{
      obligation_id: 'obl-business-health',
      value: 'TRUE',
      reason_codes: [],
      used_evidence_ids: ['obs-g3-sg-a', 'obs-g3-sg-b'],
      rejected_evidence: [],
      checked_at: '2026-11-05T02:00:06Z'
    }]
  }
})

// 样例二：HTTP 200 且 StateVerifier.passed=true，但业务字段 recovery_status=false。
// 传输与纠察信号必须并列展示，恢复轴仍然是 CONTRADICTED，回执未签发。
export const BUSINESS_FALSE_CASE = Object.freeze({
  source: 'fixture',
  note: DISPLAY_FIXTURE_NOTE,
  contract: buildContract([HEALTH_OBLIGATION, CAPACITY_OBLIGATION]),
  claim: CLAIM,
  action: 'NOT_PERFORMED',
  authorization: 'NOT_REQUIRED',
  inspection_passed: true,
  transport_signals: { http_status: 200, state_verifier_passed: true, run_status: 'succeeded' },
  obligation_results: [
    {
      obligation_id: 'obl-business-health',
      value: 'FALSE',
      reason_codes: [],
      used_evidence_ids: ['obs-g3-sg-a', 'obs-g3-sg-b'],
      rejected_evidence: [],
      checked_at: '2026-11-05T02:00:06Z'
    },
    {
      obligation_id: 'obl-downstream-capacity',
      value: 'UNKNOWN',
      reason_codes: ['MISSING', 'STALE'],
      used_evidence_ids: [],
      rejected_evidence: [{ evidence_id: 'obs-g3-sg-c', reason_code: 'STALE' }],
      checked_at: '2026-11-05T02:00:06Z'
    }
  ],
  receipt: {
    id: 'vr-edge-nginx-round1',
    contract_digest: CONTRACT_DIGEST,
    claim_digest: CONTRACT_DIGEST,
    evidence_snapshot_digest: 'sha256:59048c287e7b224d9b0794b5e1e975422a19da02158c115e9016b342764f3477',
    policy_version: 'policy-v1',
    collector_versions: { 'col-a': '1.0.0', 'col-b': '1.0.0' },
    run_id: 'run-ver-p0-01',
    verification_round: 1,
    target: TARGET,
    binding_revision: 'r17',
    observed_revision: 'r17',
    obligation_results: [
      {
        obligation_id: 'obl-business-health',
        value: 'FALSE',
        reason_codes: [],
        used_evidence_ids: ['obs-g3-sg-a', 'obs-g3-sg-b'],
        rejected_evidence: [],
        checked_at: '2026-11-05T02:00:06Z'
      },
      {
        obligation_id: 'obl-downstream-capacity',
        value: 'UNKNOWN',
        reason_codes: ['MISSING'],
        used_evidence_ids: [],
        rejected_evidence: [],
        checked_at: '2026-11-05T02:00:06Z'
      }
    ],
    verdict: 'CONTRADICTED',
    receipt_state: 'NOT_ISSUED',
    issued_at: null,
    valid_until: null,
    invalidation_event_ids: []
  },
  probe_decision: {
    decision_id: 'pd-round1-stop',
    policy_version: 'policy-v1',
    candidates: [
      { probe_id: 'probe-c', eligible: false, score: 0, registered_cost: 1, covered_obligation_ids: ['obl-downstream-capacity'], filter_reasons: ['UNREGISTERED'] }
    ],
    score: 0,
    decision: 'STOP',
    selected_probe_id: null,
    next_eligible_at: null,
    stop_reason: 'BUDGET_EXHAUSTED',
    budget_before: buildBudgetState(11, 1),
    budget_after: buildBudgetState(12, 0)
  },
  replay_bundle: {
    schema_version: 'recovery-replay/v1',
    bundle_id: 'rb-edge-nginx-deceptive-1',
    policy_version: 'policy-v1',
    decision_clock: { mode: 'RECORDED', decision_time: '2026-11-05T02:00:06Z', monotonic_origin_id: 'origin-run-ver-p0-01' },
    observation_order: ['obs-g1-sg-a', 'obs-g1-sg-b', 'obs-g2-sg-a', 'obs-g2-sg-b', 'obs-g3-sg-a', 'obs-g3-sg-b'],
    prerecorded_probe_map: { 'probe-a': ['obs-g1-sg-a', 'obs-g2-sg-a', 'obs-g3-sg-a'], 'probe-b': ['obs-g1-sg-b', 'obs-g2-sg-b', 'obs-g3-sg-b'] },
    run_event_refs: ['run-event-1'],
    source_mapping: { 'col-a': 'sg-a', 'col-b': 'sg-b' },
    dependency_versions: { 'policy-v1': '1' },
    parent_bundle_id: null,
    mutation_diff: null,
    is_historical_fact: true
  },
  replay: {
    replay_state: 'REPLAY_INCOMPLETE',
    diff_codes: ['PROBE_NOT_RECORDED', 'OBLIGATION_VALUE_CHANGED'],
    missing_probe_ids: ['probe-c'],
    policy_version: 'policy-v2',
    decision_time: '2026-11-05T02:00:06Z',
    obligation_results: [{
      obligation_id: 'obl-business-health',
      value: 'FALSE',
      reason_codes: [],
      used_evidence_ids: ['obs-g3-sg-a', 'obs-g3-sg-b'],
      rejected_evidence: [],
      checked_at: '2026-11-05T02:00:06Z'
    }]
  }
})
