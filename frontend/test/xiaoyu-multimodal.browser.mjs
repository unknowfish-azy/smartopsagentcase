// 首页「小鱼」卡片多模态 + 就地对话契约（2026-11-16）：
//   1. 输入框旁有添加图片入口，可附加 PNG/JPEG，形成待发送缩略图。
//   2. 发送后请求体携带 image_data（真实 base64），images 携带文件名。
//   3. 回答就地渲染在卡片内（.xiaoyu-thread），不发生 /chat 跳转。
//   4. 视觉模型不可用时，错误作为消息就地显示，不伪造看图结果。
// 全部 API 为 fixture，只验证前端传参与渲染契约，不验证模型识别本身。
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || process.env.SMARTOPS_VISUAL_BASE_URL
if (!base) {
  console.error('SMARTOPS_BROWSER_BASE_URL is required (run via npm run test:visual)')
  process.exit(1)
}

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
const run = id => ({ request_id: `req-${id}`, task_id: `task-${id}`, run_id: id, schema_version: '1.0.0', source: 'ai-service', status: 'succeeded', timestamp: new Date().toISOString() })

let streamBody = null
await page.route(url => url.pathname.startsWith('/api/') || url.pathname.startsWith('/ai/'), route => {
  const path = new URL(route.request().url()).pathname
  if (path.endsWith('/auth/session')) return route.fulfill(json({ user: { id: 42, username: 'mm-user', role: 'operator' }, csrfToken: 'mm-csrf' }))
  if (path.endsWith('/auth/registration')) return route.fulfill(json({ enabled: false }))
  if (path.endsWith('/assistant/options')) {
    return route.fulfill(json({ selectedKey: 'mini', options: [{ key: 'mini', name: '智维 Mini', kind: 'builtin', model: 'fixture', enabled: true, available: true, status: 'ready' }] }))
  }
  if (path.endsWith('/chat/run-token')) return route.fulfill(json({ runToken: 'fixture-run-token' }))
  if (path.endsWith('/conversations')) return route.fulfill(json([]))
  if (path.endsWith('/api/chat/stream')) {
    try { streamBody = JSON.parse(route.request().postData() || '{}') } catch { streamBody = null }
    const r = run('run-mm-1')
    return route.fulfill(sse([
      `event: token\ndata: ${JSON.stringify({ delta: '我看这是一张系统截图。' })}\n`,
      `event: done\ndata: ${JSON.stringify({
        provider: 'ollama', model: 'qwen2.5vl:3b', trust_score: 0, citations: [], evidence: [],
        metadata: { run_event: r, images: streamBody?.images || [], effective_provider: 'ollama', degraded: false },
      })}\n`,
    ]))
  }
  return route.fulfill(json([]))
})
await page.addInitScript(() => {
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 42, username: 'mm-user', role: 'operator' }))
  localStorage.setItem('smartops_theme', 'dark')
})

// 1x1 红色 PNG
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==', 'base64')

try {
  await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' })
  await page.locator('.xiaoyu-card').waitFor()

  // 入口存在
  check(await page.locator('.xiaoyu-attach').count() === 1, '应有添加图片入口（.xiaoyu-attach）')
  check((await page.locator('.xiaoyu-input textarea').getAttribute('placeholder') || '').includes('粘贴图片'), '输入框应提示可粘贴图片')

  // 附加一张图片 → 出现待发送缩略图
  await page.locator('.xiaoyu-file').setInputFiles({ name: 'shot.png', mimeType: 'image/png', buffer: PNG })
  await page.locator('.xiaoyu-tray-item').first().waitFor()
  check(await page.locator('.xiaoyu-tray-item').count() === 1, '附加后应显示 1 张待发送缩略图')

  // 发送（带图，文字可为空）
  await page.locator('.xiaoyu-send').click()

  // 就地对话出现，且不跳转到 /chat
  await page.locator('.xiaoyu-thread').waitFor()
  await page.waitForTimeout(500)
  check(page.url().endsWith('/') || page.url().endsWith('/#/'), `发送后不应跳转到 /chat，实际 URL=${page.url()}`)
  const threadText = await page.locator('.xiaoyu-thread').innerText()
  check(threadText.includes('我看这是一张系统截图'), `回答应就地显示，实际 "${threadText}"`)
  check(await page.locator('.xiaoyu-msg--user .xiaoyu-msg-images img').count() >= 1, '用户消息应显示附图缩略图')

  // 请求体契约：image_data 带真实 base64，images 带文件名
  check(streamBody !== null, '应发出 /api/chat/stream 请求')
  check(Array.isArray(streamBody?.image_data) && streamBody.image_data.length === 1, 'image_data 应含 1 张图')
  check(String(streamBody?.image_data?.[0] || '').startsWith('data:image/png;base64,'), 'image_data 应为 data URL base64')
  check(Array.isArray(streamBody?.images) && streamBody.images.includes('shot.png'), 'images 应携带文件名作证据标签')

  // 快捷入口就地填充，不跳转
  const beforeUrl = page.url()
  await page.locator('.xiaoyu-quick').first().click()
  check(page.url() === beforeUrl, '快捷入口不应跳转')
  const filled = await page.locator('.xiaoyu-input textarea').inputValue()
  check(filled.includes('体检'), `快捷入口应就地填充问题，实际 "${filled}"`)

  check(pageErrors.length === 0, `页面不应有 JS 错误：${pageErrors.join(' | ')}`)
} catch (error) {
  failures.push(`脚本异常：${error.message}`)
} finally {
  await browser.close()
}

if (failures.length) {
  console.error('FAIL')
  for (const item of failures) console.error(' -', item)
  process.exit(1)
}
console.log('ALL PASS — 小鱼卡片多模态 + 就地对话契约通过')
