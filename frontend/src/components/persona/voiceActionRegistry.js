/**
 * 语音控屏：按钮级动作注册表。
 *
 * 设计原则：
 *  - **页面组件主动注册**：按钮的 handler 只存在于页面组件里，voice 侧不知道任何 DOM 细节。
 *    页面用 ``useVoiceActionBus().register(id, handler)`` 暴露；
 *  - **registry 集中声明关键词和危险等级**：本文件集中维护哪些按钮可被语音触发、
 *    它们属于哪个路由、危险程度如何；页面组件只需按 id 注册 handler；
 *  - **拦截先于执行**：命中意图后先查 hazard，critical 直接拦截，high/medium 要求二次确认，low 直接执行；
 *  - **单次只执行一个**：一条语音文本最多触发一个按钮动作，避免多意图同时触发。
 *
 * 路由名必须与 router/index.js 里的 ``name:`` 完全一致（大小写敏感）。
 */

export const VoiceActionBusSymbol = Symbol.for('voice-action-bus')

// ---------------------------------------------------------------------------
// 按钮意图注册表
// ---------------------------------------------------------------------------

/**
 * 每条：
 *  - id: 与页面组件注册时的 id 完全一致
 *  - keywords: 任意一个子串命中即匹配（不区分大小写）
 *  - routes: 路由名数组（宽松包含匹配）、'any' 或函数
 *  - hazard: 'critical' | 'high' | 'medium' | 'low'
 *  - confirm: hazard >= high 时的二次确认提示文案
 *  - label: 展示 / 播报用的人类可读名称
 */
export const VOICE_ACTIONS = Object.freeze([
  // ── Sentinel 告警中心 ──
  {
    id: 'sentinel.alerts.acknowledge',
    label: '确认选中的告警',
    keywords: ['确认告警', '确认这个告警', 'ack告警', 'ack一下', 'acknowledge', '标记告警已确认', '处理这个告警'],
    routes: ['AlertCenter'],
    hazard: 'high',
    confirm: '你希望我确认告警吗？请再说一次"确认告警"以复核。',
  },
  {
    id: 'sentinel.alerts.ignore',
    label: '忽略选中的告警',
    keywords: ['忽略告警', '忽略这个告警', 'ignore告警', '跳过这个告警', '标记告警为误报'],
    routes: ['AlertCenter'],
    hazard: 'high',
    confirm: '忽略告警可能掩盖真实故障，请再说一次"忽略告警"以复核。',
  },
  {
    id: 'sentinel.alerts.refresh',
    label: '刷新告警列表',
    keywords: ['刷新告警', '重新加载告警', 'refresh alerts'],
    routes: ['AlertCenter'],
    hazard: 'low',
  },

  // ── Sentinel 脚本库（critical —— 涉及执行运维脚本） ──
  {
    id: 'sentinel.scripts.refresh',
    label: '刷新脚本库',
    keywords: ['刷新脚本库', '重新加载脚本', '刷新scripts'],
    routes: ['ScriptLibrary'],
    hazard: 'low',
  },

  // ── 操作中心（连接 / 终端） ──
  {
    id: 'operations.snippets.run',
    label: '执行脚本片段',
    keywords: ['执行脚本', '运行脚本', 'run snippet', '执行命令'],
    routes: ['Connections', 'Tools', 'OperationRunHistory'],
    hazard: 'critical',
    confirm: '执行脚本会直接向终端发送命令，请手动在终端执行或再说一次"执行脚本"复核（高危操作）。',
  },
  {
    id: 'connections.refresh',
    label: '刷新连接列表',
    keywords: ['刷新连接', '刷新connection', '重新加载连接'],
    routes: ['Connections'],
    hazard: 'low',
  },
  {
    id: 'connections.close',
    label: '关闭当前连接',
    keywords: ['关闭连接', '关闭会话', 'close connection', '断开连接'],
    routes: ['Connections'],
    hazard: 'high',
    confirm: '关闭当前连接会中断运维会话，请再说一次"关闭连接"复核。',
  },

  // ── 服务器列表 ──
  {
    id: 'servers.refresh',
    label: '刷新服务器列表',
    keywords: ['刷新服务器', '重新加载服务器', '刷新server'],
    routes: ['ServerList'],
    hazard: 'low',
  },
  {
    id: 'servers.rescan',
    label: '重新扫描服务器',
    keywords: ['重新扫描', 'rescan', '扫描设备'],
    routes: ['ServerList'],
    hazard: 'medium',
    confirm: '重新扫描会触发一次设备探测，可能占用网络，请再说一次"重新扫描"确认。',
  },

  // ── 健康诊断 ──
  {
    id: 'health.refresh',
    label: '刷新健康状态',
    keywords: ['刷新健康', '重新检查健康', '健康诊断', 'health check'],
    routes: ['HealthCenter'],
    hazard: 'low',
  },
  {
    id: 'health.rerun',
    label: '重新跑诊断',
    keywords: ['重新诊断', 'rerun诊断', '跑一次诊断', '重新检查'],
    routes: ['HealthCenter'],
    hazard: 'medium',
    confirm: '重新诊断会触发后端检查流程，请再说一次"重新诊断"确认。',
  },

  // ── Chat（最常见，先做两个） ──
  {
    id: 'chat.clear',
    label: '清空当前对话',
    keywords: ['清空对话', '清空聊天', 'clear chat', '清空当前会话'],
    routes: ['Chat'],
    hazard: 'medium',
    confirm: '清空当前对话会移除所有历史消息，请再说一次"清空对话"确认。',
  },
  {
    id: 'chat.copy',
    label: '复制最后一条回复',
    keywords: ['复制回复', 'copy reply', '复制最后一条', '复制答案'],
    routes: ['Chat'],
    hazard: 'low',
  },

  // ── Knowledge 空间 ──
  {
    id: 'knowledge.refresh',
    label: '刷新知识空间',
    keywords: ['刷新知识', '重新加载知识', 'refresh knowledge'],
    routes: ['KnowledgeSpace'],
    hazard: 'low',
  },
])

