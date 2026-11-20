/**
 * 入口（门户）切换：多平级门户之间的跨源导航。
 *
 * 背景：每个门户现在由**独立的开发服务器**提供（见 docs/layered-frontend-services.md）：
 *   用户层     127.0.0.1:5173      管理层     127.0.0.1:5174
 *   企业管理层 127.0.0.1:5175      审计合规层 127.0.0.1:5176
 *   决策指挥层 127.0.0.1:5177      开放生态层 127.0.0.1:5178
 * 因此切换入口不是"改一个变量"，而是**跨源导航**：必须整页跳转，
 * 让目标服务加载自己的 HTML 入口与路由表。
 *
 * 为什么不在 5173 上直接渲染其它门户：那样多个入口又会共用一个前端实例，
 * 回到拆分前的问题（端口、书签、构建产物互相占用）。
 *
 * 端口不写死：优先读 Vite 环境变量，其次按注册中心默认端口，
 * 保证部署时换成真实域名不需要改代码。合法门户集来自 portalCatalog 注册中心。
 */

import { PORTAL_IDS, portalSpec } from './portalCatalog.js'

export const PORTAL_USER = 'user'
export const PORTAL_ADMIN = 'admin'

const env = (typeof import.meta !== 'undefined' && import.meta.env) ? import.meta.env : {}

function configuredPort(portal) {
  const spec = portalSpec(portal)
  if (!spec) return NaN
  const upper = String(portal).toUpperCase()
  // 历史变量名兼容（user / admin），其余门户统一走 VITE_SMARTOPS_<ID>_PORT 前缀。
  const legacy = portal === PORTAL_ADMIN
    ? (env.VITE_SMARTOPS_ADMIN_PORT ?? env.VITE_ADMIN_PORT)
    : portal === PORTAL_USER
      ? (env.VITE_SMARTOPS_USER_PORT ?? env.VITE_USER_PORT)
      : null
  const raw = legacy ?? env[`VITE_SMARTOPS_${upper}_PORT`]
  const value = Number(raw)
  return Number.isInteger(value) && value > 0 ? value : spec.port
}

/** 目标入口的源（scheme + host + port）。 */
export function portalOrigin(portal, location = globalThis.location) {
  const spec = portalSpec(portal)
  if (!spec || !location) return ''
  const scheme = location.protocol || 'http:'
  const host = location.hostname || '127.0.0.1'
  return `${scheme}//${host}:${configuredPort(portal)}`
}

/** 目标入口的登录地址，显式带上 portal，避免目标服务再猜一次。 */
export function portalLoginUrl(portal, { path = '/login', query = {} } = {}, location = globalThis.location) {
  if (!portalSpec(portal)) return ''
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
 * 以"服务自己声明的入口"为准（各门户入口会设置 __SMARTOPS_PORTAL_SURFACE__），
 * 其次才退回端口判断 —— 端口是可配置的，不能当作唯一事实来源。
 * 未知端口按用户层处理，不把访问者误判成受限门户。
 */
export function currentPortal(location = globalThis.location) {
  const declared = globalThis.__SMARTOPS_PORTAL_SURFACE__
  if (declared && portalSpec(declared)) return declared
  if (!location) return PORTAL_USER
  const port = Number(location.port)
  if (Number.isInteger(port)) {
    const match = PORTAL_IDS.find(id => configuredPort(id) === port)
    if (match) return match
  }
  return PORTAL_USER
}

/**
 * 切换入口：同源就交给调用方做 SPA 跳转，跨源返回目标地址由调用方整页跳转。
 *
 * 返回 `{ target, crossOrigin, url }`：
 *   - crossOrigin=false：调用方用 router.replace 即可（同一前端实例内）；
 *   - crossOrigin=true ：调用方必须 `location.assign(url)`，否则目标入口不会被加载。
 *   - 未知门户返回 null，调用方应拒绝切换。
 */
export function resolvePortalSwitch(target, { path = '/login', query = {} } = {}, location = globalThis.location) {
  if (!portalSpec(target)) return null
  const url = portalLoginUrl(target, { path, query }, location)
  const here = currentPortal(location)
  const crossOrigin = target !== here
  return { target, crossOrigin, url }
}
