import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'

const root = process.cwd().replace(/\\frontend$/, '')
const artifact = `${root}\\.runtime\\optimization-20261104\\browser`
await mkdir(artifact, { recursive: true })
const port = 4317 + Math.floor(Math.random() * 100)
const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: `${root}\\frontend`, stdio: 'ignore' })
const base = `http://127.0.0.1:${port}`
for (let attempt = 0; attempt < 100; attempt++) {
  try { const response = await fetch(base); if (response.ok) break } catch {}
  await new Promise(resolve => setTimeout(resolve, 100))
}
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
const results = []
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  page.setDefaultTimeout(10000)
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.context().tracing.start({ screenshots: true, snapshots: true, sources: true })
  await page.route(url => url.pathname.startsWith('/api/') || url.pathname.startsWith('/ai/'), route => route.fulfill({ status: 501, json: { code: 501, message: 'unknown fixture route' } }))
  await page.routeWebSocket('**/*', socket => socket.close())
  await page.route('**/api/assistant/options', route => route.fulfill({ json: { code: 200, data: { selectedKey: 'mini', options: [{ key: 'mini', name: '智维 Mini', kind: 'builtin', model: 'fixture', enabled: true, available: true, status: 'ready' }] } } }))
  await page.route('**/api/conversations', route => route.fulfill({ json: { code: 200, data: [] } }))
  let loggedIn = false
  await page.route('**/api/auth/session', route => route.fulfill({ json: { code: 200, data: { user: loggedIn ? { id: 77, username: 'fixture-user', role: 'operator' } : null, csrfToken: 'fixture-csrf' } } }))
  await page.route('**/api/auth/registration', route => route.fulfill({ json: { code: 200, data: { enabled: false } } }))
  await page.route('**/api/auth/human-verification?*', route => route.fulfill({ json: { code: 200, data: { required: false, enabled: true, available: true, action: 'login' } } }))
  await page.route('**/api/auth/login', route => {
    const body = route.request().postDataJSON()
    assert.equal(body.username, 'fixture-user')
    assert.equal(route.request().headers()['x-csrf-token'], 'fixture-csrf')
    if (body.password !== 'fixture-password') return route.fulfill({ status: 401, json: { code: 401, message: '账号或密码错误' } })
    loggedIn = true
    return route.fulfill({ json: { code: 200, data: {} } })
  })
  await page.addInitScript(() => { localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 77, username: 'fixture-user', role: 'operator' })); localStorage.setItem('smartops_theme', 'light') })
  await page.route('**/ai/api/chat/stream', async route => {
    const body = route.request().postDataJSON()
    assert.equal(body.message, '磁盘空间不足怎么办')
    const run = { request_id: 'req-fixture-1', task_id: 'task-fixture-1', run_id: 'run-fixture-1', event_id: 'event-fixture-1', schema_version: '1.0.0', source: 'ai-service', status: 'started', timestamp: new Date().toISOString(), step_id: 'step-answer' }
    const sse = `event: run\ndata: ${JSON.stringify(run)}\n\nevent: thinking\ndata: ${JSON.stringify({ ...run, status: 'running', delta: '检索知识库' })}\n\nevent: token\ndata: ${JSON.stringify({ ...run, delta: '请先检查磁盘使用率。' })}\n\nevent: done\ndata: ${JSON.stringify({ ...run, status: 'succeeded', metadata: { degraded: true, run_event: { ...run, status: 'succeeded' } }, content: '请先检查磁盘使用率。', citations: [{ source: 'reference/disk.md', content: 'df -h' }], run_event: { ...run, status: 'succeeded' } })}\n\n`
    await route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream; charset=utf-8' }, body: sse })
  })
  await page.goto(`${base}/chat`, { waitUntil: 'domcontentloaded' })
  await page.locator('.login-form').waitFor()
  await page.getByPlaceholder('输入运维账号').fill('fixture-user')
  await page.getByPlaceholder('输入访问密码').fill('wrong-password')
  await page.getByRole('button', { name: '进入智维Agent', exact: true }).click()
  await page.locator('.login-form__error').filter({ hasText: '账号或密码错误' }).waitFor()
  await page.getByPlaceholder('输入访问密码').fill('fixture-password')
  await page.getByRole('button', { name: '进入智维Agent', exact: true }).click()
  await page.goto(`${base}/chat`, { waitUntil: 'domcontentloaded' })
  await page.locator('.chat-page').waitFor()
  await page.getByText('智维 Mini · 运行时就绪', { exact: true }).waitFor()
  results.push({ name: 'fixture_login_invalid_then_success_csrf', pass: true })
  await page.getByLabel('输入消息', { exact: true }).fill('磁盘空间不足怎么办')
  await page.locator('.ai-chat-send').click()
  await page.getByText('请先检查磁盘使用率。', { exact: true }).waitFor()
  assert.equal(await page.locator('.assistant-evidence details').count() > 0, true)
  await page.locator('.ai-run-diagnostics summary').click()
  await page.locator('.ai-run-diagnostics').getByText('run-fixture-1', { exact: true }).waitFor()
  await page.screenshot({ path: `${artifact}\\golden-success.png`, fullPage: true })
  await page.locator('.assistant-evidence summary').click()
  await page.getByText('reference/disk.md', { exact: true }).waitFor()
  await page.getByRole('status').filter({ hasText: '当前为降级模式' }).waitFor()
  await page.reload({ waitUntil: 'domcontentloaded' })
  const event = await page.evaluate(async () => { const { useAiChatStore } = await import('/src/stores/aiChat.js'); return useAiChatStore().messages.at(-1).metadata.run_event })
  assert.equal(event.run_id, 'run-fixture-1')
  assert.equal(event.status, 'succeeded')
  results.push({ name: 'sse_answer_citation_degraded_reload_run_event', pass: true })

  await page.route('**/ai/api/chat/stream', async route => {
    const run = { request_id: 'req-fixture-2', task_id: 'task-fixture-2', run_id: 'run-fixture-2', event_id: 'event-fixture-2', schema_version: '1.0.0', source: 'ai-service', status: 'started', timestamp: new Date().toISOString(), step_id: 'step-stream' }
    const sse = `event: run\ndata: ${JSON.stringify(run)}\n\nevent: token\ndata: ${JSON.stringify({ ...run, delta: '已输出部分内容' })}\n\n`
    await route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream' }, body: sse })
  })
  await page.getByRole('button', { name: '新建对话', exact: true }).click()
  await page.getByLabel('输入消息', { exact: true }).fill('中断测试')
  await page.locator('.ai-chat-send').click()
  await page.locator('.ai-chat-message__error').filter({ hasText: '已输出部分内容' }).waitFor()
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.locator('.ai-chat-message__error').filter({ hasText: 'AI 流响应提前结束' }).waitFor()
  assert.equal(await page.locator('.ai-chat-message__error').filter({ hasText: '已输出部分内容' }).count(), 1)
  assert.equal(await page.locator('.ai-chat-pending').count(), 0)
  assert.equal(await page.getByLabel('输入消息', { exact: true }).isEnabled(), true)
  await page.screenshot({ path: `${artifact}\\golden-interrupted.png`, fullPage: true })
  results.push({ name: 'interrupted_partial_no_done', pass: true })
  await page.route('**/ai/api/chat/stream', route => {
    const run = { request_id: 'req-denied', task_id: 'task-denied', run_id: 'run-denied', event_id: 'event-denied', schema_version: '1.0.0', source: 'ai-service', status: 'denied', timestamp: new Date().toISOString(), step_id: 'step-denied' }
    return route.fulfill({ headers: { 'content-type': 'text/event-stream' }, body: `event: done\ndata: ${JSON.stringify({ status: 'denied', metadata: { run_event: run } })}\n\n` })
  })
  await page.getByRole('button', { name: '新建对话', exact: true }).click()
  await page.getByLabel('输入消息', { exact: true }).fill('权限拒绝测试')
  await page.locator('.ai-chat-send').click()
  await page.locator('.ai-chat-message__error').waitFor()
  const denied = await page.evaluate(async () => { const { useAiChatStore } = await import('/src/stores/aiChat.js'); const message = useAiChatStore().messages.at(-1); return { error: message.error, event: message.metadata.run_event } })
  assert.equal(denied.error, true)
  assert.equal(denied.event.status, 'denied')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.locator('.ai-chat-message__error').waitFor()
  const persistedDenied = await page.evaluate(async () => { const { useAiChatStore } = await import('/src/stores/aiChat.js'); return useAiChatStore().messages.at(-1).metadata.run_event })
  assert.equal(persistedDenied.run_id, 'run-denied')
  assert.equal(persistedDenied.status, 'denied')
  await page.screenshot({ path: `${artifact}\\golden-denied.png`, fullPage: true })
  results.push({ name: 'non_success_done_denied_is_error_and_persisted', pass: true })
  await page.context().tracing.stop({ path: `${artifact}\\trace.zip` })
  assert.deepEqual(errors, [])
  await writeFile(`${artifact}\\assertions.json`, JSON.stringify({ base, fixture: true, provider_e2e: false, results }, null, 2))
} finally { await browser.close(); vite.kill() }
console.log(JSON.stringify(results))
