import assert from 'node:assert/strict'
import test from 'node:test'
import { parseTokenBudget, budgetState, formatMetric, validMonth, quotaRingState, periodAggregate, priorPeriodAggregate, periodDelta, usagePace, modelLeaderboard, daysInMonth } from '../src/components/model/modelAnalytics.js'

test('budgets accept zero and blank, reject fractional, negative and unsafe values', () => {
  assert.equal(parseTokenBudget(''), null)
  assert.equal(parseTokenBudget('0'), 0)
  assert.equal(parseTokenBudget('1000000'), 1000000)
  for (const value of ['-1', '1.5', '1e6', 'abc', '1000000000001']) {
    assert.throws(() => parseTokenBudget(value))
  }
})
test('budget progress keeps overages and unknown usage explicit', () => {
  assert.deepEqual(budgetState(null, 20), { percent: 0, remaining: null, overage: 0 })
  assert.deepEqual(budgetState(0, 20), { percent: 100, remaining: 0, overage: 20 })
  assert.deepEqual(budgetState(100, 120), { percent: 100, remaining: 0, overage: 20 })
  assert.deepEqual(budgetState(100, 20), { percent: 20, remaining: 80, overage: 0 })
  assert.equal(formatMetric(null), '—')
  assert.equal(formatMetric(0), '0')
  assert.equal(validMonth('2026-09'), true)
  for (const month of ['', '2026-13', '26-09', '1999-09']) assert.equal(validMonth(month), false)
})
test('quota ring derives health level from usage share', () => {
  // 无额度：level=none，不渲染环形（父级 v-if 兜底）
  assert.deepEqual(quotaRingState(null, 20), { percent: 0, remaining: null, overage: 0, level: 'none', hasBudget: false })
  // healthy：30% 已用
  assert.equal(quotaRingState(100, 30).level, 'healthy')
  assert.equal(quotaRingState(100, 30).percent, 30)
  // warning：≥70%
  assert.equal(quotaRingState(100, 70).level, 'warning')
  assert.equal(quotaRingState(100, 89).level, 'warning')
  // critical：≥90%
  assert.equal(quotaRingState(100, 90).level, 'critical')
  assert.equal(quotaRingState(100, 99).level, 'critical')
  // exceeded：超额优先于百分比档位
  assert.equal(quotaRingState(100, 120).level, 'exceeded')
  assert.equal(quotaRingState(100, 120).overage, 20)
  // 额度为 0 且有用量：画满整圈 + exceeded
  assert.equal(quotaRingState(0, 5).level, 'exceeded')
  assert.equal(quotaRingState(0, 5).percent, 100)
})

const day = (date, over = {}) => ({ date, calls: 1, successes: 1, failures: 0, pendingCalls: 0, unknownUsageCalls: 0, knownTokens: 100, inputTokens: 60, outputTokens: 40, successRate: 100, averageLatencyMs: 800, ...over })
const dailyFixture = [
  day('2026-10-10', { calls: 5, successes: 4, failures: 1, unknownUsageCalls: 1, knownTokens: 1000, inputTokens: 600, outputTokens: 400, successRate: 80 }),
  day('2026-10-11', { calls: 3, successes: 3, knownTokens: null, inputTokens: null, outputTokens: null }),
  day('2026-10-18', { calls: 2, successes: 1, failures: 1, knownTokens: 300, inputTokens: 200, outputTokens: 100, successRate: 50 }),
  day('2026-10-20', { calls: 9, successes: 9, knownTokens: 9000, inputTokens: 5000, outputTokens: 4000 })
]
const summaryFixture = { calls: 19, successes: 17, failures: 2, pendingCalls: 0, unknownUsageCalls: 1, knownTokens: 10300, inputTokens: 5800, outputTokens: 4500, successRate: 89.47, averageLatencyMs: 810 }

