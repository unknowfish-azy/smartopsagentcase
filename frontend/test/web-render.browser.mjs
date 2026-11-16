// T33 门禁：JS 渲染重试与会话接续 UI 实测（API mock，非真实外网证据）。
// 覆盖：JS 重试按钮态 / 会话状态掩码与流转 / 清除后态 / 桌面 + 390px + reduced-motion / 0 pageError。
// mock 注册顺序：兜底最先，具体后注册覆盖（Playwright 后注册优先）；
// 只锚定根 /api/（勿用 **/api/**，会误匹配 /src/api/*.ts 源码模块致白屏）。
import { chromium } from 'playwright'

const BASE = process.env.BASE_URL || 'http://127.0.0.1:5173'
let failures = 0
const check = (name, condition) => {
  console.log(`${condition ? 'PASS' : 'FAIL'}  ${name}`)
  if (!condition) failures++
}

const sessionState = { configured: false, displayHint: null, expiresAt: null }
const webPage = {
  taskId: 901, url: 'https://docs.example.com/spa-guide', displayUrl: 'https://docs.example.com/spa-guide',
  site: 'docs.example.com', title: 'SPA 指南', excerpt: '客户端渲染正文', content: '客户端渲染正文（JS 渲染证据）',
  contentHash: 'a'.repeat(64), fetchedAt: '2026-11-16T01:00:00Z', renderMode: 'JS', renderNote: 'JS 渲染 · 使用本人登录接续'
}

