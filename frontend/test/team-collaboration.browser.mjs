import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const base = 'http://127.0.0.1:5197'
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5197, strictPort: true }, logLevel: 'error' })
await server.listen()
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: 'block', reducedMotion: 'reduce' })
  await context.addInitScript(() => { localStorage.setItem('smartops_visual_mode', 'reduced-motion') })
  await context.routeWebSocket('**/*', socket => socket.close())
  const calls = []
  let conversationId = null
  await context.route('**/*', route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    if (url.origin !== base) return route.abort()
    if (!path.startsWith('/api/')) return route.continue()
    calls.push(`${request.method()} ${path}`)
    const response = data => route.fulfill({ json: { code: 200, message: 'OK', data } })
    if (path === '/api/auth/session') return response({ user: { id: 1, username: 'owner', role: 'operator', portal: 'user' }, csrfToken: 'token' })
    if (path === '/api/teams') return response({ items: [{ id: 10, name: '运维协作', role: 'owner', status: 'active' }], total: 1 })
    if (path === '/api/teams/10') return response({ team: { id: 10, name: '运维协作', role: 'owner', status: 'active' }, members: [], invitations: [] })
    if (path === '/api/teams/10/agents') return response([{ id: 7, teamId: 10, name: '巡检 Agent', status: 'PUBLISHED', currentVersionNo: 1 }])
    if (path === '/api/teams/10/agents/7') return response({ agent: { id: 7, teamId: 10 }, draft: null, currentVersion: { prompt: '巡检', toolsJson: '["host-health"]' } })
    if (path === '/api/teams/10/agents/7/tools') return response([{ toolId: 'host-health', readOnly: true, riskLevel: 'LOW' }])
    if (path === '/api/assistant/conversations' && request.method() === 'POST') { conversationId = request.postDataJSON().id; return response({ id: conversationId, title: '新会话' }) }
    if (path === '/api/assistant/conversations') return response(conversationId ? [{ id: conversationId, teamId: 10, title: '新会话' }] : [])
    if (path === `/api/assistant/conversations/${conversationId}`) return response({ id: conversationId, teamId: 10, title: '新会话', messages: [] })
    return response([])
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${base}/teams/10/workspace`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: '共享 Agent' }).waitFor()
  await page.getByRole('button', { name: /巡检 Agent/ }).click()
  await page.getByRole('button', { name: '工具菜单' }).click()
  await page.getByText('host-health').waitFor()
  await page.getByRole('button', { name: '协作会话' }).click()
  await page.getByRole('button', { name: '新建会话' }).click()
  await page.getByRole('textbox', { name: '发送协作消息' }).waitFor()
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 900 })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${width}px overflow`)
  }
  assert.ok(calls.includes('GET /api/teams/10/agents/7/tools'))
  assert.equal(calls.includes('GET /api/operations/tools'), false)
  assert.deepEqual(errors, [])
  console.log('PASS team collaboration workspace: scoped tools, selected session, desktop/mobile')
} finally {
  await browser.close()
  await server.close()
}
