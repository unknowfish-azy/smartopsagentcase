// 知识审核 · 键盘与快捷菜单（阶段 4）真实浏览器核验。
//
// 只用键盘走完一次采纳和一次驳回（验收线），并检查：
//   ↑↓ 焦点移动、A/R 打开 popover、Enter 提交、Esc 逐层退出、? 切换图例、
//   Shift+F10 打开快捷菜单，置灰项写明根本原因、可用项写明将执行的请求。

import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockSession } from './helpers/session.mjs'

const BASE = process.env.SMARTOPS_REVIEW_BASE_URL || 'http://127.0.0.1:5173'

const state = {
  candidates: [
    { id: 401, traceId: 'trace-k1', toolId: 'mysql.connection.diagnose', title: '连接池耗尽', status: 'PENDING_REVIEW', summary: '待审', contentMarkdown: '# 连接池耗尽', sourceRunId: 1, createdAt: '2026-11-14T01:00:00Z' },
    { id: 402, traceId: 'trace-k2', toolId: 'redis.slowlog.inspect', title: '慢查询聚集', status: 'PENDING_REVIEW', summary: '待审', contentMarkdown: '# 慢查询聚集', sourceRunId: 2, createdAt: '2026-11-14T02:00:00Z' },
    { id: 403, traceId: 'trace-k3', toolId: 'k8s.service.diagnose', title: '端口耗尽', status: 'PENDING_REVIEW', summary: '待审', contentMarkdown: '# 端口耗尽', sourceRunId: 3, createdAt: '2026-11-14T03:00:00Z' }
  ],
  entries: []
}

