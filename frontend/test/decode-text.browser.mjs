/**
 * 主题二浏览器回归：解码文本（AgentCommandCenterView Task 字段）+ HUD 切角卡片（哨兵统计卡）。
 *
 * 覆盖：
 *  1. 正常模式：aria-label 立即可用，视觉文本在 400ms 内落定为真实值；
 *  2. reduced-motion 模式（playwright reducedMotion:'reduce' → prefers-reduced-motion）：直接终值无动画；
 *  3. HUD：4 张切角统计卡 clip-path 生效、页头扫描线伪元素存在且动画被 reduced-motion 关停；
 *  4. 深/浅双主题截图，浅色下令牌切换不破坏切角与扫描线。
 *
 * 环境约定（踩过的坑，见规范文档 §6）：
 *  - 通配路由会误伤源码里的 api 模块，必须只放行 /api/ 开头的真实请求；
 *  - 登录态用单一路由内部分支 mock；
 *  - localStorage 键带 smartops_ 前缀；
 *  - dev server：用户层 5173。
 */
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
await mkdir('test-artifacts/theme2', { recursive: true })

const TASK_ID = 'TRC-9F2K7QW1'
const EVENT = { id: 1, taskId: TASK_ID, status: 'COMPLETED', severity: 'P3', target: 'web-01', metadata: { model: 'ops-reasoner', skill: 'log-triage', tool: 'grep' } }
const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET,PUT,OPTIONS' }

/** 单一路由内部分支：session / inspector events / 其余一律空数据。 */
async function mockApi(page) {
  await page.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers })
    if (path === '/api/auth/session') {
      return route.fulfill({ headers, json: { code: 200, data: { user: { id: 1, username: 'decode-check', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'decode-csrf' } } })
    }
    if (path.startsWith('/api/inspector/events')) {
      if (path === '/api/inspector/events') return route.fulfill({ headers, json: { code: 200, data: [EVENT] } })
      return route.fulfill({ headers, json: { code: 200, data: EVENT } })
    }
    await route.fulfill({ headers, json: { code: 200, data: [] } })
  })
}

function newPage(theme, reducedMotion) {
  return browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion })
}

try {
  // ── 1. 解码文本：正常模式（动画落定）──────────────────────────────
  {
    const page = await newPage('dark')
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'decode-check' }))
      localStorage.setItem('smartops_theme', 'dark')
    })
    await mockApi(page)
    await page.goto('http://127.0.0.1:5173/agent', { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: 'Agent Command Center', exact: true }).waitFor()
    const taskField = page.locator('.cards article').filter({ hasText: 'Task' }).locator('.decode-text')
    // aria-label 立即可用：屏幕阅读器不必等 300ms 动画
    assert.equal(await taskField.getAttribute('aria-label'), TASK_ID)
    // 视觉文本最终落定为真实值（帧纯逻辑已单测，这里验时序接线）
    await page.waitForFunction(id => document.querySelector('.decode-text')?.textContent === id, TASK_ID, { timeout: 2000 })
    assert.equal(await taskField.innerText(), TASK_ID)
    await page.screenshot({ path: 'test-artifacts/theme2/agent-decode-dark.png', fullPage: true })
    assert.deepEqual(errors, [])
    await page.close()
    console.log('PASS decode text (normal motion): aria-label immediate, visual settle to real value')
  }

  // ── 2. 解码文本：reduced-motion 直接终值 ─────────────────────────
  {
    const page = await newPage('dark', 'reduce')
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'decode-check' }))
      localStorage.setItem('smartops_theme', 'dark')
    })
    await mockApi(page)
    await page.goto('http://127.0.0.1:5173/agent', { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: 'Agent Command Center', exact: true }).waitFor()
    const taskField = page.locator('.cards article').filter({ hasText: 'Task' }).locator('.decode-text')
    // 无需等待：reduced-motion 下组件跳过 rAF，直接渲染终值
    assert.equal(await taskField.innerText(), TASK_ID)
    assert.equal(await taskField.getAttribute('aria-label'), TASK_ID)
    assert.deepEqual(errors, [])
    await page.close()
    console.log('PASS decode text (reduced motion): terminal value rendered immediately')
  }

  // ── 3. HUD 切角卡片 + 扫描线：深/浅双主题 ────────────────────────
  for (const theme of ['dark', 'light']) {
    const page = await newPage(theme)
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(t => {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'decode-check' }))
      localStorage.setItem('smartops_theme', t)
    }, theme)
    await mockApi(page)
    await page.goto('http://127.0.0.1:5173/sentinel', { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '哨兵监控台', exact: true }).waitFor()
    // 四张统计卡全部换成切角 HUD 变体
    assert.equal(await page.locator('.sentinel-stat--hud').count(), 4)
    assert.equal(await page.locator('.sentinel-stat:not(.sentinel-stat--hud)').count(), 0)
    // clip-path 真的切了角（border 被裁掉，描边走 inset box-shadow）
    const clip = await page.locator('.sentinel-stat--hud').first().evaluate(el => getComputedStyle(el).clipPath)
    assert.match(clip, /polygon/)
    const shadow = await page.locator('.sentinel-stat--hud').first().evaluate(el => getComputedStyle(el).boxShadow)
    assert.match(shadow, /inset/)
    // 页头扫描线：伪元素背景层存在
    const scan = await page.locator('.sentinel-page-header--hud').evaluate(el => getComputedStyle(el, '::before').backgroundImage)
    assert.match(scan, /repeating-linear-gradient/)
    const anim = await page.locator('.sentinel-page-header--hud').evaluate(el => getComputedStyle(el, '::before').animationName)
    assert.equal(anim, 'sentinel-scan')
    await page.screenshot({ path: `test-artifacts/theme2/sentinel-hud-${theme}.png`, fullPage: true })
    assert.deepEqual(errors, [])
    await page.close()
    console.log(`PASS HUD cards (${theme}): 4 clipped stat cards, scanline layer, inset border`)
  }

  // ── 4. reduced-motion 下扫描线动画被关停 ─────────────────────────
  {
    const page = await newPage('dark', 'reduce')
    await page.addInitScript(() => {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'decode-check' }))
      localStorage.setItem('smartops_theme', 'dark')
    })
    await mockApi(page)
    await page.goto('http://127.0.0.1:5173/sentinel', { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '哨兵监控台', exact: true }).waitFor()
    // 伪元素也要被局部契约关停（* 不匹配 ::before，契约已显式列出）
    const anim = await page.locator('.sentinel-page-header--hud').evaluate(el => getComputedStyle(el, '::before').animationName)
    assert.equal(anim, 'none')
    await page.close()
    console.log('PASS scanline animation disabled under prefers-reduced-motion')
  }
} finally { await browser.close() }
