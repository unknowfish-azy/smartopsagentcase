// 恢复三卡的纯展示映射。
// 状态词典与判定规则见 docs/design/recovery-contract-v1/semantics.md：
// 动作、纠察、恢复、授权四轴互不替代；passed / HTTP 200 / 审批通过都不是恢复证据。
// 本模块只翻译服务端已冻结的状态，不做任何判定、不拼接信号、不推断恢复。

const OBLIGATION_VALUE_VIEWS = Object.freeze({
  TRUE: { label: '已支持', tone: 'success', note: '窗口内有合格证据支持该业务条件' },
  FALSE: { label: '业务失败', tone: 'danger', note: '合格观测明确违反业务谓词，是有效业务反例' },
  UNKNOWN: { label: '证据不足', tone: 'unknown', note: '缺少合格观测或观测不合格；UNKNOWN 不能被补齐为 TRUE，也不能当 FALSE 抵消' }
})

const VERDICT_VIEWS = Object.freeze({
  VERIFIED: { text: '恢复已验证', badge: '已验证', tone: 'success', canIssue: true },
  CONTRADICTED: { text: '恢复被反证', badge: '未恢复', tone: 'danger', canIssue: false },
  INSUFFICIENT: { text: '恢复证据不足', badge: '证据不足', tone: 'unknown', canIssue: false }
})

const RECEIPT_STATE_VIEWS = Object.freeze({
  NOT_ISSUED: { label: '未签发', tone: 'unknown', note: '没有可达的 VERIFIED 判定，不展示有效期；从从未签发不等于曾经验证。' },
  ACTIVE: { label: '当前有效', tone: 'success', note: '基于历史 VERIFIED 且仍在 valid_until 之内。' },
  INVALIDATED: { label: '已失效', tone: 'danger', note: '收到新反例、撤回或目标版本变化后追加失效事件；历史回执保留不可改写。' },
  EXPIRED: { label: '已过期', tone: 'warning', note: '超过 valid_until，只说明曾经验证过，不代表当前业务健康。' }
})

const REASON_CODE_LABELS = Object.freeze({
  MISSING: '缺少合格观测',
  STALE: '证据已过期',
  WRONG_TARGET: '目标不匹配',
  WRONG_REVISION: '版本不匹配',
  CONFLICT: '来源未确认的冲突',
  TIMEOUT: '采集超时',
  MALFORMED: '观测结构或摘要不合格'
})

const REASON_CODE_NOTES = Object.freeze({
  MISSING: '当前轮次没有合格观测，或采样槽未填满。',
  STALE: '证据年龄超过 15000ms 或证据已作废。',
  WRONG_TARGET: '观测 target_id 与契约目标不一致。',
  WRONG_REVISION: 'binding_revision 不匹配时证据不足；binding 匹配但响应 observed_revision 明确不同才是有效反例。',
  CONFLICT: '同目标同轮次互相矛盾且来源或身份未确认，只构成证据不足。',
  TIMEOUT: '采集超时默认按证据不足处理，不当业务失败。',
  MALFORMED: 'schema、摘要、payload 或时间不合格，按证据不足拒绝。'
})

export const AXIS_ORDER = Object.freeze(['action', 'inspection', 'recovery', 'authorization'])
export const AXIS_TITLES = Object.freeze({
  action: '动作轴', inspection: '纠察轴', recovery: '恢复轴', authorization: '授权轴'
})

const REPLAY_STATE_VIEWS = Object.freeze({
  COMPLETE: { label: '回放完整', tone: 'success', prominent: false, notice: '冻结输入与录制探针齐全，可在同一证据下复现判定。' },
  REPLAY_INCOMPLETE: {
    label: '证据不完整',
    tone: 'danger',
    prominent: true,
    notice: '证据不完整：调度选择了未录制的探针，或观测顺序缺失。本次回放不能证明恢复，不得展示为通过。'
  },
  MALFORMED: { label: '回放包损坏', tone: 'danger', prominent: true, notice: '结构化校验或摘要校验失败，直接拒绝该回放包，不得边拒绝边继续求值。' },
  STALE: { label: '回放包已过期', tone: 'warning', prominent: false, notice: '录制时间超出契约有效期，只能作为历史参考。' }
})

