import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { createServer } from 'vite'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5194'
const server = process.env.SMARTOPS_BROWSER_BASE_URL ? null : await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5194, strictPort: true }, logLevel: 'error' })
await server?.listen()
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts/team-workspace', { recursive: true })
const calls = [], errors = []
let user = { id: 91, username: 'mock-owner', role: 'operator', portal: 'user', mustChangePassword: false }
let teams = [], invitations = [], members = [], failList = false, failStatus = false
const password = 'mock-admin-password-only'
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', serviceWorkers: 'block' })
  await context.addInitScript(() => { localStorage.setItem('smartops_visual_mode', 'reduced-motion'); localStorage.setItem('smartops_theme', 'light') })
  await context.routeWebSocket('**/*', socket => socket.close())
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method()
    if (url.origin !== base) return route.abort()
    if (!path.startsWith('/api/')) return route.continue()
    const body = request.postDataJSON(), headers = request.headers()
    calls.push({ path, method, body })
    const reply = (data, code = 200, message = 'OK') => route.fulfill({ status: code, json: { code, message, data } })
    if (method !== 'GET') assert.equal(headers['x-csrf-token'], 'mock-csrf')
    if (path === '/api/auth/session') return reply({ user, csrfToken: 'mock-csrf' })
    if (path === '/api/auth/human-verification') return reply({ enabled: false, available: true, required: false })
    if (path === '/api/auth/registration') return reply({ enabled: true })
    if (path === '/api/teams' && method === 'GET') return failList ? reply(null, 503, '模拟团队读取失败') : reply({ items: teams, total: teams.length })
    if (path === '/api/teams' && method === 'POST') {
      const team = { ...body, id: 71, ownerId: user.id, ownerName: user.username, role: 'owner', status: 'active', memberCount: 1 }
      teams.push(team); members = [{ userId: user.id, username: user.username, role: 'owner', enabled: true }]; return reply(team)
    }
    if (path === '/api/teams/invitations') return reply({ items: invitations.filter(item => item.inbox), total: invitations.filter(item => item.inbox).length })
    if (path === '/api/teams/invitations/9/respond') { invitations = invitations.filter(item => item.id !== 9); return reply(null) }
    if (path === '/api/teams/71' && method === 'GET') return reply({ team: teams[0], members, invitations: invitations.filter(item => !item.inbox) })
    if (path === '/api/teams/71' && method === 'PUT') { Object.assign(teams[0], body); return reply(null) }
    if (path === '/api/teams/71/invitations' && method === 'POST') { invitations.push({ id: 7, username: body.username, role: body.role, expiresAt: '2099-01-01T00:00:00Z' }); return reply(null) }
    if (path === '/api/teams/71/invitations/7' && method === 'DELETE') { invitations = invitations.filter(item => item.id !== 7); return reply(null) }
    if (path === '/api/teams/71/members/92' && method === 'PUT') { members.find(item => item.userId === 92).role = body.role; return reply(null) }
    if (path === '/api/teams/71/members/92' && method === 'DELETE') { members = members.filter(item => item.userId !== 92); teams[0].memberCount = members.length; return reply(null) }
    if (path === '/api/admin/teams') return reply({ items: teams, total: teams.length })
    if (path === '/api/admin/teams/71/members') return reply(members)
    if (path === '/api/admin/teams/71/status') {
      assert.equal(headers['x-admin-password'], password)
      if (failStatus) return reply(null, 403, '模拟管理员复核失败')
      teams[0].status = body.status; return reply(null)
    }
    if (path === '/api/admin/overview') return reply({ usersTotal: 2, usersEnabled: 2, adminsEnabled: 1, activeSessions: 1, recentFailures: 0, pendingPasswordChanges: 0 })
    return reply({ items: [], total: 0 })
  })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  page.on('dialog', dialog => dialog.accept())
  await page.goto(`${base}/`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: '展开主菜单', exact: true }).click()
  const collaborationMenu = page.getByRole('link', { name: '团队协作 / TEAM SPACE', exact: true })
  await collaborationMenu.waitFor({ state: 'visible' })
  assert.equal(await collaborationMenu.getAttribute('href'), '/teams')
  await collaborationMenu.click()
  await page.waitForURL('**/teams')
  await page.goto(`${base}/teams`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: '团队空间', exact: true }).waitFor()
  assert.equal(await page.getByRole('navigation', { name: '工作空间切换' }).getByRole('link', { name: '团队空间' }).getAttribute('aria-current'), 'page')
  assert.equal(await page.getByLabel('当前运维空间').count(), 0)
  await page.getByLabel('团队名称', { exact: true }).fill('测试协作团队')
  await page.getByLabel('团队描述', { exact: true }).fill('仅模拟数据，不写入真实账号')
  await page.getByRole('button', { name: '创建团队空间', exact: true }).click()
  await page.waitForURL('**/teams/71')
  await page.getByRole('heading', { name: '测试协作团队', exact: true }).waitFor()
  await page.getByLabel('已有账号的用户名').fill('mock-member')
  await page.getByLabel('授予角色').selectOption('viewer')
  await page.getByRole('button', { name: '发送站内邀请' }).click()
  await page.getByText('邀请已发送，等待对方接受。', { exact: true }).waitFor()
  await page.getByRole('button', { name: '撤销邀请', exact: true }).click()
  await page.getByText('邀请已撤销。', { exact: true }).waitFor()
  members.push({ userId: 92, username: 'mock-member', role: 'member', enabled: true }); teams[0].memberCount = 2
  await page.getByRole('button', { name: '刷新团队详情' }).click()
  await page.getByLabel('mock-member 的团队角色').selectOption('viewer')
  await page.getByRole('button', { name: '保存角色' }).click()
  await page.getByText('成员角色已更新。', { exact: true }).waitFor()
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `team ${theme} ${width} overflow`)
      await page.screenshot({ path: `test-artifacts/team-workspace/members-${theme}-${width}.png`, fullPage: true })
    }
  }
  await page.getByRole('button', { name: '移除成员', exact: true }).click()
  await page.getByText('成员已移除。', { exact: true }).waitFor()
  invitations.push({ id: 9, inbox: true, teamId: 99, teamName: '另一个团队', teamStatus: 'active', role: 'member', expiresAt: '2099-01-01T00:00:00Z' })
  await page.getByRole('link', { name: '← 返回团队空间', exact: true }).click()
  await page.getByRole('button', { name: '拒绝邀请', exact: true }).click()
  await page.getByText('已拒绝邀请。', { exact: true }).waitFor()
  failList = true
  await page.getByRole('button', { name: '刷新团队', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: '模拟团队读取失败' }).waitFor()
  failList = false
  await page.getByRole('button', { name: '刷新团队', exact: true }).click()
  await page.getByRole('link', { name: '测试协作团队', exact: true }).waitFor()
  teams[0].role = 'viewer'; members[0].role = 'viewer'
  await page.goto(`${base}/teams/71`, { waitUntil: 'networkidle' })
  assert.equal(await page.getByRole('button', { name: '发送站内邀请' }).count(), 0)
  assert.equal(await page.getByRole('button', { name: '保存团队资料' }).count(), 0)
  assert.equal(await page.getByRole('button', { name: '退出当前团队' }).isVisible(), true)
  user = { ...user, role: 'admin', portal: 'admin' }
  await page.goto(`${base}/admin/teams`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: '团队管理', exact: true }).waitFor()
  await page.getByRole('button', { name: '查看成员' }).click()
  await page.getByRole('heading', { name: '测试协作团队 · 成员角色' }).waitFor()
  await page.getByRole('button', { name: '冻结团队', exact: true }).click()
  await page.getByLabel('当前管理员密码').fill(password)
  failStatus = true
  await page.getByRole('button', { name: '确认状态变更', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: '模拟管理员复核失败' }).waitFor()
  assert.equal(await page.getByLabel('当前管理员密码').inputValue(), '')
  failStatus = false
  await page.getByLabel('当前管理员密码').fill(password)
  await page.getByRole('button', { name: '确认状态变更', exact: true }).click()
  await page.getByText('团队状态已更新，变更已记录审计。', { exact: true }).waitFor()
  await page.getByRole('button', { name: '恢复团队', exact: true }).waitFor()
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `admin ${theme} ${width} overflow`)
      if (width === 375) assert.ok(await page.locator('.admin-sidebar').evaluate(element => element.getBoundingClientRect().height < 300), 'mobile admin navigation must remain compact')
      await page.screenshot({ path: `test-artifacts/team-workspace/admin-${theme}-${width}.png`, fullPage: true })
    }
  }
  await page.getByRole('button', { name: '恢复团队', exact: true }).click()
  await page.getByLabel('当前管理员密码').fill(password)
  await page.getByRole('button', { name: '取消', exact: true }).click()
  assert.equal(await page.getByLabel('当前管理员密码').count(), 0)
  assert.equal(await page.evaluate(secret => JSON.stringify({ ...localStorage, ...sessionStorage }).includes(secret), password), false)
  await page.getByRole('link', { name: '管理总览', exact: true }).click()
  await page.getByRole('link', { name: /团队与成员治理/ }).waitFor()
  assert.deepEqual(errors, [])
  assert.ok(calls.some(call => call.path === '/api/teams/71/members/92' && call.method === 'DELETE'))
  console.log('PASS team spaces: create, invite/cancel/decline, role/remove, viewer boundary, retry; admin metadata/freeze/password cleanup; 375/1440 light/dark; all APIs intercepted')
} finally { await browser.close(); await server?.close() }