export const HAZARD_LEVELS = Object.freeze({
  critical: { label: '高危', color: '#e06c75', blocks: true, requiresConfirm: true },
  high:     { label: '较高危', color: '#e08a5c', blocks: false, requiresConfirm: true },
  medium:   { label: '需复核', color: '#e0c55c', blocks: false, requiresConfirm: true },
  low:      { label: '安全', color: '#6cc275',  blocks: false, requiresConfirm: false },
})


// ---------------------------------------------------------------------------
// resolveVoiceActionIntent：从文本中匹配按钮级意图
// ---------------------------------------------------------------------------

/**
 * 从语音文本中提取按钮级意图。
 *
 * @param {string} text 语音识别后的文本
 * @param {string} currentRoute 当前路由名（Vue Router 的 route.name）
 */
export function resolveVoiceActionIntent(text, currentRoute) {
  const stripped = String(text ?? '').trim().toLowerCase()
  if (!stripped) return { matched: false, reason: 'empty-text' }

  const route = String(currentRoute ?? '')

  for (const action of VOICE_ACTIONS) {
    const hit = action.keywords.some(kw => stripped.includes(kw.toLowerCase()))
    if (!hit) continue

    const allowed = _routeAllows(action.routes, route)
    if (!allowed) {
      // 命中关键词但路由不匹配 → 不是当前页面的按钮动作，让上层继续尝试导航或 AI
      return { matched: false, reason: `route-mismatch:${action.id}` }
    }

    const level = HAZARD_LEVELS[action.hazard] ?? HAZARD_LEVELS.low
    return {
      matched: true,
      actionId: action.id,
      label: action.label,
      hazard: action.hazard,
      blocked: level.blocks,
      confirm: level.requiresConfirm ? action.confirm : undefined,
    }
  }

  return { matched: false, reason: 'no-action-intent' }
}

function _routeAllows(routes, current) {
  if (!routes || routes === 'any') return true
  const cur = String(current ?? '').toLowerCase()
  if (Array.isArray(routes)) {
    return routes.some(r => cur.includes(String(r).toLowerCase()))
  }
  if (typeof routes === 'function') {
    try { return !!routes(current) } catch { return false }
  }
  return false
}

/** 播报拦截文案。 */
export function actionBlockedBubble(label, hazard) {
  return `抱歉，${label}属于${HAZARD_LEVELS[hazard]?.label ?? '高危'}操作，我不能替你执行，请手动操作。`
}
export function actionConfirmBubble(label, confirmText) {
  return confirmText ?? `好的，准备执行${label}。请再说一次"执行${label}"确认。`
}
export function actionExecuteBubble(label) {
  return `好的，正在执行${label}`
}


// ---------------------------------------------------------------------------
// VoiceActionBus：provide/inject 总线
// ---------------------------------------------------------------------------

/**
 * 给页面组件用的 composable：
 *
 *   import { useVoiceActionBus } from './voiceActionRegistry.js'
 *   const bus = useVoiceActionBus()
 *   const unregister = bus.register('servers.refresh', () => refreshServers())
 *   onBeforeUnmount(unregister)
 */
export function useVoiceActionBus() {
  return getGlobalActionBus()
}

/**
 * 创建一个新的 bus（App.vue 里 provide 时调用）。
 */
export function createVoiceActionBus() {
  const handlers = new Map()  // actionId → Set<{handler, label}>

  return {
    register(actionId, handler, meta = {}) {
      if (!actionId || typeof handler !== 'function') return () => {}
      const entry = { handler, label: meta.label ?? actionId }
      if (!handlers.has(actionId)) handlers.set(actionId, new Set())
      handlers.get(actionId).add(entry)
      return () => _unregister(actionId, entry)
    },

    async dispatch(actionId) {
      const set = handlers.get(actionId)
      if (!set || set.size === 0) return 0
      let fired = 0
      for (const { handler } of set) {
        try { await handler() } catch { /* handler 内部自己 catch */ }
        fired += 1
      }
      return fired
    },

    _debug: {
      registeredIds: () => Array.from(handlers.keys()),
      handlerCount: actionId => handlers.get(actionId)?.size ?? 0,
    },
  }

  function _unregister(actionId, entry) {
    const set = handlers.get(actionId)
    if (!set) return
    set.delete(entry)
    if (set.size === 0) handlers.delete(actionId)
  }
}

// 全局兜底（App.vue 会初始化并挂 globalThis.__voice_action_bus__，
// 测试和非 Vue 上下文也能拿到同一个实例）
let _globalBus = null
function getGlobalActionBus() {
  if (!_globalBus) _globalBus = createVoiceActionBus()
  return _globalBus
}
export function resetGlobalActionBusForTests() { _globalBus = null }
