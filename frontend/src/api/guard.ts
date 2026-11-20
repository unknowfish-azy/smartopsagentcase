import request from '../utils/request'

export interface GuardTarget {
  type: string
  id: string
  name: string
  subtitle: string
  available: boolean
}

export interface GuardRun {
  id: number
  targetType: string
  targetId: string
  targetName: string
  suite: string
  status: string
  score: number | null
  riskLevel: string | null
  totalCases: number
  passedCases: number
  failedCases: number
  errorCases: number
  baseline: boolean
  baselineRunId: number | null
  regressionVerdict: string | null
  regressionSummary: string | null
  errorMessage: string | null
  startedAt: string | null
  finishedAt: string | null
  createdAt: string | null
}

export interface GuardCaseItem {
  id: string
  category: string
  categoryLabel: string
  severity: string
  severityLabel: string
  title: string
  prompt: string
  expected: string
  detector: string
  owasp: string
}

export interface GuardCaseResult {
  caseId: string
  category: string
  categoryLabel: string
  severity: string
  severityLabel: string
  title: string
  prompt: string
  response: string | null
  verdict: string
  riskScore: number
  hitRules: string[]
  detector: string
  owasp: string
  latencyMs: number
  errorMessage: string | null
}

export interface GuardCategoryScore {
  category: string
  label: string
  score: number
  total: number
  failed: number
  error: number
}

export interface GuardOverview {
  totalRuns: number
  blockedRuns: number
  averageScore: number | null
  latestRun: GuardRun | null
  latestSummary: {
    score: number
    riskLevel: string
    total: number
    passed: number
    failed: number
    error: number
    categories: GuardCategoryScore[]
  } | null
  categoryScores: GuardCategoryScore[]
  riskFindings: Array<{
    caseId: string
    title: string
    category: string
    categoryLabel: string
    severity: string
    severityLabel: string
    riskScore: number
  }>
  trend: Array<{ runId: number; score: number; riskLevel: string | null; createdAt: string | null; targetName: string }>
  baseline: GuardRun | null
}

export function getGuardOverview() {
  return request.get('/api/guard/overview')
}

export function getGuardCases() {
  return request.get('/api/guard/cases')
}

export function getGuardTargets() {
  return request.get('/api/guard/targets')
}

export function getGuardRuns(limit = 30) {
  return request.get('/api/guard/runs', { params: { limit } })
}

export function createGuardRun(payload: {
  targetType: string
  targetId: string
  suite: string
  markBaseline?: boolean
}) {
  return request.post('/api/guard/runs', payload)
}

export function getGuardRun(id: number | string) {
  return request.get(`/api/guard/runs/${id}`)
}

export function markGuardBaseline(id: number | string) {
  return request.post(`/api/guard/runs/${id}/baseline`)
}

export function getGuardRegression(id: number | string) {
  return request.get(`/api/guard/runs/${id}/regression`)
}

export function exportGuardRun(id: number | string) {
  return request.get(`/api/guard/runs/${id}/export`)
}
