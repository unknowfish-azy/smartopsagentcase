/**
 * 哨兵 / 脚本 / 告警 三个模块的共享数据模型与纯业务逻辑。
 *
 * 设计原则（与项目既有理念一致）：
 *  1. **不做假数据**：后端接口未接入前，界面显示真实的空态与"待接入"说明，
 *     而不是填一批看起来很像真的数字。竞赛演示最容易被问穿的就是假数据。
 *  2. **可测的纯逻辑放在这里**：阈值判定、持续时间防抖、脚本高危预检，
 *     这些是模块的"业务内核"，用 node --test 直接覆盖。
 *  3. **执行与审批不从这里另开通道**：脚本最终执行仍走既有
 *     MultiExec（预览 → 二次确认 → 执行）与 TeamAgentRun（预览 → 审批 → 执行）。
 */

/* ── 采集类别 ─────────────────────────────────────────────────────────── */

export const SENTINEL_KINDS = Object.freeze([
  { id: 'system', label: '系统指标', cn: 'CPU / 内存 / 磁盘 / 网络 / TCP 连接数' },
  { id: 'business', label: '业务指标', cn: '端口存活 / 进程存活 / HTTP 健康探测' },
  { id: 'log', label: '日志哨兵', cn: '监听日志文件并匹配关键字' }
])

export const SYSTEM_METRICS = Object.freeze([
  { id: 'cpu', label: 'CPU 使用率', unit: '%', defaultThreshold: 90 },
  { id: 'memory', label: '内存使用率', unit: '%', defaultThreshold: 90 },
  { id: 'disk', label: '磁盘使用率', unit: '%', defaultThreshold: 85 },
  { id: 'disk_io', label: '磁盘 IO 等待', unit: 'ms', defaultThreshold: 200 },
  { id: 'network', label: '网络带宽', unit: 'Mbps', defaultThreshold: 800 },
  { id: 'tcp', label: 'TCP 连接数', unit: '个', defaultThreshold: 5000 }
])

export const BUSINESS_METRICS = Object.freeze([
  { id: 'port', label: '端口存活', unit: '', defaultThreshold: null },
  { id: 'process', label: '进程存活', unit: '', defaultThreshold: null },
  { id: 'http', label: 'HTTP 接口健康', unit: 'ms', defaultThreshold: 3000 }
])

export const LOG_KEYWORDS = Object.freeze(['ERROR', 'Exception', '宕机', 'OutOfMemory', 'panic'])

export const COLLECT_INTERVALS = Object.freeze([
  { id: 10, label: '10 秒' }, { id: 30, label: '30 秒' },
  { id: 60, label: '1 分钟' }, { id: 300, label: '5 分钟' }, { id: 900, label: '15 分钟' }
])

/* ── 阈值判定与持续时间防抖 ───────────────────────────────────────────── */

export const THRESHOLD_OPERATORS = Object.freeze([
  { id: 'gt', label: '大于', symbol: '>' },
  { id: 'gte', label: '大于等于', symbol: '≥' },
  { id: 'lt', label: '小于', symbol: '<' },
  { id: 'lte', label: '小于等于', symbol: '≤' },
  { id: 'ne', label: '不等于', symbol: '≠' },
  { id: 'eq', label: '等于', symbol: '=' }
])

function compare(operator, value, threshold) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return false
  switch (operator) {
    case 'gt': return value > threshold
    case 'gte': return value >= threshold
    case 'lt': return value < threshold
    case 'lte': return value <= threshold
    case 'ne': return value !== threshold
    case 'eq': return value === threshold
    default: return false
  }
}

/**
 * 判断一组规则是否全部命中（复合阈值 = 数组内全部满足）。
 * 单指标阈值就是只有一条规则的数组，两者同一条代码路径，避免两套判定逻辑漂移。
 */
