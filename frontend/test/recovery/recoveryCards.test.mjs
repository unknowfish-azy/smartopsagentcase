import test from 'node:test'
import assert from 'node:assert/strict'
import {
  axisRows,
  budgetView,
  filterReasonLabel,
  formatUtc,
  gapSummary,
  obligationValueView,
  probeDecisionView,
  reasonCodeLabel,
  reasonCodeViews,
  receiptStateView,
  receiptTimeView,
  recoveryBadge,
  replayDiffView,
  replayStateView,
  sourceView,
  stopReasonLabel,
  verdictText,
  verdictView,
  windowSummary
} from '../../src/components/operations/recovery/recoveryCards.js'
import { BUSINESS_FALSE_CASE, VERIFIED_CASE } from '../../src/components/operations/recovery/fixtures.js'

test('HTTP 200 加业务 false 时不出现“已恢复”，回执也不得签发', () => {
  const { receipt, obligation_results, transport_signals } = BUSINESS_FALSE_CASE
  assert.equal(transport_signals.http_status, 200)
  assert.equal(transport_signals.state_verifier_passed, true)
  assert.equal(verdictText(receipt.verdict), '恢复被反证')
  assert.equal(verdictView(receipt.verdict).canIssue, false)
  assert.deepEqual(recoveryBadge(receipt.verdict), { text: '未恢复', tone: 'danger', verdict: 'CONTRADICTED' })
  assert.equal(receiptStateView(receipt.receipt_state).label, '未签发')
  assert.equal(receipt.issued_at, null)
  assert.equal(receipt.valid_until, null)

  const model = JSON.stringify({
    verdict: verdictText(receipt.verdict),
    badge: recoveryBadge(receipt.verdict),
    receipt: receiptStateView(receipt.receipt_state).label,
    axes: axisRows({
      action: BUSINESS_FALSE_CASE.action,
      inspectionPassed: BUSINESS_FALSE_CASE.inspection_passed,
      verdict: receipt.verdict,
      authorization: BUSINESS_FALSE_CASE.authorization
    }),
    obligations: obligation_results.map(item => obligationValueView(item.value).label)
  })
  assert.equal(model.includes('已恢复'), false)
  assert.equal(model.includes('回放通过'), false)
})

test('passed=true 但恢复判定缺失时没有恢复徽标，其它轴不被当成恢复', () => {
  assert.equal(recoveryBadge(undefined), null)
  assert.equal(recoveryBadge(null), null)
  assert.equal(recoveryBadge('UNKNOWN'), null)
  assert.equal(verdictView('UNKNOWN'), null)
  assert.equal(verdictText(undefined), '未取得恢复判定')

  const axes = axisRows({ action: 'NOT_PERFORMED', inspectionPassed: true, verdict: undefined, authorization: null })
  const recoveryRow = axes.find(row => row.key === 'recovery')
  assert.equal(recoveryRow.label, '未取得恢复判定')
  assert.equal(recoveryRow.badge, null)
  const otherRows = axes.filter(row => row.key !== 'recovery')
  assert.equal(otherRows.some(row => row.label.includes('恢复已验证')), false)
  assert.equal(otherRows.some(row => row.tone === 'success'), false)
})

test('REPLAY_INCOMPLETE 显示“证据不完整”，任何回放状态都不显示“回放通过”', () => {
  for (const state of ['COMPLETE', 'REPLAY_INCOMPLETE', 'MALFORMED', 'STALE']) {
    const view = replayStateView(state)
    assert.equal(view.label.includes('回放通过'), false)
    assert.equal(view.notice.includes('回放通过'), false)
  }
  const incomplete = replayStateView('REPLAY_INCOMPLETE')
  assert.equal(incomplete.label, '证据不完整')
  assert.equal(incomplete.prominent, true)
  assert.equal(incomplete.tone, 'danger')
  assert.equal(replayStateView('COMPLETE').prominent, false)
  assert.equal(replayStateView('UNKNOWN_STATE').tone, 'unknown')
})

test('缺口卡在空义务时提示“无证据义务，不可签发”', () => {
  const empty = gapSummary({ obligations: [], obligationResults: [] })
  assert.equal(empty.empty, true)
  assert.equal(empty.headline, '无证据义务，不可签发')
  assert.equal(empty.rows.length, 0)
  assert.equal(empty.missingEvidence.length, 0)
  assert.equal(empty.nextProbe.label, '未提供探针决策')
  assert.match(empty.note, /不能签发/)

  const fromDefaults = gapSummary()
  assert.equal(fromDefaults.empty, true)
  assert.equal(fromDefaults.headline, '无证据义务，不可签发')
})

