import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts', { recursive: true })

async function contrast(page, selector) {
  assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).opacity), '1', 'theme must not dim the document root')
  const result = await page.locator(selector).first().evaluate(element => {
    const surface = document.createElement('canvas')
    surface.width = surface.height = 1
    const context = surface.getContext('2d', { willReadFrequently: true })
    const rgba = color => { context.clearRect(0, 0, 1, 1); context.fillStyle = color; context.fillRect(0, 0, 1, 1); return [...context.getImageData(0, 0, 1, 1).data] }
    const ancestors = []
    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) ancestors.unshift(ancestor)
    let background = [255, 255, 255]
    for (const ancestor of ancestors) {
      const color = rgba(getComputedStyle(ancestor).backgroundColor)
      background = background.map((value, index) => color[index] * color[3] / 255 + value * (1 - color[3] / 255))
    }
    const foreground = rgba(getComputedStyle(element).color)
    const composite = background.map((value, index) => foreground[index] * foreground[3] / 255 + value * (1 - foreground[3] / 255))
    const luminance = color => color.map(value => value / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((total, value, index) => total + value * [.2126, .7152, .0722][index], 0)
    const light = luminance(composite), dark = luminance(background)
    return { ratio: (Math.max(light, dark) + .05) / (Math.min(light, dark) + .05), foreground: getComputedStyle(element).color, background }
  })
  assert.ok(result.ratio >= 4.5, `${selector} contrast ${JSON.stringify(result)}`)
}

async function open(width, mode, initialTheme = 'light') {
  const page = await browser.newPage({ viewport: { width, height: 1000 } })
  page.setDefaultTimeout(20000)
  const errors = [], requests = [], serverRequests = [], mutations = []
  const mock = { failServers: false }
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => requests.push(request.url()))
  await page.addInitScript(({ mode, initialTheme }) => {
    localStorage.setItem('smartops_theme', initialTheme)
    localStorage.setItem('smartops_visual_mode', mode)
  }, { mode, initialTheme })
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (route.request().method() !== 'GET') mutations.push(path)
    let data = []
    if (path === '/api/auth/session') data = { user: { id: 81, username: 'demo-theme-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'mock-csrf' }
    if (path.startsWith('/api/servers')) {
      serverRequests.push(path)
      if (mock.failServers) return route.fulfill({ status: 503, json: { code: 503, message: 'mock server list unavailable' } })
      data = [{ id: 501, name: 'real-list-fixture', host: '192.0.2.201', port: 22, os: 'Linux', status: 'ONLINE', description: 'Real-list API fixture, not a connected host' }]
    }
    await route.fulfill({ json: { code: 200, data } })
  })
  return { page, errors, requests, serverRequests, mutations, mock }
}

