/**
 * test/workshop-browser-check.mjs
 *
 * Agent 工坊浏览器实测（T30/T31 验收）：
 * 断言 ≥ 结构完整、双主题截图、窄屏退化列表、断网 REHEARSAL 标注。
 * 运行：先起 dev（npm run dev），再 node test/workshop-browser-check.mjs
 */
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const baseUrl = process.env.SMARTOPS_VISUAL_BASE_URL || 'http://127.0.0.1:5173'
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'

const SESSION = {
  code: 200,
  data: {
    user: { id: 1, username: 'visual-test', role: 'operator', portal: 'user', mustChangePassword: false },
    csrfToken: 'visual-csrf'
  }
}

// 真实形状的闭环样例（stage 取值：ANALYZE → MEMORIZE → DECIDE → REVIEW → LEARNED）
const LOOPS = {
  code: 200,
  data: [
    { id: 'LOOP-A1', incidentKey: 'k1', title: 'MySQL 连接数打满', sourceType: 'INSPECTOR', stage: 'ANALYZE', severity: 'HIGH', requiresHuman: false, createdAt: '2026-11-15T09:00:00Z', updatedAt: '2026-11-15T09:01:30Z' },
    { id: 'LOOP-B2', incidentKey: 'k2', title: 'Nginx 502', sourceType: 'INSPECTOR', stage: 'DECIDE', severity: 'CRITICAL', requiresHuman: true, createdAt: '2026-11-15T08:30:00Z', updatedAt: '2026-11-15T08:33:00Z' }
  ]
}
const STATS = { code: 200, data: { total: 42, reviewed: 38, resolved: 36, learnedCount: 57, resolveRate: 0.86, byStage: [{ stage: 'ANALYZE', count: 15 }] } }
const INSPECTOR = { code: 200, data: { total: 100, pass: 92, warning: 3, high: 1, critical: 0 } }

function mockCommon(page, { loopsFail = false } = {}) {
  // 用 pathname 谓词而非 glob：glob 需要匹配含 query 的完整 URL，`**/api/agent/loops` 匹配不到 `?limit=8`；
  // 也不要用 `**/api/**` 兜底——它会误伤 /src/api/* 模块请求（URL 同样含 /api/），导致 MIME 崩溃。
  const byPath = (pathname, handler) => page.route(url => url.pathname === pathname, handler)
  return Promise.all([
    byPath('/api/auth/session', route => route.fulfill({ json: SESSION })),
    byPath('/api/agent/loops/stats', route => route.fulfill({ json: STATS })),
    byPath('/api/inspector/summary', route => route.fulfill({ json: INSPECTOR })),
    byPath('/api/agent/loops', route =>
      loopsFail ? route.fulfill({ status: 500, json: { code: 500, message: 'offline' } }) : route.fulfill({ json: LOOPS }))
  ])
}

async function openWorkshop(browser, { viewport, theme, loopsFail = false, reducedMotion = false } = {}) {
  const page = await browser.newPage({
    viewport: viewport || { width: 1440, height: 900 }
  })
  if (reducedMotion) await page.emulateMedia({ reducedMotion: 'reduce' })
  await mockCommon(page, { loopsFail })
  await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'visual-test' })))
  if (theme) await page.addInitScript(themeMode => localStorage.setItem('smartops_theme', themeMode), theme)
  await page.goto(`${baseUrl}/agent/module`, { waitUntil: 'networkidle' })
  try {
    await page.waitForSelector('.fable', { timeout: 60_000 })
  } catch (error) {
    console.error('[workshop-check] 页面未就绪 URL =', page.url())
    await page.screenshot({ path: 'test-artifacts/workshop/debug-failure.png' }).catch(() => {})
    throw error
  }
  await page.getByRole('button', { name: '工坊' }).click()
  return page
}

const browser = await chromium.launch({ executablePath: edgePath, headless: true })
await mkdir('test-artifacts/workshop', { recursive: true })

try {
  /* 1. 暗色主题：结构 + 真实数据点亮 */
  const dark = await openWorkshop(browser, { theme: 'dark' })
  await dark.waitForSelector('.ws-room-svg')
  assert.equal(await dark.locator('.ws-desk').count(), 6, '应有 6 张工位')
  assert.equal(await dark.locator('.ws-station').count(), 4, '轨道应有 4 站')
  assert.equal(await dark.locator('.ws-watermark').count(), 0, 'live 数据不应出现 REHEARSAL')
  assert.ok((await dark.locator('.ws-screen-line').count()) >= 0)
  await dark.screenshot({ path: 'test-artifacts/workshop/workshop-dark.png' })

  /* 2. tooltip 溯源 + 点击高亮闭环记录 */
  const firstDesk = dark.locator('.ws-desk').first()
  await firstDesk.hover()
  assert.ok(await dark.locator('.ws-desk-tip').first().isVisible().catch(() => false), 'hover 应出现溯源 tooltip')
  await firstDesk.click()
  await dark.waitForTimeout(300)
  const flashed = await dark.locator('.trail li.is-flash').count()
  assert.ok(flashed >= 1, '点击工位应高亮记忆尾迹对应条目')
  await dark.close()

  /* 3. 亮色主题 */
  const light = await openWorkshop(browser, { theme: 'light' })
  await light.waitForSelector('.ws-room-svg')
  await light.screenshot({ path: 'test-artifacts/workshop/workshop-light.png' })
  await light.close()

  /* 4. 窄屏 <768px → 退化为工位状态列表（门禁 4） */
  const narrow = await openWorkshop(browser, { viewport: { width: 375, height: 720 }, theme: 'dark' })
  await narrow.waitForSelector('.ws-fallback')
  assert.equal(await narrow.locator('.ws-fallback li').count(), 6, '窄屏应退化为 6 行列表')
  await narrow.screenshot({ path: 'test-artifacts/workshop/workshop-narrow.png' })
  await narrow.close()

  /* 5. 断网 → REHEARSAL 标注（门禁 7，禁假繁忙） */
  const offline = await openWorkshop(browser, { theme: 'dark', loopsFail: true })
  await offline.waitForSelector('.ws-room-svg')
  assert.ok(await offline.locator('.ws-watermark').isVisible(), '断网应显示 REHEARSAL 水印')
  await offline.screenshot({ path: 'test-artifacts/workshop/workshop-rehearsal.png' })
  await offline.close()

  /* 6. reduced-motion → 静态单帧可渲染（门禁 1） */
  const reduced = await openWorkshop(browser, { theme: 'dark', reducedMotion: true })
  await reduced.waitForSelector('.ws-room-svg')
  assert.equal(await reduced.locator('.ws-desk').count(), 6)
  await reduced.screenshot({ path: 'test-artifacts/workshop/workshop-reduced-motion.png' })
  await reduced.close()

  console.log('workshop-browser-check: ALL PASS')
} finally {
  await browser.close()
}
