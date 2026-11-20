/**
 * 页面上下文（只读参考信息，非指令）。
 *
 * W5 起除「路径 + 栏目」外，还可携带本页实体（entity）与白名单只读摘要（snapshot）：
 * 侧翼组件据此"带着本页实体来问"，让 Agent 回答针对当前告警/事件/设备等对象。
 * 硬性约束：绝不读取或拼接任何页面 DOM 内容，仅接受调用方显式传入的结构化字段。
 */

// 控制字符不允许进入上下文；单字段限长 200，与 ai-service 校验规则对齐。
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/g
const MAX_FIELD_LENGTH = 200
// snapshot 是白名单只读摘要：限制键数量与单值长度，禁止整页 DOM 或大对象灌入。
const MAX_SNAPSHOT_KEYS = 20
const MAX_SNAPSHOT_VALUE = 300

// 与方案 §5.3 约定的实体类型；未知类型直接丢弃，避免把任意字符串当实体上报。
export const ENTITY_TYPES = Object.freeze([
  'alert',
  'event',
  'finding',
  'device',
  'doc',
  'incident',
  'server',
  'connection',
  'diagnostic',
])

function cleanField(value) {
  return String(value ?? '').replace(CONTROL_CHARS, '').trim().slice(0, MAX_FIELD_LENGTH)
}

/** 白名单化实体：只保留 { type, id }，类型不在白名单或 id 为空时返回 null。 */
export function cleanEntity(entity) {
  if (!entity || typeof entity !== 'object') return null
  const type = cleanField(entity.type).toLowerCase()
  const id = cleanField(entity.id)
  if (!type || !id || !ENTITY_TYPES.includes(type)) return null
  return { type, id }
}

/** 白名单化摘要：仅接受字符串/数字/布尔值，限键数与单值长度；无有效项返回 null。 */
export function cleanSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) return null
  const result = {}
  let count = 0
  for (const [rawKey, rawValue] of Object.entries(snapshot)) {
    if (count >= MAX_SNAPSHOT_KEYS) break
    const key = cleanField(rawKey)
    if (!key || rawValue == null) continue
    let value
    if (typeof rawValue === 'string') {
      value = String(rawValue).replace(CONTROL_CHARS, '').trim().slice(0, MAX_SNAPSHOT_VALUE)
    } else if (typeof rawValue === 'number' || typeof rawValue === 'boolean') value = rawValue
    else continue
    if (value === '') continue
    result[key] = value
    count += 1
  }
  return Object.keys(result).length ? result : null
}

/**
 * 从 vue-router 的 route 对象构造页面上下文。
 * @param {{ path?: string, name?: string | symbol | null, meta?: Record<string, unknown> }} route
 * @param {{ entity?: { type: string, id: string } | null, snapshot?: Record<string, unknown> | null, section?: string }} [extra]
 *        侧翼组件显式传入的本页实体、只读摘要与栏目覆盖；缺省时行为与旧版一致（仅 path/section）。
 * @returns {{ path: string, section: string, entity?: object, snapshot?: object } | null}
 *          仅当栏目非空时返回对象，否则返回 null（不随请求发送，避免噪音）。
 */
export function buildPageContext(route, extra = {}) {
  if (!route || typeof route.path !== 'string') return null
  const meta = route.meta || {}
  // 栏目优先级：显式覆盖 > meta.section > meta.title > 路由名；均为空时不发送上下文。
  const section = cleanField(extra.section ?? meta.section ?? meta.title ?? route.name ?? '')
  if (!section) return null
  const context = { path: cleanField(route.path), section }
  const entity = cleanEntity(extra.entity)
  if (entity) context.entity = entity
  const snapshot = cleanSnapshot(extra.snapshot)
  if (snapshot) context.snapshot = snapshot
  return context
}

export default buildPageContext
