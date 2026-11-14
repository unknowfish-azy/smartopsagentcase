// 知识审核 · 真数据接线核验（阶段 5）真实浏览器核验。
//
// 覆盖 PROMPT 阶段 5 的验收点：
//   1. 缺口 A：条目翻页到底，第 101 条之后的条目也能把候选挂到自己的泳道（不再误标「待归类」）；
//   2. 缺口 C：候选列表里出现后端未定义的状态时如实写「未知状态」，全页不出现「生成中」；
//   3. 缺口 D：200 条候选首屏只取 100，页脚写「已加载 100 / 200」，点「加载更早」补齐；
//   4. 缺口 E：没有把条目写成 VERIFIED 的接口，所以图上不出现「已入库」主干；
//   5. 性能基线：200 行首屏到达时间 + 强制重排耗时（< 100ms）。

import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockSession } from './helpers/session.mjs'

const BASE = process.env.SMARTOPS_REVIEW_BASE_URL || 'http://127.0.0.1:5173'

const TOOLS = ['mysql.connection.diagnose', 'redis.slowlog.inspect', 'k8s.service.diagnose']
const TOTAL_CANDIDATES = 200
const TOTAL_ENTRIES = 150

const candidates = Array.from({ length: TOTAL_CANDIDATES }, (_, index) => {
  const base = {
    id: 1000 + index,
    traceId: `trace-real-${index}`,
    toolId: TOOLS[index % TOOLS.length],
    title: `候选 ${index}`,
    status: 'PENDING_REVIEW',
    summary: '待审',
    contentMarkdown: `# 候选 ${index}`,
    sourceRunId: index + 1,
    createdAt: new Date(Date.UTC(2026, 10, 14, 1, 0, index % 60)).toISOString()
  }
  if (index === 0 || index === 1) return { ...base, status: 'PROMOTED' }
  if (index === 150) return { ...base, status: 'REJECTED', summary: '已驳回\n驳回原因：证据不足（缺上游日志）' }
  // 后端契约里没有这个状态：视图必须如实写「未知状态」，不能编成「生成中」。
  if (index === 2) return { ...base, status: 'GENERATING' }
  return base
})

// 第 1 页全是无关条目；命中 trace-real-1 的条目故意放在第 2 页。
const entries = Array.from({ length: TOTAL_ENTRIES }, (_, index) => ({
  id: 5000 + index,
  libraryId: 1,
  title: index === 100 ? 'K8s 事件回放' : `条目 ${index}`,
  version: 1,
  verificationStatus: 'UNVERIFIED',
  sourceRef: index === 0 ? 'trace-real-0' : index === 100 ? 'trace-real-1' : `filler-${index}`,
  createdAt: '2026-11-01T00:00:00Z'
}))

