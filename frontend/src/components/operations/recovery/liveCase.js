// 平台记录 → 三卡展示视图的适配层。
//
// 只做字段搬运，不在前端补算 verdict、签发回执或放宽时间。
// 后端没给的（纠察轴 inspection、授权轴 authorization）一律保持 null，
// 由卡片显示"未提供"，而不是猜一个看起来合理的值。

export function liveCaseFromDetail(detail) {
  if (!detail || !detail.contract) return null
  const receipt = detail.receipt ?? null
  const replayRecord = Array.isArray(detail.replays) ? detail.replays[0] : null
  return {
    source: 'live',
    contract: detail.contract,
    claim: detail.claim ?? null,
    // 平台不执行修复动作；恢复契约只描述"应达到的业务状态"。
    action: 'NOT_PERFORMED',
    // 纠察轴与授权轴的数据不在本接口内，保持未提供。
    inspection_passed: null,
    authorization: null,
    receipt: receipt?.receipt ?? null,
    obligation_results: receipt?.obligationResults ?? [],
    probe_decision: receipt?.probeDecision ?? null,
    verdict: receipt?.verdict ?? null,
    replay_bundle: replayRecord?.bundle ?? null,
    replay: replayRecord?.replayResult ?? null
  }
}

export function receiptBadge(summary) {
  return {
    verdict: summary?.verdict ?? null,
    state: summary?.receiptState ?? 'NOT_ISSUED',
    issuedAt: summary?.issuedAt ?? null,
    validUntil: summary?.validUntil ?? null
  }
}
