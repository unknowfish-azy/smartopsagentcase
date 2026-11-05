// 运行诊断契约（P1-RUN-02）：
//   场景 1：真实路径成功回答 → 诊断区显示有效模型/降级/RAG/引用数/纠察/首 token/总耗时，
//            run_id 与 request_id 可复制，"打开运行记录"指向 /operations/runs。
//   场景 2：降级 + 检索降级 + 纠察 REJECTED → 降级原因/检索原因/0 条引用按实际元数据展示，不伪造。
//   刷新后诊断字段与耗时仍完整（history.ts 白名单持久化）。
// 事实边界：全部 API 为 fixture（fixture=true / provider_e2e=false），只验证前端展示与持久化契约。
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || process.env.SMARTOPS_VISUAL_BASE_URL
if (!base) {
  console.error('SMARTOPS_BROWSER_BASE_URL is required (run via npm run test:visual)')
  process.exit(1)
}

const HISTORY_KEY = 'smartops_chat_history:v1:user:diag-user'
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
const sse = lines => ({ status: 200, headers: { 'content-type': 'text/event-stream; charset=utf-8' }, body: lines.join('\n') })
const runEvent = (runId, status) => ({ request_id: `req-${runId}`, task_id: `task-${runId}`, run_id: runId, schema_version: '1.0.0', source: 'ai-service', status, timestamp: new Date().toISOString() })

const healthyMetadata = run => ({
  rag_enabled: true, top_k: 5, version: 'kb-v1', images: [],
  degraded: false, effective_provider: 'openai-compatible:qwen2.5-7b', degradation_reason: '',
  rag_status: 'ok', rag_degraded: false, rag_degradation_reason: '',
  inspection: { status: 'PASS', severity: 'INFO', reason: '全部检查通过', requires_human: false },
  run_event: run,
})
const degradedMetadata = run => ({
  rag_enabled: true, top_k: 5, version: null, images: [],
  degraded: true, effective_provider: 'mock-local', degradation_reason: '真实模型不可用，已回落到本地 mock',
  rag_status: 'empty', rag_degraded: true, rag_degradation_reason: '知识服务 503，已跳过检索',
  inspection: { status: 'REJECTED', severity: 'HIGH', reason: '状态核验失败', requires_human: true },
  run_event: run,
})

let streamCalls = 0
await page.route(url => url.pathname.startsWith('/api/') || url.pathname.startsWith('/ai/'), route => {
  const path = new URL(route.request().url()).pathname
  if (path.endsWith('/auth/session')) return route.fulfill(json({ user: { id: 42, username: 'diag-user', role: 'operator' }, csrfToken: 'diag-csrf' }))
  if (path.endsWith('/auth/registration')) return route.fulfill(json({ enabled: false }))
  if (path.endsWith('/assistant/options')) {
    return route.fulfill(json({ selectedKey: 'mini', options: [{ key: 'mini', name: '智维 Mini', kind: 'builtin', model: 'fixture', enabled: true, available: true, status: 'ready' }] }))
  }
  if (path.endsWith('/conversations')) return route.fulfill(json([]))
  if (path.endsWith('/api/chat/stream')) {
    streamCalls += 1
    if (streamCalls === 1) {
      const run = runEvent('run-diag-ok', 'succeeded')
      return route.fulfill(sse([
        `event: run\ndata: ${JSON.stringify({ ...run, status: 'started' })}\n`,
        `event: thinking\ndata: ${JSON.stringify({ stage: 'retrieve', label: '知识检索结果', detail: '状态：ok；返回 2 条知识片段' })}\n`,
        `event: token\ndata: ${JSON.stringify({ delta: '磁盘使用率 62%，建议先清理日志。' })}\n`,
        `event: inspection\ndata: ${JSON.stringify(healthyMetadata(run).inspection)}\n`,
        `event: done\ndata: ${JSON.stringify({
          provider: 'openai-compatible', model: 'qwen2.5-7b', trust_score: 0.82,
          citations: [
            { citation_id: 1, title: 'Nginx 日志清理', snippet: '按天轮转', source: 'reference/nginx', version: 'kb-v1', score: 0.91 },
            { citation_id: 2, title: '磁盘扩容', snippet: '先扩容再迁移', source: 'reference/os', version: 'kb-v1', score: 0.77 },
          ],
          evidence: [], metadata: healthyMetadata(run),
        })}\n`
      ]))
    }
    const run = runEvent('run-diag-degraded', 'succeeded')
    return route.fulfill(sse([
      `event: run\ndata: ${JSON.stringify({ ...run, status: 'started' })}\n`,
      `event: token\ndata: ${JSON.stringify({ delta: '当前只能给出通用建议。' })}\n`,
      `event: done\ndata: ${JSON.stringify({
        provider: 'mock-local', model: 'mock', trust_score: 0,
        citations: [], evidence: [], metadata: degradedMetadata(run),
      })}\n`
    ]))
  }
  return route.fulfill(json([]))
})
await page.addInitScript(() => {
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 42, username: 'diag-user', role: 'operator' }))
  localStorage.setItem('smartops_theme', 'dark')
  // headless 下没有可靠剪贴板权限，注入可控 stub 以验证"复制调用 + UI 反馈"，不模拟系统剪贴板。
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: async text => { window.__copiedTexts = [...(window.__copiedTexts || []), text] } },
  })
})

