// 输入框自动聚焦与快捷键契约（P1-UX-02 补充）：进页/切换/新建会话聚焦输入框，Alt+C 随时聚焦，Esc 退出输入。
// 事实边界：API 全部为 fixture（fixture=true / provider_e2e=false），只验证前端交互契约。
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || process.env.SMARTOPS_VISUAL_BASE_URL
if (!base) {
  console.error('SMARTOPS_BROWSER_BASE_URL is required (run via npm run test:visual)')
  process.exit(1)
}

const failures = []
const diagnostics = {}
const check = (condition, message) => { if (!condition) failures.push(message) }

const browser = await chromium.launch({
  executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  headless: true
})
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
const page = await context.newPage()
page.setDefaultTimeout(15000)
const pageErrors = []
page.on('pageerror', error => pageErrors.push(error.message))

const json = data => ({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })
await page.route(url => url.pathname.startsWith('/api/') || url.pathname.startsWith('/ai/'), route => {
  const path = new URL(route.request().url()).pathname
  if (path.endsWith('/auth/session')) return route.fulfill(json({ user: { id: 78, username: 'focus-user', role: 'operator' }, csrfToken: 'focus-csrf' }))
  if (path.endsWith('/auth/registration')) return route.fulfill(json({ enabled: false }))
  if (path.endsWith('/assistant/options')) {
    return route.fulfill(json({ selectedKey: 'mini', options: [{ key: 'mini', name: '智维 Mini', kind: 'builtin', model: 'fixture', enabled: true, available: true, status: 'ready' }] }))
  }
  if (path.endsWith('/conversations')) return route.fulfill(json([]))
  if (path.endsWith('/api/chat/stream')) {
    const run = { request_id: 'req-focus', task_id: 'task-focus', run_id: 'run-focus', schema_version: '1.0.0', source: 'ai-service', status: 'succeeded', timestamp: new Date().toISOString() }
    return route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream; charset=utf-8' },
      body: [
        `event: run\ndata: ${JSON.stringify({ ...run, status: 'started' })}\n`,
        `event: token\ndata: ${JSON.stringify({ ...run, delta: '先核对磁盘水位。' })}\n`,
        `event: done\ndata: ${JSON.stringify({ ...run, content: '先核对磁盘水位。', metadata: {}, run_event: run })}\n`
      ].join('\n')
    })
  }
  return route.fulfill(json([]))
})
await page.addInitScript(() => {
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 78, username: 'focus-user', role: 'operator' }))
  localStorage.setItem('smartops_theme', 'dark')
})

const active = () => page.evaluate(() => ({
  tag: document.activeElement?.tagName,
  label: document.activeElement?.getAttribute('aria-label') || '',
}))
const waitForFocus = selector => page.waitForFunction(
  target => document.activeElement?.matches?.(target),
  selector,
  { timeout: 5000 }
).catch(() => {})

