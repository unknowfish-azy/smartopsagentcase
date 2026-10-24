export function validMonth(value) {
  return /^(20\d{2}|2100)-(0[1-9]|1[0-2])$/.test(value)
}

export function parseTokenBudget(value) {
  const text = String(value).trim()
  if (!text) return null
  if (!/^\d+$/.test(text) || Number(text) > 1e12) throw new Error('额度需为 0–1,000,000,000,000 的整数，留空表示不设额度。')
  return Number(text)
}

export function budgetState(limit, used = 0) {
  if (limit == null) return { percent: 0, remaining: null, overage: 0 }
  return {
    percent: limit === 0 ? (used > 0 ? 100 : 0) : Math.min(100, used / limit * 100),
    remaining: Math.max(0, limit - used),
    overage: Math.max(0, used - limit)
  }
}

/* 环形配度的等级派生：exceeded > critical(≥90%) > warning(≥70%) > healthy；无额度时 level='none'。
   阈值与令牌的映射由 QuotaRing.vue 承担，这里只产出语义。 */
export function quotaRingState(limit, used = 0) {
  const base = budgetState(limit, used)
  if (limit == null) return { ...base, level: 'none', hasBudget: false }
  const level = base.overage > 0 ? 'exceeded' : base.percent >= 90 ? 'critical' : base.percent >= 70 ? 'warning' : 'healthy'
  return { ...base, level, hasBudget: true }
}

export function formatMetric(value, digits = 0) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

/* ── 周期聚合（今日 / 近 7 天 / 本月）────────────────────────────────
   口径与后端一致：只汇总服务商已上报值，null 表示未知、不按零补齐；
   今日 / 近 7 天从 daily[] 按 UTC 日期切片（date ≤ today），本月直接采用 summary。
   today 传 'YYYY-MM-DD'；切片为空或零调用时 available=false，由界面提示而非画空图。 */
export function periodAggregate(daily, summary, period = 'month', today = '') {
  if (period === 'month') {
    const source = summary || {}
    const calls = countOf(source.calls), successes = countOf(source.successes), failures = countOf(source.failures)
    return {
      period, available: calls > 0, calls, successes, failures,
      pendingCalls: countOf(source.pendingCalls), unknownUsageCalls: countOf(source.unknownUsageCalls),
      knownTokens: nullableOf(source.knownTokens), inputTokens: nullableOf(source.inputTokens), outputTokens: nullableOf(source.outputTokens),
      successRate: successes + failures > 0 ? successes * 100 / (successes + failures) : null
    }
  }
  const days = Array.isArray(daily) ? daily.filter(day => day && day.date && (!today || day.date <= today)) : []
  const slice = period === 'today' ? days.filter(day => day.date === today) : days.slice(-7)
  if (!slice.length) return emptyAggregate(period)
  const calls = sumField(slice, 'calls'), successes = sumField(slice, 'successes'), failures = sumField(slice, 'failures')
  return {
    period, available: calls > 0, calls, successes, failures,
    pendingCalls: sumField(slice, 'pendingCalls'), unknownUsageCalls: sumField(slice, 'unknownUsageCalls'),
    knownTokens: sumField(slice, 'knownTokens'), inputTokens: sumField(slice, 'inputTokens'), outputTokens: sumField(slice, 'outputTokens'),
    successRate: successes + failures > 0 ? successes * 100 / (successes + failures) : null
  }
}

function emptyAggregate(period) {
  return { period, available: false, calls: 0, successes: 0, failures: 0, pendingCalls: 0, unknownUsageCalls: 0, knownTokens: null, inputTokens: null, outputTokens: null, successRate: null }
}
const countOf = value => value == null || !Number.isFinite(Number(value)) ? 0 : Number(value)
const nullableOf = value => value == null || !Number.isFinite(Number(value)) ? null : Number(value)
function sumField(slice, key) {
  let total = 0, seenValue = false, seenNull = false
  for (const day of slice) {
    const value = day[key]
    if (value == null || !Number.isFinite(Number(value))) { seenNull = true; continue }
    seenValue = true; total += Number(value)
  }
  if (seenValue) return total
  return seenNull ? null : 0
}

/* ── 消耗速率与全月预计（token-monitor 的"环形配额 + 实时速率"）──────────
   纯线性推算：日均 = 已知用量 / 已过去天数；预计 = 日均 × 当月天数。
   exhaustDate 为按当前速率触及额度线的日期（仅当确实会在当月触及时给出）。
   未来月份已过去天数为 0，不猜速率；pacePercent 在额度为 0 时恒 null（另作超额提示）。 */
