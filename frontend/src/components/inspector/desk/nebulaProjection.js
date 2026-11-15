/**
 * nebulaProjection.js — 星云投影纯函数层（T32）
 *
 * 职责：把纠察事件列表映射为球面粒子（纬度=等级环带，经度=时间窗比例），
 *       并提供手写旋转矩阵 + 透视除法的 2D 投影与画家算法深度排序。
 *
 * 设计约束（见 docs/design/inspector-nebula-projection-v1/DESIGN.md）：
 *   - 纯函数、零 DOM 依赖，可直接单测；
 *   - 粒子上限 1000，超出按索引均匀抽样（确定性），如实返回 sampled/total；
 *   - 不引 three.js：投影数学全部手写。
 */
import { SEVERITIES } from './deskModel.js'

/** 粒子上限：超出后均匀抽样并在脚注标注 */
export const NEBULA_CAP = 1000

/** 掉帧降采样档位 1000 → 500 → 250 */
export const NEBULA_DOWNSAMPLE = Object.freeze([1000, 500, 250])

/**
 * 等级 → 纬度环带（弧度）。PASS 赤道 → CRITICAL 北极圈，与平面时间轴 Y 轨道同构。
 * 每条环带带内抖动 ±BAND_HALF，四带区间互不相交。
 */
export const PHI_BANDS = Object.freeze({
  PASS: 0.1,
  WARN: 0.48,
  HIGH: 0.86,
  CRITICAL: 1.24
})
const BAND_HALF = 0.12

/** 等级 → 粒子基础尺寸（严重更大；视觉调校：半径放大 ~40% 保证投影仪/录屏下可见） */
const SIZE_BY_SEVERITY = { PASS: 2.2, WARN: 2.6, HIGH: 3.0, CRITICAL: 3.6 }

/** 维度八色带（hover「色环扫描」重着色用；色值取自代码库既有令牌色系） */
export const DIMENSION_COLORS = Object.freeze({
  behavior: '#2496ed',
  evidence: '#7ad7f5',
  tool: '#3fb950',
  risk: '#f0883e',
  approval: '#d29922',
  verification: '#58a6ff',
  knowledge: '#a383a6',
  security: '#f85149'
})

export function severityColorOf(severity) {
  return severityMetaSafe(severity).color
}

function severityMetaSafe(severity) {
  return SEVERITIES.find(s => s.key === severity) || { cn: severity || '—', color: '#5d6b78' }
}

/** 确定性字符串散列 → [0,1)，用于环带内抖动，保证同 id 每次渲染位置一致 */
function hash01(str) {
  let h = 2166136261
  const s = String(str)
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) % 10000) / 10000
}

/**
 * buildNebula(events, range) → { particles, sampled, total, cap }
 * 粒子：{ id, severity, taskId, category, dimKey, at, theta, phi, size, age }
 *   - theta：经度 = createdAt 在窗口内的比例 × 2π（时间单调）
 *   - phi：纬度 = 等级环带中心 ± 确定性抖动
 *   - age：0 = 最新（最亮）→ 1 = 最旧（最暗）
 */
export function buildNebula(events, range, cap = NEBULA_CAP) {
  const list = Array.isArray(events) ? events : []
  const start = range?.start ?? 0
  const end = range?.end ?? 0
  const span = Math.max(1, end - start)

  const inWindow = list
    .filter(e => e && e.at >= start && e.at <= end)
    .sort((a, b) => a.at - b.at || String(a.id).localeCompare(String(b.id)))

  const total = inWindow.length
  const limit = typeof cap === 'number' && cap > 0 ? Math.min(cap, NEBULA_CAP) : NEBULA_CAP
  const sampled = total > limit
  const source = sampled ? downsample(inWindow, limit) : inWindow

  const particles = source.map(event => {
    const frac = Math.min(1, Math.max(0, (event.at - start) / span))
    const band = PHI_BANDS[event.severity] ?? PHI_BANDS.WARN
    return {
      id: event.id,
      severity: event.severity,
      taskId: event.taskId || 'unknown',
      category: event.category || null,
      dimKey: event.dimKey || dimensionKey(event),
      at: event.at,
      theta: frac * Math.PI * 2,
      phi: band + (hash01(event.id) * 2 - 1) * BAND_HALF,
      size: SIZE_BY_SEVERITY[event.severity] || 1.9,
      age: 1 - frac
    }
  })

  return { particles, sampled, total, cap: limit }
}

