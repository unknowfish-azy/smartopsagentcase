import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

/**
 * 智能体模块（/agent/module）浏览器验收。
 *
 * 覆盖：五种构成状态的可见切换、构成参数的数值联动、运行时/离线标签、
 * 三个断点无横向溢出、减少动效下无持续动画、浅色纸面不被全局 .panel 规则污染、
 * 以及正文与按钮的对比度。接口一律用测试夹具，不读取真实运维数据。
 */

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts', { recursive: true })

const sessionBody = {
  code: 200,
  message: 'ok',
  data: {
    user: { id: 91, username: 'module-test', role: 'operator', portal: 'user', mustChangePassword: false },
    csrfToken: 'module-csrf'
  }
}

async function openModule({ width = 1440, height = 1000, theme = 'dark', reduced = false, offline = false } = {}) {
  const context = await browser.newContext({
    viewport: { width, height },
    colorScheme: theme === 'dark' ? 'dark' : 'light',
    reducedMotion: reduced ? 'reduce' : 'no-preference'
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))

  await page.route('**/api/auth/session', route => route.fulfill({ json: sessionBody }))
  await page.route('**/api/inspector/summary', route => route.fulfill(offline
    ? { status: 503, json: { code: 503, message: 'unavailable' } }
    : { json: { code: 200, message: 'ok', data: { total: 20, pass: 18, warning: 1, high: 1, critical: 0 } } }))
  await page.route('**/api/agent/loops**', route => route.fulfill(offline
    ? { status: 503, json: { code: 503, message: 'unavailable' } }
    : { json: { code: 200, message: 'ok', data: [
        { id: 1, title: 'MySQL 连接数打满', stage: 'REVIEW', updatedAt: '2026-11-18T09:20:00Z' },
        { id: 2, title: 'Nginx 502 upstream 超时', stage: 'DECIDE', updatedAt: '2026-11-17T21:05:00Z' }
      ] } }))

  await page.addInitScript(({ mode }) => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'module-test' }))
    localStorage.setItem('smartops_theme', mode)
    localStorage.setItem('smartops_visual_mode', 'balanced')
  }, { mode: theme })

  await page.goto(`${base}/agent/module`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.fable', { timeout: 20000 })
  return { page, context, errors }
}

function contrastOf(locator) {
  return locator.evaluate(element => {
    const parse = color => color.match(/[\d.]+/g).map(Number)
    const luminance = color => parse(color)
      .slice(0, 3)
      .map(value => value / 255)
      .map(value => (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4))
      .reduce((total, value, index) => total + value * [0.2126, 0.7152, 0.0722][index], 0)
    const style = getComputedStyle(element)
    const foreground = luminance(style.color)
    // 向上找到第一层不透明底色：模块里的文字多半落在舞台或面板底色上
    let node = element
    let background = 0
    while (node && node !== document.documentElement) {
      const parentStyle = getComputedStyle(node)
      const channels = parentStyle.backgroundColor.match(/[\d.]+/g)
      if (channels && (channels.length < 4 || Number(channels[3]) > 0.5)) {
        background = luminance(parentStyle.backgroundColor)
        break
      }
      node = node.parentElement
    }
    return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05)
  })
}

