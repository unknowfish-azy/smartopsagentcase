import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts/login-layout', { recursive: true })
const overlaps = (first, second) => first.x < second.x + second.width && first.x + first.width > second.x && first.y < second.y + second.height && first.y + first.height > second.y

async function geometry(page) {
  const jelly = await page.locator('.login-jellyfish .organism').boundingBox()
  const form = await page.locator('.login-form').boundingBox()
  const copy = await page.locator('.login-copy').boundingBox()
  assert.ok(jelly?.width > 40 && jelly?.height > 40, 'jellyfish remains visible')
  assert.equal(overlaps(jelly, form), false, 'jellyfish must not sit beneath the authentication form')
  assert.equal(overlaps(jelly, copy), false, 'jellyfish must not obscure the title')
  const stage = await page.locator('.login-organisms').boundingBox()
  assert.ok(jelly.x >= stage.x && jelly.y >= stage.y && jelly.x + jelly.width <= stage.x + stage.width && jelly.y + jelly.height <= stage.y + stage.height, 'animated jellyfish stays in its reserved stage')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
}

async function readable(page, selector, pseudo = null) {
  const result = await page.locator(selector).first().evaluate((element, pseudo) => {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 1
    const context = canvas.getContext('2d', { willReadFrequently: true })
    const rgba = color => { context.clearRect(0, 0, 1, 1); context.fillStyle = color; context.fillRect(0, 0, 1, 1); return [...context.getImageData(0, 0, 1, 1).data] }
    const ancestors = []
    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) ancestors.unshift(ancestor)
    let background = [255, 255, 255]
    for (const ancestor of ancestors) {
      const color = rgba(getComputedStyle(ancestor).backgroundColor)
      background = background.map((value, index) => color[index] * color[3] / 255 + value * (1 - color[3] / 255))
    }
    const foreground = rgba(getComputedStyle(element, pseudo).color)
    const composite = background.map((value, index) => foreground[index] * foreground[3] / 255 + value * (1 - foreground[3] / 255))
    const luminance = color => color.map(value => value / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((total, value, index) => total + value * [.2126, .7152, .0722][index], 0)
    const light = luminance(composite), dark = luminance(background)
    return { ratio: (Math.max(light, dark) + .05) / (Math.min(light, dark) + .05), foreground, background }
  }, pseudo)
  assert.ok(result.ratio >= 4.5, `${selector} ${pseudo || ''}: ${JSON.stringify(result)}`)
}

try {
  for (const [width, height, theme] of [[1440, 900, 'light'], [1440, 900, 'dark'], [1280, 720, 'light'], [1024, 768, 'dark'], [768, 1024, 'light'], [375, 812, 'light'], [390, 844, 'dark'], [375, 600, 'light']]) {
    const page = await browser.newPage({ viewport: { width, height }, reducedMotion: 'reduce' })
    const errors = [], requests = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => requests.push(request.url()))
    await page.addInitScript(theme => {
      if (!localStorage.getItem('smartops_theme')) localStorage.setItem('smartops_theme', theme)
      if (!localStorage.getItem('smartops_visual_mode')) localStorage.setItem('smartops_visual_mode', 'balanced')
    }, theme)
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname
      if (!path.startsWith('/api/')) return route.continue()
      assert.equal(route.request().method(), 'GET', 'visual checks never submit real credentials')
      const data = path === '/api/auth/session' ? { user: null, csrfToken: 'mock-csrf' } : path === '/api/auth/human-verification' ? { enabled: false, available: true, required: false, provider: 'none', action: new URL(route.request().url()).searchParams.get('action') } : { enabled: true, userPasswordMinLength: 12, adminPasswordMinLength: 16, passwordMaxBytes: 72 }
      return route.fulfill({ json: { code: 200, data } })
    })
    await page.goto(`${base}/login`, { waitUntil: 'networkidle' })
    await page.locator('.login-jellyfish .body').waitFor()
    await geometry(page)
    for (const selector of ['.login-copy h1', '.login-form h2', '.login-field__label', '.login-form__footer', '.login-form__policy', '.login-submit', '.role-switcher button', '.login-registration button']) await readable(page, selector)
    await readable(page, 'input[autocomplete="username"]', '::placeholder')
    await page.locator('.login-submit').hover()
    await readable(page, '.login-submit')
    await page.screenshot({ path: `test-artifacts/login-layout/${width}-${height}-${theme}-user.png`, fullPage: true })
    await page.getByRole('tab', { name: '管理员层', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: '注册普通账号', exact: true }).count(), 0)
    assert.match(await page.locator('.login-form__footer').innerText(), /10 分钟/)
    await geometry(page)
    await page.getByRole('tab', { name: '用户层', exact: true }).click()
    await page.getByRole('button', { name: '注册普通账号', exact: true }).click()
    await page.getByRole('heading', { name: '注册普通账号', exact: true }).waitFor()
    assert.equal(await page.locator('.login-form__notice').count(), 0, 'opening registration is not registration success')
    assert.equal(await page.locator('.login-form select').count(), 0)
    await geometry(page)
    await page.getByRole('button', { name: '创建普通账号', exact: true }).click()
    await page.getByRole('alert').waitFor()
    await geometry(page)
    await page.screenshot({ path: `test-artifacts/login-layout/${width}-${height}-${theme}-registration.png`, fullPage: true })
    await page.getByRole('button', { name: '返回登录', exact: true }).click()
    for (const appearance of ['dark', 'light']) {
      await page.getByLabel('选择主题模式').selectOption(appearance)
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
      await readable(page, '.login-form__footer')
      await readable(page, '.login-submit')
    }
    await page.getByLabel('选择视觉模式').selectOption('lightweight')
    assert.equal(await page.locator('.meteor-shower').count(), 0)
    assert.equal(await page.locator('.login-jellyfish .particles circle').count(), 120)
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await page.getByLabel('选择视觉模式').selectOption('reduced-motion')
    await page.locator('.login-jellyfish[data-motion-mode="reduced-motion"]').waitFor()
    const still = await page.locator('.login-jellyfish .organism').getAttribute('transform')
    await page.waitForTimeout(180)
    assert.equal(await page.locator('.login-jellyfish .organism').getAttribute('transform'), still)
    if (width === 1440 && theme === 'dark') {
      await page.getByLabel('选择视觉模式').selectOption('balanced')
      await page.locator('.login-jellyfish[data-motion-mode="balanced"]').waitFor()
      const moving = await page.locator('.login-jellyfish .organism').getAttribute('transform')
      for (let sample = 0; sample < 6; sample++) {
        await page.waitForTimeout(500)
        await geometry(page)
      }
      assert.notEqual(await page.locator('.login-jellyfish .organism').getAttribute('transform'), moving)
      await page.reload({ waitUntil: 'networkidle' })
      assert.equal(await page.getByLabel('选择主题模式').inputValue(), 'light')
      assert.equal(await page.getByLabel('选择视觉模式').inputValue(), 'balanced')
    }
    assert.equal(requests.some(url => /vendor-three|\/three(?:\.js|\/)|milky-way-scene/.test(url)), false)
    assert.deepEqual(errors, [])
    await page.close()
    console.log(`PASS ${width}x${height} ${theme}: composition, contrast, auth states, theme and motion`)
  }
} finally {
  await browser.close()
}