const REPLAY_DIFF_CODE_LABELS = Object.freeze({
  OBLIGATION_VALUE_CHANGED: '义务值变化',
  VERDICT_CHANGED: '恢复判定变化',
  PROBE_NOT_RECORDED: '探针未录制',
  ORDER_MISSING: '观测顺序缺失',
  POLICY_VERSION_CHANGED: '策略版本变化',
  CONFIG_CHANGED: '策略配置变化',
  EVIDENCE_DROPPED: '证据在实验包中被删除',
  SOURCE_MAPPING_CHANGED: '来源映射变化'
})

const PROBE_DECISION_VIEWS = Object.freeze({
  SELECTED: { label: '建议继续探针', tone: 'neutral' },
  WAIT: { label: '等待下一采样窗口', tone: 'unknown' },
  STOP: { label: '停止补证，保留缺口', tone: 'danger' }
})

const STOP_REASON_LABELS = Object.freeze({
  BUDGET_EXHAUSTED: '探针调用预算耗尽',
  DEADLINE_EXCEEDED: '超过运行截止时间',
  NO_COVERAGE: '没有探针覆盖剩余缺口',
  STATIC_INCOMPATIBLE: '静态预算不足以完成最小窗口',
  NO_NEW_INFORMATION: '连续无新增有效信息'
})

const FILTER_REASON_LABELS = Object.freeze({
  UNREGISTERED: '探针未登记',
  IDENTITY: '采集器身份不合格',
  SCOPE: '可见范围不匹配',
  TARGET_ALLOWLIST: '目标不在白名单',
  TOOL_PERMISSION: '工具权限不足',
  READ_ONLY: '只读限制',
  QUOTA: '配额不足',
  DEADLINE: '超过截止时间',
  COST: '成本不可接受',
  DUPLICATE: '重复探针'
})

const SOURCE_LABELS = Object.freeze({
  fixture: '静态展示样例（fixture，未接入 API）',
  live: '真实采集（平台运行记录）',
  replay: '离线回放包',
  test: '受控测试控制器注入'
})

export function obligationValueView(value) {
  return OBLIGATION_VALUE_VIEWS[value] || {
    label: '未取得义务值',
    tone: 'unknown',
    note: '没有该义务的结果记录，不能按 TRUE 处理。'
  }
}

export function reasonCodeLabel(code) {
  return REASON_CODE_LABELS[code] || String(code || '未记录原因码')
}

export function reasonCodeViews(codes) {
  return (Array.isArray(codes) ? codes : []).map(code => ({
    code,
    label: reasonCodeLabel(code),
    note: REASON_CODE_NOTES[code] || '原因码未在 V1 词典内，按证据不足处理。'
  }))
}

export function verdictView(verdict) {
  return VERDICT_VIEWS[verdict] || null
}

export function verdictText(verdict) {
  const view = verdictView(verdict)
  return view ? view.text : '未取得恢复判定'
}

// 只有服务端给出 VERIFIED/CONTRADICTED/INSUFFICIENT 时才有恢复徽标。
// passed、HTTP 200、审批结果或缺失判定都返回 null，避免把别的轴画成恢复。
export function recoveryBadge(verdict) {
  const view = verdictView(verdict)
  return view ? { text: view.badge, tone: view.tone, verdict } : null
}

export function receiptStateView(state) {
  return RECEIPT_STATE_VIEWS[state] || {
    label: '回执状态未知',
    tone: 'unknown',
    note: '未识别的回执状态，不得按当前有效展示。'
  }
}

