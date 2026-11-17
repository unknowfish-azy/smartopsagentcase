/**
 * 语音控屏意图词典 + 高危路由注册表。
 *
 * 设计原则：
 *  - **纯配置**：所有意图和高危标记都是静态映射，方便 review 和扩展；
 *  - **前端本地解析**：语音文本先在本地匹配意图，命中就直接路由/拦截，
 *    不依赖 AI 输出 JSON，避免 LLM 跑偏导致的越权；
 *  - **高危优先拦截**：意图先匹配路由，如果目标在 HAZARD_ROUTES 里，
 *    直接返回 { blocked: true }，PersonaPet 播报"这个属于高危操作，请手动打开"。
 */

/**
 * 高危路由：语音不能直接跳转，即使命中意图也会被拦截。
 * 每条含 reason，拦截时播报给用户。
 *
 * 准入标准（满足任一即入表）：
 *  - 涉及写操作 / 破坏性操作（删除、重启、执行脚本、下线）；
 *  - 涉及审批 / 财务 / 安全审计；
 *  - 涉及用户、权限、MFA、密码；
 *  - 任何要求"双重确认 / 双人操作"的 SOP 页面。
 */
export const HAZARD_ROUTES = Object.freeze({
  // Admin 全部——默认只有 admin 角色可达，但语音侧再兜一层。
  '/admin': { level: 'critical', reason: '管理控制台，涉及用户、安全与审批' },
  '/admin/users': { level: 'critical', reason: '用户管理，涉及账号变更与权限' },
  '/admin/audit': { level: 'high', reason: '安全审计，涉及敏感操作记录' },
  '/admin/approvals': { level: 'critical', reason: '审批流，涉及资金与授权' },
  '/admin/models': { level: 'high', reason: '模型治理，涉及模型上线/下线' },
  '/admin/security': { level: 'critical', reason: '安全设置，涉及 MFA 与密码策略' },
  '/admin/readiness': { level: 'medium', reason: '就绪检查，可语音打开但需谨慎' },

  // Sentinel 脚本库——脚本执行是破坏性操作。
  '/sentinel/scripts': { level: 'critical', reason: '脚本库，涉及直接执行运维脚本' },

  // 机器人控制台——涉及物理/云机器人控制。
  '/robot': { level: 'critical', reason: '机器人控制台，涉及硬件控制' },

  // 恢复契约 / 知识审核——前者涉及故障恢复 SOP，后者涉及知识准入。
  '/operations/recovery': { level: 'high', reason: '恢复契约，涉及线上故障回滚' },
  '/knowledge/review': { level: 'medium', reason: '知识审核，涉及生产知识准入' },

  // 智能体命令中心——Agent 可调用工具链，当前视为高危。
  '/agent': { level: 'high', reason: '智能体控制中心，涉及工具调用与执行' },
  '/agent/trace': { level: 'medium', reason: '执行轨迹，可追溯高危动作' },

  // 工单中心 / 守护 Agent——前者涉及生产影响，后者涉及自动响应。
  '/incidents': { level: 'high', reason: '工单中心，涉及线上事故处理' },
  '/sentinel/guardian': { level: 'high', reason: '守护 Agent，涉及自动处置' },
})

/**
 * 语音导航意图词典。每条含关键词数组（命中任意一个即匹配）和目标路由。
 *
 * 约定：
 *  - 关键词不区分大小写，全部小写匹配；
 *  - 匹配顺序按数组序，第一条命中即返回；
 *  - 关键词尽量短（2-4 字），避免误匹配；
 *  - 新增路由时在此处同步加条目。
 */