try {
  /* 1. 五种状态的构成参数与舞台属性联动 */
  {
    const { page, context, errors } = await openModule()
    assert.equal(await page.locator('.fable').count(), 1)
    assert.equal(await page.locator('.state-strip button').count(), 5)

    const readState = () => page.evaluate(() => {
      const fable = document.querySelector('.fable')
      const shape = document.querySelector('.aperture-shape')
      return {
        state: fable.dataset.state,
        aperture: getComputedStyle(fable).getPropertyValue('--aperture').trim(),
        shapeTransform: getComputedStyle(shape).transform,
        caption: document.querySelector('.stage-caption h2').textContent.trim(),
        params: [...document.querySelectorAll('.cap-params dd')].map(node => node.textContent.trim())
      }
    })

    const seen = new Set()
    const buttons = page.locator('.state-strip button')
    for (let index = 0; index < 5; index += 1) {
      await buttons.nth(index).click()
      await page.waitForTimeout(1000)
      const view = await readState()
      assert.ok(view.state, 'data-state must be set')
      seen.add(view.state)
      assert.equal(await buttons.nth(index).getAttribute('aria-pressed'), 'true')
      assert.match(view.caption, /静观|解析|决断|执行|复盘/)
      assert.equal(view.params.length, 3, `构成参数应为 3 项：${JSON.stringify(view)}`)
      if (view.state !== 'idle') {
        assert.notEqual(view.aperture, '1', `非静观状态的孔径应变化：${JSON.stringify(view)}`)
      }
      assert.notEqual(view.shapeTransform, 'none', '孔径遮罩必须带 scaleY 变换')
    }
    assert.equal(seen.size, 5, `五种状态都应可切换：${[...seen].join(',')}`)

    // 再次点击当前状态：取消演练，回到运行时构成
    await buttons.nth(4).click()
    await page.waitForTimeout(900)
    assert.equal(await page.locator('.seal-reset').count(), 0, '再次点击当前状态应回到运行时构成')

    assert.deepEqual(errors, [])
    await context.close()
  }

  /* 2. 运行时 / 离线标签与真实信号 */
  {
    const { page, context } = await openModule()
    assert.equal(await page.locator('.fable-panel .tag--live').count() >= 1, true)
    const health = await page.locator('.runtime-rows div').nth(1).locator('b').innerText()
    assert.match(health, /\d{1,3}\/100/)
    await page.locator('.btn--primary').click()
    await page.waitForTimeout(200)
    assert.match(await page.locator('.gate-result').innerText(), /仅本页构成演练/)
    await context.close()

    const offline = await openModule({ offline: true })
    const dashboards = await offline.page.locator('.runtime-rows b').allInnerTexts()
    assert.deepEqual(dashboards.slice(1), ['—', '—', '—'], `离线时必须显示占位符：${dashboards.join('|')}`)
    assert.match(await offline.page.locator('.fable-panel .tag--sample').first().innerText(), /SAMPLE/)
    await offline.context.close()
  }

  /* 3. 三个断点无横向溢出 */
  {
    for (const width of [375, 768, 1440]) {
      const { page, context } = await openModule({ width, height: 900 })
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      assert.ok(overflow <= 1, `${width}px 出现横向溢出：${overflow}`)
      if (width === 375) {
        const stripColumns = await page.locator('.state-strip').evaluate(node => getComputedStyle(node).gridTemplateColumns.split(' ').length)
        assert.equal(stripColumns, 2, '窄屏状态条应为两列')
      }
      await context.close()
    }
  }

  /* 4. 减少动效：构成与肥波都不再持续动画 */
  {
    const { page, context } = await openModule({ reduced: true })
    const reduced = await page.evaluate(() => ({
      fable: document.querySelector('.fable').dataset.reduced,
      gazePressed: document.querySelector('.gaze-toggle').getAttribute('aria-pressed'),
      running: document.querySelectorAll('.fat-blob').length
        ? [...document.querySelectorAll('.fat-blob')].some(node => Number(getComputedStyle(node).animationDuration.replace('s', '')) > 0 && getComputedStyle(node).animationName !== 'none')
        : false
    }))
    assert.equal(reduced.fable, 'true')
    assert.equal(reduced.gazePressed, 'false', '减少动效下注视指针默认关闭')
    assert.equal(reduced.running, false, '减少动效下肥波不应继续呼吸')
    await context.close()
  }

  /* 5. 浅色纸面：不被全局 .panel 规则改成白卡，正文保持可读 */
  {
    const { page, context } = await openModule({ theme: 'light' })
    const panelBackground = await page.locator('.fable-panel').first().evaluate(node => getComputedStyle(node).backgroundColor)
    assert.notEqual(panelBackground, 'rgb(255, 255, 255)', '浅色模式下模块面板必须保持纸面底色，而非全局白卡')
    const fableBackground = await page.locator('.fable').evaluate(node => getComputedStyle(node).backgroundColor)
    assert.equal(fableBackground, 'rgb(246, 241, 230)')

    for (const selector of ['.stage-caption h2', '.cap-desc', '.fable-panel-head h3', '.weights .w-label']) {
      const ratio = await contrastOf(page.locator(selector).first())
      assert.ok(ratio >= 4.5, `${selector} 对比度不足：${ratio.toFixed(2)}`)
    }
    await page.screenshot({ path: 'test-artifacts/agent-module-light.png', fullPage: true, animations: 'disabled' })
    await context.close()
  }

  /* 6. 注视指针开关 */
  {
    const { page, context } = await openModule()
    const toggle = page.locator('.gaze-toggle')
    assert.equal(await toggle.getAttribute('aria-pressed'), 'true')
    await toggle.click()
    assert.equal(await toggle.getAttribute('aria-pressed'), 'false')
    await toggle.click()
    assert.equal(await toggle.getAttribute('aria-pressed'), 'true')
    await page.locator('.stage-field').hover({ position: { x: 200, y: 200 } })
    await page.waitForTimeout(400)
    const pupilTransform = await page.locator('.gaze-pupil').evaluate(node => getComputedStyle(node).transform)
    assert.match(pupilTransform, /matrix/, '注视时瞳孔应带位移矩阵')
    await page.screenshot({ path: 'test-artifacts/agent-module-dark.png', fullPage: true, animations: 'disabled' })
    await context.close()
  }

  console.log('agent-module browser checks passed')
} finally {
  await browser.close()
}