export function receiptTimeView(receipt) {
  if (!receipt) return { issuedAt: '—', validUntil: '—', text: '未提供回执' }
  if (receipt.receipt_state === 'NOT_ISSUED') {
    return { issuedAt: '—', validUntil: '—', text: '未签发，无签发时间与有效期' }
  }
  return {
    issuedAt: formatUtc(receipt.issued_at),
    validUntil: formatUtc(receipt.valid_until),
    text: `签发于 ${formatUtc(receipt.issued_at)}，有效至 ${formatUtc(receipt.valid_until)}`
  }
}

export function actionAxisView(value) {
  if (value === 'NOT_PERFORMED') {
    return { label: '未执行（隔离只读 PoC）', tone: 'unknown', note: '只读取观测，没有执行任何修复动作；动作完成与否都不是恢复证据。' }
  }
  if (value == null || value === '') {
    return { label: '未提供动作状态', tone: 'unknown', note: '动作轴缺省时不得用恢复判定填充。' }
  }
  return { label: String(value), tone: 'neutral', note: '动作状态来自运行/动作模型，不能替代恢复判定。' }
}

export function inspectionAxisView(passed) {
  if (passed === true) {
    return { label: '声明与观测一致（passed=true）', tone: 'neutral', note: 'passed 只表示声明与观测一致，不表示业务恢复，也不进入恢复徽标。' }
  }
  if (passed === false) {
    return { label: '声明与观测不一致（passed=false）', tone: 'warning', note: '纠察结论不满足也不等于业务失败，恢复判定仍由服务端核验给出。' }
  }
  return { label: '未提供纠察结论', tone: 'unknown', note: '没有纠察结论时不得推断恢复。' }
}

export function recoveryAxisView(verdict) {
  const view = verdictView(verdict)
  if (!view) {
    return { label: '未取得恢复判定', tone: 'unknown', badge: null, note: '缺少服务端恢复判定；不得用其它轴的结论代替。' }
  }
  return { label: view.text, tone: view.tone, badge: view.badge, note: '恢复判定只由核验回执产生，不由动作、传输或审批推出。' }
}

export function authorizationAxisView(value) {
  if (value === 'APPROVED') {
    return { label: '动作已获授权', tone: 'neutral', note: '授权只允许动作，不构成恢复证据。' }
  }
  if (value === 'REJECTED') {
    return { label: '授权被拒绝', tone: 'warning', note: '授权结果属于平台审批来源，与恢复判定无关。' }
  }
  if (value === 'NOT_REQUIRED') {
    return { label: '无需授权（只读观测）', tone: 'neutral', note: '隔离只读 PoC 没有动作授权需求；授权轴不构成恢复证据。' }
  }
  return { label: value ? String(value) : '未记录授权结论', tone: 'unknown', note: '授权轴缺省时不得填充为恢复结论。' }
}

export function axisRows({ action, inspectionPassed, verdict, authorization } = {}) {
  return [
    { key: 'action', title: AXIS_TITLES.action, ...actionAxisView(action) },
    { key: 'inspection', title: AXIS_TITLES.inspection, ...inspectionAxisView(inspectionPassed) },
    { key: 'recovery', title: AXIS_TITLES.recovery, ...recoveryAxisView(verdict) },
    { key: 'authorization', title: AXIS_TITLES.authorization, ...authorizationAxisView(authorization) }
  ]
}

export function sourceView(source) {
  return SOURCE_LABELS[source] || '未提供数据来源'
}

export function stopReasonLabel(code) {
  return STOP_REASON_LABELS[code] || String(code || '未记录停止原因')
}

export function filterReasonLabel(code) {
  return FILTER_REASON_LABELS[code] || String(code || '未记录过滤理由')
}

