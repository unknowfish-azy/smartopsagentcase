/**
 * 入口（门户）切换：用户层 ↔ 管理员层。
 *
 * 背景：两个入口现在由**两个独立的开发服务器**提供（见 docs/layered-frontend-services.md）：
 *   用户层   127.0.0.1:5173
 *   管理员层 127.0.0.1:5174
 * 因此切换入口不是"改一个变量"，而是**跨源导航**：必须整页跳转，
 * 让目标服务加载自己的 HTML 入口与路由表。
 *
 * 为什么不在 5173 上直接渲染管理员层：那样两个入口又会共用一个前端实例，
 * 回到拆分前的问题（端口、书签、构建产物互相占用）。
 *
 * 端口不写死：优先读 Vite 环境变量（VITE_SMARTOPS_ADMIN_PORT / VITE_SMARTOPS_USER_PORT），
 * 其次按 hostname 推导，保证部署时换成真实域名不需要改代码。
 */

export const PORTAL_USER = 'user'
export const PORTAL_ADMIN = 'admin'

const DEFAULT_PORTS = Object.freeze({ user: 5173, admin: 5174 })

const env = (typeof import.meta !== 'undefined' && import.meta.env) ? import.meta.env : {}

function configuredPort(portal) {
  const raw = portal === PORTAL_ADMIN
    ? (env.VITE_SMARTOPS_ADMIN_PORT ?? env.VITE_ADMIN_PORT)
    : (env.VITE_SMARTOPS_USER_PORT ?? env.VITE_USER_PORT)
  const value = Number(raw)
  return Number.isInteger(value) && value > 0 ? value : DEFAULT_PORTS[portal]
}

/** 目标入口的源（scheme + host + port）。 */
export function portalOrigin(portal, location = globalThis.location) {
  if (!location) return ''
  const scheme = location.protocol || 'http:'
  const host = location.hostname || '127.0.0.1'
  return `${scheme}//${host}:${configuredPort(portal)}`
}

/** 目标入口的登录地址，显式带上 portal，避免目标服务再猜一次。 */
export function portalLoginUrl(portal, { path = '/login', query = {} } = {}, location = globalThis.location) {
  if (![PORTAL_USER, PORTAL_ADMIN].includes(portal)) return ''
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    if (key === 'portal') continue
    params.set(key, String(value))
  }
  params.set('portal', portal)
  return `${portalOrigin(portal, location)}${path}?${params.toString()}`
}

/**
 * 当前页面属于哪个入口。
 *
 * 以"服务自己声明的入口"为准（管理员层入口会设置 __SMARTOPS_PORTAL_SURFACE__），
 * 其次才退回端口判断 —— 端口是可配置的，不能当作唯一事实来源。
 */
export function currentPortal(location = globalThis.location) {
  const declared = globalThis.__SMARTOPS_PORTAL_SURFACE__
  if (declared === PORTAL_ADMIN || declared === PORTAL_USER) return declared
  if (!location) return PORTAL_USER
  const port = Number(location.port)
  if (Number.isInteger(port) && port === configuredPort(PORTAL_ADMIN)) return PORTAL_ADMIN
  if (Number.isInteger(port) && port === configuredPort(PORTAL_USER)) return PORTAL_USER
  return PORTAL_USER
}

/**
 * 切换入口：同源就交给调用方做 SPA 跳转，跨源返回目标地址由调用方整页跳转。
 *
 * 返回 `{ crossOrigin, url }`：
 *   - crossOrigin=false：调用方用 router.replace 即可（同一前端实例内）；
 *   - crossOrigin=true ：调用方必须 `location.assign(url)`，否则目标入口不会被加载。
 */
export function resolvePortalSwitch(target, { path = '/login', query = {} } = {}, location = globalThis.location) {
  if (![PORTAL_USER, PORTAL_ADMIN].includes(target)) return null
  const url = portalLoginUrl(target, { path, query }, location)
  const here = currentPortal(location)
  const crossOrigin = target !== here
  return { target, crossOrigin, url }
}