const requests = []
const find = id => state.candidates.find(candidate => candidate.id === id)

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE })
  const page = await context.newPage()
  page.setDefaultTimeout(15000)
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))

  await page.route(/^http:\/\/127\.0\.0\.1:5173\/api\//, route => route.fulfill({ json: { code: 200, data: null } }))
  await mockSession(page)
  await page.route(new RegExp(`^${BASE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/api/knowledge/`), route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    requests.push(`${request.method()} ${path}`)
    const reply = data => route.fulfill({ json: { code: 200, message: 'success', data } })

    if (path === '/api/knowledge/candidates' && request.method() === 'GET') {
      return reply({ items: state.candidates, total: state.candidates.length, page: 1, pageSize: 100 })
    }
    if (path === '/api/knowledge/personal/libraries') return reply([{ id: 1, name: 'K8s 运行手册' }])
    if (path === '/api/knowledge/personal/libraries/1/entries') return reply({ items: state.entries, total: state.entries.length })

    const detail = /^\/api\/knowledge\/candidates\/(\d+)$/.exec(path)
    if (detail && request.method() === 'GET') return reply(find(Number(detail[1])))

    const promote = /^\/api\/knowledge\/candidates\/(\d+)\/promote$/.exec(path)
    if (promote) {
      const candidate = find(Number(promote[1]))
      candidate.status = 'PROMOTED'
      const entry = { id: 501, libraryId: 1, title: candidate.title, version: 1, verificationStatus: 'UNVERIFIED', sourceRef: candidate.traceId, createdAt: new Date().toISOString() }
      state.entries.push(entry)
      return reply(entry)
    }

    const reject = /^\/api\/knowledge\/candidates\/(\d+)\/reject$/.exec(path)
    if (reject) {
      const candidate = find(Number(reject[1]))
      const reason = JSON.parse(request.postData() || '{}').reason || ''
      candidate.status = 'REJECTED'
      candidate.summary = `${candidate.summary}\n驳回原因：${reason}`
      return reply(null)
    }
    return reply(null)
  })

  await page.goto(`${BASE}/knowledge/review`)
  await page.locator('.rg-band .rg-row--cand').first().waitFor()
  await page.locator('body').click({ position: { x: 5, y: 5 } })

  const focusedRow = () => page.locator('.rg-row.is-focused')
  const toastText = () => page.locator('.kr-toast').innerText()

  // 键盘停到一个真待审行（跳过条目行与已决策行）。
  async function focusPending() {
    for (let step = 0; step < 10; step += 1) {
      if (await focusedRow().count() && await focusedRow().locator('.rg-act').count()) return
      await page.keyboard.press('ArrowDown')
      await page.waitForTimeout(60)
    }
    throw new Error('没有聚焦到待审行')
  }

  // 1. ↑↓ 移动焦点，行上有可感知的焦点环。
  await page.keyboard.press('ArrowDown')
  await focusedRow().waitFor()
  const firstFocus = await focusedRow().getAttribute('data-row-id')
  await page.keyboard.press('ArrowDown')
  const secondFocus = await focusedRow().getAttribute('data-row-id')
  assert.notEqual(firstFocus, secondFocus, 'ArrowDown 应该移动到下一行')

  // 2. 只用键盘完成一次采纳：A → 标题框 → Enter。
  await focusPending()
  const adoptTitle = await focusedRow().locator('.rg-cand__title').innerText()
  await page.keyboard.press('a')
  await page.locator('.kr-pop').waitFor()
  assert.match(await page.locator('.kr-pop').innerText(), /POST \/api\/knowledge\/candidates\/\d+\/promote/)
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('placeholder')), '条目标题', 'A 打开后焦点应在标题框')
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => document.querySelector('.kr-toast')?.textContent.includes('已采纳'))
  assert.match(await toastText(), new RegExp(`新建条目「${adoptTitle}」v1（未验证）`))
  assert.equal(await page.locator('.kr-pop').count(), 0)
  const adoptedRow = page.locator('.rg-band .rg-row--cand', { hasText: adoptTitle })
  await adoptedRow.and(page.locator('.rg-row--done')).waitFor()

  // 3. 只用键盘完成一次驳回：R → 原因必填 → 输入后 Enter。
  await focusPending()
  await page.keyboard.press('r')
  await page.locator('.kr-pop').waitFor()
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('placeholder')), '例：证据不足（缺上游日志）')
  await page.keyboard.press('Enter')
  await page.locator('.kr-pop__error').waitFor()
  assert.match(await page.locator('.kr-pop__error').innerText(), /请填写驳回原因/)
  assert.equal(requests.some(item => item.endsWith('/reject')), false, '原因为空时不应发出请求')
  await page.keyboard.type('证据不足（缺上游日志）')
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => document.querySelector('.kr-toast')?.textContent.includes('已驳回'))
  assert.match(await toastText(), /\/reject → summary/)

  // 4. Esc 逐层退出：popover → 行焦点 → 图例筛选。
  await focusPending()
  await page.keyboard.press('a')
  await page.locator('.kr-pop').waitFor()
  await page.keyboard.press('Escape')
  assert.equal(await page.locator('.kr-pop').count(), 0, 'Esc 应先关闭 popover')
  assert.equal(await focusedRow().count(), 1, '关闭 popover 后行焦点还在')
  await page.keyboard.press('Escape')
  assert.equal(await focusedRow().count(), 0, '第二次 Esc 清掉行焦点')

  // 5. ? 切换图例。
  assert.equal(await page.locator('.rg-legend').isVisible(), true)
  await page.keyboard.press('?')
  assert.equal(await page.locator('.rg-legend').isVisible(), false)
  await page.keyboard.press('?')
  assert.equal(await page.locator('.rg-legend').isVisible(), true)

  // 6. Shift+F10 打开快捷菜单：可用项写请求，置灰项写根本原因；Esc 只关菜单。
  await focusPending()
  await page.keyboard.press('Shift+F10')
  await page.locator('.rg-menu').waitFor()
  const menuBox = await page.locator('.rg-menu').boundingBox()
  const viewport = page.viewportSize()
  assert.ok(menuBox.y >= 0 && menuBox.y + menuBox.height <= viewport.height, '菜单整体落在视口内，不被底边裁掉')
  assert.ok(menuBox.x >= 0 && menuBox.x + menuBox.width <= viewport.width, '菜单不横向溢出视口')
  const menuText = await page.locator('.rg-menu').innerText()
  assert.match(menuText, /采纳并入库/)
  assert.match(menuText, /POST \/api\/knowledge\/candidates\/\d+\/promote/)
  assert.match(menuText, /当前后端只支持新建条目，条目合并需要 target_entry_id/)
  assert.match(menuText, /UNIQUE\(user_id, source_run_id\)/)
  assert.match(menuText, /尚未实现；先驳回，再丢弃/)
  assert.equal(await page.locator('.rg-menu__item:not(:disabled)').count(), 4, '只有采纳、驳回、查看正文、复制 Trace 可用')
  await page.screenshot({ path: 'test-artifacts/review-menu-shift-f10.png' })
  await page.keyboard.press('Escape')
  assert.equal(await page.locator('.rg-menu').count(), 0)
  assert.equal(await focusedRow().count(), 1, '关闭菜单不会清掉行焦点')

  // 7. 菜单里的「采纳并入库」能把动作继续交给 popover。
  await page.keyboard.press('Shift+F10')
  await page.locator('.rg-menu').waitFor()
  await page.locator('.rg-menu__item', { hasText: '采纳并入库' }).click()
  await page.locator('.kr-pop').waitFor()
  assert.match(await page.locator('.kr-pop').innerText(), /\/promote/)
  await page.keyboard.press('Escape')

  assert.deepEqual(pageErrors, [])
  console.log('PASS: 键盘完成采纳与驳回；↑↓/A/R/Enter/Esc/? 生效；Shift+F10 菜单的可用项写请求、置灰项写根本原因')
} finally {
  await browser.close()
}
