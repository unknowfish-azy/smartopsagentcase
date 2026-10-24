import { chromium } from 'playwright'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const server = await createServer({
  root: fileURLToPath(new URL('../', import.meta.url)),
  server: { host: '127.0.0.1', port: 5212, strictPort: true },
  logLevel: 'error'
})
await server.listen()
const base = 'http://127.0.0.1:5212'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' })
  const page = await context.newPage()
  page.on('console', m => { if (m.type() !== 'debug') console.log('CONSOLE', m.type(), m.text().slice(0, 160)) })
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
  for (let i = 0; i < 16; i += 1) {
    const state = await page.evaluate(() => ({
      hook: window.__milestoneRain ? window.__milestoneRain() : null,
      status: document.querySelector('.rain-status')?.textContent,
      canvas: !!document.querySelector('.vessel-stage canvas'),
      hidden: document.hidden
    }))
    console.log(i * 500, JSON.stringify(state))
    await page.waitForTimeout(500)
  }
} finally {
  await browser.close()
  await server.close()
}