const entryPages = []
const candidatePages = []

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  const page = await context.newPage()
  page.setDefaultTimeout(20000)
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))

  // 首行出现的时间：从文档开始算，包含取数与挂载。
  await page.addInitScript(() => {
    window.__rowsAt = null
    const start = performance.now()
    const tick = () => {
      if (document.querySelectorAll('.rg-row').length) { window.__rowsAt = performance.now() - start; return }
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })

  await page.route(/^http:\/\/127\.0\.0\.1:5173\/api\//, route => route.fulfill({ json: { code: 200, data: null } }))
  await mockSession(page)
  await page.route(new RegExp(`^${BASE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/api/knowledge/`), route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const reply = data => route.fulfill({ json: { code: 200, message: 'success', data } })

    if (path === '/api/knowledge/candidates' && request.method() === 'GET') {
      const requested = Number(url.searchParams.get('page') || 1)
      candidatePages.push(requested)
      const items = candidates.slice((requested - 1) * 100, requested * 100)
      return reply({ items, total: candidates.length, page: requested, pageSize: 100 })
    }
    if (path === '/api/knowledge/personal/libraries') return reply([{ id: 1, name: 'K8s 运行手册' }])
    if (path === '/api/knowledge/personal/libraries/1/entries') {
      const requested = Number(url.searchParams.get('page') || 1)
      entryPages.push(requested)
      const items = entries.slice((requested - 1) * 100, requested * 100)
      return reply({ items, total: entries.length, page: requested, pageSize: 100 })
    }
    const detail = /^\/api\/knowledge\/candidates\/(\d+)$/.exec(path)
    if (detail) return reply(candidates.find(candidate => candidate.id === Number(detail[1])) || null)
    return reply(null)
  })

  await page.goto(`${BASE}/knowledge/review`)
  await page.locator('.rg-row--cand').first().waitFor()

  const bodyText = () => page.locator('body').innerText()
  const rowOf = id => page.locator(`[data-row-id="candidate-${id}"]`)

  // 1. 缺口 A：条目分两页取全，第 2 页条目照样挂上泳道。
  await page.locator('.rg-entry-name', { hasText: 'K8s 事件回放' }).waitFor()
  assert.deepEqual(entryPages, [1, 2], '条目要翻到第 2 页')
  assert.equal(await rowOf(1001).locator('.rg-tag--target').count(), 0, '第 2 页条目对应的候选不应标「待归类」')
  assert.match(await rowOf(1001).innerText(), /已新建条目 v1（未验证）/)
  assert.equal(await rowOf(1000).locator('.rg-tag--target').count(), 0, '第 1 页条目对应的候选也挂上泳道')

  // 2. 缺口 C：未知状态如实呈现，没有假「生成中」。
  assert.match(await rowOf(1002).innerText(), /未知状态/)
  assert.doesNotMatch(await bodyText(), /生成中/, '不能伪造生成中状态')

  // 3. 缺口 E：没有验证接口，就不画「已入库」主干。
  assert.doesNotMatch(await bodyText(), /已入库/)

  // 4. 缺口 D：首屏 100 条 + 加载更早。
  assert.equal(await page.locator('.rg-band .rg-row--cand').count(), 100)
  assert.match(await page.locator('.rg-band .rg-band__foot').innerText(), /已加载 100 \/ 200 条候选/)
  await page.locator('.rg-link', { hasText: '加载更早' }).click()
  await page.waitForFunction(() => document.querySelectorAll('.rg-band .rg-row--cand').length === 200)
  // 补齐后不再有截断提示与「加载更早」，说明列表已是全量。
  assert.doesNotMatch(await page.locator('.rg-band .rg-band__foot').innerText(), /已加载/)
  assert.equal(await page.locator('.rg-link', { hasText: '加载更早' }).count(), 0)
  assert.deepEqual(candidatePages, [1, 2])

  // 5. 四个宽度：无横向溢出，头像中心压在自己的泳道线上（改宽度后仍对齐）。
  for (const width of [1440, 1024, 768, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.waitForTimeout(120)
    const check = await page.evaluate(() => {
      const root = document.documentElement
      const svg = document.querySelector('.rg-band .rg-lanes')
      if (!svg) return { overflow: 0, misaligned: -1 }
      const rect = svg.getBoundingClientRect()
      const laneCount = Math.round((svg.width.baseVal.value - 24) / 22)
      const laneXs = Array.from({ length: laneCount }, (_, index) => rect.left + 12 + index * 22 + 11)
      let misaligned = 0
      for (const row of document.querySelectorAll('.rg-band .rg-row--cand')) {
        const avatar = row.querySelector('.rg-avatar')
        if (!avatar) continue
        const box = avatar.getBoundingClientRect()
        const center = box.left + box.width / 2
        if (!laneXs.some(x => Math.abs(x - center) <= 1)) misaligned += 1
      }
      return { overflow: root.scrollWidth - root.clientWidth, misaligned }
    })
    assert.ok(check.overflow <= 1, `${width} 宽不应横向溢出，实际 ${check.overflow}px`)
    assert.equal(check.misaligned, 0, `${width} 宽头像应压在泳道线上`)
  }
  await page.setViewportSize({ width: 1440, height: 1000 })

  // 6. 性能：200 行的重排耗时与首屏到达时间。
  //    重排测量方式：切到紧凑密度（字号变化 → 200 行全部重新排版），强制同步布局后读数，再切回。
  const perf = await page.evaluate(() => {
    const graph = document.querySelector('.rg')
    const started = performance.now()
    graph.classList.add('rg--compact')
    void graph.offsetHeight
    for (const row of document.querySelectorAll('.rg-row')) void row.getBoundingClientRect()
    const relayout = performance.now() - started
    graph.classList.remove('rg--compact')
    void graph.offsetHeight
    return { relayout, rowsAt: window.__rowsAt }
  })
  console.log(`BASELINE 200 行：首屏到达 ${perf.rowsAt?.toFixed(1)}ms，强制重排 ${perf.relayout.toFixed(1)}ms`)
  assert.ok(perf.relayout < 100, `200 行重排应低于 100ms，实际 ${perf.relayout.toFixed(1)}ms`)

  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: 'test-artifacts/review-realdata-200.png' })
  assert.deepEqual(pageErrors, [])

  // 7. 演示模式：没有真实候选与条目时，补的演示条目要挂上配对候选，并产生采纳事件。
  const demoContext = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  const demoPage = await demoContext.newPage()
  demoPage.setDefaultTimeout(20000)
  const demoErrors = []
  demoPage.on('pageerror', error => demoErrors.push(error.message))
  await demoPage.route(/^http:\/\/127\.0\.0\.1:5173\/api\//, route => route.fulfill({ json: { code: 200, data: null } }))
  await mockSession(demoPage)
  await demoPage.route(/^http:\/\/127\.0\.0\.1:5173\/api\/knowledge\//, route => {
    const path = new URL(route.request().url()).pathname
    const reply = data => route.fulfill({ json: { code: 200, message: 'success', data } })
    if (path === '/api/knowledge/candidates') return reply({ items: [], total: 0, page: 1, pageSize: 100 })
    if (path === '/api/knowledge/personal/libraries') return reply([])
    return reply(null)
  })
  await demoPage.goto(`${BASE}/knowledge/review`)
  await demoPage.locator('.rg-entry-name', { hasText: 'Kubernetes Service 无可用 Endpoint' }).waitFor()

  assert.equal(await demoPage.locator('.rg-row--entry .rg-tag', { hasText: '演示条目' }).count(), 1, '演示条目行要明确标注')
  assert.equal(await demoPage.locator('.rg-row--cand', { hasText: '已采纳示意，未写库' }).count(), 1, '配对候选落在演示条目泳道且写明未写库')
  assert.match(await demoPage.locator('.rg-history').innerText(), /演示 · 采纳后条目 v1（未写库）/, '演化史要有演示采纳事件且不宣称写库')
  assert.equal(await demoPage.locator('.rg-cand__acts').count(), 0, '演示数据不给可写入口')
  assert.match(await demoPage.locator('.rg-bar').innerText(), /演示数据 · 不写库/)
  assert.deepEqual(demoErrors, [])

  await demoPage.evaluate(() => window.scrollTo(0, 0))
  await demoPage.screenshot({ path: 'test-artifacts/review-guide-mode.png' })
  await demoContext.close()
  console.log('PASS: 条目翻页接线、未知状态如实呈现、首屏 100 + 加载更早、无假「已入库」、200 行重排 < 100ms、演示条目配对')
} finally {
  await browser.close()
}
