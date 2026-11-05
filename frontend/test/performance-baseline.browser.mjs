// 性能基线（P1-PERF-01）：FCP/LCP、应答渲染延迟、长会话堆内存与卡顿帧。
// 事实边界：本脚本使用本机 Edge + 全量 API fixture，输出一律 fixture=true / provider_e2e=false，
// 只代表前端工程链路，不能当作真实 Provider 延迟或平台端到端性能。
//
// 用法：
//   node test/performance-baseline.browser.mjs                       # 默认 20 次采样
//   SMARTOPS_PERF_ITERATIONS=20 node ...                            # 指定采样次数
//   SMARTOPS_PERF_SOAK_MINUTES=20 node ...                          # 追加真实 20 分钟长会话 soak
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { execSync } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'

const iterations = Number(process.env.SMARTOPS_PERF_ITERATIONS || 20)
const soakMinutes = Number(process.env.SMARTOPS_PERF_SOAK_MINUTES || 0)
const longMessages = Number(process.env.SMARTOPS_PERF_LONG_MESSAGES || 300)

const root = process.cwd().replace(/\\frontend$/, '')
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '')
const artifact = `${root}\\.runtime\\performance-${stamp}`
await mkdir(artifact, { recursive: true })

const port = 4410 + Math.floor(Math.random() * 80)
const base = `http://127.0.0.1:${port}`
const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
  cwd: `${root}\\frontend`,
  stdio: 'ignore'
})
for (let attempt = 0; attempt < 150; attempt++) {
  try { const response = await fetch(base); if (response.ok) break } catch {}
  await new Promise(resolve => setTimeout(resolve, 100))
}

let commit = 'unknown'
try { commit = execSync('git rev-parse HEAD', { cwd: root }).toString().trim() } catch {}

const browser = await chromium.launch({
  executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  headless: true
})

const percentile = (values, p) => {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1))
  return Number(sorted[index].toFixed(1))
}
const summary = values => ({ n: values.length, p50: percentile(values, 50), p95: percentile(values, 95), p99: percentile(values, 99), max: percentile(values, 100) })

async function preparePage() {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  page.setDefaultTimeout(15000)
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  // fixture 模式下 Vite HMR websocket 被主动关闭、未 mock 的接口返回 501，属预期噪音，单独记录不计失败。
  const noise = []
  page.on('console', message => {
    if (message.type() === 'error') noise.push(message.text())
  })

  await page.route(url => url.pathname.startsWith('/api/') || url.pathname.startsWith('/ai/'),
    route => route.fulfill({ status: 501, json: { code: 501, message: 'unknown fixture route' } }))
  await page.routeWebSocket('**/*', socket => socket.close())
  await page.route('**/api/assistant/options', route => route.fulfill({
    json: { code: 200, data: { selectedKey: 'mini', options: [{ key: 'mini', name: '智维 Mini', kind: 'builtin', model: 'fixture', enabled: true, available: true, status: 'ready' }] } }
  }))
  await page.route('**/api/conversations', route => route.fulfill({ json: { code: 200, data: [] } }))
  await page.route('**/api/auth/session', route => route.fulfill({
    json: { code: 200, data: { user: { id: 77, username: 'perf-user', role: 'operator' }, csrfToken: 'perf-csrf' } }
  }))
  await page.route('**/api/auth/registration', route => route.fulfill({ json: { code: 200, data: { enabled: false } } }))
  await page.route('**/ai/api/chat/stream', route => {
    const run = { request_id: 'req-perf', task_id: 'task-perf', run_id: 'run-perf', event_id: 'event-perf', schema_version: '1.0.0', source: 'ai-service', status: 'started', timestamp: new Date().toISOString(), step_id: 'step-answer' }
    const sse = [
      `event: run\ndata: ${JSON.stringify(run)}\n`,
      `event: thinking\ndata: ${JSON.stringify({ ...run, status: 'running', delta: '检索知识库' })}\n`,
      `event: token\ndata: ${JSON.stringify({ ...run, delta: '请先检查磁盘使用率，' })}\n`,
      `event: token\ndata: ${JSON.stringify({ ...run, delta: '再清理日志与临时文件。' })}\n`,
      `event: done\ndata: ${JSON.stringify({ ...run, status: 'succeeded', content: '请先检查磁盘使用率，再清理日志与临时文件。', citations: [{ source: 'reference/disk.md', content: 'df -h' }], metadata: { degraded: true, run_event: { ...run, status: 'succeeded' } }, run_event: { ...run, status: 'succeeded' } })}\n`
    ].join('\n')
    return route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream; charset=utf-8' }, body: sse })
  })
  await page.addInitScript(() => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 77, username: 'perf-user', role: 'operator' }))
    localStorage.setItem('smartops_theme', 'light')
    // 卡顿帧采样：记录相邻 rAF 间隔，> 50ms 计为一次掉帧。
    window.__perfFrames = { total: 0, slow: 0, maxGap: 0 }
    let previous = performance.now()
    const tick = now => {
      const gap = now - previous
      previous = now
      window.__perfFrames.total += 1
      if (gap > 50) window.__perfFrames.slow += 1
      if (gap > window.__perfFrames.maxGap) window.__perfFrames.maxGap = Number(gap.toFixed(1))
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })
  return { page, errors, noise }
}

