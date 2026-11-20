// 门户注册中心（前端）：与后端 com.smartops.security.PortalCatalog 同构，
// 是所有「入口层面」判断的唯一事实来源。
//
// 历史上 user/admin 的端口、标签、角色散落在 portalSwitch / portalPolicy /
// accessModel / LoginView / 各 Layout 的硬编码里。新增一个平级门户要改 N 处，
// 极易漏改。这里收敛为一张注册表：新增门户 = 加一条注册，切换/着陆/鉴权引导自动跟随。
//
// 字段说明：
//   id        门户标识，与登录请求 ?portal= 及后端 portal 一致
//   label     中文展示名
//   role      该门户要求的账号角色（app_user.role）
//   port      默认开发端口（可被 VITE_SMARTOPS_<ID>_PORT 覆盖）
//   idle      会话空闲超时时长（秒），与后端保持一致
//   public    是否在用户层登录页公开暴露入口（只有用户层为 true）
//   sensitive 是否高敏：强制 MFA + 更严登录限流（与后端 isSensitive 对齐）
//   surface   前端服务自声明的 __SMARTOPS_PORTAL_SURFACE__ 值

export const PORTAL_REGISTRY = Object.freeze({
  user:       Object.freeze({ id: 'user',       label: '用户层',     role: 'operator',   port: 5173, idle: 1800, public: true,  sensitive: false, surface: 'user',       purpose: '运维一线操作、知识问答与 Agent 执行' }),
  admin:      Object.freeze({ id: 'admin',      label: '管理层',     role: 'admin',      port: 5174, idle: 600,  public: false, sensitive: true,  surface: 'admin',      purpose: '账户治理、平台配置、会话处置与安全审计' }),
  enterprise: Object.freeze({ id: 'enterprise', label: '企业管理层', role: 'enterprise', port: 5175, idle: 900,  public: false, sensitive: false, surface: 'enterprise', purpose: '公司级 SLA / 成本 / 容量 / KPI 驾驶舱，只读分析' }),
  audit:      Object.freeze({ id: 'audit',      label: '审计合规层', role: 'auditor',    port: 5176, idle: 600,  public: false, sensitive: true,  surface: 'audit',      purpose: '独立审计证据、合规报表与操作回溯（与管理层职责分离）' }),
  command:    Object.freeze({ id: 'command',    label: '决策指挥层', role: 'commander',  port: 5177, idle: 600,  public: false, sensitive: true,  surface: 'command',    purpose: '跨域故障态势、重大事件审批与应急指挥' }),
  open:       Object.freeze({ id: 'open',       label: '开放生态层', role: 'partner',    port: 5178, idle: 1800, public: false, sensitive: false, surface: 'open',       purpose: '开放 API 门户、密钥、Webhook 与伙伴配额' })
})

export const PORTAL_IDS = Object.freeze(Object.keys(PORTAL_REGISTRY))

/** 在用户层登录页公开广告的入口。阶段 1 起登录页只渲染这些，其余门户隐蔽。 */
export const PUBLIC_PORTALS = Object.freeze(PORTAL_IDS.filter(id => PORTAL_REGISTRY[id].public))

export function portalSpec(id) {
  return PORTAL_REGISTRY[id] ?? null
}

export function portalLabel(id) {
  return portalSpec(id)?.label ?? id
}

export function portalRole(id) {
  return portalSpec(id)?.role ?? null
}

/**
 * 门户的工作台落地路由：用户层为 '/'，其余门户为 '/<id>'。
 * 由门户 ID 运行时推导，避免在用户层产物中写死管理端路径。
 */
export function portalHome(id) {
  return !id || id === 'user' ? '/' : `/${id}`
}

export function isPublicPortal(id) {
  return Boolean(portalSpec(id)?.public)
}

export function isSensitivePortal(id) {
  return Boolean(portalSpec(id)?.sensitive)
}
