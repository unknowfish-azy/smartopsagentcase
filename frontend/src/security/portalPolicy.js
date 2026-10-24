import { canAccess } from './accessModel.js'

export function isAdminSession(user) {
  return user?.role === 'admin' && user?.portal === 'admin' && !user?.mustChangePassword
}

export function sessionRouteDecision(user, route) {
  if (!user) return { path: '/login', query: { redirect: route.fullPath || route.path } }
  if (user.mustChangePassword) return route.path === '/account/security' ? true : { path: '/account/security' }
  if (isAdminSession(user) && !/^\/admin(?:\/|$)/.test(route.path) && route.path !== '/account/security') return { path: '/admin' }
  const role = isAdminSession(user) ? 'admin' : 'operator'
  const meta = route.meta || {}
  if ((/^\/admin(?:\/|$)/.test(route.path) || meta.roles?.includes('admin') && !meta.roles.includes('operator')) && !isAdminSession(user)) {
    return { path: '/', query: { denied: 'portal' } }
  }
  if (meta.roles?.length && !meta.roles.includes(role)) return { path: '/', query: { denied: 'role' } }
  if (meta.capability && !canAccess(role, meta.capability)) return { path: '/', query: { denied: 'capability' } }
  return true
}

export function sessionLanding(user, redirect) {
  if (user?.mustChangePassword) return '/account/security'
  const fallback = isAdminSession(user) ? '/admin' : '/'
  if (typeof redirect !== 'string' || !redirect.startsWith('/') || redirect.startsWith('//') || /[\\\u0000-\u001f]/.test(redirect)) return fallback
  const path = redirect.split(/[?#]/)[0]
  if (path === '/login' || !isAdminSession(user) && /^\/(admin(?:\/|$)|architecture(?:\/|$))/.test(path)) return fallback
  return redirect
}
