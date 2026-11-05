// 失败恢复手感契约（P1-UX-01）：
//   场景 1：模型 502 → 错误可见且草稿保留 → 原地重试成功 → 消息不重复、焦点回到输入框。
//   场景 2：已输出部分内容后上游 error 事件中断 → partial 保留且失败 run 可区分 → 原地重试成功替换为完整回答。
// 事实边界：全部 API 为 fixture（fixture=true / provider_e2e=false），只验证前端交互契约。
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || process.env.SMARTOPS_VISUAL_BASE_URL
if (!base) {
  console.error('SMARTOPS_BROWSER_BASE_URL is required (run via npm run test:visual)')
  process.exit(1)
}

const HISTORY_KEY = 'smartops_chat_history:v1:user:retry-user'
const failures = []
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
const sse = (lines) => ({ status: 200, headers: { 'content-type': 'text/event-stream; charset=utf-8' }, body: lines.join('\n') })
const runEvent = (runId, status) => ({ request_id: `req-${runId}`, task_id: `task-${runId}`, run_id: runId, schema_version: '1.0.0', source: 'ai-service', status, timestamp: new Date().toISOString() })
let streamCalls = 0
await page.route(url => url.pathname.startsWith('/api/') || url.pathname.startsWith('/ai/'), route => {
  const path = new URL(route.request().url()).pathname
  if (path.endsWith('/auth/session')) return route.fulfill(json({ user: { id: 77, username: 'retry-user', role: 'operator' }, csrfToken: 'retry-csrf' }))
  if (path.endsWith('/auth/registration')) return route.fulfill(json({ enabled: false }))
  if (path.endsWith('/assistant/options')) {
    return route.fulfill(json({ selectedKey: 'mini', options: [{ key: 'mini', name: '智维 Mini', kind: 'builtin', model: 'fixture', enabled: true, available: true, status: 'ready' }] }))
  }
  if (path.endsWith('/conversations')) return route.fulfill(json([]))
  if (path.endsWith('/api/chat/stream')) {
    streamCalls += 1
    if (streamCalls === 1) {
      // 第一次：上游 502，模拟"模型不可达"。
      return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: 'upstream unavailable' }) })
    }
    if (streamCalls === 2) {
      const run = runEvent('run-retry', 'succeeded')
      return route.fulfill(sse([
        `event: run\ndata: ${JSON.stringify({ ...run, status: 'started' })}\n`,
        `event: token\ndata: ${JSON.stringify({ ...run, delta: '请先检查磁盘使用率。' })}\n`,
        `event: done\ndata: ${JSON.stringify({ ...run, content: '请先检查磁盘使用率。', metadata: {}, run_event: run })}\n`
      ]))
    }
    if (streamCalls === 3) {
      // 第三次：先输出 partial，再收到 error 事件（run 状态 failed），模拟"首 token 后中断"。
      const started = runEvent('run-partial', 'started')
      const failedRun = runEvent('run-partial', 'failed')
      return route.fulfill(sse([
        `event: run\ndata: ${JSON.stringify(started)}\n`,
        `event: token\ndata: ${JSON.stringify({ ...started, delta: '磁盘使用率偏高，' })}\n`,
        `event: error\ndata: ${JSON.stringify({ message: '上游模型输出中断', run_event: failedRun })}\n`
      ]))
    }
    if (streamCalls === 5) {
      // 第五次：刷新前再次 502，用于验证刷新后重试仍可用。
      return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: 'upstream unavailable' }) })
    }
    const run = runEvent('run-retry-2', 'succeeded')
    return route.fulfill(sse([
      `event: run\ndata: ${JSON.stringify({ ...run, status: 'started' })}\n`,
      `event: token\ndata: ${JSON.stringify({ ...run, delta: '已完成磁盘检查。' })}\n`,
      `event: done\ndata: ${JSON.stringify({ ...run, content: '已完成磁盘检查。', metadata: {}, run_event: run })}\n`
    ]))
  }
  return route.fulfill(json([]))
})
await page.addInitScript(() => {
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 77, username: 'retry-user', role: 'operator' }))
  localStorage.setItem('smartops_theme', 'dark')
})

const counts = () => page.evaluate(() => ({
  user: document.querySelectorAll('.ai-chat-message--user').length,
  assistant: document.querySelectorAll('.ai-chat-message--assistant').length,
  retryButtons: document.querySelectorAll('.ai-chat-retry').length,
  focusTag: document.activeElement?.tagName,
  focusLabel: document.activeElement?.getAttribute('aria-label') || '',
  draft: document.querySelector('.ai-chat-composer textarea')?.value ?? ''
}))

