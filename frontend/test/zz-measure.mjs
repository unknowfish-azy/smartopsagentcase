// 临时测量脚本：量里程碑战报页的 chrome 偏移与各区块高度，用于视口锁定计算。测完即删。
import { chromium } from 'playwright'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const server = await createServer({
  root: fileURLToPath(new URL('../', import.meta.url)),
  server: { host: '127.0.0.1', port: 5211, strictPort: true },
  logLevel: 'error'
})
await server.listen()
const base = 'http://127.0.0.1:5211'
const browser = await chromium.launch({ channel: 'msedge', headless: true })

const report = {
  month: '2026-10', timezone: 'UTC', budget: 300000, budgetUsedTokens: 284100, budgetUnknownCalls: 4,
  summary: { calls: 1234, successes: 1200, failures: 30, pendingCalls: 0, unknownUsageCalls: 4, knownTokens: 284100, successRate: 97.2 },
  models: [], daily: []
}

const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
await page.addInitScript(() => {
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'measure' }))
  localStorage.setItem('smartops_theme', 'dark')
})
await page.route('**/api/**', async route => {
  const req = route.request()
  const url = new URL(req.url())
  if (!url.pathname.startsWith('/api/')) return route.continue()
  if (req.method() === 'OPTIONS') return route.fulfill({ status: 204 })
  if (url.pathname === '/api/auth/session') {
    return route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 'measure', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'x' } } })
  }
  if (url.pathname.startsWith('/api/model-analytics')) return route.fulfill({ json: report })
  return route.fulfill({ json: { code: 200, data: [] } })
})
await page.goto(`${base}/milestones`, { waitUntil: 'networkidle' })
await page.locator('.vessel-stage canvas').waitFor()
const info = await page.evaluate(() => {
  const rect = sel => {
    const el = document.querySelector(sel)
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height) }
  }
  return {
    viewport: { w: window.innerWidth, h: window.innerHeight },
    topbar: rect('.topbar'),
    workspaceContext: rect('.workspace-context'),
    stepper: rect('#main-content > *'),
    main: rect('main.content'),
    achievements: rect('.achievements'),
    heading: rect('.hall-heading'),
    layout: rect('.hall-layout'),
    vessel: rect('.vessel-panel'),
    list: rect('.achievement-list'),
    footer: rect('.hall-footer'),
    bodyScrollHeight: document.body.scrollHeight
  }
})
console.log(JSON.stringify(info, null, 2))
await browser.close()
await server.close()