export function probeDecisionView(decision) {
  if (!decision) {
    return { decision: 'UNKNOWN', label: '未提供探针决策', tone: 'unknown', detail: '没有可展示的下一探针建议。' }
  }
  const view = PROBE_DECISION_VIEWS[decision.decision] || {
    decision: String(decision.decision || 'UNKNOWN'),
    label: '未识别的探针决策',
    tone: 'unknown'
  }
  const score = Number(decision.score)
  const scoreText = Number.isFinite(score) ? `优先级分数 ${score.toFixed(2)}` : ''
  if (decision.decision === 'SELECTED') {
    const covered = decision.candidates?.find(candidate => candidate.probe_id === decision.selected_probe_id)?.covered_obligation_ids ?? []
    return {
      decision: 'SELECTED',
      label: view.label,
      tone: view.tone,
      detail: `下一探针：${decision.selected_probe_id || '未给出'}，覆盖 ${covered.length} 项义务。${scoreText}`,
      probeId: decision.selected_probe_id || null
    }
  }
  if (decision.decision === 'WAIT') {
    return {
      decision: 'WAIT',
      label: view.label,
      tone: view.tone,
      detail: `最早可执行时间：${formatUtc(decision.next_eligible_at)}；等待不消耗探针调用预算，但受总 deadline 约束。${scoreText}`,
      probeId: null
    }
  }
  if (decision.decision === 'STOP') {
    return {
      decision: 'STOP',
      label: view.label,
      tone: view.tone,
      detail: `停止原因：${stopReasonLabel(decision.stop_reason)}；停止不是恢复结论。${scoreText}`,
      probeId: null
    }
  }
  return { decision: view.decision, label: view.label, tone: view.tone, detail: scoreText, probeId: null }
}

export function budgetView(budget) {
  if (!budget) return { text: '未提供预算状态', used: null, remaining: null, limit: null, deadlineAt: '—' }
  const limits = budget.limits || budget
  const used = budget.calls_used ?? budget.callsUsed ?? null
  const limit = limits.max_probe_calls ?? null
  const remaining = budget.calls_remaining ?? (limit != null && used != null ? Math.max(0, limit - used) : null)
  const deadlineAt = budget.deadline_at ?? null
  const parts = [
    used != null ? `已用 ${used}${limit != null ? `/${limit}` : ''} 次探针调用` : '未记录调用次数',
    remaining != null ? `剩余 ${remaining} 次` : null,
    `截止 ${formatUtc(deadlineAt)}`
  ].filter(Boolean)
  return { text: parts.join('，'), used, remaining, limit, deadlineAt }
}

export function windowSummary(window) {
  if (!window) return { text: '未提供观测窗口', items: [] }
  const items = [
    { label: '最少有效组数', value: `${window.sample_groups} 组` },
    { label: '首末组最小间隔', value: `${(window.min_first_last_gap_ms ?? 0) / 1000} 秒` },
    { label: '相邻组最大间隔', value: `${(window.max_adjacent_gap_ms ?? 0) / 1000} 秒` },
    { label: '组内最大偏差', value: `${window.max_intra_group_skew_ms} 毫秒` },
    { label: '下一组最早启动', value: `前组完成后 ${(window.min_next_group_gap_ms ?? 0) / 1000} 秒` }
  ]
  return { text: items.map(item => `${item.label} ${item.value}`).join('；'), items }
}

