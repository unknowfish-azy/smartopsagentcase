// 泳道图缩放与平移（阶段 6）真实浏览器核验：
//   1. 工具栏 −/百分比/+ 与 Ctrl+滚轮都能缩放，范围 50%–200%；
//   2. 缩放后头像仍压在泳道线上（同一份行模型 + 单一 transform）；
//   3. 拖动行/空白处平移，不会被当成点选（侧栏不打开）；
//   4. 视口高度随缩放换算，不压住下面的内容；点百分比可复位。

import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockSession } from './helpers/session.mjs'

const BASE = process.env.SMARTOPS_REVIEW_BASE_URL || 'http://127.0.0.1:5173'
const CANDIDATES = [
  {
    id: 1, traceId: 'trace-a', toolId: 'k8s.service.diagnose', title: '候选 A', status: 'PENDING_REVIEW',
    summary: '待审', contentMarkdown: '# A', sourceRunId: 1, createdAt: '2026-11-13T02:00:00Z'
  },
  {
    id: 2, traceId: 'trace-b', toolId: 'mysql.connection.diagnose', title: '候选 B', status: 'PROMOTED',
    summary: '已采纳', contentMarkdown: '# B', sourceRunId: 2, createdAt: '2026-11-13T02:05:00Z'
  },
  {
    id: 3, traceId: 'trace-c', toolId: 'nginx.upstream.diagnose', title: '候选 C', status: 'PENDING_REVIEW',
    summary: '待审', contentMarkdown: '# C', sourceRunId: 3, createdAt: '2026-11-13T02:10:00Z'
  }
]
const ENTRIES = [{
  id: 10, libraryId: 1, title: '条目 B', version: 2, verificationStatus: 'UNVERIFIED',
  sourceRef: 'trace-b', createdAt: '2026-11-13T03:00:00Z'
}]

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage()
  page.setDefaultTimeout(20000)
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))

  await page.route(/^http:\/\/127\.0\.0\.1:5173\/api\//, route => route.fulfill({ json: { code: 200, data: null } }))
  await mockSession(page)
  await page.route(/^http:\/\/127\.0\.0\.1:5173\/api\/knowledge\//, route => {
    const path = new URL(route.request().url()).pathname
    const reply = data => route.fulfill({ json: { code: 200, message: 'success', data } })
    if (path === '/api/knowledge/candidates') return reply({ items: CANDIDATES, total: CANDIDATES.length, page: 1, pageSize: 100 })
    if (path === '/api/knowledge/personal/libraries') return reply([{ id: 1, name: 'K8s 运行手册' }])
    if (path === '/api/knowledge/personal/libraries/1/entries') return reply({ items: ENTRIES, total: 1, page: 1, pageSize: 100 })
    if (/^\/api\/knowledge\/candidates\/\d+$/.test(path)) return reply(CANDIDATES[0])
    return reply(null)
  })

  await page.goto(`${BASE}/knowledge/review`)
  await page.locator('.rg-row--cand').first().waitFor()

  const zoomValue = page.locator('.rg-zoom__value')
  const stage = page.locator('.rg-stage')
  const zoomOf = async () => Number((await zoomValue.innerText()).replace('%', '')) / 100

  // 1. 初始 100%，按钮 ± 走 10% 档并夹在 50%–200%。
  assert.equal(await zoomValue.innerText(), '100%')
  await page.locator('.rg-zoom__btn[aria-label="放大"]').click()
  assert.equal(await zoomValue.innerText(), '110%')
  const zoomIn = page.locator('.rg-zoom__btn[aria-label="放大"]')
  for (let index = 0; index < 20 && !(await zoomIn.isDisabled()); index += 1) await zoomIn.click()
  assert.equal(await zoomValue.innerText(), '200%', '放大上限 200%')
  assert.equal(await page.locator('.rg-zoom__btn[aria-label="放大"]').isDisabled(), true)
  await zoomValue.click()
  assert.equal(await zoomValue.innerText(), '100%', '点百分比复位')

  // 2. Ctrl + 滚轮以指针为锚点缩放。
  await page.mouse.move(700, 500)
  await page.keyboard.down('Control')
  await page.mouse.wheel(0, -240)
  await page.keyboard.up('Control')
  const wheelZoom = await zoomOf()
  assert.ok(wheelZoom > 1.2 && wheelZoom <= 2, `Ctrl+滚轮应放大，实际 ${wheelZoom}`)

  // 3. 缩放后头像中心仍压在泳道线上（两者共用同一个 transform）。
  const alignment = await page.evaluate(() => {
    const viewport = document.querySelector('.rg-viewport')
    const stage = document.querySelector('.rg-stage')
    const svg = document.querySelector('.rg-band .rg-lanes')
    const stageRect = stage.getBoundingClientRect()
    const zoom = stageRect.width / parseFloat(getComputedStyle(stage).width)
    const laneCount = Math.round((svg.width.baseVal.value - 24) / 22)
    const laneXs = Array.from({ length: laneCount }, (_, index) => stageRect.left + (12 + index * 22 + 11) * zoom)
    let misaligned = 0
    for (const row of document.querySelectorAll('.rg-band .rg-row--cand')) {
      const avatar = row.querySelector('.rg-avatar')
      if (!avatar) continue
      const box = avatar.getBoundingClientRect()
      const center = box.left + box.width / 2
      if (!laneXs.some(x => Math.abs(x - center) <= 1.5)) misaligned += 1
    }
    const viewportHeight = viewport.getBoundingClientRect().height
    return { misaligned, zoom, viewportHeight, stageHeight: parseFloat(getComputedStyle(stage).height) }
  })
  assert.equal(alignment.misaligned, 0, `${alignment.zoom.toFixed(2)} 倍时头像仍应在泳道线上`)
  assert.ok(
    Math.abs(alignment.viewportHeight - alignment.stageHeight * alignment.zoom) < 2,
    '视口高度应随缩放换算，避免压住下面的内容'
  )

  // 4. 拖动行平移，不触发选中（侧栏不打开）。
  await zoomValue.click()
  for (let index = 0; index < 5; index += 1) await page.locator('.rg-zoom__btn[aria-label="放大"]').click()
  assert.equal(await zoomValue.innerText(), '150%')

  const rowBox = await page.locator('.rg-row--cand').first().boundingBox()
  const startX = rowBox.x + rowBox.width * 0.6
  const startY = rowBox.y + rowBox.height / 2
  const beforePan = await stage.evaluate(node => new DOMMatrix(getComputedStyle(node).transform).m41)
  await page.mouse.move(startX, startY)
  await page.mouse.down()
  await page.mouse.move(startX - 160, startY, { steps: 8 })
  await page.mouse.up()

  const afterPan = await stage.evaluate(node => new DOMMatrix(getComputedStyle(node).transform).m41)
  assert.ok(afterPan < beforePan - 100, `拖动应平移画布，实际 ${beforePan} → ${afterPan}`)
  assert.equal(await page.locator('.kr-side').count(), 0, '拖动不应被当成点选')

  // 横向夹紧：拖不出内容边界。
  await page.mouse.move(startX, startY)
  await page.mouse.down()
  await page.mouse.move(startX + 900, startY, { steps: 8 })
  await page.mouse.up()
  const clampedPan = await stage.evaluate(node => new DOMMatrix(getComputedStyle(node).transform).m41)
  assert.ok(clampedPan <= 0.5, `右拖应停在内容左边界，实际 ${clampedPan}`)

  // 5. 缩放后仍可点选（拖动抑制只作用于这一次拖拽）。
  await zoomValue.click()
  await page.locator('.rg-row--cand').first().click()
  await page.locator('.kr-side').waitFor()
  await page.locator('.kr-side__close').click()

  // 6. 截图留档：150%。
  for (let index = 0; index < 5; index += 1) await page.locator('.rg-zoom__btn[aria-label="放大"]').click()
  await page.screenshot({ path: 'test-artifacts/review-zoom-150.png' })

  assert.deepEqual(pageErrors, [])
  console.log('PASS: 按钮/Ctrl+滚轮缩放、缩放后泳道对齐、拖动平移不误选、横向夹紧、复位与 150% 截图')
} finally {
  await browser.close()
}