// 读取 paint / LCP；PerformanceObserver 需在页面内注册，这里等 1.2s 让 LCP 稳定。
async function readPaint(page) {
  return page.evaluate(() => new Promise(resolve => {
    const out = { fcp: 0, lcp: 0 }
    try {
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
          if (entry.name === 'first-contentful-paint') out.fcp = entry.startTime
        }
      }).observe({ type: 'paint', buffered: true })
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) { out.lcp = entry.startTime }
      }).observe({ type: 'largest-contentful-paint', buffered: true })
    } catch {}
    setTimeout(() => resolve({ fcp: Number(out.fcp.toFixed(1)), lcp: Number(out.lcp.toFixed(1)) }), 1200)
  }))
}

const heapMb = async page => page.evaluate(() => {
  const memory = performance.memory
  return memory ? Number((memory.usedJSHeapSize / 1048576).toFixed(2)) : null
})

const messageCount = page => page.evaluate(async () => {
  const { useAiChatStore } = await import('/src/stores/aiChat.js')
  const store = useAiChatStore()
  return store.conversations.find(item => item.id === store.activeId)?.messages.length ?? 0
})

const loads = []
const answers = []
const heaps = []
const longSession = { enabled: false }
const soak = { enabled: false }
const pageErrors = []
const consoleNoise = []