export function gapSummary({ obligations = [], obligationResults = [], probeDecision = null, budget = null } = {}) {
  const contractObligations = Array.isArray(obligations) ? obligations : []
  if (contractObligations.length === 0) {
    return {
      empty: true,
      headline: '无证据义务，不可签发',
      note: '契约没有可计算的证据义务，任何回执都不能签发；这不是“已满足”。',
      rows: [],
      unmet: [],
      missingEvidence: [],
      reasonCodes: [],
      satisfied: 0,
      total: 0,
      nextProbe: probeDecisionView(probeDecision),
      budget: budgetView(budget)
    }
  }
  const resultsById = new Map((obligationResults || []).map(result => [result.obligation_id, result]))
  const rows = contractObligations.map(obligation => {
    const result = resultsById.get(obligation.obligation_id)
    const view = obligationValueView(result?.value)
    return {
      obligationId: obligation.obligation_id,
      predicateId: obligation.predicate_id,
      predicateVersion: obligation.predicate_version ?? '—',
      required: obligation.required !== false,
      requiredLabel: obligation.required === false ? '可选义务' : '必需义务',
      value: result?.value ?? null,
      valueLabel: view.label,
      tone: view.tone,
      note: view.note,
      reasonCodes: result?.reason_codes ?? [],
      reasonLabels: reasonCodeViews(result?.reason_codes),
      evidenceIds: result?.used_evidence_ids ?? [],
      rejected: result?.rejected_evidence ?? [],
      checkedAt: result?.checked_at ?? null
    }
  })
  const unmet = rows.filter(row => row.value !== 'TRUE')
  const missingEvidence = rows.filter(row => row.value == null || row.value === 'UNKNOWN')
  const reasonCodes = [...new Set(unmet.flatMap(row => row.reasonCodes))]
  return {
    empty: false,
    headline: unmet.length === 0 ? '必需义务均已支持' : `${unmet.length} 项义务未满足`,
    note: '缺口清单只由服务端逐义务结果生成。',
    rows,
    unmet,
    missingEvidence,
    reasonCodes,
    satisfied: rows.filter(row => row.value === 'TRUE').length,
    total: rows.length,
    nextProbe: probeDecisionView(probeDecision),
    budget: budgetView(budget)
  }
}

export function replayStateView(state) {
  return REPLAY_STATE_VIEWS[state] || {
    label: '回放状态未知',
    tone: 'unknown',
    prominent: false,
    notice: '未识别的回放状态，不得按完整回放展示。'
  }
}

export function diffCodeViews(codes) {
  return (Array.isArray(codes) ? codes : []).map(code => ({
    code,
    label: REPLAY_DIFF_CODE_LABELS[code] || `未登记差异码：${code}`
  }))
}

export function missingProbeViews(ids) {
  return (Array.isArray(ids) ? ids : []).map(id => ({
    id,
    label: '未录制，回放不能补造结果'
  }))
}

export function replayDiffRows({ baselineResults = [], replayResults = [], replayState = null } = {}) {
  const replayById = new Map((replayResults || []).map(result => [result.obligation_id, result]))
  const rows = (baselineResults || []).map(baseline => {
    const replay = replayById.get(baseline.obligation_id) || null
    const baselineView = obligationValueView(baseline.value)
    const replayView = replay ? obligationValueView(replay.value) : null
    const changed = replayState !== 'COMPLETE' || !replay || replay.value !== baseline.value
    return {
      obligationId: baseline.obligation_id,
      baselineValue: baseline.value ?? null,
      baselineLabel: baselineView.label,
      baselineTone: baselineView.tone,
      replayValue: replay ? replay.value ?? null : null,
      replayLabel: replayView ? replayView.label : '回放缺项（未覆盖）',
      replayTone: replayView ? replayView.tone : 'unknown',
      changed,
      changeLabel: !replay ? '回放缺项' : replayState !== 'COMPLETE' ? '回放不完整' : changed ? '与原包不同' : '与原包一致'
    }
  })
  return {
    rows,
    codes: diffCodeViews([]),
    missingProbes: missingProbeViews([]),
    hasChanges: rows.some(row => row.changed)
  }
}

export function replayDiffView({ baselineResults = [], replayResults = [], replayState = null, diffCodes = [], missingProbeIds = [] } = {}) {
  const rows = replayDiffRows({ baselineResults, replayResults, replayState })
  return {
    rows: rows.rows,
    hasChanges: rows.hasChanges,
    codes: diffCodeViews(diffCodes),
    missingProbes: missingProbeViews(missingProbeIds)
  }
}

export function formatUtc(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const iso = date.toISOString()
  return `${iso.slice(0, 10)} ${iso.slice(11, 19)} UTC`
}