async function setupMocks(page) {
  await page.route(url => new URL(url).pathname.startsWith('/api/'), route =>
    route.fulfill({ json: { code: 200, data: [] } }))
  await page.route(/\/api\/auth\/session$/, route => route.fulfill({
    json: { code: 200, data: { user: { id: 7, username: 'render-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'render-test-csrf' } }
  }))
  await page.route(/\/api\/web-research\/render-session$/, route => {
    const method = route.request().method()
    if (method === 'GET') return route.fulfill({ json: { code: 200, data: sessionState } })
    if (method === 'DELETE') {
      sessionState.configured = false; sessionState.displayHint = null; sessionState.expiresAt = null
      return route.fulfill({ json: { code: 200, data: sessionState } })
    }
    return route.fulfill({ status: 405, json: { code: 405 } })
  })
  await page.route(/\/api\/web-research\/render-session\/(start|finish)$/, route => {
    if (route.request().url().includes('/start')) {
      sessionState.configured = false; sessionState.displayHint = 'PENDING_LOGIN'
      sessionState.expiresAt = '2026-11-23T00:00:00Z'
    } else {
      sessionState.configured = true; sessionState.displayHint = '会话已加密保存 · 1 条'
      sessionState.expiresAt = '2026-11-23T00:00:00Z'
    }
    return route.fulfill({ json: { code: 200, data: sessionState } })
  })
  await page.route(/\/api\/web-research\/fetch-js$/, route => {
    if (!sessionState.configured) {
      return route.fulfill({ json: { code: 200, data: { ...webPage, renderNote: 'JS 渲染 · 匿名会话' } } })
    }
    return route.fulfill({ json: { code: 200, data: webPage } })
  })
  await page.route(/\/api\/web-research\/tasks/, route => route.fulfill({ json: { code: 200, data: [] } }))
  await page.route(/\/api\/web-research\/runtime/, route => route.fulfill({
    json: { code: 200, data: { available: false, model: 'Ollama', detail: 'fixture' } }
  }))
  await page.route(/\/api\/web-research\/search$/, route => route.fulfill({
    json: { code: 200, data: { taskId: 1, status: 'SUCCESS', query: 'q', scope: 'ALL', results: [], errors: [], searchedAt: '2026-11-16T01:00:00Z' } }
  }))
  await page.route(/\/api\/web-research\/fetch$/, route => route.fulfill({
    json: { code: 200, data: { ...webPage, renderMode: 'STATIC', renderNote: null } }
  }))
  await page.route(/\/api\/web-research\/evidence\/compare$/, route => route.fulfill({
    json: { code: 200, data: { comparisons: [], commonSignals: [], disclaimer: 'fixture', comparedAt: '2026-11-16T01:00:00Z' } }
  }))
}

const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--no-proxy-server', '--proxy-bypass-list=*'] })
const errors = []
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(String(error)))
  await setupMocks(page)

  await page.goto(BASE + '/web-research', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.fetch-form', { timeout: 15000 })

  // 1) 会话未配置态
  check('初始提示为未配置', (await page.textContent('.render-session-state')).includes('未配置'))
  check('打开登录窗口按钮可见', await page.isVisible('button:has-text("打开登录窗口")'))

  // 2) start → PENDING_LOGIN：出现"保存会话"
  await page.click('button:has-text("打开登录窗口")')
  await page.waitForSelector('button:has-text("保存会话")', { timeout: 5000 })
  check('start 后进入 PENDING_LOGIN 提示', (await page.textContent('.render-session-state')).includes('登录窗口已打开'))

  // 3) finish → configured：提示含"已加密保存"与条数掩码（不出现明文 cookie 字样）
  await page.click('button:has-text("保存会话")')
  await page.waitForSelector('.render-session-state:has-text("已加密保存")', { timeout: 5000 })
  check('finish 后提示已加密保存', (await page.textContent('.render-session-state')).includes('1 条'))
  const pageText = await page.textContent('body')
  check('页面不出现明文凭据字样', !pageText.includes('s3cret') && !pageText.includes('sid='))

  // 4) JS 渲染重试：读回正文并显示渲染方式
  await page.fill('input[type="url"]', 'https://docs.example.com/spa-guide')
  await page.click('button:has-text("JS 渲染重试")')
  await page.waitForSelector('.page-evidence', { timeout: 8000 })
  check('JS 渲染回填正文', (await page.textContent('.page-evidence')).includes('SPA 指南'))
  check('渲染方式展示 renderNote', (await page.textContent('.page-evidence')).includes('使用本人登录接续'))

  // 5) 清除会话 → 回到未配置
  await page.click('button:has-text("清除会话")')
  await page.waitForSelector('.render-session-state:has-text("未配置")', { timeout: 5000 })
  check('清除后回到未配置', (await page.textContent('.render-session-state')).includes('未配置'))

  await page.screenshot({ path: 'test-artifacts/web-research/t33-web-render-desktop.png', fullPage: true })
  await context.close()

  // 6) 390px 窄屏
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const mpage = await mobile.newPage()
  mpage.on('pageerror', error => errors.push(String(error)))
  await setupMocks(mpage)
  await mpage.goto(BASE + '/web-research', { waitUntil: 'domcontentloaded' })
  await mpage.waitForSelector('.fetch-form', { timeout: 15000 })
  const overflow = await mpage.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check('390px 无横向溢出（容忍 2px）', overflow <= 2)
  await mpage.screenshot({ path: 'test-artifacts/web-research/t33-web-render-mobile.png', fullPage: true })
  await mobile.close()

  // 7) reduced-motion：页面可加载 0 pageError（本页无强动画依赖，行为不变即通过）
  const reduced = await browser.newContext({ viewport: { width: 1440, height: 960 }, reducedMotion: 'reduce' })
  const rpage = await reduced.newPage()
  rpage.on('pageerror', error => errors.push(String(error)))
  await setupMocks(rpage)
  await rpage.goto(BASE + '/web-research', { waitUntil: 'domcontentloaded' })
  await rpage.waitForSelector('.fetch-form', { timeout: 15000 })
  check('reduced-motion 正常加载', true)
  await reduced.close()
} catch (step) {
  console.log('STEP FAILURE at:', step.message?.split('\n')[0])
  console.log('captured errors:', errors.slice(0, 8))
  process.exit(1)
} finally {
  await browser.close()
}

check('0 pageError', errors.length === 0)
if (errors.length) console.log('pageErrors:', errors.slice(0, 5))
console.log(failures === 0 ? 'ALL PASS' : `FAILED: ${failures}`)
process.exit(failures === 0 ? 0 : 1)