test('四轴文案互不替代，动作与恢复不共用状态词', () => {
  const axes = axisRows({
    action: 'NOT_PERFORMED',
    inspectionPassed: true,
    verdict: 'VERIFIED',
    authorization: 'NOT_REQUIRED'
  })
  assert.equal(axes.length, 4)
  assert.deepEqual(axes.map(row => row.key), ['action', 'inspection', 'recovery', 'authorization'])
  assert.equal(new Set(axes.map(row => row.title)).size, 4)
  assert.equal(new Set(axes.map(row => row.label)).size, 4)
  assert.equal(axes[0].label, '未执行（隔离只读 PoC）')
  assert.equal(axes[1].label, '声明与观测一致（passed=true）')
  assert.equal(axes[2].label, '恢复已验证')
  assert.equal(axes[3].label, '无需授权（只读观测）')
  for (const row of axes) assert.match(row.note, /不/)
  assert.equal(axes[0].note.includes('恢复证据'), true)
  assert.equal(axes[1].note.includes('不进入恢复徽标'), true)
  assert.equal(axes[3].note.includes('不构成恢复证据'), true)
})

test('缺口卡逐义务区分 TRUE/FALSE/UNKNOWN 并给出缺失证据与停止原因', () => {
  const summary = gapSummary({
    obligations: BUSINESS_FALSE_CASE.contract.obligations,
    obligationResults: BUSINESS_FALSE_CASE.obligation_results,
    probeDecision: BUSINESS_FALSE_CASE.probe_decision,
    budget: BUSINESS_FALSE_CASE.probe_decision.budget_after
  })
  assert.equal(summary.empty, false)
  assert.equal(summary.total, 2)
  assert.equal(summary.satisfied, 0)
  const health = summary.rows.find(row => row.obligationId === 'obl-business-health')
  assert.equal(health.value, 'FALSE')
  assert.equal(health.valueLabel, '业务失败')
  assert.equal(health.tone, 'danger')
  const capacity = summary.rows.find(row => row.obligationId === 'obl-downstream-capacity')
  assert.equal(capacity.value, 'UNKNOWN')
  assert.equal(capacity.valueLabel, '证据不足')
  assert.deepEqual(capacity.reasonCodes, ['MISSING', 'STALE'])
  assert.equal(capacity.rejected[0].reason_code, 'STALE')
  assert.deepEqual(summary.missingEvidence.map(row => row.obligationId), ['obl-downstream-capacity'])
  assert.equal(summary.nextProbe.label, '停止补证，保留缺口')
  assert.match(summary.nextProbe.detail, /探针调用预算耗尽/)
  assert.match(summary.budget.text, /已用 12 次探针调用/)
  assert.match(summary.budget.text, /剩余 0 次/)

  const verified = gapSummary({
    obligations: VERIFIED_CASE.contract.obligations,
    obligationResults: VERIFIED_CASE.obligation_results,
    probeDecision: VERIFIED_CASE.probe_decision
  })
  assert.equal(verified.satisfied, 1)
  assert.equal(verified.unmet.length, 0)
  assert.equal(verified.headline, '必需义务均已支持')
})

test('回放差异逐义务标注变化，缺失探针与差异码有中文说明', () => {
  const diff = replayDiffView({
    baselineResults: BUSINESS_FALSE_CASE.receipt.obligation_results,
    replayResults: BUSINESS_FALSE_CASE.replay.obligation_results,
    replayState: BUSINESS_FALSE_CASE.replay.replay_state,
    diffCodes: BUSINESS_FALSE_CASE.replay.diff_codes,
    missingProbeIds: BUSINESS_FALSE_CASE.replay.missing_probe_ids
  })
  assert.equal(diff.hasChanges, true)
  assert.equal(diff.rows.length, 2)
  const capacity = diff.rows.find(row => row.obligationId === 'obl-downstream-capacity')
  assert.equal(capacity.replayLabel, '回放缺项（未覆盖）')
  assert.equal(capacity.changeLabel, '回放缺项')
  assert.equal(capacity.changed, true)
  const health = diff.rows.find(row => row.obligationId === 'obl-business-health')
  assert.equal(health.changeLabel, '回放不完整')
  assert.deepEqual(diff.codes.map(code => code.label), ['探针未录制', '义务值变化'])
  assert.deepEqual(diff.missingProbes.map(probe => probe.id), ['probe-c'])

  const verified = replayDiffView({
    baselineResults: VERIFIED_CASE.receipt.obligation_results,
    replayResults: VERIFIED_CASE.replay.obligation_results,
    replayState: VERIFIED_CASE.replay.replay_state,
    diffCodes: VERIFIED_CASE.replay.diff_codes,
    missingProbeIds: VERIFIED_CASE.replay.missing_probe_ids
  })
  assert.equal(verified.hasChanges, false)
  assert.equal(verified.rows[0].changeLabel, '与原包一致')
  assert.equal(diffUnregisteredCodeFallback(), '未登记差异码：X_UNKNOWN')
})

