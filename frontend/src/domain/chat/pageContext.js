/**
 * 页面上下文（只读参考信息，非指令）。
 *
 * 从当前路由提取「路径 + 栏目」两个字符串字段，随 AI 聊天请求上报，
 * 供助手回答"当前巡检状态如何 / 这个页面是什么"类问题时参考。
 * 硬性约束：绝不读取或拼接任何页面 DOM 内容，仅取路由元信息。
 */

// 控制字符不允许进入上下文；单字段限长 200，与 ai-service 校验规则对齐。
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/g
const MAX_FIELD_LENGTH = 200

function cleanField(value) {
  return String(value ?? '').replace(CONTROL_CHARS, '').trim().slice(0, MAX_FIELD_LENGTH)
}

/**
 * 从 vue-router 的 route 对象构造页面上下文。
 * @param {{ path?: string, name?: string | symbol | null, meta?: Record<string, unknown> }} route
 * @returns {{ path: string, section: string } | null} 仅当栏目非空时返回对象，否则返回 null（不随请求发送，避免噪音）。
 */
export function buildPageContext(route) {
  if (!route || typeof route.path !== 'string') return null
  const meta = route.meta || {}
  // 栏目优先级：meta.section > meta.title > 路由名；均为空时不发送上下文。
  const section = cleanField(meta.section ?? meta.title ?? route.name ?? '')
  if (!section) return null
  return { path: cleanField(route.path), section }
}

export default buildPageContext
