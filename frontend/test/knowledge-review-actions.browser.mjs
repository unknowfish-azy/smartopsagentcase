// 知识审核 · 就地动作（阶段 3）真实浏览器核验。
//
// 覆盖三条真实路径：
//   1. 采纳时被并发处理：服务端 409 → 不弹错误框，提示「该候选已被处理」，行刷新成真实状态；
//   2. 驳回原因为空：就地报错，不发出写请求；
//   3. 驳回成功与采纳成功：toast 给出结果 + 方法 + 路径，行状态以服务端返回为准。
//
// 只 mock 读写接口的返回值，组件逻辑走真实代码路径。

import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockSession } from './helpers/session.mjs'

const BASE = process.env.SMARTOPS_REVIEW_BASE_URL || 'http://127.0.0.1:5173'

const state = {
  candidates: [
    { id: 201, traceId: 'trace-x', toolId: 'mysql.connection.diagnose', title: '连接池耗尽', status: 'PENDING_REVIEW', summary: '待审', contentMarkdown: '# 连接池耗尽', sourceRunId: 1, createdAt: '2026-11-14T01:00:00Z' },
    { id: 202, traceId: 'trace-y', toolId: 'redis.slowlog.inspect', title: '慢查询聚集', status: 'PENDING_REVIEW', summary: '待审', contentMarkdown: '# 慢查询聚集', sourceRunId: 2, createdAt: '2026-11-14T02:00:00Z' },
    { id: 203, traceId: 'trace-z', toolId: 'mysql.connection.diagnose', title: '主从延迟', status: 'PENDING_REVIEW', summary: '待审', contentMarkdown: '# 主从延迟', sourceRunId: 3, createdAt: '2026-11-14T03:00:00Z' },
    { id: 204, traceId: 'trace-w', toolId: 'k8s.service.diagnose', title: '端口耗尽', status: 'PENDING_REVIEW', summary: '待审', contentMarkdown: '# 端口耗尽', sourceRunId: 4, createdAt: '2026-11-14T04:00:00Z' }
  ],
  entries: [],
  promoteConflict: true
}

const requests = []
const find = id => state.candidates.find(candidate => candidate.id === id)

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  const page = await context.newPage()
  page.setDefaultTimeout(15000)
  page.on('dialog', dialog => { throw new Error(`不应出现模态框：${dialog.message()}`) })
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))

  await page.route(/^http:\/\/127\.0\.0\.1:5173\/api\//, route => route.fulfill({ json: { code: 200, data: null } }))
  await mockSession(page)
  await page.route(new RegExp(`^${BASE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/api/knowledge/`), async route => {
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
      if (state.promoteConflict) {
        // 模拟别人在「读详情」和「提交」之间抢先驳回。
        state.promoteConflict = false
        candidate.status = 'REJECTED'
        candidate.summary = `${candidate.summary}\n驳回原因：证据不足（并发处理）`
        return route.fulfill({ status: 409, json: { code: 409, message: 'KNOWLEDGE_CANDIDATE_NOT_PENDING' } })
      }
      candidate.status = 'PROMOTED'
      const entry = { id: 301, libraryId: 1, title: candidate.title, version: 1, verificationStatus: 'UNVERIFIED', sourceRef: candidate.traceId, createdAt: new Date().toISOString() }
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

  const row = title => page.locator('.rg-band .rg-row--cand', { hasText: title })
  const toast = () => page.locator('.kr-toast')

  // 1. 采纳遇 409：提示已被处理，行刷成真实状态，不出现错误弹窗。
  await row('连接池耗尽').getByRole('button', { name: '采纳' }).click()
  const popover = page.locator('.kr-pop')
  await popover.waitFor()
  assert.match(await popover.innerText(), /POST \/api\/knowledge\/candidates\/201\/promote/)
  assert.equal(await popover.locator('select').inputValue(), '1')
  await popover.getByRole('button', { name: '确认采纳' }).click()
  await page.waitForFunction(() => document.querySelector('.kr-toast')?.textContent.includes('该候选已被处理'))
  assert.equal(await page.locator('.kr-pop').count(), 0, '409 后应关闭 popover')
  await row('连接池耗尽').and(page.locator('.rg-row--rejected')).waitFor()
  const conflictToast = await toast().innerText()
  assert.match(conflictToast, /409 KNOWLEDGE_CANDIDATE_NOT_PENDING/)
  assert.match(conflictToast, /已刷新为服务端真实状态/)
  assert.equal(requests.filter(item => item.endsWith('/201/promote')).length, 1)

  // 2. 驳回原因必填：就地报错，且没有发出 reject 请求。
  await row('慢查询聚集').getByRole('button', { name: '驳回' }).click()
  await page.locator('.kr-pop').getByRole('button', { name: '确认驳回' }).click()
  await page.locator('.kr-pop__error').waitFor()
  assert.match(await page.locator('.kr-pop__error').innerText(), /请填写驳回原因/)
  assert.equal(requests.some(item => item.endsWith('/202/reject')), false)

  // 3. 填写原因后驳回成功：提示带方法与路径，行变已驳回。
  await page.locator('.kr-pop input').fill('证据不足（缺上游日志）')
  await page.locator('.kr-pop').getByRole('button', { name: '确认驳回' }).click()
  await page.waitForFunction(() => document.querySelector('.kr-toast')?.textContent.includes('已驳回'))
  assert.match(await toast().innerText(), /POST \/api\/knowledge\/candidates\/202\/reject → summary/)
  await row('慢查询聚集').and(page.locator('.rg-row--rejected')).waitFor()

  // 4. 采纳成功：提示写入目标与请求，行变已采纳且新条目回挂到同一泳道。
  await row('主从延迟').getByRole('button', { name: '采纳' }).click()
  await page.locator('.kr-pop').waitFor()
  await page.screenshot({ path: 'test-artifacts/review-actions-adopt-1440.png' })
  await page.locator('.kr-pop input').first().fill('主从延迟排查手册')
  await page.locator('.kr-pop').getByRole('button', { name: '确认采纳' }).click()
  await page.waitForFunction(() => document.querySelector('.kr-toast')?.textContent.includes('已采纳'))
  const adoptToast = await toast().innerText()
  assert.match(adoptToast, /在「K8s 运行手册」新建条目「主从延迟排查手册」v1（未验证）/)
  assert.match(adoptToast, /POST \/api\/knowledge\/candidates\/203\/promote/)
  await row('主从延迟').and(page.locator('.rg-row--done')).waitFor()
  assert.match(await row('主从延迟').innerText(), /已新建条目 v1（未验证）/)

  // 5. 375 宽：popover 仍完整落在视口内，页面不产生横向溢出。
  await page.setViewportSize({ width: 375, height: 900 })
  await row('端口耗尽').getByRole('button', { name: '驳回' }).click()
  await page.locator('.kr-pop').waitFor()
  const box = await page.locator('.kr-pop').boundingBox()
  assert.ok(box.x >= 0 && box.x + box.width <= 375, `popover out of viewport: ${JSON.stringify(box)}`)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  assert.ok(overflow <= 0, `horizontal overflow at 375: ${overflow}px`)
  await page.screenshot({ path: 'test-artifacts/review-actions-reject-375.png' })
  await page.locator('.kr-pop').getByRole('button', { name: '取消' }).click()

  assert.deepEqual(pageErrors, [])
  console.log('PASS: 409 → 刷新真实状态；驳回原因必填；驳回/采纳成功提示含方法与路径；新条目回挂泳道')
} finally {
  await browser.close()
}
