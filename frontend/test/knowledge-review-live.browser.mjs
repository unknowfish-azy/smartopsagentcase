// 泳道图 · 真实后端联调（不 mock 任何 /api）。
// 前置：scripts/e2e/knowledge_review_live_seed.py 已写入夹具并生成 test-artifacts/live-session.json。
// 校验：source_ref 回挂、真实计数、侧栏事实、UI 采纳/驳回真实落库、并发已被处理时不重复写库。

import assert from 'node:assert/strict'
import fs from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.env.SMARTOPS_REVIEW_BASE_URL || 'http://127.0.0.1:5173'
const SESSION_FILE = process.env.SMARTOPS_LIVE_SESSION
  || new URL('../test-artifacts/live-session.json', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')

const session = JSON.parse(fs.readFileSync(SESSION_FILE, 'utf8'))
const adoptTitle = 'E2E 联调：upstream 502 排查'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  await context.addCookies(session.cookies.map(({ name, value, domain, path }) => ({ name, value, domain, path })))
  const page = await context.newPage()
  page.setDefaultTimeout(25000)
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))

  const api = async path => {
    const response = await page.request.get(`${BASE}${path}`)
    return response.json()
  }
  const entriesNow = async () => {
    const body = await api(`/api/knowledge/personal/libraries/${session.libraryId}/entries?page=1&pageSize=100`)
    return body.data.items
  }

  await page.goto(`${BASE}/knowledge/review`)
  await page.locator('.rg-row--cand').first().waitFor()

  // 1. 真实计数与 source_ref 回挂。
  const bar = page.locator('.rg-bar')
  assert.match(await bar.innerText(), /3 待审/)
  assert.match(await bar.innerText(), /1 已采纳/)
  assert.match(await bar.innerText(), /1 已驳回/)
  assert.equal(await page.locator('.rg-chip').count(), 0, '有真实候选时不应进入演示模式')

  const entryA = page.locator('.rg-row--entry', { hasText: 'Pod 反复重启排查' })
  const entryB = page.locator('.rg-row--entry', { hasText: '连接池耗尽排查' })
  await entryA.waitFor()
  await entryB.waitFor()
  assert.match(await entryB.innerText(), /v1/, '条目版本来自真实 entry.version')
  assert.match(await entryB.innerText(), /无待审|1 条候选/, '已采纳候选挂在条目泳道')

  const crashRow = page.locator('.rg-row--cand', { hasText: 'Pod 反复重启：探针超时' }).first()
  assert.equal(await crashRow.locator('.rg-tag--target').count(), 0, 'source_ref 命中就不应标「待归类」')
  assert.equal(await page.locator('.rg-row--cand', { hasText: 'upstream 502' }).locator('.rg-tag--target').count(), 1)

  // 2. 侧栏事实来自真实候选与条目。
  await crashRow.click()
  const side = page.locator('.kr-side')
  await side.locator('.kr-side__facts').waitFor()
  assert.match(await side.innerText(), /live-trace-pod-crash/)
  assert.match(await side.innerText(), /Pod 反复重启排查 · v1/)

  // 3. UI 采纳：选一条没有条目的待审候选，真实 POST promote 后应自己形成一条新泳道。
  await page.locator('.rg-row--cand', { hasText: 'upstream 502' }).click()
  await side.locator('h2', { hasText: 'upstream 502' }).waitFor()
  await page.getByRole('button', { name: '采纳并新建条目' }).click()
  await page.locator('.kr-pop').waitFor()
  await page.locator('.kr-pop select').selectOption({ label: 'E2E 泳道联调库' })
  await page.locator('.kr-pop input[placeholder="条目标题"]').fill(adoptTitle)
  await page.locator('.kr-pop .kr-btn--primary').click()
  await page.locator('.kr-toast', { hasText: '已采纳' }).waitFor()
  await page.locator('.rg-row--entry', { hasText: adoptTitle }).waitFor()

  const afterAdopt = await entriesNow()
  assert.ok(afterAdopt.some(entry => entry.title === adoptTitle), 'promote 后条目应真实落库')

  // 4. UI 驳回：原因写进真实候选摘要。
  await page.locator('.rg-row--cand', { hasText: 'Pod 反复重启：探针超时' }).click()
  await side.locator('h2', { hasText: 'Pod 反复重启' }).waitFor()
  await page.getByRole('button', { name: '驳回并记录原因' }).click()
  await page.locator('.kr-pop input[placeholder="例：证据不足（缺上游日志）"]').fill('证据不足（联调）')
  await page.locator('.kr-pop .kr-btn--primary').click()
  await page.locator('.kr-toast', { hasText: '已驳回' }).waitFor()
  await page.locator('.rg-row--cand', { hasText: '驳回：证据不足（联调）' }).waitFor()

  // 5. 并发：先在接口上采纳 race 候选，再在已打开的弹层里确认 → 重新校验拦住，不重复写库。
  const raceId = session.candidates.race
  await page.locator('.rg-row--cand', { hasText: '取证顺序' }).click()
  await page.getByRole('button', { name: '采纳并新建条目' }).click()
  await page.locator('.kr-pop').waitFor()
  await page.locator('.kr-pop select').selectOption({ label: 'E2E 泳道联调库' })
  await page.locator('.kr-pop input[placeholder="条目标题"]').fill('E2E 竞态标题')

  const sessionBody = await api('/api/auth/session')
  const csrf = sessionBody.data.csrfToken
  const promote = await page.request.post(`${BASE}/api/knowledge/candidates/${raceId}/promote`, {
    headers: { 'X-CSRF-TOKEN': csrf },
    data: { libraryId: session.libraryId, title: 'E2E 竞态标题', contentMarkdown: '# 竞态' }
  })
  assert.equal(promote.status(), 200, '接口侧先行采纳应成功')

  await page.locator('.kr-pop .kr-btn--primary').click()
  await page.locator('.kr-toast', { hasText: '该候选已被处理' }).waitFor()
  const entryTitles = (await entriesNow()).map(entry => entry.title)
  assert.equal(entryTitles.filter(title => title === 'E2E 竞态标题').length, 1, '重复提交不应再建条目')

  await page.waitForTimeout(300)
  await page.screenshot({ path: 'test-artifacts/review-live-backend.png', fullPage: true })
  assert.deepEqual(pageErrors, [])
  console.log('PASS: 真实后端——计数、source_ref 回挂、侧栏事实、采纳/驳回落库、并发重复提交被拦')
} finally {
  await browser.close()
}
