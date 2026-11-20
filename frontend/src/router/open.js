import { createRouter, createWebHistory } from 'vue-router'
import { loadSession } from '../security/session.js'
import { sessionRouteDecision } from '../security/portalPolicy.js'
import PortalScaffoldLayout from '../layouts/PortalScaffoldLayout.vue'
import PortalLandingView from '../views/portal/PortalLandingView.vue'

const PORTAL = 'open'
const ROLE = 'partner'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/auth/LoginView.vue') },
  { path: '/account/security', name: 'account-security', component: () => import('../views/account/AccountSecurityView.vue') },
  {
    path: '/open',
    component: PortalScaffoldLayout,
    props: { portal: 'open' },
    meta: { roles: [ROLE] },
    children: [
      { path: '', name: 'open-home', component: PortalLandingView, meta: { roles: [ROLE] } },
      { path: ':pathMatch(.*)*', name: 'open-not-found', redirect: '/open' }
    ]
  },
  { path: '/', redirect: '/open' },
  { path: '/:pathMatch(.*)*', redirect: '/open' }
]

const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) })

router.beforeEach(async (to) => {
  const fromQuery = to.query.portal
  if (fromQuery && fromQuery !== PORTAL) return { path: '/login', query: { ...to.query, portal: PORTAL } }
  if (!to.query.portal && (to.path === '/login' || to.path.startsWith('/open'))) {
    return { path: to.path, query: { ...to.query, portal: PORTAL }, replace: true }
  }
  const user = await loadSession()
  const decision = sessionRouteDecision(user, to, PORTAL)
  if (decision !== true) return decision
  return true
})

export default router
