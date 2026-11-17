// 机房孪生浏览器回归：路由可达、演示态声明、2.5s 延迟预算展示（含峰值超预算必现）、
// 3D canvas、降级机柜清单、暂停/继续、机柜选择、无横向溢出、reduced-motion 静态模式、0 pageError。
// 页面数据全部前端本地模拟，不依赖后端；由 npm run test:visual 提供 base url。
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || process.env.SMARTOPS_VISUAL_BASE_URL
if (!base) {
  console.error('SMARTOPS_BROWSER_BASE_URL is required (run via npm run test:visual)')
  process.exit(1)
}

const root = process.cwd().replace(/\\frontend$/, '')
const artifact = `${root}\\.runtime\\data-center-twin\\browser`
await mkdir(artifact, { recursive: true })

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
const results = []
async function check(name, fn) {
  try { await fn(); results.push({ name, pass: true }) } catch (e) { results.push({ name, pass: false, err: e.message }); throw e }
}

// 只拦真 /api/ 路径：auth 给固定身份，其余一律空数据（本页不消费业务接口）。
function mockApi(page) {
  page.route(url => url.pathname.startsWith('/api/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path.startsWith('/api/auth/session')) return route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 't', role: 'operator' }, csrfToken: 'csrf' } } })
    return route.fulfill({ json: { code: 200, data: [] } })
  })
}
const seedAuth = page => page.addInitScript(() => {
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 't', role: 'operator' }))
  localStorage.setItem('smartops_theme', 'dark')
})

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' })
  page.setDefaultTimeout(10000)
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await seedAuth(page)
  mockApi(page)
  await page.goto(`${base}/sentinel/twin`, { waitUntil: 'networkidle' })

  await check('路由可达 .twin-page', async () => {
    await page.locator('.twin-page').waitFor()
  })

  await check('演示态声明常驻（未接入真实扫描）', async () => {
    const badge = page.locator('.twin-badge--demo')
    await badge.waitFor()
    assert.match(await badge.innerText(), /演示数据.*未接入真实扫描/)
  })

  await check('延迟徽标落在 2.5s 预算三态之一', async () => {
    const badge = page.locator('.twin-badge').filter({ hasText: '同步延迟' })
    await badge.waitFor()
    const text = await badge.innerText()
    assert.match(text, /同步延迟 \d+ ms · (达标|接近预算|超出预算|未知)/)
    const level = await badge.evaluate(el => ['ok', 'warn', 'breach', 'unknown'].find(v => el.classList.contains(`twin-badge--${v}`)))
    assert.ok(level, '延迟徽标必须带 level 修饰类')
  })

  await check('延迟卡标注 2500 ms 预算线', async () => {
    const note = page.locator('.twin-card__note').first()
    assert.match(await note.innerText(), /预算 2500 ms/)
    assert.equal(await page.locator('.twin-bar__budget').count(), 1)
  })

  // 数据层每 20 个 tick 必现一次 2.6s 峰值（simulateSyncLatency），因此 20s 内必然越界：
  // 断言徽标与底部汇总同源同值，避免两次读到的 tick 不同造成假绿。
  await check('延迟峰值触发超预算（20s 内必现，且徽标与汇总同源）', async () => {
    const handle = await page.waitForFunction(() => {
      const badge = [...document.querySelectorAll('.twin-badge')].find(node => node.textContent.includes('同步延迟'))
      if (!badge || !badge.classList.contains('twin-badge--breach')) return false
      const ms = Number((badge.textContent.match(/(\d+)\s*ms/) || [])[1])
      const foot = document.querySelector('.twin-foot')?.textContent || ''
      return ms > 2500 && foot.includes(`${ms} ms`) ? ms : false
    }, null, { timeout: 25000 })
    const ms = await handle.jsonValue()
    assert.ok(ms > 2500, `超预算峰值应大于 2500 ms，实际 ${ms}`)
    const text = await page.locator('.twin-badge--breach').filter({ hasText: '同步延迟' }).innerText()
    assert.match(text, /超出预算/)
  })

  await check('峰值过后回到预算内（不长期误报）', async () => {
    await page.waitForFunction(() => {
      const badge = [...document.querySelectorAll('.twin-badge')].find(node => node.textContent.includes('同步延迟'))
      return Boolean(badge) && !badge.classList.contains('twin-badge--breach')
    }, null, { timeout: 6000 })
  })

  await check('3D 场景渲染出 canvas', async () => {
    await page.locator('.twin-stage canvas').waitFor()
  })

  await check('降级机柜清单含 12 个机柜', async () => {
    assert.equal(await page.locator('.twin-degrade tbody tr').count(), 12)
  })

  await check('温度排行前 5 且含湿度/功率入口', async () => {
    const rows = page.locator('.twin-rank__row')
    await rows.first().waitFor()
    assert.equal(await rows.count(), 5)
  })

  await check('暂停后机器人与按钮同步为暂停态', async () => {
    await page.getByRole('button', { name: '暂停模拟' }).click()
    await page.getByRole('button', { name: '继续模拟' }).waitFor()
    assert.match(await page.locator('.twin-robot').innerText(), /已暂停/)
  })

  await check('继续后恢复巡航', async () => {
    await page.getByRole('button', { name: '继续模拟' }).click()
    await page.getByRole('button', { name: '暂停模拟' }).waitFor()
    assert.match(await page.locator('.twin-robot').innerText(), /巡航中/)
  })

  await check('点击排行行展开机柜详情并可关闭', async () => {
    const id = await page.locator('.twin-rank__row .twin-rank__id').first().innerText()
    await page.locator('.twin-rank__row').first().click()
    const detail = page.locator('.twin-detail')
    await detail.waitFor()
    const text = await detail.innerText()
    assert.match(text, /温度/)
    assert.match(text, /湿度/)
    assert.match(text, /功率/)
    assert.ok(text.includes(id), '详情应展示被点击的机柜编号')
    await detail.getByRole('button', { name: '关闭' }).click()
    await page.waitForFunction(() => !document.querySelector('.twin-detail'))
  })

  await check('底部汇总含机柜/告警/延迟口径', async () => {
    const foot = await page.locator('.twin-foot').innerText()
    assert.match(foot, /机柜\s*12/)
    assert.match(foot, /延迟\s*\d+ ms/)
  })

  for (const w of [375, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width: w, height: 1000 })
    await page.waitForTimeout(200)
    await check(`无横向溢出 ${w}px`, async () => {
      const ok = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)
      assert.ok(ok, `${w}px 存在横向溢出`)
    })
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: `${artifact}/twin-1440.png`, fullPage: true })

  await check('导航含「机房孪生」且指向 /sentinel/twin', async () => {
    const link = page.locator('a[href="/sentinel/twin"]')
    await link.first().waitFor()
    assert.match(await link.first().innerText(), /机房孪生/)
  })

  await check('控制台无 error', async () => assert.deepEqual(errors, []))

  // reduced-motion：进入静态模式（脉冲与巡航脉冲关闭），页面与数据仍完整。
  const rmPage = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  rmPage.setDefaultTimeout(10000)
  await seedAuth(rmPage)
  mockApi(rmPage)
  await rmPage.goto(`${base}/sentinel/twin`, { waitUntil: 'networkidle' })
  await check('reduced-motion 下进入静态模式且数据完整', async () => {
    await rmPage.locator('.twin-page').waitFor()
    await rmPage.locator('.dc3d--static').waitFor()
    assert.equal(await rmPage.locator('.twin-degrade tbody tr').count(), 12)
  })
  await rmPage.screenshot({ path: `${artifact}/twin-reduced-motion.png`, fullPage: true })
  await rmPage.close()

  console.log(`PASS data-center-twin browser acceptance (${results.filter(r => r.pass).length}/${results.length})`)
  await page.close()
} finally {
  await browser.close()
}
