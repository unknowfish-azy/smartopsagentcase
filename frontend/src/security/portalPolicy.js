import { canAccess } from './accessModel.js'
import { PORTAL_IDS, portalHome, portalRole } from './portalCatalog.js'

/** 非用户层门户（含管理端）的路由前缀。由注册中心运行时生成，不在用户层产物里写死管理路径。 */
const FOREIGN_SURFACE_RE = new RegExp(`^/(?:${PORTAL_IDS.filter(id => id !== 'user').join('|')})(?:/|$)`)

/** 路径是否落在指定门户的工作台内（home 为 '/' 时只认根路径）。 */
function isWithin(path, home) {
  return home === '/' ? path === '/' : path === home || path.startsWith(home + '/')
}

export function isAdminSession(user) {
  return user?.role === 'admin' && user?.portal === 'admin' && !user?.mustChangePassword
}

/** 泛化：会话是否属于指定门户（角色与入口匹配、未处于改密态）。 */
export function isPortalSession(user, portal) {
  return user?.portal === portal && user?.role === portalRole(portal) && !user?.mustChangePassword
}

/** 新增平级门户（enterprise/audit/command/open）的路由判定：本门户会话只能停留在本门户路由。 */
function genericRouteDecision(user, route, portalId) {
  // 未登录时登录页必须可直接渲染：否则守卫会把 /login 反复重定向回 /login，
  // 造成无限重定向与空白页（四个平级门户的真实缺陷）。
  if (!user) {
    return route.path === '/login'
      ? true
      : { path: '/login', query: { portal: portalId, redirect: route.fullPath || route.path } }
  }
  if (user.mustChangePassword) return route.path === '/account/security' ? true : { path: '/account/security' }
  const own = isPortalSession(user, portalId)
  const prefix = `/${portalId}`
  const prefixRe = new RegExp(`^${prefix}(?:/|$)`)
  if (own && !prefixRe.test(route.path) && route.path !== '/account/security') return { path: prefix }
  if (prefixRe.test(route.path) && !own) {
    return { path: '/login', query: { portal: portalId, reason: 'denied', redirect: route.fullPath } }
  }
  const role = own ? portalRole(portalId) : (user?.role || 'operator')
  const meta = route.meta || {}
  if (meta.roles?.length && !meta.roles.includes(role)) return { path: '/login', query: { portal: portalId, denied: 'role' } }
  if (meta.capability && !canAccess(role, meta.capability)) return { path: '/login', query: { portal: portalId, denied: 'capability' } }
  return true
}

export function sessionRouteDecision(user, route, portalId) {
  if (portalId) return genericRouteDecision(user, route, portalId)
  // —— 以下为 user / admin 原有逻辑，保持不变 ——
  if (!user) return { path: '/login', query: { redirect: route.fullPath || route.path } }
  if (user.mustChangePassword) return route.path === '/account/security' ? true : { path: '/account/security' }
  const home = portalHome(user.portal)
  if (isAdminSession(user) && !isWithin(route.path, home) && route.path !== '/account/security') return { path: home }
  const role = isAdminSession(user) ? 'admin' : 'operator'
  const meta = route.meta || {}
  if ((FOREIGN_SURFACE_RE.test(route.path) || meta.roles?.includes('admin') && !meta.roles.includes('operator')) && !isAdminSession(user)) {
    return { path: '/', query: { denied: 'portal' } }
  }
  if (meta.roles?.length && !meta.roles.includes(role)) return { path: '/', query: { denied: 'role' } }
  if (meta.capability && !canAccess(role, meta.capability)) return { path: '/', query: { denied: 'capability' } }
  return true
}

export function sessionLanding(user, redirect, portalId) {
  if (user?.mustChangePassword) return '/account/security'
  const fallback = portalId ? `/${portalId}` : (isAdminSession(user) ? portalHome(user.portal) : '/')
  if (typeof redirect !== 'string' || !redirect.startsWith('/') || redirect.startsWith('//') || /[\\\u0000-\u001f]/.test(redirect)) return fallback
  const path = redirect.split(/[?#]/)[0]
  if (path === '/login' || (!portalId && !isAdminSession(user) && (FOREIGN_SURFACE_RE.test(path) || /^\/architecture(?:\/|$)/.test(path)))) return fallback
  return redirect
}
