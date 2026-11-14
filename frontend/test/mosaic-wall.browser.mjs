// 照片墙（mosaic）浏览器实测 — 绕过登录墙（mock /api/auth/session + 其余 api 返回空）
// 用法：cd frontend && node test/mosaic-wall.browser.mjs
// 依赖：dev server 已在 http://127.0.0.1:5173 运行；playwright + 本机 Microsoft Edge
import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--no-proxy-server', '--proxy-bypass-list=*'] })

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  // 登录墙绕过：/api/auth/session 返回 operator 用户，其余 api 一律返回空数组
  // 只 mock 根路径 /api/* 真实后端接口；注意 /src/api/*.ts 是源码模块，不能被误匹配
  await page.route(url => new URL(url).pathname.startsWith('/api/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/session') {
      return route.fulfill({ json: { code: 200, data: { user: { id: 7, username: 'mosaic-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'mosaic-test-csrf' } } })
    }
    return route.fulfill({ json: { code: 200, data: [] } })
  })

  const errors = []
  page.on('pageerror', e => errors.push('pageerror: ' + String(e)))
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()) })

  await page.goto(`${base}/knowledge/space`, { waitUntil: 'load' })
  await page.waitForSelector('.mw-tile', { timeout: 20000 })

  // 1) 默认即照片墙：tile 数 === 顶栏统计总数（自洽，不硬编码 737）
  const totalText = (await page.locator('.ks-stat b').first().innerText()).trim()
  const total = parseInt(totalText, 10)
  assert.ok(total >= 700 && total <= 800, `unexpected total ${total}`)
  const tileCount = await page.locator('.mw-tile').count()
  assert.equal(tileCount, total, `tile count ${tileCount} !== stat total ${total}`)

  // 2) 默认视图为照片墙（照片墙 pill 高亮），且无右侧 .ks-side--alt 双弹
  assert.equal(await page.locator('.ks-pill--on', { hasText: '照片墙' }).count(), 1)
  assert.equal(await page.locator('.ks-side--alt').count(), 0)

  // 3) 四档缩放：滚轮放大后 .mw-world 的 data-size 变化（LOD 切换）
  const sizeBefore = await page.locator('.mw-world').getAttribute('data-size')
  await page.mouse.move(720, 450)
  await page.mouse.wheel(0, -900)
  await page.waitForTimeout(250)
  const sizeAfter = await page.locator('.mw-world').getAttribute('data-size')
  assert.ok(sizeBefore && sizeAfter && sizeBefore !== sizeAfter, `data-size did not change: ${sizeBefore} -> ${sizeAfter}`)

  // 4) 点击视口内某格 → 锚定悬浮详情窗出现（已非 s0，openTile 直接开详情）
  const clickPt = await page.evaluate(() => {
    const stage = document.querySelector('.mw-stage')
    if (!stage) return null
    const sr = stage.getBoundingClientRect()
    for (const t of document.querySelectorAll('.mw-tile')) {
      const r = t.getBoundingClientRect()
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2
      if (cx > sr.left + 20 && cx < sr.right - 20 && cy > sr.top + 20 && cy < sr.bottom - 20) {
        return { x: cx, y: cy }
      }
    }
    return null
  })
  assert.ok(clickPt, 'no in-viewport tile found to click')
  await page.mouse.click(clickPt.x, clickPt.y)
  await page.waitForSelector('.mw-pop', { timeout: 5000 })
  assert.equal(await page.locator('.mw-pop').count(), 1)
  // 详情窗含真实字段（域 / 类型 / 风险 / 待核验）
  assert.equal(await page.locator('.mw-pop-domain').count(), 1)
  assert.ok((await page.locator('.mw-pop').innerText()).includes('未核验'))

  // 5) Esc 关闭悬浮窗
  await page.keyboard.press('Escape')
  await page.waitForTimeout(150)
  assert.equal(await page.locator('.mw-pop').count(), 0)

  // 6) Ctrl+K 打开 FieldSearch（自管键盘，复用 FieldSearch）
  await page.keyboard.press('Control+k')
  await page.waitForSelector('.fs-input', { timeout: 5000 })
  assert.equal(await page.locator('.fs-input').count(), 1)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(150)
  assert.equal(await page.locator('.fs-overlay').count(), 0)

  // 7) 浅色主题不崩，tile 数稳定
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'))
  await page.waitForTimeout(150)
  assert.equal(await page.locator('.mw-tile').count(), total)

  // 8) 无运行时错误
  assert.equal(errors.length, 0, `page errors:\n${errors.join('\n')}`)

  console.log(`mosaic browser verify OK — ${tileCount} tiles (total ${total}), data-size ${sizeBefore}->${sizeAfter}, light theme stable, 0 errors`)
} finally {
  await browser.close()
}