export const NAVIGATION_INTENTS = Object.freeze([
  // 首页 / 快捷入口
  { path: '/', label: '首页', keywords: ['首页', '主页', '回到首页', '回首页', 'home', '主页', '首页去'] },
  { path: '/chat', label: 'AI 对话', keywords: ['对话', '聊天', 'ai对话', '开始对话', '去聊天', '打开对话'] },

  // Knowledge
  { path: '/knowledge/space', label: '知识空间', keywords: ['知识空间', '知识中心', '去知识', '打开知识'] },
  { path: '/atlas', label: '知识蒸馏图谱', keywords: ['知识图谱', '蒸馏图谱', 'atlas', '图谱'] },
  { path: '/scholar/qa', label: '引用溯源问答', keywords: ['溯源问答', '引用问答', 'scholar', '引用溯源'] },
  { path: '/scholar/cards', label: '研究资料卡', keywords: ['资料卡', '研究卡'] },
  { path: '/knowledge/shared', label: '共享知识', keywords: ['共享知识', '公共知识'] },

  // Repository
  { path: '/repository', label: '智能仓库', keywords: ['智能仓库', '仓库', 'repo', '去仓库'] },

  // Research
  { path: '/web-research', label: '联网检索', keywords: ['联网检索', 'web检索', 'research', '联网研究'] },
  { path: '/radar', label: '时效雷达', keywords: ['时效雷达', '雷达', 'freshness'] },
  { path: '/re-workbench', label: '逆向研究工作台', keywords: ['逆向工作台', '逆向研究', 're workbench'] },

  // Extensions
  { path: '/plugins', label: '插件中心', keywords: ['插件中心', 'plugins', '插件'] },
  { path: '/skills', label: '技能中心', keywords: ['技能中心', 'skills'] },

  // Operations
  { path: '/servers', label: '服务器列表', keywords: ['服务器列表', '服务器', 'server', '去服务器'] },
  { path: '/connections', label: '连接中心', keywords: ['连接中心', 'connections'] },
  { path: '/health', label: '健康诊断', keywords: ['健康诊断', '健康中心', 'health'] },
  { path: '/log-diagnosis', label: '日志诊断', keywords: ['日志诊断', 'log诊断', '查日志'] },
  { path: '/devices', label: '设备接入台账', keywords: ['设备台账', '设备列表', 'device'] },
  { path: '/patrol', label: '巡检计划', keywords: ['巡检计划', 'patrol'] },

  // Models
  { path: '/model-settings', label: '模型接入', keywords: ['模型接入', '模型设置', 'model settings'] },
  { path: '/model-gateway', label: '模型网关', keywords: ['模型网关', 'gateway'] },
  { path: '/model-strength', label: '模型强度', keywords: ['模型强度'] },
  { path: '/token-usage', label: '用量与额度', keywords: ['用量额度', '用量', 'token usage', 'milestones'] },

  // Agent
  { path: '/agent', label: '智能体控制中心', keywords: ['智能体', 'agent', '控制中心', '命令中心'] },
  { path: '/agent/persona', label: '人格化身（小鱼全页）', keywords: ['小鱼全页', '人格化身', 'persona', '全页模式'] },

  // Inspector / Memory
  { path: '/inspector', label: '纠察中心', keywords: ['纠察中心', 'inspector', '纠察'] },
  { path: '/inspector/desk', label: '洞察台', keywords: ['洞察台', 'inspector desk'] },
  { path: '/inspector/statistics', label: '统计', keywords: ['inspector统计', 'inspector statistics'] },

  // Sentinel
  { path: '/sentinel', label: '哨兵监控台', keywords: ['哨兵', 'sentinel', '监控台', '去哨兵'] },
  { path: '/sentinel/alerts', label: '告警中心', keywords: ['告警中心', '告警', 'alert', '去告警'] },
  { path: '/sentinel/scripts', label: '脚本库', keywords: ['脚本库', '脚本', 'script library'] },
  { path: '/sentinel/forecast', label: '预测面', keywords: ['预测面', 'forecast', '预测'] },
  { path: '/sentinel/sections', label: '断面对比', keywords: ['断面对比', 'section analysis', '断面'] },
  { path: '/sentinel/observability', label: '引擎可观测', keywords: ['可观测', 'observability'] },

  // Sentinel 高危（即使能匹配，后面也会被 HAZARD_ROUTES 拦截）
  { path: '/incidents', label: '工单中心', keywords: ['工单中心', 'incident', '工单'] },
  { path: '/sentinel/guardian', label: '守护 Agent', keywords: ['守护agent', 'guardian'] },

  // Robot
  { path: '/robot', label: '机器人控制台', keywords: ['机器人', 'robot', '机器人控制台'] },

  // Admin
  { path: '/admin', label: '管理控制台', keywords: ['管理控制台', 'admin', '管理后台', '控制台'] },
])

/**
 * 从语音文本中提取导航意图。
 *
 * @param {string} text 语音识别后的原始文本
 * @returns {{ matched: false, reason: 'no-nav-intent' }
 *          | { matched: true, path: string, label: string, blocked: boolean, hazard?: { level: string, reason: string } }}
 */
export function resolveNavigationIntent(text) {
  const stripped = String(text ?? '').trim().toLowerCase()
  if (!stripped) return { matched: false, reason: 'no-nav-intent' }

  // 先粗筛：如果文本里不含任何导航关键词前缀（打开/跳转/去/到/回到/进入），
  // 直接返回 no-nav-intent，避免"告警率很高"这种业务查询误匹配。
  const NAV_PREFIXES = ['打开', '跳转', '去', '到', '回到', '进入', '切换到', '看一下', '看看', '帮我', '导航', 'navigate', 'go', 'open', 'show', 'take me']
  const hasNavPrefix = NAV_PREFIXES.some(prefix => stripped.includes(prefix))

  for (const intent of NAVIGATION_INTENTS) {
    const hit = intent.keywords.some(kw => stripped.includes(kw.toLowerCase()))
    if (!hit) continue

    // 没有导航前缀但命中关键词——极可能是业务查询（"告警率很高"、"cpu多少"），
    // 只有带导航前缀才认定为导航意图。
    if (!hasNavPrefix) continue

    const hazard = HAZARD_ROUTES[intent.path]
    if (hazard) {
      return { matched: true, path: intent.path, label: intent.label, blocked: true, hazard }
    }
    return { matched: true, path: intent.path, label: intent.label, blocked: false }
  }

  return { matched: false, reason: 'no-nav-intent' }
}

/**
 * 判断路由是否属于高危（给导航守卫/菜单视觉标记用）。
 */
export function isHazardRoute(path) {
  if (!path) return false
  return Object.prototype.hasOwnProperty.call(HAZARD_ROUTES, normalizeRoutePath(path))
}

/**
 * 归一化路由路径：去掉 query / hash、末尾斜杠。
 */
export function normalizeRoutePath(path) {
  if (!path) return ''
  const withoutQuery = String(path).split('?')[0].split('#')[0]
  if (withoutQuery.length > 1 && withoutQuery.endsWith('/')) {
    return withoutQuery.slice(0, -1)
  }
  return withoutQuery
}

/**
 * 语音拦截后的友好提示文案——数字人播报给用户。
 */
export function hazardBubble(intent) {
  const { label, hazard } = intent
  return `抱歉，${label}属于高危操作（${hazard?.reason ?? '需手动操作'}），我不能替你跳，请手动打开。`
}
