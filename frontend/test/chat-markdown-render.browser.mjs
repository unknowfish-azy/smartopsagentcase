// 全对话出口 Markdown 渲染验收（2026-11-16）：
//   截图场景：用户问「给我来几个简单的运维操作指令」，助手回复含 **加粗**、有序列表、
//   ```bash 围栏代码块、无序说明行。修复前这些符号以纯文本原样显示。
//   本脚本以 fixture 流式返回该回复，断言三处出口均渲染为真实 DOM（strong/ol/pre/code），
//   且代码块内容被转义（不产生可执行节点），流式过程中保持纯文本。
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

const ANSWER = [
  '以下是一些简单的运维操作指令，适用于日常运维工作：',
  '1. **查看系统状态**',
  '```bash',
  'systemctl status <service>',
  '```',
  '- 用于查看某个服务是否正在运行。',
  '2. **查看进程信息**',
  '```bash',
  'ps aux',
  '```'
].join('\n')

const json = data => ({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })
const sse = lines => ({ status: 200, headers: { 'content-type': 'text/event-stream; charset=utf-8' }, body: lines.map(line => line.endsWith('\n') ? `${line}\n` : line).join('') })
const run = id => ({ request_id: `req-${id}`, task_id: `task-${id}`, run_id: id, schema_version: '1.0.0', source: 'ai-service', status: 'succeeded', timestamp: new Date().toISOString() })

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
    const r = run('run-md-1')
    // 内容只由 token 事件累积；done 只带运行元数据（与真实 ai-service 契约一致）
    return route.fulfill(sse([
      `event: token\ndata: ${JSON.stringify({ delta: ANSWER })}\n`,
      `event: done\ndata: ${JSON.stringify({
        provider: 'ollama', model: 'qwen2.5:3b', trust_score: 0, citations: [], evidence: [],
        metadata: { run_event: r, effective_provider: 'ollama', degraded: false },
      })}\n`,
    ]))
  }
  return route.fulfill(json([]))
})
await page.addInitScript(() => {
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 42, username: 'mm-user', role: 'operator' }))
  localStorage.setItem('smartops_theme', 'dark')
})

const assertMarkdown = async (root, label) => {
  const md = root.locator('.ai-chat-markdown').first()
  check(await md.count() === 1, `${label}：助手回复应使用 .ai-chat-markdown 容器`)
  if (!await md.count()) return
  const html = await md.innerHTML()
  const text = await md.innerText()
  check(!text.includes('**'), `${label}：不应残留字面 ** 加粗符号，实际 "${text}"`)
  check(!text.includes('```'), `${label}：不应残留字面围栏符号，实际 "${text}"`)
  check(await md.locator('strong').count() >= 2, `${label}：应渲染至少 2 个 <strong>`)
  check(await md.locator('ol li').count() >= 2, `${label}：应渲染有序列表`)
  check(await md.locator('pre code').count() >= 2, `${label}：应渲染至少 2 个代码块`)
  check(html.includes('&lt;service&gt;'), `${label}：代码块内 <service> 应被转义`)
  check(!html.includes('<service>'), `${label}：代码块不应注入真实标签`)
  check(await md.locator('ul li').count() >= 1, `${label}：应渲染无序说明列表`)
}

try {
  await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' })
  await page.locator('.xiaoyu-card').waitFor()

  // 场景一：首页小鱼卡（截图位置）
  await page.locator('.xiaoyu-input textarea').fill('给我来几个简单的运维操作指令')
  await page.locator('.xiaoyu-send').click()
  await page.locator('.xiaoyu-thread .ai-chat-markdown').waitFor()
  await assertMarkdown(page.locator('.xiaoyu-thread'), '首页小鱼卡')

  // 场景二：桌宠浮窗共用同一 store，消息应同样渲染
  const pet = page.locator('.ops-spider-pet')
  if (await pet.count()) {
    const chatButton = pet.locator('button[aria-label="打开 AI 对话"], button[title="AI 对话"]').first()
    if (await chatButton.count()) {
      await chatButton.click()
      await page.locator('.pet-chat__message--assistant .ai-chat-markdown').waitFor()
      await assertMarkdown(page.locator('.pet-chat'), '桌宠对话')
    }
  }

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
console.log('ALL PASS — 全对话出口 Markdown 渲染验收通过')