try {
  await page.goto(`${base}/chat`, { waitUntil: 'domcontentloaded' })
  await page.locator('.chat-page').waitFor()

  // 1. 进入聊天页自动聚焦输入框（桌面精确指针设备）。
  await waitForFocus('.ai-chat-composer textarea')
  check((await active()).tag === 'TEXTAREA', `进入聊天页应自动聚焦输入框，实际 ${JSON.stringify(await active())}`)
  check(await page.locator('.ai-chat-composer textarea').getAttribute('aria-keyshortcuts') === 'Alt+C', '输入框应声明 aria-keyshortcuts="Alt+C"')
  check((await page.locator('.ai-chat-composer textarea').getAttribute('title') || '').includes('Alt+C'), '输入框 title 应提示 Alt+C，便于鼠标用户发现快捷键')

  // 2. 焦点离开后 Alt+C 可回到输入框。
  await page.locator('.chat-page__header h1').click()
  check((await active()).tag !== 'TEXTAREA', `点击标题后焦点应离开输入框，实际 ${JSON.stringify(await active())}`)
  await page.keyboard.press('Alt+C')
  await waitForFocus('.ai-chat-composer textarea')
  check((await active()).tag === 'TEXTAREA', `Alt+C 应聚焦输入框，实际 ${JSON.stringify(await active())}`)

  // 3. 输入法组合中按 Enter 不应发送；Shift+Enter 只换行不发送。
  await page.locator('.ai-chat-composer textarea').click()
  const composingSent = await page.evaluate(() => {
    const textarea = document.querySelector('.ai-chat-composer textarea')
    const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, isComposing: true })
    textarea.dispatchEvent(event)
    return document.querySelectorAll('.ai-chat-message--user').length
  })
  check(composingSent === 0, `输入法组合中 Enter 不应发送，实际新增 ${composingSent} 条用户消息`)
  await page.keyboard.type('第一行')
  await page.keyboard.press('Shift+Enter')
  await page.keyboard.type('第二行')
  const composedDraft = await page.locator('.ai-chat-composer textarea').inputValue()
  check(composedDraft.includes('\n'), `Shift+Enter 应换行而不发送，实际草稿 "${composedDraft}"`)
  check(await page.locator('.ai-chat-message--user').count() === 0, 'Shift+Enter 不应产生用户消息')
  await page.getByLabel('输入消息', { exact: true }).fill('')

  // 4. 在侧边栏搜索框里编辑时，Alt+C 不应抢走焦点。
  const search = page.getByLabel('搜索历史会话')
  await search.click()
  await page.keyboard.press('Alt+C')
  check((await active()).tag === 'INPUT', `在其他输入控件内 Alt+C 不应抢焦点，实际 ${JSON.stringify(await active())}`)
  await page.locator('.ai-chat-composer textarea').click()

  // 5. Enter 发送成功后焦点回收，Esc 退出输入并落到消息区。
  await page.getByLabel('输入消息', { exact: true }).fill('检查磁盘水位')
  await page.keyboard.press('Enter')
  await page.locator('.ai-chat-message--assistant .ai-chat-message__meta').filter({ hasText: 'SMARTOPS AGENT' }).waitFor()
  await waitForFocus('.ai-chat-composer textarea')
  check((await active()).tag === 'TEXTAREA', `回答完成后焦点应回到输入框，实际 ${JSON.stringify(await active())}`)

  await page.keyboard.press('Escape')
  const afterEscape = await active()
  check(afterEscape.tag === 'DIV' && afterEscape.label === '会话消息', `Esc 应把焦点交还消息区，实际 ${JSON.stringify(afterEscape)}`)

  await page.keyboard.press('Alt+C')
  await waitForFocus('.ai-chat-composer textarea')
  check((await active()).tag === 'TEXTAREA', `Esc 之后 Alt+C 应能回到输入框，实际 ${JSON.stringify(await active())}`)

  // 5. 新建会话后焦点回到输入框。
  await page.getByRole('button', { name: '新建对话' }).click()
  await waitForFocus('.ai-chat-composer textarea')
  check((await active()).tag === 'TEXTAREA', `新建会话后焦点应回到输入框，实际 ${JSON.stringify(await active())}`)
  check(await page.locator('.ai-chat-message--user').count() === 0, '新建会话应为空会话')

  // 6. 切换回历史会话后焦点也回到输入框。
  await page.locator('.chat-history__select', { hasText: '检查磁盘水位' }).first().click()
  await waitForFocus('.ai-chat-composer textarea')
  check((await active()).tag === 'TEXTAREA', `切换历史会话后焦点应回到输入框，实际 ${JSON.stringify(await active())}`)
  check(await page.locator('.ai-chat-message--user').count() === 1, '切换后应显示原会话的消息')

  // 7. 命令面板（原生 dialog[open]，无显式 aria-modal）打开时 Alt+C 不抢焦点。
  await page.keyboard.press('Control+K')
  await page.waitForTimeout(400)
  const ctrlK = await page.evaluate(() => ({
    open: Boolean(document.querySelector('dialog.nav-discovery[open]')),
    blockers: [...document.querySelectorAll('[aria-modal="true"], dialog')].map(el => ({ tag: el.tagName, cls: String(el.className).slice(0, 60), open: el.open === true, visible: el.getClientRects().length > 0 })),
  }))
  if (!ctrlK.open) await page.getByRole('button', { name: '搜索页面' }).first().click()
  check(ctrlK.open, `Ctrl+K 应打开命令面板，实际 ${JSON.stringify(ctrlK.blockers)}`)
  await page.locator('dialog.nav-discovery[open]').waitFor()
  await page.keyboard.press('Alt+C')
  const paletteFocus = await page.evaluate(() => Boolean(document.activeElement?.closest?.('dialog.nav-discovery')))
  check(paletteFocus, `命令面板打开时 Alt+C 不应抢走焦点，实际 ${JSON.stringify(await active())}`)
  await page.keyboard.press('Escape')
  diagnostics.ctrlK = ctrlK
} catch (error) {
  failures.push(`执行异常：${error.message}`)
} finally {
  await browser.close()
}

const result = {
  task: 'P1-UX-02-focus',
  fixture: true,
  provider_e2e: false,
  scenarios: 1,
  diagnostics,
  pageErrors,
  failures
}
console.log(JSON.stringify(result, null, 2))
process.exitCode = failures.length || pageErrors.length ? 1 : 0
