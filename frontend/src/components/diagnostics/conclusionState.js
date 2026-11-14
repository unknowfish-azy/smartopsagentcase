/* 结论带（ConclusionBar）的纯函数逻辑模块。
 *
 * 设计上让 Vue 组件直接复用这些函数，测试也复用同一份实现 ——
 * 避免对 SFC 模板字符串做脆弱的 regex 断言。
 */
import { FIVE_MINUTES_MS } from './healthState.js'

// ---- verdict 文案（设计 §结论带：按 count 优先级生成）----
// 优先级：action > config > unknown > pass
export function verdictText(counts) {
  const c = counts || {}
  const action = c.action || 0
  const config = c.config || 0
  const unknown = c.unknown || 0
  const pass = c.pass || 0
  const total = action + config + unknown + pass

  if (total === 0) return '尚未检查 · 没有证据'
  if (action) return `${action} 项需要处理`
  if (config) return `${config} 项等待配置`
  if (unknown) return `${unknown} 项缺少证据`
  return `全部通过 · ${pass} 项检查`
}

export function verdictLevel(counts) {
  const c = counts || {}
  if ((c.action || 0) > 0) return 'action'
  if ((c.config || 0) > 0) return 'config'
  if ((c.unknown || 0) > 0) return 'unknown'
  if (((c.action || 0) + (c.config || 0) + (c.unknown || 0) + (c.pass || 0)) > 0) return 'pass'
  return 'empty'
}

// 新鲜度相关（§5 过期降饱和）
export function freshInfo({ checkedAt, now, stale }) {
  const ms = (() => {
    if (checkedAt == null) return 0
    if (typeof checkedAt === 'number') return checkedAt
    const parsed = Date.parse(checkedAt)
    return Number.isFinite(parsed) ? parsed : 0
  })()
  const n = now ?? Date.now()
  const remainMs = Math.max(0, FIVE_MINUTES_MS - (n - ms))
  const fresh = remainMs > 0 && !stale
  const ringDeg = Math.round(remainMs / FIVE_MINUTES_MS * 360)
  const ringText = fresh ? `${Math.ceil(remainMs / 60000)}′` : '过期'
  const ringColorToken = fresh ? '--ds-semantic-info' : '--ds-semantic-warning'

  const fmtAgo = ageMs => {
    const m = Math.round(ageMs / 60000)
    if (m < 1) return '刚刚'
    if (m < 60) return `${m} 分钟前`
    return `${Math.round(m / 60)} 小时前`
  }

  const absolute = ms > 0 ? new Date(ms).toLocaleString('zh-CN') : null
  const ageMs = ms > 0 ? (n - ms) : 0
  const tooltip = (() => {
    if (!ms) return '尚未执行检查'
    const suffix = stale
      ? ` · 已过期 ${Math.max(1, Math.round((ageMs - FIVE_MINUTES_MS) / 60000))} 分钟`
      : remainMs >= 60_000
        ? ` · ${Math.round(remainMs / 60000)} 分钟后过期`
        : ' · 即将过期'
    return `最近获取 ${absolute}${suffix}`
  })()

  const label = (() => {
    if (!ms) return '尚未检查'
    return `最近 ${fmtAgo(ageMs)}获取 · 5 分钟内有效`
  })()

  return { ringDeg, ringText, ringColorToken, tooltip, label, absolute }
}
