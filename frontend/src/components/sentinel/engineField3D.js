/**
 * 引擎场 3D 的纯函数层：真实状态 → 视觉参数。
 * 铁律：任何动画强度必须能追到真实字段；无事件 / 未运行的节点一律静止。
 * 无 DOM / three 依赖，可独立单测。
 */

export const ENGINE_FIELD_IDS = Object.freeze([
  'sentinel-poll',
  'sentinel-guardian',
  'web-research',
  'inspector',
  'decision-loop',
  'operation-run'
])

/** 固定角度布局：同一 id 永远在同一位置，刷新不跳位。 */
export function engineNodeLayout(ids = ENGINE_FIELD_IDS, radius = 1.7) {
  const list = ids.length ? ids : ENGINE_FIELD_IDS
  return list.map((id, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / list.length
    return Object.freeze({ id, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius * 0.55, angle })
  })
}

/** 状态色：与 EngineObservabilityView.statusColor 同源语义，CSS 变量交由调用方解析。 */
export function engineVisualState(engine, nowSec = Date.now() / 1000) {
  const status = String(engine?.status || '').toUpperCase()
  const age = typeof engine?.ageSec === 'number' && Number.isFinite(engine.ageSec) ? Math.max(0, engine.ageSec) : null
  const period = typeof engine?.expectedPeriodSec === 'number' && engine.expectedPeriodSec > 0 ? engine.expectedPeriodSec : null
  const ratio = age != null && period ? age / period : null
  const animated = status === 'RUNNING' || status === 'STALLED' || status === 'ERROR'

  return Object.freeze({
    status,
    colorVar: status === 'RUNNING' ? '--ds-color-success'
      : status === 'STALLED' ? '--ds-semantic-warning'
        : status === 'ERROR' ? '--ds-semantic-danger'
          : '--ds-color-muted',
    /* 呼吸周期完全由 age/period 推导：新鲜 2.4s，越接近阈值越慢；超时后按倍数进一步放慢 */
    breathSec: status === 'RUNNING' && ratio != null
      ? 2.4 + Math.min(1, Math.max(0, ratio)) * 1.6
      : status === 'STALLED' && ratio != null
        ? 4 + Math.min(6, ratio) * 0.8
        : 0,
    glow: status === 'RUNNING' ? 0.85 : status === 'STALLED' ? 0.5 : status === 'ERROR' ? 0.35 : 0.12,
    /* 环上进度弧：只显示已过去的周期占比，到阈值封顶，不画满圈假装"完成" */
    progress: ratio == null ? 0 : Math.min(1, ratio),
    animated,
    outline: status === 'NOT_RUN' || status === 'NO_DATA',
    /* ERROR 只闪一次后稳态，不循环 */
    flashOnce: status === 'ERROR'
  })
}

/** 中心聚合：只读快照字段，不推算、不补充。 */
export function engineFieldCenter(engines, generatedAtText = '—') {
  const list = Array.isArray(engines) ? engines : []
  const live = list.filter(e => String(e?.status || '').toUpperCase() === 'RUNNING').length
  const quiet = list.filter(e => ['NO_DATA', 'NOT_RUN'].includes(String(e?.status || '').toUpperCase())).length
  return Object.freeze({ live, quiet, total: list.length, generatedAtText })
}
