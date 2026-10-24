import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const base = 'http://127.0.0.1:5198'
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5198, strictPort: true }, logLevel: 'error' })
await server.listen()
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block', reducedMotion: 'reduce' })
  await context.addInitScript(() => localStorage.setItem('smartops_visual_mode', 'reduced-motion'))
  await context.routeWebSocket('**/*', socket => socket.close())
  const calls = []
  const runs = [{ id: 31, teamId: 10, agentId: 7, versionId: 11, requesterId: 2, toolId: 'service-restart', status: 'PENDING_APPROVAL' }]
  await context.route('**/*', route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    if (url.origin !== base) return route.abort()
    if (!path.startsWith('/api/')) return route.continue()
    calls.push(`${request.method()} ${path}`)
    const reply = data => route.fulfill({ json: { code: 200, message: 'OK', data } })
    if (path === '/api/auth/session') return reply({ user: { id: 1, username: 'owner', role: 'operator', portal: 'user' }, csrfToken: 'token' })
    if (path === '/api/teams') return reply({ items: [{ id: 10, name: 'Ops', role: 'owner', status: 'active' }], total: 1 })
    if (path === '/api/teams/10') return reply({ team: { id: 10, name: 'Ops', role: 'owner', status: 'active' }, members: [], invitations: [] })
    if (path === '/api/teams/10/agents') return reply([{ id: 7, teamId: 10, name: 'Shared Agent', status: 'PUBLISHED', currentVersionNo: 1 }])
    if (path === '/api/teams/10/agents/catalog') return reply([])
    if (path === '/api/teams/10/agents/7') return reply({ agent: { id: 7, teamId: 10 }, draft: null, currentVersion: { id: 11, prompt: 'inspect', toolsJson: '["host-health","service-restart"]' } })
    if (path === '/api/teams/10/agents/7/tools') return reply([{ toolId: 'host-health', readOnly: true, riskLevel: 'LOW' }, { toolId: 'service-restart', readOnly: false, riskLevel: 'HIGH' }])
    if (path === '/api/teams/10/runs') return reply(runs)
    if (path === '/api/assistant/conversations') return reply([])
    if (path === '/api/team-agent-runs/31/preview') return reply({ toolId: 'service-restart', readOnly: false, commands: ['systemctl restart api'] })
    if (path === '/api/team-agent-runs/31/approve') { runs[0] = { ...runs[0], status: 'APPROVED', approvedBy: 1 }; return reply(runs[0]) }
    if (path === '/api/teams/10/agents/7/runs') { const run = { id: 32, teamId: 10, agentId: 7, versionId: 11, requesterId: 1, toolId: request.postDataJSON().toolId, status: 'APPROVED' }; runs.push(run); return reply(run) }
    return reply([])
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${base}/teams/10/workspace`, { waitUntil: 'networkidle' })
  await page.locator('.team-workbench__agent-list button').first().click()
  await page.locator('.team-workbench__menu button').nth(2).click()
  assert.equal(await page.getByRole('button', { name: '批准' }).count(), 0)
  await page.getByRole('button', { name: '预览' }).click()
  await page.getByText('systemctl restart api').waitFor()
  await page.getByRole('button', { name: '批准' }).click()
  await page.getByText('APPROVED · Agent 7').first().waitFor()
  assert.ok(calls.indexOf('POST /api/team-agent-runs/31/preview') < calls.indexOf('POST /api/team-agent-runs/31/approve'))
  assert.deepEqual(errors, [])
  console.log('PASS team approval UI: preview before approval and scoped run request')
} finally {
  await browser.close()
  await server.close()
}
