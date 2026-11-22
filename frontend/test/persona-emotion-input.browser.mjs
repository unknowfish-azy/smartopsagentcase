/**
 * P2-8 情绪识别输入 —— 浏览器实测（E3）。
 *
 * 链路：端点（fixture）→ 前端 `withEmotion` 合成 → AgentPersona 状态行如实标注来源档位。
 * 事实边界：
 * - `/api/nn/emotion` 用夹具（不连真实 ai-service），验证的是**前端接线与降级契约**；
 * - 渲染层 expressions 的数值合并由 `persona-emotion-input.test.mjs` 纯函数单测覆盖
 *   （本项渲染层零改动，浏览器只断言「是否生效 + 来源档位文案」）。
 * - 所有 `/api/**` 都需夹具：任何真实 401 会触发 `smartops:unauthorized` 把页面踢回登录。
 */
import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const failures = []
const check = (condition, message) => { if (!condition) failures.push(message) }

const browser = await chromium.launch({
  executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  headless: true
})
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage()
page.setDefaultTimeout(20000)
const pageErrors = []
page.on('pageerror', error => pageErrors.push(error.message))

const json = data => ({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })

const EMOTION_FIXTURES = {
  生气: { available: true, ok: true, reason: null, engine: 'composite+lexicon', status: 'SUCCEEDED', label: 'angry', confidence: 0.8, scores: {}, warnings: [], elapsed_ms: 2 },
  开心: { available: true, ok: true, reason: null, engine: 'composite+model', status: 'SUCCEEDED', label: 'happy', confidence: 0.9, scores: {}, warnings: ['模型为情感极性二分类，仅输出 happy/sad'], elapsed_ms: 20 },
  有点难过: { available: true, ok: true, reason: null, engine: 'composite+model', status: 'SUCCEEDED', label: 'sad', confidence: 0.3, scores: {}, warnings: ['模型为情感极性二分类，仅输出 happy/sad'], elapsed_ms: 20 },
  没装依赖: { available: false, ok: false, reason: '缺少可选依赖', engine: 'none', status: 'UNAVAILABLE', label: 'neutral', confidence: null, scores: {}, warnings: ['缺少可选依赖'], elapsed_ms: 1 }
}

await page.route(url => url.pathname.startsWith('/api/') || url.pathname.startsWith('/ai/'), route => {
  const path = new URL(route.request().url()).pathname
  const request = route.request()
  if (path.endsWith('/auth/session')) {
    return route.fulfill(json({ user: { id: 1, username: 'emotion-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'csrf' }))
  }
  if (path.endsWith('/auth/registration')) return route.fulfill(json({ enabled: false }))
  if (path.endsWith('/auth/human-verification')) return route.fulfill(json({ required: false }))
  if (path.endsWith('/chat/run-token')) return route.fulfill(json({ runToken: 'fixture-run-token' }))
  if (path.endsWith('/inspector/summary')) return route.fulfill(json({ total: 20, pass: 18, warning: 1, high: 1, critical: 0 }))
  if (path.endsWith('/nn/emotion')) {
    const text = request.postDataJSON()?.text ?? ''
    const key = Object.keys(EMOTION_FIXTURES).find(token => text.includes(token)) ?? '没装依赖'
    return route.fulfill(json(EMOTION_FIXTURES[key]))
  }
  if (path.endsWith('/api/chat/stream')) {
    return route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream; charset=utf-8' },
      body: [
        `event: run\ndata: ${JSON.stringify({ request_id: 'req', task_id: 'task', status: 'started' })}\n`,
        `event: token\ndata: ${JSON.stringify({ delta: '先核对磁盘水位。' })}\n`,
        `event: done\ndata: ${JSON.stringify({ answer: '先核对磁盘水位。', status: 'succeeded' })}\n`
      ].join('\n')
    })
  }
  return route.fulfill(json({}))
})

await page.addInitScript(() => {
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 'emotion-test', role: 'operator' }))
})

const emotionText = () => page.evaluate(() => document.querySelector('.persona__emotion')?.textContent?.trim() ?? '')

async function send(text) {
  await page.fill('#persona-chat-input', text)
  await page.click('.persona-view__composer button[type="submit"]')
}

async function waitForEmotion(expected) {
  await page.waitForFunction(
    want => (document.querySelector('.persona__emotion')?.textContent?.trim() ?? '') === want,
    expected,
    { timeout: 15000 }
  )
}

async function waitForNoEmotion() {
  await page.waitForFunction(() => !document.querySelector('.persona__emotion'), null, { timeout: 15000 })
}

try {
  await page.goto(`${base}/agent/persona`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('#persona-chat-input')
  await page.waitForSelector('.persona__status')

  // 初始：无情绪输入 → 不出现情绪标注
  check((await emotionText()) === '', '初始状态不应出现情绪标注')

  // 词典路径：强情绪词 → 如实标注「词典兜底」
  await send('这个故障怎么又出现了，真生气')
  await waitForEmotion('· 情绪：生气（词典兜底）')

  // 模型路径：标注「本地模型」
  await send('今天告警全恢复了，真开心')
  await waitForEmotion('· 情绪：开心（本地模型）')

  // 低置信度：不叠加（0.3 < 默认阈值 0.5）
  await send('我有点难过')
  await waitForNoEmotion()

  // 引擎不可用：不叠加、不伪造 → 标注消失
  await send('没装依赖的环境')
  await waitForNoEmotion()

  // 页面未被 401 踢回登录
  check(page.url().includes('/agent/persona'), `页面被重定向：${page.url()}`)
  check(pageErrors.length === 0, `页面出现运行时错误：${pageErrors.join(' | ')}`)
} catch (error) {
  failures.push(`浏览器实测异常：${error?.message ?? error}`)
} finally {
  await browser.close()
}

if (failures.length) {
  console.error('P2-8 情绪输入浏览器实测失败：')
  for (const item of failures) console.error(` - ${item}`)
  process.exit(1)
}
console.log('P2-8 情绪输入浏览器实测通过：词典兜底 / 本地模型 / 低置信不叠加 / 引擎不可用降级')
