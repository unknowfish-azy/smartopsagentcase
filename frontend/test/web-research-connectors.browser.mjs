// T34 门禁：连接器形态下拉与来源标注实测（API mock，非真实外网证据）。
// 覆盖：来源范围下拉只列已启用检索形态 / fetch-form C 形态选项 / 检索结果 kind 展示 / 桌面 + 390px + reduced-motion / 0 pageError。
import { chromium } from 'playwright'

const BASE = process.env.BASE_URL || 'http://127.0.0.1:5173'
let failures = 0
const check = (name, condition) => {
  console.log(`${condition ? 'PASS' : 'FAIL'}  ${name}`)
  if (!condition) failures++
}

const connectorsFixture = [
  { id: 'DDG', enabled: true, supportsSearch: true },
  { id: 'GITHUB', enabled: true, supportsSearch: true },
  { id: 'BAIDU_PUBLIC', enabled: true, supportsSearch: true },
  { id: 'ZHIHU_PUBLIC', enabled: false, supportsSearch: true },
  { id: 'BAIDU_OFFICIAL', enabled: false, supportsSearch: true },
  { id: 'ZHIHU_OFFICIAL', enabled: false, supportsSearch: true },
  { id: 'BAIDU_URL', enabled: true, supportsSearch: false },
  { id: 'ZHIHU_URL', enabled: false, supportsSearch: false }
]

async function setupMocks(page) {
  await page.route(url => new URL(url).pathname.startsWith('/api/'), route =>
    route.fulfill({ json: { code: 200, data: [] } }))
  await page.route(/\/api\/auth\/session$/, route => route.fulfill({
    json: { code: 200, data: { user: { id: 7, username: 'connector-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'connector-test-csrf' } }
  }))
  await page.route(/\/api\/web-research\/connectors$/, route =>
    route.fulfill({ json: { code: 200, data: connectorsFixture } }))
  await page.route(/\/api\/web-research\/search$/, route => route.fulfill({
    json: { code: 200, data: { taskId: 1, status: 'SUCCESS', query: 'q', scope: 'ALL', results: [
      { id: 'baidu-1', title: '百度公开结果', url: 'https://www.baidu.com/link?url=x', displayUrl: 'https://www.baidu.com/link?url=x', site: 'baidu.com', snippet: '公开页摘要', kind: 'BAIDU_PUBLIC', publishedAt: null, retrievedAt: '2026-11-16T01:00:00Z' }
    ], errors: [], searchedAt: '2026-11-16T01:00:00Z' } }
  }))
  await page.route(/\/api\/web-research\/runtime/, route => route.fulfill({
    json: { code: 200, data: { available: false, model: 'Ollama', detail: 'fixture' } }
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
  await page.waitForSelector('.scope-input select', { timeout: 15000 })

  // 1) 检索范围下拉只列 ALL + 已启用的检索形态（禁用的 ZHIHU_PUBLIC/ZHIHU_OFFICIAL 不出现）
  const options = await page.locator('.scope-input select option').allTextContents()
  check('下拉含全部已启用来源', options.some(text => text.includes('全部已启用来源')))
  check('下拉含 DDG/GITHUB/百度公开页', options.some(text => text.includes('公开网页')) && options.some(text => text.includes('GitHub')) && options.some(text => text.includes('百度 · 公开页')))
  check('禁用形态不出现', !options.some(text => text.includes('知乎')))

  // 2) fetch-form 的 C 形态选项只列已启用的 URL 读取
  const urlScopes = await page.locator('select[aria-label="网址读取形态"] option').allTextContents()
  check('网址读取含静态默认 + 百度链接', urlScopes.some(text => text.includes('静态读取')) && urlScopes.some(text => text.includes('百度链接')))
  check('禁用 C 形态不出现', !urlScopes.some(text => text.includes('知乎链接')))

  // 3) 检索结果 kind 原样展示形态标识
  await page.fill('input[type="search"]', 'kubernetes')
  await page.click('button:has-text("开始检索")')
  await page.waitForSelector('.result-card', { timeout: 8000 })
  check('kind 展示 BAIDU_PUBLIC', (await page.textContent('.result-card .result-kind')).includes('BAIDU_PUBLIC'))

  await page.screenshot({ path: 'test-artifacts/web-research/t34-connectors-desktop.png', fullPage: true })
  await context.close()

  // 4) 390px
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const mpage = await mobile.newPage()
  mpage.on('pageerror', error => errors.push(String(error)))
  await setupMocks(mpage)
  await mpage.goto(BASE + '/web-research', { waitUntil: 'domcontentloaded' })
  await mpage.waitForSelector('.scope-input select', { timeout: 15000 })
  const overflow = await mpage.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check('390px 无横向溢出（容忍 2px）', overflow <= 2)
  await mpage.screenshot({ path: 'test-artifacts/web-research/t34-connectors-mobile.png', fullPage: true })
  await mobile.close()

  // 5) reduced-motion
  const reduced = await browser.newContext({ viewport: { width: 1440, height: 960 }, reducedMotion: 'reduce' })
  const rpage = await reduced.newPage()
  rpage.on('pageerror', error => errors.push(String(error)))
  await setupMocks(rpage)
  await rpage.goto(BASE + '/web-research', { waitUntil: 'domcontentloaded' })
  await rpage.waitForSelector('.scope-input select', { timeout: 15000 })
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
console.log(failures === 0 ? 'ALL PASS' : `FAILED: ${failures}`)
process.exit(failures === 0 ? 0 : 1)