test('period aggregate slices today / last 7 days / month with unknown usage kept explicit', () => {
  // 本月：直接采用 summary（后端权威口径）
  const month = periodAggregate(dailyFixture, summaryFixture, 'month', '2026-10-18')
  assert.equal(month.available, true)
  assert.equal(month.knownTokens, 10300)
  assert.equal(month.successRate, 17 / 19 * 100)
  // 今日：只取当天；未来日与 null 不参与
  const today = periodAggregate(dailyFixture, summaryFixture, 'today', '2026-10-18')
  assert.equal(today.available, true)
  assert.equal(today.calls, 2)
  assert.equal(today.knownTokens, 300)
  assert.equal(today.successRate, 50)
  // 今日无数据（查过去的月份或当天无调用）
  assert.equal(periodAggregate(dailyFixture, summaryFixture, 'today', '2026-10-15').available, false)
  assert.equal(periodAggregate([day('2026-10-18', { calls: 0 })], null, 'today', '2026-10-18').available, false)
  // 近 7 天：date ≤ today 的最后 7 天，10-20 是未来日被排除；10-11 全 null 不计入已知
  const week = periodAggregate(dailyFixture, summaryFixture, 'week', '2026-10-18')
  assert.equal(week.calls, 10)
  assert.equal(week.knownTokens, 1300)
  assert.equal(week.successRate, 8 / 10 * 100)
  // 空 daily / 空 summary 不炸
  assert.equal(periodAggregate([], summaryFixture, 'week', '2026-10-18').available, false)
  assert.equal(periodAggregate(dailyFixture, null, 'month').knownTokens, null)
})

test('usage pace projects month-end spend linearly and dates the budget line', () => {
  // 10 月 18 日：已过 18 天，用量 28,410 → 日均 1,578.3，预计全月 48,928（额度 163.1%），10-20 触额
  const pace = usagePace(30000, 28410, '2026-10', '2026-10-18')
  assert.equal(pace.daysInMonth, 31)
  assert.equal(pace.daysElapsed, 18)
  assert.equal(pace.dailyRate, 28410 / 18)
  assert.equal(pace.projected, 28410 / 18 * 31)
  assert.equal(pace.pacePercent, 28410 / 18 * 31 / 30000 * 100)
  assert.equal(pace.exhaustDate, '2026-10-20')
  assert.equal(pace.remaining, 1590)
  // 节奏慢于额度：有速率、无触额日
  const slow = usagePace(30000, 15780, '2026-10', '2026-10-18')
  assert.equal(slow.exhaustDate, null)
  assert.ok(slow.pacePercent < 100)
  assert.equal(slow.remaining, 14220)
  // 无额度：仍给速率与预计，但不给占比/触额/剩余
  const noLimit = usagePace(null, 500, '2026-10', '2026-10-18')
  assert.equal(noLimit.pacePercent, null)
  assert.equal(noLimit.exhaustDate, null)
  assert.equal(noLimit.remaining, null)
  assert.equal(noLimit.projected, 500 / 18 * 31)
  // 过去的月份：已过去天数夹取到当月全长（月末视角）
  const past = usagePace(30000, 900, '2026-09', '2026-10-18')
  assert.equal(past.daysElapsed, 30)
  assert.equal(past.dailyRate, 30)
  // 未来的月份：已过去天数为 0，不猜速率
  const future = usagePace(30000, 0, '2026-11', '2026-10-18')
  assert.equal(future.daysElapsed, 0)
  assert.equal(future.dailyRate, null)
  // 额度为 0：占比恒 null（界面另走超额文案），不产出 Infinity
  assert.equal(usagePace(0, 120, '2026-10', '2026-10-18').pacePercent, null)
  assert.equal(usagePace(0, 120, '2026-10', '2026-10-18').overage, 120)
})

test('days in month handles leap years and invalid input', () => {
  assert.equal(daysInMonth('2026-10'), 31)
  assert.equal(daysInMonth('2026-09'), 30)
  assert.equal(daysInMonth('2026-02'), 28)
  assert.equal(daysInMonth('2028-02'), 29)
  assert.equal(daysInMonth(''), 0)
  assert.equal(daysInMonth('2026-13'), 0)
})