export function rulesBreached(rules, snapshot) {
  if (!Array.isArray(rules) || rules.length === 0) return false
  if (!snapshot || typeof snapshot !== 'object') return false
  return rules.every(rule => {
    if (!rule || typeof rule.metric !== 'string') return false
    const value = snapshot[rule.metric]
    return compare(rule.operator ?? 'gt', value, Number(rule.value))
  })
}

/**
 * 持续时间防抖判定。
 *
 * 瞬时峰值不告警：只有当阈值**连续**满足到 `debounceSec` 之后才允许触发。
 * `breachedSinceMs` 由服务端持久化（不能只放浏览器内存，否则刷新页面就丢）。
 *
 * @returns {{breached:boolean, shouldFire:boolean, heldSec:number, remainingSec:number}}
 */
export function debounceDecision({ rules, snapshot, debounceSec = 300, breachedSinceMs = null, nowMs = Date.now() }) {
  const breached = rulesBreached(rules, snapshot)
  if (!breached) return { breached: false, shouldFire: false, heldSec: 0, remainingSec: 0 }
  if (!Number.isFinite(breachedSinceMs)) {
    // 刚刚越界：本轮只记录起点，不触发。
    return { breached: true, shouldFire: false, heldSec: 0, remainingSec: Math.max(0, debounceSec) }
  }
  const heldSec = Math.max(0, Math.floor((nowMs - breachedSinceMs) / 1000))
  const remainingSec = Math.max(0, debounceSec - heldSec)
  return { breached: true, shouldFire: remainingSec === 0, heldSec, remainingSec }
}

/** 把规则渲染成人类可读的一段话，用于界面与告警标题。 */
export function describeRules(rules) {
  if (!Array.isArray(rules) || rules.length === 0) return '未配置阈值'
  return rules.map(rule => {
    const operator = THRESHOLD_OPERATORS.find(item => item.id === (rule.operator ?? 'gt'))?.symbol ?? '>'
    const metric = [...SYSTEM_METRICS, ...BUSINESS_METRICS].find(item => item.id === rule.metric)?.label ?? rule.metric
    return `${metric} ${operator} ${rule.value}`
  }).join(' 且 ')
}

/* ── 脚本：语言、风险、高危预检 ───────────────────────────────────────── */

export const SCRIPT_LANGUAGES = Object.freeze([
  { id: 'shell', label: 'Shell', ext: 'sh' },
  { id: 'python', label: 'Python', ext: 'py' },
  { id: 'bat', label: 'Bat', ext: 'bat' },
  { id: 'powershell', label: 'PowerShell', ext: 'ps1' }
])

export const SCRIPT_RISKS = Object.freeze([
  { id: 'LOW', label: '低', cn: '只读查询类' },
  { id: 'MEDIUM', label: '中', cn: '可重启服务、清理临时文件' },
  { id: 'HIGH', label: '高', cn: '涉及数据删除、格式化、权限变更，需管理员审批' }
])

/**
 * 平台变量。
 *
 * ⚠️ 这份清单必须与服务端 `SentinelVariables.SUPPORTED` 一致 —— 服务端才是权威，
 * 这里只用于渲染输入框与示例。不一致会导致"界面上能填、后端说不认识"的割裂，
 * 因此有测试比对两侧清单。
 */
export const PLATFORM_VARIABLES = Object.freeze([
  { token: '${主机IP}', key: '主机IP', label: '主机 IP', example: '10.0.0.7', description: '目标资产地址' },
  { token: '${主机名}', key: '主机名', label: '主机名', example: 'web-01', description: '目标资产名称' },
  { token: '${告警指标}', key: '告警指标', label: '告警指标', example: 'memory', description: '触发告警的指标' },
  { token: '${告警值}', key: '告警值', label: '告警值', example: '95.0', description: '越界的观测值' },
  { token: '${阈值}', key: '阈值', label: '阈值', example: 'memory > 90', description: '命中的阈值表达式' },
  { token: '${告警级别}', key: '告警级别', label: '告警级别', example: 'P2', description: 'P0..P3' },
  { token: '${告警标题}', key: '告警标题', label: '告警标题', example: 'web-01：内存越界', description: '告警标题' },
  { token: '${脚本名}', key: '脚本名', label: '脚本名', example: 'memory-cleanup', description: '当前脚本名称' },
  { token: '${执行人}', key: '执行人', label: '执行人', example: 'operator', description: '发起人账号' },
  { token: '${时间}', key: '时间', label: '时间', example: '2026-10-17T02:00:00Z', description: '发起时刻（ISO-8601）' }
])

