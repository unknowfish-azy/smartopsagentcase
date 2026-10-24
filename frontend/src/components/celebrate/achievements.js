// 里程碑推导：只从真实调用账本计算，证据优先（未知不猜、不按零伪造）。
// 界面侧（AchievementsView / ModelAnalyticsView 入口芯片）消费这里的纯函数结果。
import { milestoneProgress } from '../effects/milestoneRain.js'

export const CALL_TIERS = [100, 500, 1000, 5000, 10000]
export const TOKEN_TIERS = [10000, 100000, 1000000]

const num = value => (typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null)
const fmtTier = value => (value >= 10000 ? `${value / 10000} 万` : value.toLocaleString('zh-CN'))

function tiered(idPrefix, titlePrefix, value, thresholds, valueText, basis, window) {
  return thresholds.map(threshold => ({
    id: `${idPrefix}-${threshold}`,
    kind: 'tier',
    title: `${titlePrefix} · ${fmtTier(threshold)}`,
    threshold,
    thresholdText: fmtTier(threshold),
    unlocked: value != null && value >= threshold,
    progress: value == null ? 0 : Math.min(1, value / threshold),
    valueText,
    basis,
    window
  }))
}

export function buildAchievements(report) {
  const summary = report?.summary || {}
  const month = report?.month || ''
  const calls = num(summary.calls)
  const knownTokens = num(summary.knownTokens)
  const successRate = num(summary.successRate)
  const pending = num(summary.pendingCalls)
  const unknown = num(summary.unknownUsageCalls)
  const window = month || '未知月份'

  const list = [
    ...tiered(
      'calls', '本月累计调用', calls, CALL_TIERS,
      calls == null ? '—' : calls.toLocaleString('zh-CN'),
      '口径：调用账本全部状态（含失败与待确认），按 UTC 自然月汇总', window
    ),
    ...tiered(
      'tokens', '本月已知 Token 消耗', knownTokens, TOKEN_TIERS,
      knownTokens == null ? '—' : knownTokens.toLocaleString('zh-CN'),
      '口径：仅服务商已上报值；用量未知的调用不计入，不按零补齐', window
    ),
    {
      id: 'stable-month',
      kind: 'quality',
      title: '高稳定月',
      thresholdText: '成功率 ≥ 95% 且调用 ≥ 100 次',
      unlocked: successRate != null && successRate >= 95 && calls != null && calls >= 100,
      // 双条件成就：进度取约束更紧的一侧，不猜平均
      progress: Math.min(
        successRate == null ? 0 : Math.min(1, successRate / 95),
        calls == null ? 0 : Math.min(1, calls / 100)
      ),
      valueText: successRate == null ? '成功率未知' : `成功率 ${successRate.toFixed(1)}%`,
      basis: '口径：有效回复 / 已完成调用；样本量、网络与任务长度都会影响结果',
      window
    },
    {
      id: 'zero-pending',
      kind: 'quality',
      title: '零待确认',
      thresholdText: '当月无处理中调用',
      unlocked: calls != null && calls > 0 && pending === 0,
      progress: calls != null && calls > 0 && pending != null ? Math.max(0, 1 - pending / calls) : 0,
      valueText: pending == null ? '待确认未知' : `${pending.toLocaleString('zh-CN')} 次待确认`,
      basis: '口径：处理中或最终结果尚未写入账本的调用数',
      window
    },
    {
      id: 'fully-metered',
      kind: 'quality',
      title: '全量可计量',
      thresholdText: '当月无用量未知调用',
      unlocked: calls != null && calls > 0 && unknown === 0,
      progress: calls != null && calls > 0 && unknown != null ? Math.max(0, 1 - unknown / calls) : 0,
      valueText: unknown == null ? '用量未知数未知' : `${unknown.toLocaleString('zh-CN')} 次用量未知`,
      basis: '口径：服务商未上报用量的调用数；这类调用不参与 Token 类统计',
      window
    }
  ]

  // 下一档：第一个未达成项（供界面高亮；全部达成时为 null）
  const next = list.find(item => !item.unlocked)
  for (const item of list) item.isNext = item === next
  return list
}

// 演示实例：固定样例卡片，只用于展示三种卡片状态（已达成 / 进行中 / 未解锁）的视觉样式，
// 并给独立滚动容器提供可滚动内容。硬性隔离：demo=true → 不参与任何统计、不进下一档推导、
// 不挂庆祝按钮；界面以虚线框 + 「演示」芯片 + 分隔带标注，绝不与真实账本混淆。
export const DEMO_ACHIEVEMENTS = Object.freeze([
  {
    id: 'demo-calls-unlocked',
    kind: 'demo',
    demo: true,
    title: '演示 · 累计调用 12,000',
    threshold: 10000,
    thresholdText: '1 万',
    unlocked: true,
    isNext: false,
    progress: 1,
    valueText: '12,000',
    basis: '演示数据：仅展示已达成状态的视觉样式，不来自调用账本',
    window: '演示'
  },
  {
    id: 'demo-tokens-running',
    kind: 'demo',
    demo: true,
    title: '演示 · Token 消耗 46 万',
    threshold: 1000000,
    thresholdText: '100 万',
    unlocked: false,
    isNext: false,
    progress: 0.46,
    valueText: '460,000',
    basis: '演示数据：仅展示进行中状态的视觉样式，不来自调用账本',
    window: '演示'
  },
  {
    id: 'demo-stable-locked',
    kind: 'demo',
    demo: true,
    title: '演示 · 高稳定月',
    threshold: null,
    thresholdText: '成功率 ≥ 95% 且调用 ≥ 100 次',
    unlocked: false,
    isNext: false,
    progress: 0.92,
    valueText: '成功率 91.0%',
    basis: '演示数据：仅展示未解锁状态的视觉样式，不来自调用账本',
    window: '演示'
  }
])

// TokenUsage 入口芯片用：已达到的最高 calls 档位；未达最低档返回 null（不炫耀）
export function callMilestoneReached(calls) {
  return milestoneProgress(calls, CALL_TIERS).reached
}