/** 按时间均匀抽样：等步长取索引，保留首尾 */
function downsample(sorted, limit) {
  if (sorted.length <= limit) return sorted
  const out = []
  const step = (sorted.length - 1) / (limit - 1)
  for (let i = 0; i < limit; i += 1) out.push(sorted[Math.round(i * step)])
  return out
}

function dimensionKey(event) {
  const category = String(event?.category || '').toUpperCase()
  if (!category) return ''
  const aliases = {
    behavior: ['AGENT_BEHAVIOR', 'BEHAVIOR', 'PLANNER', 'AGENT'],
    evidence: ['EVIDENCE_QUALITY', 'EVIDENCE'],
    tool: ['TOOL_USAGE', 'TOOL'],
    risk: ['RISK', 'OBSERVABILITY'],
    approval: ['APPROVAL', 'HITL'],
    verification: ['VERIFICATION', 'VERIFY'],
    knowledge: ['KNOWLEDGE', 'DATABASE'],
    security: ['SECURITY', 'STABILITY', 'CLOUD_NATIVE']
  }
  for (const [key, list] of Object.entries(aliases)) {
    if (list.includes(category)) return key
  }
  return ''
}

export function dimensionColorOf(dimKey, fallback) {
  return DIMENSION_COLORS[dimKey] || fallback
}

/**
 * project(particles, rotY, rotX, width, height, radius) →
 *   [{ p, x, y, scale, z }] 按 z 升序（远 → 近，画家算法先画远的）。
 * 手写旋转：先绕 Y 轴（自转），再绕 X 轴（俯仰），透视除法 scale = f/(f - z)。
 */
export function project(particles, rotY, rotX, width, height, radius) {
  const cx = width / 2
  const cy = height / 2
  const f = 2.4
  const cosY = Math.cos(rotY)
  const sinY = Math.sin(rotY)
  const cosX = Math.cos(rotX)
  const sinX = Math.sin(rotX)
  const R = radius ?? Math.min(width, height) * 0.36

  const out = particles.map(p => {
    // 球面坐标 → 直角坐标（phi 从赤道向北为正）
    const x0 = Math.cos(p.phi) * Math.cos(p.theta)
    const y0 = Math.sin(p.phi)
    const z0 = Math.cos(p.phi) * Math.sin(p.theta)
    // 绕 Y 轴
    const x1 = x0 * cosY + z0 * sinY
    const z1 = -x0 * sinY + z0 * cosY
    // 绕 X 轴
    const y1 = y0 * cosX - z1 * sinX
    const z2 = y0 * sinX + z1 * cosX
    const scale = f / (f - z2)
    return { p, z: z2, scale, x: cx + x1 * R * scale, y: cy - y1 * R * scale }
  })

  // 稳定排序：z 相同按原顺序（.map 保留原索引语义）
  return out
    .map((item, index) => ({ item, index }))
    .sort((a, b) => a.item.z - b.item.z || a.index - b.index)
    .map(entry => entry.item)
}

/**
 * flatPosition(p, width, height) → 切投影转场的平面出发点：
 * 与「纠察」视图同构——x 沿时间轴铺开，y 按等级泳道。
 */
export function flatPosition(p, width, height) {
  const padL = 56
  const padR = 16
  const padT = 16
  const padB = 36
  const lanes = SEVERITIES.length // 4
  const laneH = (height - padT - padB - 40) / lanes
  const laneIndex = SEVERITIES.findIndex(s => s.key === p.severity)
  return {
    x: padL + (p.theta / (Math.PI * 2)) * (width - padL - padR),
    y: padT + laneH * (laneIndex + 0.5)
  }
}

/** easeOutCubic：转场汇聚缓动 */
export function easeOutCubic(t) {
  const c = Math.min(1, Math.max(0, t))
  return 1 - Math.pow(1 - c, 3)
}
