import { createRouter, createWebHistory } from 'vue-router'
import { loadSession } from '../security/session.js'
import { sessionRouteDecision } from '../security/portalPolicy.js'
import PortalScaffoldLayout from '../layouts/PortalScaffoldLayout.vue'
import PortalLandingView from '../views/portal/PortalLandingView.vue'

const PORTAL = 'enterprise'
const ROLE = 'enterprise'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/auth/LoginView.vue') },
  { path: '/account/security', name: 'account-security', component: () => import('../views/account/AccountSecurityView.vue') },
  {
    path: '/enterprise',
    component: PortalScaffoldLayout,
    props: { portal: 'enterprise' },
    meta: { roles: [ROLE] },
    children: [
      { path: '', name: 'enterprise-home', component: PortalLandingView, meta: { roles: [ROLE] } },
      { path: ':pathMatch(.*)*', name: 'enterprise-not-found', redirect: '/enterprise' }
    ]
  },
  { path: '/', redirect: '/enterprise' },
  { path: '/:pathMatch(.*)*', redirect: '/enterprise' }
]

const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) })

router.beforeEach(async (to) => {
  const fromQuery = to.query.portal
  if (fromQuery && fromQuery !== PORTAL) return { path: '/login', query: { ...to.query, portal: PORTAL } }
  if (!to.query.portal && (to.path === '/login' || to.path.startsWith('/enterprise'))) {
    return { path: to.path, query: { ...to.query, portal: PORTAL }, replace: true }
  }
  const user = await loadSession()
  const decision = sessionRouteDecision(user, to, PORTAL)
  if (decision !== true) return decision
  return true
})

export default router
