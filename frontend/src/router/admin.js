// 管理员层专用路由表。
//
// 与用户层共用 portalPolicy 的门户语义（入口选择不授予角色、管理层会话
// 只能停留在管理路由），但在这里物理上不注册用户层路由：管理员层服务
// 上没有可落入的用户层页面，用户层服务上也没有管理页面。
//
// 用户层路由表仍是 src/router/index.js，本文件不修改它。

import {
    createRouter,
    createWebHistory
} from 'vue-router'

import { sessionRouteDecision, isAdminSession } from '../security/portalPolicy.js'
import { clearSession, loadSession } from '../security/session.js'

const routes = [
    { path: '/login', name: 'Login', component: () => import('../views/auth/LoginView.vue'), meta: { public: true } },
    { path: '/account/security', name: 'AccountSecurity', component: () => import('../views/account/AccountSecurityView.vue') },
    {
        path: '/admin', component: () => import('../layouts/AdminLayout.vue'), meta: { roles: ['admin'] },
        children: [
            { path: '', name: 'AdminControlCenter', component: () => import('../views/admin/AdminOverviewView.vue') },
            { path: 'users', name: 'AdminUsers', component: () => import('../views/admin/AdminUsersView.vue') },
            { path: 'governance', name: 'AdminGovernance', component: () => import('../views/admin/AdminGovernanceView.vue') },
            { path: 'teams', name: 'AdminTeams', component: () => import('../views/admin/AdminTeamsView.vue') },
            { path: 'sessions', name: 'AdminSessions', component: () => import('../views/admin/AdminSessionsView.vue') },
            { path: 'audit', name: 'AdminAudit', component: () => import('../views/admin/AdminAuditView.vue') },
            { path: 'approvals', name: 'AdminApprovals', component: () => import('../views/admin/AdminApprovalsView.vue') },
            { path: 'models', name: 'AdminModels', component: () => import('../views/admin/AdminModelGovernanceView.vue') },
            { path: 'security', name: 'AdminMfa', component: () => import('../views/admin/AdminMfaView.vue') },
            { path: 'readiness', name: 'AdminReadiness', component: () => import('../views/admin/AdminReadinessView.vue') },
            { path: 'system/dept', name: 'AdminDept', component: () => import('../views/admin/system/DeptView.vue') },
            { path: 'system/post', name: 'AdminPost', component: () => import('../views/admin/system/PostView.vue') },
            { path: 'system/role', name: 'AdminRole', component: () => import('../views/admin/system/RoleView.vue') },
            { path: 'system/menu', name: 'AdminMenu', component: () => import('../views/admin/system/MenuView.vue') },
            { path: 'system/dict', name: 'AdminDict', component: () => import('../views/admin/system/DictView.vue') },
            { path: 'system/notice', name: 'AdminNotice', component: () => import('../views/admin/system/NoticeView.vue') },
            { path: 'system/loginlog', name: 'AdminLoginLog', component: () => import('../views/admin/system/LoginLogView.vue') },
            // 管理端内部无效访问不再静默回总览：明确告知页面不存在及其边界。
            { path: ':pathMatch(.*)*', name: 'AdminNotFound', component: () => import('../views/admin/AdminNotFoundView.vue') }
        ]
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

// 管理员层服务只服务管理员门户：登录页未显式指定门户时补上 ?portal=admin，
// 使打开 http://127.0.0.1:5174/ 或直接深链 /admin 都停在管理员层登录。
// 这是「服务决定默认门户」，仍然只是入口选择，不授予任何角色——
// 角色判定始终由服务端会话与 sessionRouteDecision 负责。
// 一旦查询串里出现了显式门户（用户在登录页切换过），就不再干预。
let explicitPortalSeen = false

// 管理员层没有 404 页面：任何未注册路径都回到门户判断，
// 由 sessionRouteDecision 决定去登录页还是管理总览。
router.beforeEach(async (to) => {
    if (to.query.portal === 'admin' || to.query.portal === 'user') {
        explicitPortalSeen = true
    } else if (!explicitPortalSeen && to.path === '/login') {
        return { path: '/login', query: { ...to.query, portal: 'admin' }, replace: true }
    }
    let user
    try {
        user = await loadSession()
    } catch {
        return to.meta.public ? true : { path: '/login', query: { redirect: to.fullPath, reason: 'unavailable' } }
    }
    if (to.meta.public && !user?.mustChangePassword) return true
    if (to.matched.length === 0) return { path: user ? '/admin' : '/login' }
    // 管理路由只对管理员入口会话开放。非管理员会话在这里明确退回登录页，
    // 避免跳回服务上未注册的 '/' 造成无限重定向；不授予任何降级访问。
    if (user && !user.mustChangePassword && !isAdminSession(user) && /^\/admin(?:\/|$)/.test(to.path)) {
        return { path: '/login', query: { portal: 'admin', reason: 'denied', redirect: to.fullPath } }
    }
    return sessionRouteDecision(user, to)
})

export default router

window.addEventListener('smartops:unauthorized', () => {
    clearSession()
    if (router.currentRoute.value.path !== '/login') router.replace({ path: '/login', query: { portal: 'admin', redirect: router.currentRoute.value.fullPath } })
})