test('model leaderboard ranks by known tokens with badges and honest nulls', () => {
  const { total, rows } = modelLeaderboard([
    { connectionId: 2, modelName: 'lite-helper', calls: 5, knownTokens: 12000, inputTokens: 8000, outputTokens: 4000 },
    { connectionId: 1, modelName: 'ops-reasoner', calls: 12, knownTokens: 28410, inputTokens: 18000, outputTokens: 10410 },
    { connectionId: 3, modelName: 'ghost-model', calls: 4, knownTokens: null }
  ])
  assert.equal(total, 40410)
  assert.deepEqual(rows.map(row => [row.rank, row.modelName, row.badge]), [[1, 'ops-reasoner', 'gold'], [2, 'lite-helper', 'silver'], [3, 'ghost-model', null]])
  assert.equal(rows[0].share, 28410 / 40410)
  // 用量未知排最后、无徽章、share 为 null（不按零伪造占比）
  assert.equal(rows[2].share, null)
  // 全部未知：total 为 0 时一律无占比
  const blank = modelLeaderboard([{ connectionId: 9, modelName: 'x', calls: 1, knownTokens: null }])
  assert.equal(blank.total, 0)
  assert.equal(blank.rows[0].share, null)
  assert.equal(blank.rows[0].badge, null)
})

test('prior period aggregate slices the previous equal-length window', () => {
  // month 档：接口只给当月 summary，不跨月拼凑 → null（界面不给环比徽标）
  assert.equal(priorPeriodAggregate(dailyFixture, 'month', '2026-10-18'), null)
  // 15 天连续 fixture（10-04 ~ 10-18，knownTokens = 100×(序号)）：与 periodAggregate 的 week 切片对称
  const twoWeek = Array.from({ length: 15 }, (_, index) => day(`2026-10-${String(4 + index).padStart(2, '0')}`, { knownTokens: (index + 1) * 100, inputTokens: 60, outputTokens: 40 }))
  // week 近窗 = 倒数 7 条（序号 9–15 → 8400），prior = 倒数第 8–14 条（序号 2–8 → 3500）
  assert.equal(periodAggregate(twoWeek, null, 'week', '2026-10-18').knownTokens, 8400)
  const priorWeek = priorPeriodAggregate(twoWeek, 'week', '2026-10-18')
  assert.equal(priorWeek.available, true)
  assert.equal(priorWeek.knownTokens, 3500)
  // today 档：昨日一天（序号 14 → 1400）
  const priorToday = priorPeriodAggregate(twoWeek, 'today', '2026-10-18')
  assert.equal(priorToday.available, true)
  assert.equal(priorToday.knownTokens, 1400)
  // 窗口内全部用量未知：available=true 但 knownTokens=null（界面据此不给徽标）
  const nullYesterday = priorPeriodAggregate([day('2026-10-17', { knownTokens: null }), day('2026-10-18')], 'today', '2026-10-18')
  assert.equal(nullYesterday.available, true)
  assert.equal(nullYesterday.knownTokens, null)
  // 记录不足两个窗口 / 无昨日记录 / 空与非数组：一律 null，不猜环比
  assert.equal(priorPeriodAggregate(dailyFixture, 'week', '2026-10-18'), null)
  assert.equal(priorPeriodAggregate([day('2026-10-18')], 'today', '2026-10-18'), null)
  assert.equal(priorPeriodAggregate([], 'week', '2026-10-18'), null)
  assert.equal(priorPeriodAggregate(null, 'today', '2026-10-18'), null)
})

test('period delta gives honest directions without guessing unknowns', () => {
  // 增长：percent 取绝对值，方向由 direction 表意（用量无褒贬，不用红绿）
  assert.deepEqual(periodDelta(1200, 1000), { direction: 'up', percent: 20 })
  // 下降
  assert.deepEqual(periodDelta(800, 1000), { direction: 'down', percent: 20 })
  // 持平（±0.05% 内）
  assert.equal(periodDelta(1000, 1000).direction, 'flat')
  assert.equal(periodDelta(1000.01, 1000).direction, 'flat')
  // 上期为 0 且本期 > 0：新增消耗，无基数可比 → percent null
  assert.deepEqual(periodDelta(500, 0), { direction: 'new', percent: null })
  // 两端皆 0：持平
  assert.equal(periodDelta(0, 0).direction, 'flat')
  // 任一端未知（null/undefined/非数字）：不猜方向——Number(null)===0 的坑必须显式挡住
  assert.equal(periodDelta(null, 1000).direction, 'unknown')
  assert.equal(periodDelta(1000, null).direction, 'unknown')
  assert.equal(periodDelta(undefined, 1000).direction, 'unknown')
  assert.equal(periodDelta('abc', 1000).direction, 'unknown')
})
