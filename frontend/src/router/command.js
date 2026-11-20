import { createRouter, createWebHistory } from 'vue-router'
import { loadSession } from '../security/session.js'
import { sessionRouteDecision } from '../security/portalPolicy.js'
import PortalScaffoldLayout from '../layouts/PortalScaffoldLayout.vue'
import PortalLandingView from '../views/portal/PortalLandingView.vue'

const PORTAL = 'command'
const ROLE = 'commander'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/auth/LoginView.vue') },
  { path: '/account/security', name: 'account-security', component: () => import('../views/account/AccountSecurityView.vue') },
  {
    path: '/command',
    component: PortalScaffoldLayout,
    props: { portal: 'command' },
    meta: { roles: [ROLE] },
    children: [
      { path: '', name: 'command-home', component: PortalLandingView, meta: { roles: [ROLE] } },
      { path: ':pathMatch(.*)*', name: 'command-not-found', redirect: '/command' }
    ]
  },
  { path: '/', redirect: '/command' },
  { path: '/:pathMatch(.*)*', redirect: '/command' }
]

const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) })

router.beforeEach(async (to) => {
  const fromQuery = to.query.portal
  if (fromQuery && fromQuery !== PORTAL) return { path: '/login', query: { ...to.query, portal: PORTAL } }
  if (!to.query.portal && (to.path === '/login' || to.path.startsWith('/command'))) {
    return { path: to.path, query: { ...to.query, portal: PORTAL }, replace: true }
  }
  const user = await loadSession()
  const decision = sessionRouteDecision(user, to, PORTAL)
  if (decision !== true) return decision
  return true
})

export default router