/** 三种触发模式；与服务端 TRIGGER_MANUAL / TRIGGER_SCHEDULE / TRIGGER_ALERT 对应。 */
export const TRIGGER_MODES = Object.freeze([
  { id: 'MANUAL', label: '手动执行', cn: '人工选择目标后发起' },
  { id: 'SCHEDULE', label: '定时执行', cn: '按计划到点发起（同样需确认）' },
  { id: 'ALERT', label: '告警联动', cn: '由告警触发（P0/P1 与高危必须人工）' }
])

/**
 * 高危命令黑名单。
 *
 * 说明：这是**防御性预检**，不是沙箱。它的作用是拦住明显的误操作与最危险的写法，
 * 真正的边界仍在服务端（固定命令、参数校验、最小权限、超时、审批）。
 * 任何声称"前端黑名单等于安全"的说法都是错的，界面文案也如实这么写。
 */
export const DANGEROUS_PATTERNS = Object.freeze([
  { pattern: /\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rf]/i, label: '递归删除文件（rm -rf）' },
  { pattern: /\brm\s+-[a-zA-Z]*f\s+\/(?!\w)/i, label: '删除根目录内容' },
  { pattern: /\bmkfs(\.\w+)?\b/i, label: '格式化文件系统（mkfs）' },
  { pattern: /\bdd\b[^\n]*\bof=\/dev\//i, label: '向块设备裸写（dd of=/dev/…）' },
  { pattern: />\s*\/dev\/[sh]d[a-z]/i, label: '重定向覆盖磁盘设备' },
  { pattern: /\b(shutdown|reboot|halt|poweroff)\b/i, label: '关机或重启主机' },
  { pattern: /:\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:/, label: 'Fork 炸弹' },
  { pattern: /\bchmod\s+(-[a-zA-Z]*\s+)*777\s+\//i, label: '把根目录权限设为 777' },
  { pattern: /\b(iptables|nft)\b[^\n]*\s-F\b/i, label: '清空防火墙规则' },
  { pattern: /\buserdel\b|\bgroupdel\b/i, label: '删除用户或用户组' },
  { pattern: /\bDROP\s+(TABLE|DATABASE)\b/i, label: '删除数据库对象' },
  { pattern: /\bTRUNCATE\s+TABLE\b/i, label: '清空数据表' }
])

/**
 * 脚本高危预检。
 *
 * @returns {{verdict:'ok'|'blocked'|'syntax_error', matches:Array, detail:string}}
 */
export function lintScript(body, language = 'shell') {
  if (typeof body !== 'string' || body.trim() === '') {
    return { verdict: 'syntax_error', matches: [], detail: '脚本内容为空' }
  }
  if (!SCRIPT_LANGUAGES.some(item => item.id === language)) {
    return { verdict: 'syntax_error', matches: [], detail: `不支持的语言：${language}` }
  }
  const matches = []
  for (const entry of DANGEROUS_PATTERNS) {
    const found = entry.pattern.exec(body)
    if (found) matches.push({ label: entry.label, sample: found[0].trim().slice(0, 80) })
  }
  // 括号/引号明显不配对的粗检：只作为提示，不冒充真正的语法分析器。
  const unbalanced = (body.match(/\(/g)?.length ?? 0) !== (body.match(/\)/g)?.length ?? 0)
  if (matches.length > 0) {
    return { verdict: 'blocked', matches, detail: `命中 ${matches.length} 条高危规则，已拒绝保存或执行` }
  }
  if (unbalanced) {
    return { verdict: 'syntax_error', matches: [], detail: '括号不配对，疑似语法错误（仅粗检）' }
  }
  return { verdict: 'ok', matches: [], detail: '未命中高危规则；服务端仍会做参数校验与最小权限约束' }
}

/** 按风险级别推断脚本是否需要管理员审批。 */
export function requiresApproval(riskLevel) {
  return riskLevel === 'HIGH'
}

/** 用平台变量替换脚本中的占位符；未提供的变量保持原样以便界面提示未替换项。 */
export function applyVariables(body, variables = {}) {
  if (typeof body !== 'string') return ''
  let output = body
  const missing = []
  for (const variable of PLATFORM_VARIABLES) {
    const value = variables[variable.key]
    if (value === undefined || value === null || value === '') {
      if (body.includes(variable.token)) missing.push(variable.token)
      continue
    }
    output = output.split(variable.token).join(String(value))
  }
  return { body: output, missing }
}

/* ── 告警：分级、状态机、通知渠道 ─────────────────────────────────────── */

export const ALERT_SEVERITIES = Object.freeze([
  { id: 'P0', label: 'P0 紧急', cn: '业务中断，必须人工确认', needsHuman: true },
  { id: 'P1', label: 'P1 高', cn: '影响可用性，必须人工确认', needsHuman: true },
  { id: 'P2', label: 'P2 中', cn: '可由策略自动发起，仍需预览与审批' },
  { id: 'P3', label: 'P3 低', cn: '可由策略自动发起，仍需预览与审批' }
])

export const ALERT_STATUSES = Object.freeze([
  { id: 'OPEN', label: '待处理' },
  { id: 'NOTIFIED', label: '已通知' },
  { id: 'PENDING_APPROVAL', label: '待审批' },
  { id: 'REMEDIATING', label: '处置中' },
  { id: 'RESOLVED', label: '已恢复' },
  { id: 'CLOSED', label: '已关闭' },
  { id: 'SUPPRESSED', label: '静默抑制' }
])

export const NOTIFY_CHANNELS = Object.freeze([
  { id: 'inapp', label: '站内消息', cn: '复用团队通知' },
  { id: 'email', label: '邮件' },
  { id: 'webhook', label: 'Webhook', cn: '企业微信 / 钉钉' }
])

export const ALERT_EVENT_KINDS = Object.freeze([
  { id: 'FIRED', label: '告警产生' },
  { id: 'NOTIFIED', label: '通知已发送' },
  { id: 'AI_ANALYZED', label: 'AI 研判完成' },
  { id: 'DISPATCH_REQUESTED', label: '发起处置' },
  { id: 'APPROVED', label: '审批通过' },
  { id: 'EXECUTED', label: '脚本执行' },
  { id: 'RESULT_FILLED', label: '结果回填' },
  { id: 'CLOSED', label: '工单关闭' }
])

/** 该级别的告警是否必须人工确认后才能处置（P0/P1 一律是）。 */
export function requiresHumanBeforeRemediation(severity) {
  return ALERT_SEVERITIES.find(item => item.id === severity)?.needsHuman === true
}

/**
 * 是否允许"由策略自动发起处置"。
 *
 * 即使允许，也只是**免去人工点击发起**，脚本仍要经过既有
 * MultiExec 预览 + 审批 + 二次确认；这里不产生任何直接执行的通路。
 */
export function canAutoDispatch({ severity, autoDispatch, scriptRisk, scriptApproved }) {
  if (requiresHumanBeforeRemediation(severity)) return false
  if (autoDispatch !== true) return false
  if (scriptRisk === 'HIGH') return false
  return scriptApproved === true
}