try {
  for (const width of [375, 1440]) {
    for (const mode of ['balanced', 'lightweight']) {
      const { page, errors, requests, serverRequests, mutations, mock } = await open(width, mode)
      await page.goto(`${base}/servers?view=demo`, { waitUntil: 'networkidle' })
      await page.locator('.demo-banner').waitFor()
      assert.equal(await page.getByRole('button', { name: '演示详情', exact: true }).count(), 6)
      assert.equal(await page.getByRole('button', { name: '编辑', exact: true }).count(), 0)
      assert.equal(await page.getByRole('button', { name: '删除', exact: true }).count(), 0)
      assert.equal(await page.getByRole('button', { name: '添加服务器', exact: true }).isDisabled(), true)
      assert.deepEqual(serverRequests, [])
      await page.getByPlaceholder('搜索服务器名称 / IP地址').fill('mysql')
      assert.equal(await page.getByRole('button', { name: '演示详情', exact: true }).count(), 1)
      await page.getByPlaceholder('搜索服务器名称 / IP地址').fill('')
      for (const theme of ['light', 'dark']) {
        await page.getByLabel('选择主题模式').selectOption(theme)
        await page.waitForFunction(theme => document.documentElement.dataset.theme === theme, theme)
        for (const selector of ['.stat-label', '.stat-value', '.server-source-switch span', '.el-table .host', '.el-tag__content']) await contrast(page, selector)
        await page.getByRole('button', { name: '演示详情', exact: true }).first().click()
        const dialog = page.getByRole('dialog', { name: '虚拟服务器演示详情' })
        await dialog.waitFor()
        await dialog.evaluate(async element => { await Promise.all(element.getAnimations({ subtree: true }).map(animation => animation.finished.catch(() => {}))) })
        assert.match(await dialog.innerText(), /非真实监控/)
        await contrast(page, '.demo-details h2')
        await contrast(page, '.demo-facts dt')
        assert.equal(await dialog.getByRole('meter').count(), 3)
        await page.screenshot({ path: `test-artifacts/server-demo-${mode}-${theme}-${width}.png` })
        await dialog.getByRole('button', { name: '关闭演示' }).click()
      }
      await page.getByPlaceholder('搜索服务器名称 / IP地址').fill('offline')
      await page.getByRole('button', { name: '演示详情', exact: true }).click()
      await page.getByRole('dialog', { name: '虚拟服务器演示详情' }).waitFor()
      assert.equal(await page.getByRole('meter').count(), 0)
      await page.getByRole('button', { name: '关闭演示' }).click()
      assert.deepEqual(serverRequests, [])
      await page.getByRole('button', { name: '真实服务器', exact: true }).click()
      await page.getByText('real-list-fixture', { exact: true }).waitFor()
      assert.equal(await page.locator('.demo-banner').count(), 0)
      assert.equal(await page.locator('.stat-value').first().innerText(), '1')
      await page.getByLabel('选择主题模式').selectOption('light')
      await page.getByRole('button', { name: '添加服务器', exact: true }).hover()
      await contrast(page, '.page-header .el-button--primary span')
      mock.failServers = true
      await page.locator('.table-header').getByRole('button', { name: '刷新' }).click()
      await page.locator('.list-error').waitFor()
      assert.equal(await page.getByRole('button', { name: '演示详情', exact: true }).count(), 0)
      assert.deepEqual(mutations, [])
      assert.equal(requests.some(url => /vendor-three|\/three(?:\.js|\/)|milky-way-scene/.test(url)), false)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
      assert.deepEqual(errors, [])
      await page.close()
      console.log(`PASS servers ${width}px ${mode}: six isolated demos, readonly details, real failures, both themes and contrast`)
    }
  }

  for (const theme of ['light', 'dark']) {
    const { page, errors } = await open(1440, 'lightweight', theme)
    const samples = [
      { path: '/knowledge', selectors: ['.knowledge-hero h1', '.hero-copy', '.search-button', '.search-wrap label', '#knowledge-query', '#knowledge-domain'] },
      { path: '/harbor', selectors: ['.workbench-header h1', '.lede', '.note-card strong', '.note-card small'] },
      { path: '/cloud-native', selectors: ['h1', '.context-panel label', '.domain-card strong'] },
      { path: '/agent', selectors: ['h1', '.page > header > button', '.virtual-agent h2', '.virtual-task strong', '.virtual-task small'] },
      { path: '/model-settings', selectors: ['h1', '.connections-heading p', '.empty h3', '.empty .primary'] }
    ]
    for (const sample of samples) {
      await page.goto(`${base}${sample.path}`, { waitUntil: 'networkidle' })
      for (const selector of sample.selectors) await contrast(page, selector)
      await page.screenshot({ path: `test-artifacts/theme-audit-${sample.path.slice(1)}-${theme}.png` })
      if (sample.path === '/knowledge') {
        assert.equal(await page.locator('.atc-shader').count(), 0)
        await page.getByLabel('选择视觉模式').selectOption('balanced')
        await page.locator(`.atc-shader canvas[data-effect-theme="${theme}"]`).waitFor()
        for (const selector of sample.selectors) await contrast(page, selector)
        const opposite = theme === 'light' ? 'dark' : 'light'
        await page.getByLabel('选择主题模式').selectOption(opposite)
        await page.locator(`.atc-shader canvas[data-effect-theme="${opposite}"]`).waitFor()
        await page.getByLabel('选择主题模式').selectOption(theme)
        await page.locator(`.atc-shader canvas[data-effect-theme="${theme}"]`).waitFor()
        await page.screenshot({ path: `test-artifacts/theme-audit-knowledge-balanced-${theme}.png` })
        await page.getByLabel('选择视觉模式').selectOption('lightweight')
        assert.equal(await page.locator('.atc-shader').count(), 0)
      }
    }
    assert.deepEqual(errors, [])
    await page.close()
    console.log(`PASS ${theme}: knowledge, Harbor, cloud, agent and model page text samples`)
  }

  for (const mode of ['balanced', 'lightweight', 'reduced-motion']) {
    const { page, errors, requests, mutations } = await open(1440, mode, 'dark')
    await page.goto(`${base}/`, { waitUntil: 'networkidle' })
    await page.locator('.home').waitFor()
    const whaleSelector = mode === 'balanced' ? '.whale-host' : '.canvas-whale'
    await page.locator(`${whaleSelector}[data-effect-theme="dark"]`).waitFor()
    const originalWhale = await page.locator(whaleSelector).elementHandle()
    const colors = []
    for (const theme of ['light', 'dark', 'light']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      await page.locator(`${whaleSelector}[data-effect-theme="${theme}"]`).waitFor()
      colors.push(await page.locator(whaleSelector).getAttribute('data-effect-color'))
      assert.equal(await originalWhale.evaluate(element => element.isConnected), true)
      if (mode === 'balanced') {
        await page.locator(`.milky-way[data-effect-theme="${theme}"]`).waitFor()
        assert.equal(await page.locator('.milky-way').getAttribute('data-state'), 'ready', 'WebGL is required for this scene verification')
        assert.equal(await page.locator('.milky-way canvas').evaluate(canvas => getComputedStyle(canvas).visibility), 'visible')
      }
      if (theme === 'light') await page.screenshot({ path: `test-artifacts/effects-${mode}-light.png`, fullPage: true })
    }
    assert.notEqual(colors[0], colors[1])
    assert.equal(colors[0], colors[2])
    if (mode !== 'balanced') assert.equal(requests.some(url => /vendor-three|\/three(?:\.js|\/)|milky-way-scene/.test(url)), false)
    await page.getByLabel('选择视觉模式').selectOption('reduced-motion')
    await page.locator('.canvas-whale').waitFor()
    await page.waitForTimeout(300)
    const still = await page.locator('.canvas-whale').evaluate(canvas => canvas.toDataURL())
    await page.waitForTimeout(300)
    assert.equal(await page.locator('.canvas-whale').evaluate(canvas => canvas.toDataURL()), still)
    assert.deepEqual(errors, [])
    assert.deepEqual(mutations, [])
    await page.close()
    console.log(`PASS homepage ${mode}: live light/dark palette, stable scene identity, resource boundary, reduced-motion`)
  }
} finally { await browser.close() }