try {
  await page.goto(`${base}/chat`, { waitUntil: 'domcontentloaded' })
  await page.locator('.chat-page').waitFor()
  await page.getByLabel('输入消息', { exact: true }).fill('检查磁盘使用率')
  await page.locator('.ai-chat-send').click()

  // 1. 失败态：错误文案 + 重试按钮，且消息条数为 1 问 1 答。
  await page.locator('.ai-chat-retry').waitFor()
  await page.waitForFunction(() => document.activeElement?.tagName === 'TEXTAREA', { timeout: 5000 }).catch(() => {})
  const failed = await counts()
  check(failed.user === 1 && failed.assistant === 1, `失败态消息条数应为 1/1，实际 ${failed.user}/${failed.assistant}`)
  check(failed.retryButtons === 1, `失败态应出现 1 个重试按钮，实际 ${failed.retryButtons}`)
  check(failed.draft === '检查磁盘使用率', `失败后草稿应保留，实际 "${failed.draft}"`)
  check(failed.focusTag === 'TEXTAREA', `失败后焦点应回到输入框，实际 ${failed.focusTag}`)
  const errorText = await page.locator('.ai-chat-message__error').innerText()
  check(errorText.includes('502'), `错误文案应包含状态码 502，实际 "${errorText}"`)

  // 2. 原地重试：不新增消息、错误消失、显示恢复状态。
  await page.locator('.ai-chat-retry').click()
  await page.locator('.ai-chat-status--recovered').waitFor()
  await page.waitForFunction(() => document.activeElement?.tagName === 'TEXTAREA', { timeout: 5000 }).catch(() => {})
  const recovered = await counts()
  check(recovered.user === 1, `重试后用户消息不应重复，实际 ${recovered.user}`)
  check(recovered.assistant === 1, `重试后回答不应新增，实际 ${recovered.assistant}`)
  check(recovered.retryButtons === 0, `重试成功后重试按钮应消失，实际 ${recovered.retryButtons}`)
  check(recovered.focusTag === 'TEXTAREA', `重试成功后焦点应回到输入框，实际 ${recovered.focusTag}`)
  const recoveredText = await page.locator('.ai-chat-status--recovered').innerText()
  check(recoveredText.includes('第 2 次'), `恢复提示应显示尝试次数，实际 "${recoveredText}"`)
  check(await page.locator('.ai-chat-message__error').count() === 0, '重试成功后不应残留错误样式')
  check(await page.locator('.ai-chat-message--assistant').innerText().then(text => text.includes('请先检查磁盘使用率')), '重试成功后应显示新回答')

  // 3. 场景 2：已输出 partial 后被 error 事件中断 → partial 保留、失败 run 可区分。
  await page.getByLabel('输入消息', { exact: true }).fill('再检查一次磁盘')
  await page.locator('.ai-chat-send').click()
  await page.locator('.ai-chat-retry').waitFor()
  await page.waitForFunction(() => document.activeElement?.tagName === 'TEXTAREA', { timeout: 5000 }).catch(() => {})
  const partial = await counts()
  check(partial.user === 2 && partial.assistant === 2, `partial 失败态消息条数应为 2/2，实际 ${partial.user}/${partial.assistant}`)
  check(partial.draft === '再检查一次磁盘', `partial 失败后草稿应保留，实际 "${partial.draft}"`)
  check(partial.focusTag === 'TEXTAREA', `partial 失败后焦点应回到输入框，实际 ${partial.focusTag}`)
  const partialText = await page.locator('.ai-chat-message--assistant').nth(1).innerText()
  check(partialText.includes('磁盘使用率偏高'), `失败后应保留已输出的 partial 内容，实际 "${partialText}"`)
  check(partialText.includes('上游模型输出中断'), `失败文案应保留上游中断原因，实际 "${partialText}"`)

  const failedMessage = await page.evaluate(key => JSON.parse(localStorage.getItem(key) || '{}')?.conversations?.[0]?.messages?.at(-1), HISTORY_KEY)
  check(failedMessage?.error === true, `失败回答应持久化 error=true，实际 ${JSON.stringify(failedMessage?.error)}`)
  check(failedMessage?.metadata?.run_event?.status === 'failed', `失败 run 应可区分，实际 ${JSON.stringify(failedMessage?.metadata?.run_event)}`)
  check(failedMessage?.metadata?.run_event?.run_id === 'run-partial', `失败 run 应保留 run_id，实际 ${JSON.stringify(failedMessage?.metadata?.run_event?.run_id)}`)
  check(failedMessage?.attempt === 1, `首次失败 attempt 应为 1，实际 ${JSON.stringify(failedMessage?.attempt)}`)

  // 4. 同样的失败回答原地重试：partial 被完整回答替换，恢复 run 可区分。
  await page.locator('.ai-chat-retry').click()
  await page.locator('.ai-chat-status--recovered').last().waitFor()
  await page.waitForFunction(() => document.activeElement?.tagName === 'TEXTAREA', { timeout: 5000 }).catch(() => {})
  const partialRecovered = await counts()
  check(partialRecovered.user === 2 && partialRecovered.assistant === 2, `partial 重试后消息条数应保持 2/2，实际 ${partialRecovered.user}/${partialRecovered.assistant}`)
  check(partialRecovered.retryButtons === 0, `partial 重试成功后重试按钮应消失，实际 ${partialRecovered.retryButtons}`)
  check(partialRecovered.focusTag === 'TEXTAREA', `partial 重试成功后焦点应回到输入框，实际 ${partialRecovered.focusTag}`)
  const recoveredLast = await page.locator('.ai-chat-status--recovered').last().innerText()
  check(recoveredLast.includes('第 2 次'), `partial 恢复提示应显示尝试次数，实际 "${recoveredLast}"`)
  const recoveredMessage = await page.evaluate(key => JSON.parse(localStorage.getItem(key) || '{}')?.conversations?.[0]?.messages?.at(-1), HISTORY_KEY)
  check(recoveredMessage?.content === '已完成磁盘检查。', `重试后应替换为完整回答，实际 "${recoveredMessage?.content}"`)
  check(recoveredMessage?.attempt === 2, `重试后 attempt 应为 2，实际 ${JSON.stringify(recoveredMessage?.attempt)}`)
  check(recoveredMessage?.recovered === true, `重试成功后应标记 recovered，实际 ${JSON.stringify(recoveredMessage?.recovered)}`)
  check(recoveredMessage?.metadata?.run_event?.status === 'succeeded', `恢复 run 应可区分，实际 ${JSON.stringify(recoveredMessage?.metadata?.run_event)}`)
  check(recoveredMessage?.metadata?.run_event?.run_id === 'run-retry-2', `恢复 run 应记录新 run_id，实际 ${JSON.stringify(recoveredMessage?.metadata?.run_event?.run_id)}`)

  // 5. 刷新页面后重试按钮必须仍可点（prompt/attempt/recovered 随历史还原）。
  await page.getByLabel('输入消息', { exact: true }).fill('刷新后再试一次')
  await page.keyboard.press('Enter')
  await page.locator('.ai-chat-retry').waitFor()
  const beforeReloadLabel = await page.locator('.ai-chat-retry').getAttribute('aria-label')
  check(beforeReloadLabel === '重试第 1 次失败的回答', `重试按钮应说明尝试次数，实际 "${beforeReloadLabel}"`)

  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.locator('.chat-page').waitFor()
  await page.locator('.ai-chat-retry').waitFor()
  const reloaded = await counts()
  check(reloaded.user === 3 && reloaded.assistant === 3, `刷新后应还原 3/3 条消息，实际 ${reloaded.user}/${reloaded.assistant}`)
  const reloadedText = await page.locator('.ai-chat-message--assistant').last().innerText()
  check(reloadedText.includes('502'), `刷新后失败原因应保留，实际 "${reloadedText}"`)
  const reloadedMessage = await page.evaluate(key => JSON.parse(localStorage.getItem(key) || '{}')?.conversations?.[0]?.messages?.at(-1), HISTORY_KEY)
  check(reloadedMessage?.error === true, `刷新后失败消息应仍标记 error，实际 ${JSON.stringify(reloadedMessage?.error)}`)

  // 刷新后的原地重试仍生效（不追加消息、不丢草稿语境）。
  // 刷新后已有 2 条历史"恢复"提示，必须等第 3 条出现再断言，否则会在重试完成前读到旧 DOM。
  await page.locator('.ai-chat-retry').click()
  await page.waitForFunction(() => document.querySelectorAll('.ai-chat-status--recovered').length === 3, { timeout: 5000 })
  const focusRestored = await page.waitForFunction(() => document.activeElement?.tagName === 'TEXTAREA', { timeout: 5000 }).then(() => true).catch(() => false)
  const afterReload = await counts()
  check(afterReload.user === 3 && afterReload.assistant === 3, `刷新后重试不应追加消息，实际 ${afterReload.user}/${afterReload.assistant}`)
  check(afterReload.retryButtons === 0, `刷新后重试成功应移除重试按钮，实际 ${afterReload.retryButtons}`)
  check(focusRestored && afterReload.focusTag === 'TEXTAREA', `刷新后重试成功焦点应回输入框，实际 ${afterReload.focusTag}`)
  const reloadedRecovered = await page.evaluate(key => JSON.parse(localStorage.getItem(key) || '{}')?.conversations?.[0]?.messages?.at(-1), HISTORY_KEY)
  check(reloadedRecovered?.attempt === 2 && reloadedRecovered?.recovered === true, `刷新后重试应记录 attempt=2/recovered，实际 ${JSON.stringify([reloadedRecovered?.attempt, reloadedRecovered?.recovered])}`)
} catch (error) {
  failures.push(`执行异常：${error.message}`)
} finally {
  await browser.close()
}

const result = {
  task: 'P1-UX-01',
  fixture: true,
  provider_e2e: false,
  scenarios: 3,
  retries: 3,
  retrySuccessRate: failures.length ? 0 : '100%',
  streamCalls,
  pageErrors,
  failures
}
console.log(JSON.stringify(result, null, 2))
process.exitCode = failures.length || pageErrors.length ? 1 : 0