export function usagePace(limit, used, month, today = '') {
  const total = daysInMonth(month)
  const usedTokens = countOf(used)
  const result = {
    daysInMonth: total, daysElapsed: 0, dailyRate: null, projected: null, pacePercent: null, exhaustDate: null,
    remaining: limit == null ? null : Math.max(0, limit - usedTokens),
    overage: limit == null ? 0 : Math.max(0, usedTokens - limit)
  }
  const start = monthStartUtc(month)
  if (!start || !total) return result
  const todayTime = today ? Date.parse(`${today}T00:00:00Z`) : Date.now()
  if (!Number.isFinite(todayTime)) return result
  const elapsed = todayTime < start.getTime() ? 0
    : todayTime >= start.getTime() + total * 86400000 ? total
    : Math.floor((todayTime - start.getTime()) / 86400000) + 1
  result.daysElapsed = elapsed
  if (elapsed <= 0) return result
  const rate = usedTokens / elapsed
  result.dailyRate = rate
  result.projected = rate * total
  if (limit != null && limit > 0) {
    result.pacePercent = rate * total / limit * 100
    if (usedTokens < limit) {
      const daysToLimit = Math.ceil(limit / rate)
      if (daysToLimit <= total) result.exhaustDate = new Date(start.getTime() + (daysToLimit - 1) * 86400000).toISOString().slice(0, 10)
    }
  }
  return result
}

export function daysInMonth(month) {
  const start = monthStartUtc(month)
  return start ? new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate() : 0
}
function monthStartUtc(month) {
  const match = /^(\d{4})-(\d{2})$/.exec(month || '')
  if (!match) return null
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1))
  return date.getUTCMonth() === Number(match[2]) - 1 ? date : null
}

/* ── 上一等长周期聚合（环比徽标的数据源）────────────────────────────
   week → 再往前 7 天窗口；today → 昨日；month → null（接口只给当月 summary，
   不跨月拼凑、不猜上月）。切片内无有效调用时 available=false，徽标不渲染。 */
export function priorPeriodAggregate(daily, period = 'month', today = '') {
  if (period === 'month') return null
  const days = Array.isArray(daily) ? daily.filter(day => day && day.date && (!today || day.date <= today)) : []
  if (!days.length) return null
  const index = days.length
  const slice = period === 'today' ? days.slice(-2, -1) : days.slice(Math.max(0, index - 14), Math.max(0, index - 7))
  if (!slice.length) return null
  const calls = sumField(slice, 'calls'), successes = sumField(slice, 'successes'), failures = sumField(slice, 'failures')
  return {
    period, available: calls > 0, calls, successes, failures,
    pendingCalls: sumField(slice, 'pendingCalls'), unknownUsageCalls: sumField(slice, 'unknownUsageCalls'),
    knownTokens: sumField(slice, 'knownTokens'), inputTokens: sumField(slice, 'inputTokens'), outputTokens: sumField(slice, 'outputTokens'),
    successRate: successes + failures > 0 ? successes * 100 / (successes + failures) : null
  }
}

/* ── 环比变化（tremor KPI Card 的 delta badge 语义）────────────────────
   只对"上一等长周期"有完整已上报口径的指标给方向：任一端 null（未知）→ unknown，
   界面不渲染方向徽标也不猜百分比；上期为 0 且本期 > 0 → 'new'（新增消耗，无基数可比）。
   注意这是用量指标而非股价：增长本身无褒贬，方向色只表"升/降/新增"，不用红绿涨跌色。 */
export function periodDelta(current, previous) {
  // 显式 null 检查：Number(null)===0 会把"未知"误判成"上期为 0 的新增"
  const now = current == null ? NaN : Number(current)
  const before = previous == null ? NaN : Number(previous)
  if (!Number.isFinite(now) || !Number.isFinite(before)) return { direction: 'unknown', percent: null }
  if (before === 0) return now === 0 ? { direction: 'flat', percent: 0 } : { direction: 'new', percent: null }
  const change = (now - before) / before * 100
  return { direction: change > 0.05 ? 'up' : change < -0.05 ? 'down' : 'flat', percent: Math.abs(change) }
}

/* ── 模型消耗榜（tokscale 排行榜卡片 + codeburn 按工具分布）─────────────
   按已知 Token 降序；用量未知（null）排最后且不授徽章；share 为占全部模型已知总量的比例，
   全部未知时 share 均为 null（界面改示"用量未知"），不按零伪造占比。 */
export function modelLeaderboard(models) {
  const list = (Array.isArray(models) ? models : []).filter(item => item && item.modelName)
  const total = list.reduce((sum, item) => sum + countOf(item.knownTokens), 0)
  const rows = list.map(item => ({
    connectionId: item.connectionId,
    modelName: item.modelName,
    calls: countOf(item.calls),
    knownTokens: nullableOf(item.knownTokens),
    inputTokens: nullableOf(item.inputTokens),
    outputTokens: nullableOf(item.outputTokens),
    share: null, badge: null, rank: 0
  })).sort((a, b) => (b.knownTokens ?? -1) - (a.knownTokens ?? -1) || b.calls - a.calls)
  rows.forEach((row, index) => {
    row.rank = index + 1
    if (total > 0 && row.knownTokens != null) {
      row.share = row.knownTokens / total
      if (index < 3) row.badge = ['gold', 'silver', 'bronze'][index]
    }
  })
  return { total, rows }
}
