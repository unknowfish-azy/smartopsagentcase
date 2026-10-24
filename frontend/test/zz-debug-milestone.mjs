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
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' })
  const page = await context.newPage()
  page.on('console', m => console.log('CONSOLE', m.type(), m.text().slice(0, 200)))
  page.on('pageerror', e => console.log('PAGEERROR', e.message.slice(0, 300)))
  await page.addInitScript(() => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'milestone-check' }))
    localStorage.setItem('smartops_theme', 'dark')
  })
  await page.route('**/api/**', async route => {
    const req = route.request()
    const url = new URL(req.url())
    if (!url.pathname.startsWith('/api/')) return route.continue()
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204 })
    if (url.pathname === '/api/auth/session') return route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 'milestone-check', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'x' } } })
    if (url.pathname.startsWith('/api/model-analytics')) {
      return route.fulfill({ json: { month: '2026-10', timezone: 'UTC', budget: 300000, budgetUsedTokens: 284100, budgetUnknownCalls: 4, summary: { calls: 1234, successes: 1200, failures: 30, pendingCalls: 0, unknownUsageCalls: 4, knownTokens: 284100, successRate: 97.2 }, models: [], daily: [] } })
    }
    return route.fulfill({ json: { code: 200, data: [] } })
  })
  await page.goto(`${base}/milestones?preview=1`, { waitUntil: 'networkidle' })
  await page.locator('.vessel-stage canvas').waitFor()
  await page.waitForTimeout(1200)
  const diag = await page.evaluate(() => ({
    hasHook: typeof window.__milestoneRain,
    hookResult: typeof window.__milestoneRain === 'function' ? window.__milestoneRain() : null,
    rainStatus: document.querySelector('.rain-status')?.textContent,
    canvases: document.querySelectorAll('canvas').length,
    stageCanvas: !!document.querySelector('.vessel-stage canvas')
  }))
  console.log('DIAG', JSON.stringify(diag, null, 2))
} finally {
  await browser.close()
  await server.close()
}