try {
  // ---- 阶段 1：页面加载 FCP/LCP（先 warm-up 2 次不计入，再采样 iterations 次）----
  for (let index = 0; index < iterations + 2; index++) {
    const { page, errors, noise } = await preparePage()
    const startedAt = Date.now()
    await page.goto(`${base}/chat`, { waitUntil: 'domcontentloaded' })
    await page.locator('.chat-page').waitFor()
    const paint = await readPaint(page)
    const loadMs = Date.now() - startedAt
    pageErrors.push(...errors)
    consoleNoise.push(...noise)
    if (index >= 2) loads.push({ ...paint, loadMs, heapMb: await heapMb(page) })
    await page.close()
  }

  // ---- 阶段 2：发送 → 应答渲染延迟（fixture SSE，无 Provider 延迟）----
  {
    const { page, errors, noise } = await preparePage()
    await page.goto(`${base}/chat`, { waitUntil: 'domcontentloaded' })
    await page.locator('.chat-page').waitFor()
    await page.getByText('智维 Mini · 运行时就绪', { exact: true }).waitFor()
    for (let index = 0; index < iterations + 2; index++) {
      if (index > 0) await page.getByRole('button', { name: '新建对话', exact: true }).click()
      await page.getByLabel('输入消息', { exact: true }).fill(`基线采样 ${index}`)
      const startedAt = Date.now()
      await page.locator('.ai-chat-send').click()
      await page.getByText('请先检查磁盘使用率，再清理日志与临时文件。', { exact: true }).waitFor()
      if (index >= 2) answers.push(Date.now() - startedAt)
    }
    pageErrors.push(...errors)
    consoleNoise.push(...noise)
    await page.close()
  }

  // ---- 阶段 3：长会话堆内存与卡顿（模拟长会话，非真实 20 分钟）----
  {
    const { page, errors, noise } = await preparePage()
    await page.goto(`${base}/chat`, { waitUntil: 'domcontentloaded' })
    await page.locator('.chat-page').waitFor()
    const batch = 50
    const heapSeries = []
    for (let sent = 0; sent < longMessages; sent += batch) {
      await page.evaluate(async count => {
        const { useAiChatStore } = await import('/src/stores/aiChat.js')
        const store = useAiChatStore()
        // messages 是 activeConversation.messages 的 computed，必须写入会话本身才会触发渲染。
        if (!store.activeConversation) store.newConversation()
        const conversation = store.conversations.find(item => item.id === store.activeId)
        for (let index = 0; index < count; index++) {
          conversation.messages.push({
            id: `perf-${conversation.messages.length}-${index}`,
            role: index % 2 === 0 ? 'user' : 'assistant',
            content: '长会话压力样本：检查磁盘、内存与网络指标，输出处置建议。'.repeat(6),
            thinking: [{ label: '检索', detail: '匹配参考文档' }],
            metadata: {}
          })
        }
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      }, batch)
      const memory = await heapMb(page)
      if (memory !== null) heapSeries.push(memory)
      heaps.push(memory)
    }
    const frames = await page.evaluate(() => window.__perfFrames)
    longSession.enabled = true
    longSession.messages = await page.evaluate(async () => {
      const { useAiChatStore } = await import('/src/stores/aiChat.js')
      const store = useAiChatStore()
      return store.conversations.find(item => item.id === store.activeId)?.messages.length ?? 0
    })
    longSession.renderedArticles = await page.locator('.ai-chat-message').count()
    longSession.heapStartMb = heapSeries[0] ?? null
    longSession.heapEndMb = heapSeries.at(-1) ?? null
    longSession.heapGrowthMb = heapSeries.length > 1 ? Number((heapSeries.at(-1) - heapSeries[0]).toFixed(2)) : null
    longSession.heapSeriesMb = heapSeries
    longSession.frames = frames
    pageErrors.push(...errors)
    consoleNoise.push(...noise)
    await page.close()
  }

  // ---- 阶段 4（可选）：真实 soak，按分钟持续交互，采样内存与掉帧 ----
  if (soakMinutes > 0) {
    const { page, errors, noise } = await preparePage()
    await page.goto(`${base}/chat`, { waitUntil: 'domcontentloaded' })
    await page.locator('.chat-page').waitFor()
    await page.getByText('智维 Mini · 运行时就绪', { exact: true }).waitFor()
    const samples = []
    const until = Date.now() + soakMinutes * 60 * 1000
    let turn = 0
    while (Date.now() < until) {
      turn += 1
      // 保持同一会话连续问答：这才是"长会话演示"，新建会话会重置上下文与 DOM。
      const before = await messageCount(page)
      await page.getByLabel('输入消息', { exact: true }).fill(`soak ${turn}`)
      const startedAt = Date.now()
      await page.locator('.ai-chat-send').click()
      // 等消息条数真正增加（DOM 只渲染最近 30 条，不能用元素数量判断）。
      await page.waitForFunction(async previous => {
        const { useAiChatStore } = await import('/src/stores/aiChat.js')
        const store = useAiChatStore()
        const messages = store.conversations.find(item => item.id === store.activeId)?.messages ?? []
        return messages.length > previous && !messages.at(-1)?.pending
      }, before, { timeout: 15000 })
      samples.push({
        atMinute: Number(((soakMinutes * 60 * 1000 - (until - Date.now())) / 60000).toFixed(1)),
        answerMs: Date.now() - startedAt,
        heapMb: await heapMb(page)
      })
      await page.waitForTimeout(1000)
    }
    const frames = await page.evaluate(() => window.__perfFrames)
    soak.enabled = true
    soak.minutes = soakMinutes
    soak.turns = samples.length
    soak.slowFrames = frames.slow
    soak.totalFrames = frames.total
    soak.maxFrameGapMs = frames.maxGap
    soak.answerMs = summary(samples.map(sample => sample.answerMs))
    soak.heapSeriesMb = samples.map(sample => sample.heapMb).filter(value => value !== null)
    soak.samples = samples
    pageErrors.push(...errors)
    consoleNoise.push(...noise)
    await page.close()
  }
} finally {
  await browser.close()
  if (!vite.killed) vite.kill()
}

const report = {
  task: 'P1-PERF-01',
  fixture: true,
  provider_e2e: false,
  note: '本机 Edge + 全量 API fixture；只代表前端工程链路，不含真实 Provider/服务端延迟。',
  environment: {
    base,
    commit,
    node: process.version,
    viewport: '1440x1000',
    iterations,
    headless: true,
    memoryApi: 'performance.memory.usedJSHeapSize'
  },
  load: {
    fcp: summary(loads.map(load => load.fcp).filter(value => value > 0)),
    lcp: summary(loads.map(load => load.lcp).filter(value => value > 0)),
    readyMs: summary(loads.map(load => load.loadMs))
  },
  answer: summary(answers),
  longSession,
  soak,
  frameJank: longSession.frames,
  pageErrors,
  consoleNoiseCount: consoleNoise.length,
  raw: { loads, answers, heaps }
}

await writeFile(`${artifact}\\baseline.json`, JSON.stringify(report, null, 2))
console.log(JSON.stringify({
  artifact,
  load: report.load,
  answer: report.answer,
  longSession: {
    messages: longSession.messages,
    rendered: longSession.renderedArticles,
    heapStartMb: longSession.heapStartMb,
    heapEndMb: longSession.heapEndMb,
    slowFrames: longSession.frames?.slow,
    maxFrameGapMs: longSession.frames?.maxGap
  },
  soak: soak.enabled ? { minutes: soak.minutes, turns: soak.turns, slowFrames: soak.slowFrames, maxFrameGapMs: soak.maxFrameGapMs } : 'skipped',
  pageErrors
}, null, 2))
process.exitCode = pageErrors.length ? 1 : 0
