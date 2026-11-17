import assert from 'node:assert/strict'
import { chromium } from 'playwright'

/**
 * REA 工具辐射图浏览器实测（/re-workbench）。
 * 由 test-artifacts/one-off-runners/rea-radiation-check.mjs 转正：
 * 15 条流线、无事件静默、管线点亮/取消、lightweight 与 reduced-motion 降级、
 * balanced 强效果三层动画 + 管线顺序错峰、窄屏无溢出、零 pageerror。
 * 运行方式与其它 *.browser.mjs 一致：先起 dev server，再 node 本文件。
 */
const BASE = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({
  executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  headless: true
})

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const errors = []
  page.on('pageerror', error => errors.push(String(error)))

  // 按路径分发 mock：会话必须返回真实结构，否则路由守卫重定向到 /login
  const json = data => ({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })
  await page.route(url => url.pathname.startsWith('/api/') || url.pathname.startsWith('/ai/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/session')) {
      return route.fulfill(json({ user: { id: 91, username: 'rea-check', role: 'operator' }, csrfToken: 'rea-csrf' }))
    }
    if (path.endsWith('/auth/registration')) return route.fulfill(json({ enabled: false }))
    return route.fulfill(json([]))
  })
  await page.routeWebSocket('**/*', socket => socket.close())
  await page.addInitScript(() => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 91, username: 'rea-check', role: 'operator' }))
  })

  await page.goto(`${BASE}/re-workbench`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.rewb-radia__svg', { timeout: 20000 })

  // 1. 15 条真实工具流线 + a11y 基础
  assert.equal(await page.locator('.rewb-ray').count(), 15, '应有 15 条工具流线')
  assert.equal(
    await page.locator('.rewb-radia__scroll').getAttribute('role'), 'region',
    '横向滚动区必须可键盘聚焦（axe scrollable-region-focusable）'
  )

  // 2. 无事件静默：未选目标时 0 条激活
  assert.equal(await page.locator('.rewb-ray--active').count(), 0, '未选目标时应静默')
  assert.match(await page.locator('.rewb-radia__hint').innerText(), /静默/)

  // 3. 选「安卓应用」→ 管线 5 把工具点亮
  await page.getByRole('tab', { name: /安卓应用/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('.rewb-ray--active').length === 5, null, { timeout: 8000 })
  assert.match(await page.locator('.rewb-radia__hint').innerText(), /5 \/ 15/)

  // 4. 切「本机二进制」→ 7 把
  await page.getByRole('tab', { name: /本机二进制/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('.rewb-ray--active').length === 7, null, { timeout: 8000 })

  // 5. 再点一次取消 → 回到静默
  await page.getByRole('tab', { name: /本机二进制/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('.rewb-ray--active').length === 0, null, { timeout: 8000 })

  // 6. lightweight 档降级：命中流线不跑动画
  await page.getByRole('tab', { name: /本机二进制/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('.rewb-ray--active').length === 7, null, { timeout: 8000 })
  await page.evaluate(() => localStorage.setItem('smartops_visual_mode', 'lightweight'))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.rewb-radia__svg', { timeout: 20000 })
  const mode = await page.locator('.app-layout').getAttribute('data-visual-mode')
  assert.equal(mode, 'lightweight', '视觉档位应切到 lightweight')
  // reload 后选中态重置，需重新选目标才能检查命中流线的降级行为
  await page.getByRole('tab', { name: /本机二进制/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('.rewb-ray--active').length === 7, null, { timeout: 8000 })
  const anim = await page.locator('.rewb-ray--active').first().evaluate(el => getComputedStyle(el).animationName)
  assert.equal(anim, 'none', `lightweight 档流线动画应停用，实际 ${anim}`)

  // 7. 强效果层：balanced 档下中心扫描 + 沿路径流光 + 端点扩散环在跑
  await page.evaluate(() => localStorage.setItem('smartops_visual_mode', 'balanced'))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.rewb-radia__svg', { timeout: 20000 })
  await page.getByRole('tab', { name: /安卓应用/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('.rewb-ray--active').length === 5, null, { timeout: 8000 })
  assert.equal(await page.locator('.app-layout').getAttribute('data-visual-mode'), 'balanced')
  const coreAnim = await page.locator('.rewb-radia__core-scan').evaluate(el => getComputedStyle(el).animationName)
  const sparkAnim = await page.locator('.rewb-ray--on .rewb-ray__spark').first().evaluate(el => getComputedStyle(el).animationName)
  const pulseAnim = await page.locator('.rewb-ray--on .rewb-ray__pulse').first().evaluate(el => getComputedStyle(el).animationName)
  assert.match(coreAnim, /rewb-core-spin/, `中心扫描应在跑，实际 ${coreAnim}`)
  assert.match(sparkAnim, /rewb-ray-spark/, `流光点应在跑，实际 ${sparkAnim}`)
  assert.match(pulseAnim, /rewb-ray-pulse/, `端点扩散环应在跑，实际 ${pulseAnim}`)

  // 传导顺序绑真实 pipeline：安卓应用 = frida → mitmproxy → jadx → apktool → yara
  const delays = await page.locator('.rewb-ray--on .rewb-ray__spark').evaluateAll(nodes =>
    nodes.map(el => getComputedStyle(el).animationDelay).sort()
  )
  assert.equal(new Set(delays).size, 5, `5 条命中流线应按管线顺序错峰，实际延迟 ${delays.join(',')}`)

  // 8. lightweight 档强效果层全部退场
  await page.evaluate(() => localStorage.setItem('smartops_visual_mode', 'lightweight'))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.rewb-radia__svg', { timeout: 20000 })
  await page.getByRole('tab', { name: /安卓应用/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('.rewb-ray--active').length === 5, null, { timeout: 8000 })
  const lightSpark = await page.locator('.rewb-ray--on .rewb-ray__spark').first().evaluate(el => getComputedStyle(el).opacity)
  assert.equal(lightSpark, '0', `lightweight 档强效果层应退场，实际 opacity ${lightSpark}`)

  // 9. 系统 reduced-motion 降级：基线动画停用
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const animReduced = await page.locator('.rewb-ray--active').first().evaluate(el => getComputedStyle(el).animationName)
  assert.equal(animReduced, 'none', `prefers-reduced-motion 下动画应停用，实际 ${animReduced}`)

  // 10. 375 窄屏无横向溢出
  await page.setViewportSize({ width: 375, height: 812 })
  await page.waitForTimeout(400)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  assert.ok(overflow <= 1, `375 视口横向溢出 ${overflow}px`)

  assert.deepEqual(errors, [], `页面异常: ${errors.join(' | ')}`)
  console.log('REA RADIATION BROWSER TEST: ALL PASS')
} finally {
  await browser.close()
}
