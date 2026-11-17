// 实景还原浏览器回归：路由可达、引擎未接入声明、素材识别与覆盖度、被拒素材提示、
// 开始还原恒为 BLOCKED（绝不出现「已完成」）、与 3D 机房页的衔接、导航落位、
// 无横向溢出、0 pageError。上传走本地临时素材，不依赖后端。
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || process.env.SMARTOPS_VISUAL_BASE_URL
if (!base) {
  console.error('SMARTOPS_BROWSER_BASE_URL is required (run via npm run test:visual)')
  process.exit(1)
}

const root = process.cwd().replace(/\\frontend$/, '')
const artifact = `${root}\\.runtime\\scene-reconstruction\\browser`
const scanDir = `${artifact}\\scan`
await mkdir(scanDir, { recursive: true })
const plyPath = `${scanDir}\\hall.ply`
const txtPath = `${scanDir}\\notes.txt`
await writeFile(plyPath, 'ply\nformat ascii 1.0\nelement vertex 0\nend_header\n')
await writeFile(txtPath, 'not a scan asset\n')

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
const results = []
async function check(name, fn) {
  try { await fn(); results.push({ name, pass: true }) } catch (e) { results.push({ name, pass: false, err: e.message }); throw e }
}

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
  await page.goto(`${base}/reconstruction`, { waitUntil: 'networkidle' })

  await check('路由可达 .rec-page', async () => {
    await page.locator('.rec-page').waitFor()
  })

  await check('引擎未接入声明常驻', async () => {
    const badge = page.locator('.rec-badge--off')
    await badge.waitFor()
    assert.match(await badge.innerText(), /还原引擎未接入/)
  })

  await check('未上传时开始按钮禁用且覆盖度为空态', async () => {
    assert.equal(await page.getByRole('button', { name: '开始还原' }).isDisabled(), true)
    assert.match(await page.locator('.rec-actions__note').innerText(), /还没有可用的扫描素材/)
    assert.equal(await page.locator('.rec-preview__body').filter({ hasText: '占位预览' }).count(), 1)
  })

  await check('上传点云被识别为「点云」并解锁开始', async () => {
    await page.locator('.rec-drop__input').setInputFiles(plyPath)
    const file = page.locator('.rec-files li').first()
    await file.waitFor()
    assert.match(await file.innerText(), /点云/)
    assert.match(await file.innerText(), /hall\.ply/)
    assert.match(await page.locator('.rec-actions__note').innerText(), /具备几何来源/)
    assert.equal(await page.getByRole('button', { name: '开始还原' }).isEnabled(), true)
    assert.match(await page.locator('.rec-head__right').innerText(), /共 1 个素材/)
  })

  await check('不支持的素材进入被拒列表并提示跳过', async () => {
    await page.locator('.rec-drop__input').setInputFiles([plyPath, txtPath])
    await page.locator('.rec-files--rejected li').first().waitFor()
    assert.match(await page.locator('.rec-files--rejected li').first().innerText(), /已跳过/)
    assert.match(await page.locator('.rec-files--rejected li').first().innerText(), /notes\.txt/)
    await page.locator('.rec-note').filter({ hasText: '已跳过 1 个文件' }).waitFor()
  })

  await check('开始还原如实返回 BLOCKED（无伪造进度）', async () => {
    await page.getByRole('button', { name: '开始还原' }).click()
    const note = page.locator('.rec-note--warn')
    await note.waitFor()
    assert.match(await note.innerText(), /还原引擎尚未接入/)
    const firstStage = page.locator('.rec-stages li').first()
    assert.ok((await firstStage.getAttribute('class')).includes('is-blocked'))
    assert.match(await firstStage.innerText(), /依赖缺失/)
    assert.equal(await page.getByText('已完成').count(), 0, '引擎未接入时不得出现任何已完成阶段')
  })

  await check('清空后回到空态', async () => {
    await page.getByRole('button', { name: '清空' }).click()
    await page.locator('.rec-files').waitFor({ state: 'detached' })
    assert.match(await page.locator('.rec-actions__note').innerText(), /还没有可用的扫描素材/)
    assert.equal(await page.getByRole('button', { name: '开始还原' }).isDisabled(), true)
  })

  await check('技术路线指向 3D 机房孪生页', async () => {
    await page.locator('a[href="/sentinel/twin"]').waitFor()
  })

  await check('导航含「实景还原」且指向 /reconstruction', async () => {
    const link = page.locator('a[href="/reconstruction"]')
    await link.first().waitFor()
    assert.match(await link.first().innerText(), /实景还原/)
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

  // 截图保留「已识别素材 + 流水线 blocked」这一忠实状态。
  await page.locator('.rec-drop__input').setInputFiles(plyPath)
  await page.locator('.rec-files li').first().waitFor()
  await page.getByRole('button', { name: '开始还原' }).click()
  await page.locator('.rec-note--warn').waitFor()
  await page.screenshot({ path: `${artifact}/reconstruction-blocked-1440.png`, fullPage: true })

  await check('控制台无 error', async () => assert.deepEqual(errors, []))

  console.log(`PASS scene-reconstruction browser acceptance (${results.filter(r => r.pass).length}/${results.length})`)
  await page.close()
} finally {
  await browser.close()
}