const openDetails = async index => {
  await page.locator('.ai-run-diagnostics summary').nth(index).click()
  await page.locator('.ai-run-diagnostics').nth(index).waitFor()
}
const diagnosticsText = index => page.locator('.ai-run-diagnostics').nth(index).innerText()

try {
  await page.goto(`${base}/chat`, { waitUntil: 'domcontentloaded' })
  await page.locator('.chat-page').waitFor()

  // 场景 1：成功回答的完整诊断。
  await page.getByLabel('输入消息', { exact: true }).fill('检查磁盘使用率')
  await page.locator('.ai-chat-send').click()
  await page.locator('.ai-run-diagnostics').waitFor()
  await openDetails(0)
  const healthyText = await diagnosticsText(0)
  check(healthyText.includes('运行诊断 · 已完成'), `诊断标题应显示成功状态，实际 "${healthyText}"`)
  check(healthyText.includes('有效模型') && healthyText.includes('openai-compatible:qwen2.5-7b'), `诊断应显示 effective provider，实际 "${healthyText}"`)
  check(healthyText.includes('否（真实模型可用）'), `未降级时应明确显示否，实际 "${healthyText}"`)
  check(healthyText.includes('正常（有命中）') && healthyText.includes('top_k 5'), `诊断应显示 RAG 状态与 top_k，实际 "${healthyText}"`)
  check(healthyText.includes('2 条'), `诊断应显示引用数 2，实际 "${healthyText}"`)
  check(healthyText.includes('PASS · INFO · 全部检查通过'), `诊断应显示 inspection，实际 "${healthyText}"`)
  check(/首 token[^\n]*\n?[^\n]*\d+ ms/.test(healthyText), `诊断应显示首 token 耗时，实际 "${healthyText}"`)
  check(/总耗时[^\n]*\n?[^\n]*\d+ ms/.test(healthyText), `诊断应显示总耗时，实际 "${healthyText}"`)
  check(!healthyText.includes('降级原因'), `无降级原因时不应出现该行，实际 "${healthyText}"`)
  check(!healthyText.includes('检索原因'), `无检索降级原因时不应出现该行，实际 "${healthyText}"`)

  // 复制 run_id / request_id：调用 stub 成功并出现"已复制"反馈。
  // 反馈按字段独立显示，断言各自行内的文案，避免两条"已复制"触发 strict mode 冲突。
  await page.getByLabel('复制运行 ID run-diag-ok').click()
  const runRowText = await page.locator('.ai-run-diagnostics').nth(0).locator('.ai-run-diagnostics__id').nth(1).innerText()
  check(runRowText.includes('已复制'), `复制运行 ID 后应显示已复制，实际 "${runRowText}"`)
  const copied = await page.evaluate(() => window.__copiedTexts || [])
  check(copied.includes('run-diag-ok'), `复制运行 ID 应写入剪贴板，实际 ${JSON.stringify(copied)}`)
  await page.getByLabel('复制请求 ID req-run-diag-ok').click()
  const requestRowText = await page.locator('.ai-run-diagnostics').nth(0).locator('.ai-run-diagnostics__id').nth(0).innerText()
  check(requestRowText.includes('已复制'), `复制请求 ID 后应显示已复制，实际 "${requestRowText}"`)
  const copied2 = await page.evaluate(() => window.__copiedTexts || [])
  check(copied2.includes('req-run-diag-ok'), `复制请求 ID 应写入剪贴板，实际 ${JSON.stringify(copied2)}`)

  // "打开运行记录"只做诚实跳转，不带伪造的 run 过滤参数。
  const links = page.locator('.ai-run-diagnostics__link')
  check(await links.count() === 1, `每条诊断应有 1 个运行记录入口，实际 ${await links.count()}`)
  const href = await links.first().getAttribute('href')
  check(href === '/operations/runs', `运行记录入口应指向 /operations/runs，实际 "${href}"`)

  // 场景 2：降级 + 检索降级 + 纠察 REJECTED。
  await page.getByLabel('输入消息', { exact: true }).fill('模型不可用时还能回答吗')
  await page.locator('.ai-chat-send').click()
  await page.locator('.ai-chat-status--degraded').waitFor()
  await page.locator('.ai-chat-status--rejected').waitFor()
  await page.locator('.ai-run-diagnostics').nth(1).waitFor()
  await openDetails(1)
  const degradedText = await diagnosticsText(1)
  check(degradedText.includes('已回落到 mock-local'), `降级行应显示回落目标，实际 "${degradedText}"`)
  check(degradedText.includes('降级原因') && degradedText.includes('真实模型不可用，已回落到本地 mock'), `应显示降级原因，实际 "${degradedText}"`)
  check(degradedText.includes('无命中'), `应显示 RAG 无命中，实际 "${degradedText}"`)
  check(degradedText.includes('检索原因') && degradedText.includes('知识服务 503，已跳过检索'), `应显示检索降级原因，实际 "${degradedText}"`)
  check(degradedText.includes('0 条'), `无引用时应显示 0 条，实际 "${degradedText}"`)
  check(degradedText.includes('REJECTED · HIGH · 状态核验失败'), `应显示纠察结论，实际 "${degradedText}"`)

  const stored = await page.evaluate(key => JSON.parse(localStorage.getItem(key) || '{}')?.conversations?.[0]?.messages, HISTORY_KEY)
  check(Number.isFinite(stored?.at(-1)?.firstTokenMs), `首 token 耗时应持久化，实际 ${JSON.stringify(stored?.at(-1)?.firstTokenMs)}`)
  check(Number.isFinite(stored?.at(-1)?.totalMs), `总耗时应持久化，实际 ${JSON.stringify(stored?.at(-1)?.totalMs)}`)

  // 刷新后诊断字段必须仍完整。
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.locator('.chat-page').waitFor()
  await page.locator('.ai-run-diagnostics').nth(1).waitFor()
  await openDetails(0)
  const reloadedHealthy = await diagnosticsText(0)
  check(reloadedHealthy.includes('openai-compatible:qwen2.5-7b'), `刷新后应保留 effective provider，实际 "${reloadedHealthy}"`)
  check(reloadedHealthy.includes('2 条'), `刷新后应保留引用数，实际 "${reloadedHealthy}"`)
  check(reloadedHealthy.includes('PASS · INFO · 全部检查通过'), `刷新后应保留 inspection，实际 "${reloadedHealthy}"`)
  check(/首 token[^\n]*\n?[^\n]*\d+ ms/.test(reloadedHealthy), `刷新后应保留首 token 耗时，实际 "${reloadedHealthy}"`)
  await openDetails(1)
  const reloadedDegraded = await diagnosticsText(1)
  check(reloadedDegraded.includes('真实模型不可用，已回落到本地 mock'), `刷新后应保留降级原因，实际 "${reloadedDegraded}"`)
  check(reloadedDegraded.includes('知识服务 503，已跳过检索'), `刷新后应保留检索降级原因，实际 "${reloadedDegraded}"`)
  check(reloadedDegraded.includes('REJECTED · HIGH · 状态核验失败'), `刷新后应保留纠察结论，实际 "${reloadedDegraded}"`)
  const reloadedHref = await page.locator('.ai-run-diagnostics__link').first().getAttribute('href')
  check(reloadedHref === '/operations/runs', `刷新后运行记录入口应仍指向 /operations/runs，实际 "${reloadedHref}"`)
} catch (error) {
  failures.push(`执行异常：${error.message}`)
} finally {
  await browser.close()
}

const result = {
  task: 'P1-RUN-02',
  fixture: true,
  provider_e2e: false,
  scenarios: 2,
  streamCalls,
  checks: 32,
  pageErrors,
  failures
}
console.log(JSON.stringify(result, null, 2))
process.exitCode = failures.length || pageErrors.length ? 1 : 0