function diffUnregisteredCodeFallback() {
  const view = replayDiffView({ diffCodes: ['X_UNKNOWN'] })
  return view.codes[0].label
}

test('原因码、回执状态、预算与时钟的展示文案完整', () => {
  assert.equal(reasonCodeLabel('MISSING'), '缺少合格观测')
  assert.equal(reasonCodeLabel('WRONG_REVISION'), '版本不匹配')
  assert.equal(reasonCodeLabel('NOPE'), 'NOPE')
  assert.equal(reasonCodeViews(['TIMEOUT'])[0].note, '采集超时默认按证据不足处理，不当业务失败。')
  assert.equal(reasonCodeViews([]).length, 0)

  assert.equal(receiptStateView('ACTIVE').label, '当前有效')
  assert.equal(receiptStateView('INVALIDATED').tone, 'danger')
  assert.equal(receiptStateView('EXPIRED').label, '已过期')
  assert.equal(receiptStateView('NOT_ISSUED').note.includes('不等于'), true)
  assert.equal(receiptStateView('ANY').tone, 'unknown')

  assert.equal(receiptTimeView(null).text, '未提供回执')
  assert.equal(receiptTimeView(BUSINESS_FALSE_CASE.receipt).text, '未签发，无签发时间与有效期')
  assert.equal(receiptTimeView(VERIFIED_CASE.receipt).validUntil, '2026-11-05 02:00:14 UTC')

  assert.equal(probeDecisionView(VERIFIED_CASE.probe_decision).label, '停止补证，保留缺口')
  assert.equal(stopReasonLabel('DEADLINE_EXCEEDED'), '超过运行截止时间')
  assert.equal(stopReasonLabel(null), '未记录停止原因')
  assert.equal(filterReasonLabel('UNREGISTERED'), '探针未登记')
  assert.equal(probeDecisionView(null).label, '未提供探针决策')

  const selected = probeDecisionView({
    decision: 'SELECTED',
    selected_probe_id: 'probe-a',
    score: 1.5,
    candidates: [{ probe_id: 'probe-a', covered_obligation_ids: ['obl-1', 'obl-2'] }]
  })
  assert.match(selected.detail, /probe-a/)
  assert.match(selected.detail, /覆盖 2 项义务/)
  assert.equal(probeDecisionView({ decision: 'WAIT', next_eligible_at: '2026-11-05T02:00:08Z' }).detail.includes('最早可执行时间'), true)

  const budget = budgetView(VERIFIED_CASE.probe_decision.budget_after)
  assert.equal(budget.used, 6)
  assert.equal(budget.remaining, 6)
  assert.match(budget.text, /截止 2026-11-05 02:00:30 UTC/)

  assert.equal(formatUtc('2026-11-05T02:00:06Z'), '2026-11-05 02:00:06 UTC')
  assert.equal(formatUtc('2026-11-05T10:00:06+08:00'), '2026-11-05 02:00:06 UTC')
  assert.equal(formatUtc(null), '—')

  const window = windowSummary(VERIFIED_CASE.contract.window)
  assert.equal(window.items.length, 5)
  assert.match(window.text, /3 组/)
})

test('fixture 来源标记为展示样例，且回执与判定语义一致', () => {
  assert.equal(sourceView('fixture'), '静态展示样例（fixture，未接入 API）')
  assert.equal(sourceView('live'), '真实采集（平台运行记录）')
  assert.equal(sourceView('other'), '未提供数据来源')
  assert.equal(VERIFIED_CASE.source, 'fixture')
  assert.equal(VERIFIED_CASE.note.includes('不是运行证据'), true)
  assert.equal(BUSINESS_FALSE_CASE.receipt.verdict, 'CONTRADICTED')
  assert.equal(BUSINESS_FALSE_CASE.receipt.receipt_state, 'NOT_ISSUED')
  assert.equal(VERIFIED_CASE.receipt.verdict, 'VERIFIED')
  assert.equal(VERIFIED_CASE.receipt.receipt_state, 'ACTIVE')
})
