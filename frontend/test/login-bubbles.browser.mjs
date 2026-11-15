import { chromium } from 'playwright'

const base = 'http://localhost:5173'
const browser = await chromium.launch({ headless: true, channel: 'msedge' })
const results = []
const check = (name, ok, extra = '') => { results.push(`${ok ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); if (!ok) process.exitCode = 1 }

async function setup(page, visual) {
  await page.addInitScript(v => { localStorage.setItem('smartops_theme', 'dark'); localStorage.setItem('smartops_visual_mode', v) }, visual)
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    const data = path === '/api/auth/session' ? { user: null, csrfToken: 'mock-csrf' } : path === '/api/auth/human-verification' ? { enabled: false, available: true, required: false, provider: 'none' } : { enabled: true, userPasswordMinLength: 12, adminPasswordMinLength: 16, passwordMaxBytes: 72 }
    return route.fulfill({ json: { code: 200, data } })
  })
  await page.goto(`${base}/login`, { waitUntil: 'networkidle' })
}

// 1. balanced：气泡层挂载 10 颗，动画运行中（两帧位置不同）
const p1 = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await setup(p1, 'balanced')
await p1.locator('.login-bubbles').waitFor()
check('balanced: 10 颗气泡挂载', await p1.locator('.login-bubbles span').count() === 10)
const moved = await p1.evaluate(async () => {
  const s = document.querySelector('.login-bubbles span')
  const a = getComputedStyle(s).transform
  await new Promise(r => setTimeout(r, 700))
  return a !== getComputedStyle(s).transform
})
check('balanced: 气泡动画帧推进', moved)
await p1.screenshot({ path: 'test-artifacts/login-bubbles/dark-balanced.png' })

// 2. 浅色主题气泡令牌
await p1.evaluate(() => { localStorage.setItem('smartops_theme', 'light') })
await p1.getByLabel('选择主题模式').selectOption('light')
await p1.waitForTimeout(200)
const glint = await p1.evaluate(() => getComputedStyle(document.querySelector('.login-shell')).getPropertyValue('--bubble-glint').trim())
check('light: 气泡高光令牌切换', glint.includes('255'), glint)
await p1.screenshot({ path: 'test-artifacts/login-bubbles/light-balanced.png' })

// 3. lightweight：只留 4 颗
await p1.getByLabel('选择视觉模式').selectOption('lightweight')
await p1.waitForTimeout(200)
check('lightweight: 只剩 4 颗可见', await p1.locator('.login-bubbles span:visible').count() === 4)
await p1.close()

// 4. reduced-motion 档：整层不挂载
const p2 = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await setup(p2, 'reduced-motion')
await p2.locator('.login-form').waitFor()
check('reduced-motion: 气泡层不挂载', await p2.locator('.login-bubbles').count() === 0)
await p2.close()

// 5. 系统 prefers-reduced-motion：气泡动画关闭
const p3 = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
await setup(p3, 'balanced')
await p3.locator('.login-bubbles').waitFor()
const anim = await p3.evaluate(() => getComputedStyle(document.querySelector('.login-bubbles span')).animationName)
check('系统 reduce: 气泡动画为 none', anim === 'none', anim)
await p3.close()

// 6. 0 报错
const errors = []
const p4 = await browser.newPage({ viewport: { width: 1440, height: 900 } })
p4.on('pageerror', e => errors.push(e.message))
await setup(p4, 'balanced')
await p4.waitForTimeout(500)
check('控制台无 error', errors.length === 0, errors.join('; '))
await p4.close()

await browser.close()
console.log(results.join('\n'))
