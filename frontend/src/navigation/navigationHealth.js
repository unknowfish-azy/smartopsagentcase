// 菜单健康徽章的派生逻辑：把伴生存储（companion store）的能力状态与活动故障
// 映射为导航分组上的状态点。纯函数、无框架依赖，供组件与单元测试共用。
//
// 数据源约定（与 stores/companion.js 对齐）：
//   capabilities[name].status ∈ capabilityStatuses（available / degraded / offline）
//   activeFault：investigation.activeContext?.faultEvent（有活动故障时为真值）
//
// 严重度排序：alert > offline > degraded > ready。

export const NAV_HEALTH_LEVELS = Object.freeze(['ready', 'degraded', 'alert', 'offline'])

const SEVERITY = Object.freeze({ ready: 1, degraded: 2, offline: 3, alert: 4 })

export const NAV_HEALTH_LABELS = Object.freeze({
  ready: '运行正常',
  degraded: '部分能力降级',
  alert: '存在活动告警',
  offline: '信号未接入'
})

// 分组 → 观测的能力信号键（不存在于本表的分组不显示徽章）。
const GROUP_SIGNALS = Object.freeze({
  sentinel: Object.freeze(['telemetry', 'ai']),
  health: Object.freeze(['telemetry'])
})

function worstLevel(levels) {
  return levels.reduce((worst, level) => (
    level && NAV_HEALTH_LEVELS.includes(level) && (!worst || SEVERITY[level] > SEVERITY[worst]) ? level : worst
  ), null)
}

/**
 * 单个导航分组的健康等级；无信号配置的分组返回 null（不渲染徽章）。
 * 能力键缺失按 offline 处理——未接入与显式 offline 对用户是同一语义。
 */
export function navHealthLevelForGroup(groupId, snapshot = {}) {
  const signals = GROUP_SIGNALS[groupId]
  if (!signals) return null
  const capabilities = snapshot.capabilities || {}
  const levels = signals.map(name => {
    const status = capabilities[name]?.status
    if (!status) return 'offline'
    return status === 'available' ? 'ready' : NAV_HEALTH_LEVELS.includes(status) ? status : 'offline'
  })
  if (snapshot.activeFault) levels.push('alert')
  return worstLevel(levels) || 'ready'
}

/** 批量派生 { groupId: level }，供侧栏一次性下发。 */
export function navHealthBadgeMap(groups = [], snapshot = {}) {
  const badges = {}
  for (const group of groups) {
    const level = navHealthLevelForGroup(group.id, snapshot)
    if (level) badges[group.id] = level
  }
  return badges
}

/** 徽章悬浮/读屏文案，如「哨兵与自动化 / SENTINEL · 存在活动告警」。 */
export function navHealthBadgeTitle(group, level) {
  const label = NAV_HEALTH_LABELS[level] || NAV_HEALTH_LABELS.offline
  const name = group?.cn ? `${group.cn} / ${group.label || ''}`.replace(/ \/$/, '') : ''
  return name ? `${name} · ${label}` : label
}
