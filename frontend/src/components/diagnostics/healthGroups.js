/* 健康诊断分组与排序（阶段 1）

   只提供纯函数：groupOf / severityRank / sortChecks / partitionChecks / kindLabel / statusVisual。
   不碰 DOM、不触发请求、不改 healthState.js 既有签名。
*/

// ---- 状态 → 语义组映射（§4 设计核心） ----
// 五种 Check.status 映射到五个语义组；诊断结果的 layer/check 也复用同一套组名。
export const STATUS_GROUP = Object.freeze({
  HEALTHY: 'pass',
  UNHEALTHY: 'action',
  UNCONFIGURED: 'config',
  NOT_CHECKED: 'unknown',
  FORBIDDEN: 'forbidden',
  // 诊断结果层/分项状态（可能出现在 DiagnosisResultPanel，不在 Check 列表里）
  UNVERIFIED: 'unknown',
  BLOCKED: 'config',
  TIMEOUT: 'action'
})

// 固定分组顺序：action → config → unknown → pass → forbidden
export const GROUP_ORDER = Object.freeze(['action', 'config', 'unknown', 'pass', 'forbidden'])

export const GROUP_META = Object.freeze({
  action: { title: '需要处理', hint: '先看这里，通常意味着真实故障', urgent: true, colorToken: '--ds-semantic-danger' },
  config: { title: '需要配置', hint: '你还没给它条件，不是它坏了', urgent: true, colorToken: '--ds-semantic-warning' },
  unknown: { title: '缺证据', hint: '没有证据不等于正常', urgent: false, colorToken: '--ds-semantic-neutral' },
  pass: { title: '通过', hint: '默认折叠', urgent: false, colorToken: '--ds-semantic-success' },
  forbidden: { title: '无权查看', hint: '需要更高权限才能查看此项', urgent: false, colorToken: '--ds-semantic-neutral' }
})

// 每个语义组的形状+图标+文字（§4 表，形状是 a11y 的核心）
export const STATUS_VISUAL = Object.freeze({
  action:    { cls: 'unhealthy',    icon: '✕',  label: '异常',     shape: 'solid' },
  config:    { cls: 'unconfigured',  icon: '!',   label: '未配置',   shape: 'solid' },
  unknown:   { cls: 'not_checked',   icon: '◌',   label: '未检查',   shape: 'dashed' },
  pass:      { cls: 'healthy',       icon: '✓',  label: '正常',     shape: 'solid' },
  forbidden: { cls: 'forbidden',     icon: '⌾',   label: '无权限',   shape: 'outline' }
})

// ---- Check.status → 组名 ----
export function groupOf(status) {
  if (!status) return 'unknown'
  return STATUS_GROUP[status] || 'unknown'
}

// ---- checkKind 硬度排名（§6.1：ACTIVE_PROBE 最硬 → 0） ----
const KIND_RANK = Object.freeze({ ACTIVE_PROBE: 0, LOCAL_CHECK: 1, CONFIGURATION: 2 })
export function severityRank(check) {
  return KIND_RANK[check?.checkKind] ?? 2
}

// ---- 组内排序：先按硬度升序（硬的排前），再按 durationMs 降序（慢的更可能是源头） ----
export function sortChecks(checks) {
  return [...checks].sort((a, b) => {
    const r = severityRank(a) - severityRank(b)
    if (r !== 0) return r
    return (b.durationMs || 0) - (a.durationMs || 0)
  })
}

// ---- 把 Check[] 按语义组分桶，FORBIDDEN 单独取出 ----
export function partitionChecks(checks) {
  const buckets = { action: [], config: [], unknown: [], pass: [] }
  const forbidden = []
  for (const check of checks || []) {
    const g = groupOf(check.status)
    if (g === 'forbidden') forbidden.push(check)
    else if (buckets[g]) buckets[g].push(check)
  }
  for (const key of Object.keys(buckets)) buckets[key] = sortChecks(buckets[key])
  return { buckets, forbidden }
}

// ---- checkKind 中文标签 + tooltip ----
export const KIND_META = Object.freeze({
  ACTIVE_PROBE: {
    label: '主动探测',
    icon: 'probe',
    tip: '真的连了一次下游，这是最硬的证据'
  },
  LOCAL_CHECK: {
    label: '本地检查',
    icon: 'shield',
    tip: '只证明请求链路活着，不证明下游服务本身是否健康'
  },
  CONFIGURATION: {
    label: '配置读取',
    icon: 'doc',
    tip: '只读了配置，没有建立连接'
  }
})

export function kindLabel(checkKind) {
  return KIND_META[checkKind] || { label: checkKind || '未知', icon: 'doc', tip: '未知检查类型' }
}

// ---- 检查状态 → 视觉元组（供 CheckRow 渲染） ----
export function statusVisual(status) {
  return STATUS_VISUAL[groupOf(status)] || STATUS_VISUAL.unknown
}

// ---- 计数聚合（供 ConclusionBar） ----
export function countByGroup(checks) {
  const counts = { action: 0, config: 0, unknown: 0, pass: 0, forbidden: 0 }
  for (const check of checks || []) {
    counts[groupOf(check.status)]++
  }
  return counts
}
