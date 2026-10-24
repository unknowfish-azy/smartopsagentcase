const PHASES = Object.freeze(['RETRIEVE', 'PREVIEW', 'RISK_CHECK', 'AWAIT_CONFIRMATION', 'EXECUTE', 'VERIFY', 'COMPLETED'])

export const toolCallPhases = PHASES

export function createToolCallPlan({ task, tool, parameters = {}, traceId = null }: { task?: string; tool?: any; parameters?: Record<string, any>; traceId?: string | null } = {}) {
  if (!task || !tool?.id) throw new Error('任务和工具不能为空')
  const requiresConfirmation = Boolean(tool.requireConfirm || !tool.readOnly)
  return Object.freeze({
    task: String(task).trim(), toolId: tool.id, parameters: Object.freeze({ ...parameters }),
    traceId, readOnly: Boolean(tool.readOnly), riskLevel: tool.riskLevel || 'LOW',
    requiresConfirmation, phase: requiresConfirmation ? 'AWAIT_CONFIRMATION' : 'PREVIEW',
    evidence: Object.freeze([]), error: null
  })
}

export function advanceToolCallPlan(plan: any, event: { type?: string; ok?: boolean; traceId?: string; evidence?: any[]; error?: any } = {}) {
  if (!plan || !PHASES.includes(plan.phase)) throw new Error('工具调用计划无效')
  if (plan.phase === 'AWAIT_CONFIRMATION' && event.type !== 'CONFIRM') return plan
  if (plan.phase === 'RISK_CHECK' && plan.requiresConfirmation && event.type !== 'CONFIRM') return plan
  const next = {
    RETRIEVE: 'PREVIEW', PREVIEW: 'RISK_CHECK', RISK_CHECK: plan.requiresConfirmation ? 'AWAIT_CONFIRMATION' : 'EXECUTE',
    AWAIT_CONFIRMATION: 'EXECUTE', EXECUTE: event.ok === false ? 'VERIFY' : 'VERIFY', VERIFY: event.ok === false ? 'VERIFY' : 'COMPLETED', COMPLETED: 'COMPLETED'
  }[plan.phase]
  return Object.freeze({ ...plan, phase: next, traceId: event.traceId || plan.traceId, evidence: Object.freeze(event.evidence || plan.evidence), error: event.error || null })
}

export function canExecuteToolCall(plan: any) {
  return Boolean(plan && plan.phase === 'EXECUTE' && !plan.error)
}
