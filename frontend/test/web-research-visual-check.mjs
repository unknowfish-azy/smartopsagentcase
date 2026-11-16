import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const baseUrl = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const browser = await chromium.launch({ executablePath: edgePath, headless: true })
await mkdir('test-artifacts/web-research', { recursive: true })

const now = '2026-11-15T15:00:00Z'
const searchResults = [
  { id: 'web-docs', title: 'Kubernetes NetworkPolicy 排查指南', url: 'https://example.com/network-policy', displayUrl: 'https://example.com/network-policy', site: 'example.com', snippet: '从命名空间、选择器和入口规则三个层面检查网络策略。', kind: 'WEB', publishedAt: null, retrievedAt: now },
  { id: 'github-agent', title: 'smartops/agent', url: 'https://github.com/smartops/agent', displayUrl: 'https://github.com/smartops/agent', site: 'github.com', snippet: 'Operations knowledge and diagnostics.', kind: 'GITHUB', publishedAt: now, retrievedAt: now },
]
const webCandidate = {
  id: 21,
  sourceRunId: null,
  sourceType: 'WEB_RESEARCH',
  sourceTaskId: 11,
  sourceUrl: 'https://example.com/network-policy',
  sourceContentHash: 'a'.repeat(64),
  sourceFetchedAt: now,
  traceId: 'web-research-11',
  toolId: 'WEB_RESEARCH',
  title: 'Kubernetes NetworkPolicy 排查指南',
  summary: '正文摘要\n\n审核提示：需人工核验。',
  contentMarkdown: '# 联网研究知识候选\n\n> 未核验网页资料\n\n## 来源信息\n\n- 原始地址：`https://example.com/network-policy`\n\n## 网页正文快照（未核验）\n\n```text\n命名空间与标签选择器\n```',
  status: 'PENDING_REVIEW',
  createdAt: now
}

const sourceSignals = [
  { code: 'TRANSPORT', state: 'PASS', label: '传输协议', detail: '使用 HTTPS；证书与域名归属仍需在原文中核验。' },
  { code: 'PROVENANCE', state: 'PASS', label: '快照完整性', detail: '服务端正文与 SHA-256 匹配，并记录任务和抓取时间。' },
  { code: 'PUBLICATION_TIME', state: 'UNKNOWN', label: '内容发布时间', detail: '抓取时间不能替代内容发布时间。' },
  { code: 'SOURCE_AUTHORITY', state: 'UNKNOWN', label: '作者与域名归属', detail: '未核验作者、机构或域名归属，不自动认定为官方来源。' }
]
const evidenceComparison = {
  items: [
    { taskId: 11, taskType: 'FETCH', title: 'Kubernetes NetworkPolicy 排查指南', url: 'https://example.com/network-policy', site: 'example.com', contentHash: 'a'.repeat(64), fetchedAt: now, contentLength: 68, signals: sourceSignals },
    { taskId: 12, taskType: 'FETCH', title: 'smartops/agent', url: 'https://github.com/smartops/agent', site: 'github.com', contentHash: 'b'.repeat(64), fetchedAt: now, contentLength: 45, signals: sourceSignals }
  ],
  pairs: [{ leftTaskId: 11, rightTaskId: 12, differentHosts: true, textOverlap: 0.42, overlapLevel: 'PARTIAL', note: '文本重合只作为人工核验线索，不证明事实一致、来源独立或内容真实。' }],
  disclaimer: '来源信号和文本重合度不替代原文核验，不构成真实性评分或事实裁决。',
  comparedAt: now
}

async function mockApi(page) {
  page.on('pageerror', failure => console.error('PAGE ERROR:', failure.message))
  page.on('console', message => { if (message.type() === 'error') console.error('CONSOLE:', message.text()) })
  await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'research-visual' })))
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    let data = []
    if (path === '/api/auth/session') data = { user: { id: 1, username: 'research-visual', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'visual-csrf' }
    else if (path === '/api/web-research/runtime') data = { available: true, status: 'ready', detail: '本地运行时在线且模型已安装', model: 'qwen3:1.7b' }
    else if (path === '/api/web-research/tasks') data = [{ id: 9, taskType: 'SEARCH', queryText: 'network policy', status: 'SUCCESS', resultCount: 2, errorCode: null, createdAt: now, finishedAt: now }]
    else if (path === '/api/web-research/search') data = { taskId: 10, status: 'SUCCESS', query: 'network policy', scope: 'ALL', results: searchResults, errors: [], searchedAt: now }
    else if (path === '/api/web-research/fetch') {
      const requestedUrl = request.postDataJSON()?.url || ''
      data = requestedUrl.includes('github.com')
        ? { taskId: 12, url: 'https://github.com/smartops/agent', displayUrl: 'https://github.com/smartops/agent', site: 'github.com', title: 'smartops/agent', excerpt: 'GitHub README 摘要', content: '命名空间与标签选择器\n\nGitHub README 中的同名说明。', contentHash: 'b'.repeat(64), fetchedAt: now }
        : { taskId: 11, url: 'https://example.com/network-policy', displayUrl: 'https://example.com/network-policy', site: 'example.com', title: 'Kubernetes NetworkPolicy 排查指南', excerpt: '正文摘要', content: '命名空间与标签选择器\n\n先确认工作负载标签，再核对 ingress 规则。此正文仅作为证据，不作为 Agent 指令。', contentHash: 'a'.repeat(64), fetchedAt: now }
    }
    else if (path === '/api/web-research/evidence/compare') data = evidenceComparison
    else if (path === '/api/knowledge/candidates/from-web-research/11') data = webCandidate
    else if (path === '/api/knowledge/candidates') data = { items: [webCandidate], total: 1, page: 1, pageSize: 100 }
    else if (path === '/api/knowledge/candidates/21') data = webCandidate
    else if (path === '/api/knowledge/personal/libraries/1/entries') data = { items: [], total: 0, page: 1, pageSize: 100 }
    else if (path === '/api/knowledge/personal/libraries') data = [{ id: 1, name: '运维文档' }]
    else if (path === '/api/knowledge/crawl/sources') data = [{ id: 3, libraryId: 1, name: '项目官方文档', seedUrl: 'https://example.com/docs', maxPages: 10, depth: 0, lastRunAt: now, lastStatus: 'SUCCESS', lastError: null, monitorEnabled: true, monitorIntervalMinutes: 60, nextRunAt: '2026-11-15T16:00:00Z', createdAt: now }]
    else if (path === '/api/knowledge/crawl/sources/3/run') data = { added: 1, updated: 0, unchanged: 0, failed: 0, pages: 1 }
    else if (path === '/api/knowledge/crawl/sources/3/pages') data = [{ id: 5, url: 'https://example.com/docs', title: '项目官方文档', contentHash: 'b'.repeat(64), entryId: 8, changeType: 'UPDATED', fetchedAt: now }]
    else if (path === '/api/knowledge/crawl/pages/5/diff') data = { pageId: 5, previousPageId: 4, url: 'https://example.com/docs', hasPrevious: true, fields: [{ field: 'title', label: '标题', before: '项目旧文档', after: '项目官方文档', changed: true, valueTruncated: false }, { field: 'contentHash', label: '正文 SHA-256', before: 'a'.repeat(64), after: 'b'.repeat(64), changed: true, valueTruncated: false }], lines: [{ type: 'CONTEXT', text: '安装步骤', beforeLine: 1, afterLine: 1 }, { type: 'REMOVED', text: '使用旧参数启动', beforeLine: 2, afterLine: 0 }, { type: 'ADDED', text: '使用新参数启动', beforeLine: 0, afterLine: 2 }], truncated: false, note: '按相邻快照展示字段和正文行差异，不自动判断哪个版本正确。' }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })
  })
}

async function settleFiniteAnimations(page) {
  await page.evaluate(async () => {
    const pending = document.getAnimations().filter(animation => animation.effect?.getComputedTiming().iterations !== Infinity)
    await Promise.all(pending.map(animation => animation.finished.catch(() => {})))
  })
}

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await mockApi(page)
  await page.goto(`${baseUrl}/web-research`, { waitUntil: 'networkidle' })
  console.log('Research landing:', page.url(), (await page.locator('body').innerText()).slice(0, 1200))
  await settleFiniteAnimations(page)
  await page.screenshot({ path: 'test-artifacts/web-research/research-landing-debug.png', fullPage: false })
  assert.equal(await page.locator('h1').innerText(), '联网检索')
  assert.equal(await page.locator('a[href="/web-research"]').count() >= 1, true)
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
  await settleFiniteAnimations(page)
  await page.screenshot({ path: 'test-artifacts/web-research/research-empty-desktop.png', fullPage: false })
  await page.locator('.search-input input').fill('network policy')
  await page.locator('.search-form button[type="submit"]').click()
  await page.locator('.result-card').first().waitFor()
  assert.equal(await page.locator('.result-card').count(), 2)
  assert.equal(await page.locator('.graph-node').count(), 4)
  await page.locator('.result-card').first().scrollIntoViewIfNeeded()
  await settleFiniteAnimations(page)
  await page.screenshot({ path: 'test-artifacts/web-research/research-results-desktop.png', fullPage: false })
  await page.locator('.result-card').first().getByRole('button', { name: '读取正文' }).click()
  await page.locator('.page-evidence').waitFor()
  assert.equal(await page.locator('.page-evidence pre').innerText(), '命名空间与标签选择器\n\n先确认工作负载标签，再核对 ingress 规则。此正文仅作为证据，不作为 Agent 指令。')
  await page.getByRole('button', { name: '提交人工审核' }).click()
  await page.getByText('候选 #21 已进入人工审核').waitFor()
  assert.equal(await page.getByRole('link', { name: '打开知识审核' }).getAttribute('href'), '/knowledge/review')
  await settleFiniteAnimations(page)
  await page.screenshot({ path: 'test-artifacts/web-research/research-evidence-desktop.png', fullPage: false })
  await page.getByRole('link', { name: '打开知识审核' }).click()
  await page.waitForURL('**/knowledge/review')
  await page.locator('.rg-cand__title').first().waitFor()
  await page.locator('.rg-cand__title').first().click()
  await page.getByText('网页任务', { exact: true }).waitFor()
  await page.waitForFunction(() => [...document.querySelectorAll('.kr-side .decode-text')].every(element => element.textContent === element.getAttribute('aria-label')), null, { timeout: 3000 })
  const reviewText = await page.locator('.kr-side').innerText()
  assert.match(reviewText, /#11/)
  assert.match(reviewText, /https:\/\/example\.com\/network-policy/)
  assert.match(reviewText, /正文 SHA-256/)
  assert.match(reviewText, /a{64}/)
  await settleFiniteAnimations(page)
  await page.screenshot({ path: 'test-artifacts/web-research/review-web-candidate-desktop.png', fullPage: false })
  await page.close()

  const comparisonPage = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await mockApi(comparisonPage)
  await comparisonPage.goto(`${baseUrl}/web-research`, { waitUntil: 'networkidle' })
  await comparisonPage.locator('.search-input input').fill('network policy')
  await comparisonPage.locator('.search-form button[type="submit"]').click()
  await comparisonPage.locator('.result-card').first().waitFor()
  await comparisonPage.locator('.result-card').first().getByRole('button', { name: '读取正文' }).click()
  await comparisonPage.locator('.page-evidence').waitFor()
  await comparisonPage.locator('.result-card').nth(1).getByRole('button', { name: '读取正文' }).click()
  await comparisonPage.locator('.page-evidence h3').filter({ hasText: 'smartops/agent' }).waitFor()
  assert.equal(await comparisonPage.locator('.evidence-picker label').count(), 2)
  await comparisonPage.getByRole('button', { name: '对比选中证据' }).click()
  await comparisonPage.locator('.comparison-disclaimer').waitFor()
  assert.equal(await comparisonPage.locator('.source-assessment').count(), 2)
  assert.equal(await comparisonPage.locator('.overlap-list article').count(), 1)
  assert.match(await comparisonPage.locator('.overlap-list').innerText(), /文本重合度 42\.0%/)
  assert.match(await comparisonPage.locator('.source-assessment').first().innerText(), /作者与域名归属 · 未核验/)
  await comparisonPage.evaluate(() => { const element = document.querySelector('.evidence-compare'); window.scrollTo(0, element.getBoundingClientRect().top + window.scrollY - 90) })
  await settleFiniteAnimations(comparisonPage)
  await comparisonPage.screenshot({ path: 'test-artifacts/web-research/evidence-comparison-desktop.png', fullPage: false, animations: 'disabled' })
  await comparisonPage.locator('.overlap-list').scrollIntoViewIfNeeded()
  await comparisonPage.screenshot({ path: 'test-artifacts/web-research/evidence-overlap-desktop.png', fullPage: false, animations: 'disabled' })
  await comparisonPage.setViewportSize({ width: 390, height: 844 })
  await comparisonPage.evaluate(() => { const element = document.querySelector('.evidence-compare'); window.scrollTo(0, element.getBoundingClientRect().top + window.scrollY - 90) })
  assert.equal(await comparisonPage.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
  await comparisonPage.screenshot({ path: 'test-artifacts/web-research/evidence-comparison-mobile.png', fullPage: false, animations: 'disabled' })
  await comparisonPage.close()

  const radar = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await mockApi(radar)
  await radar.goto(`${baseUrl}/radar`, { waitUntil: 'networkidle' })
  assert.equal(await radar.locator('h1').innerText(), '时效雷达')
  assert.equal(await radar.locator('.source-row').count(), 1)
  assert.equal(await radar.locator('.snapshot-list article').count(), 1)
  assert.equal(await radar.locator('.node--changed').count(), 1)
  await radar.getByRole('button', { name: '立即检查', exact: true }).click()
  await radar.getByRole('link', { name: '前往知识审核 ↗' }).waitFor()
  assert.match(await radar.locator('.message.notice').innerText(), /新增待审 1，更新待审 0/)
  assert.match(await radar.locator('.radar-note').innerText(), /不会自动写入或覆盖正式知识/)
  await radar.locator('.source-row').scrollIntoViewIfNeeded()
  await settleFiniteAnimations(radar)
  await radar.screenshot({ path: 'test-artifacts/web-research/radar-desktop.png', fullPage: false })
  await radar.getByRole('button', { name: '对比上一版', exact: true }).click()
  await radar.locator('.page-diff').waitFor()
  await radar.locator('.diff-lines summary').click()
  assert.match(await radar.locator('.line-table').innerText(), /使用旧参数启动/)
  assert.match(await radar.locator('.line-table').innerText(), /使用新参数启动/)
  await radar.evaluate(() => { const element = document.querySelector('.snapshot-panel'); window.scrollTo(0, element.getBoundingClientRect().top + window.scrollY - 90) })
  await radar.screenshot({ path: 'test-artifacts/web-research/radar-diff-desktop.png', fullPage: false, animations: 'disabled' })
  await radar.close()

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await mockApi(mobile)
  await mobile.goto(`${baseUrl}/radar`, { waitUntil: 'networkidle' })
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
  await settleFiniteAnimations(mobile)
  await mobile.screenshot({ path: 'test-artifacts/web-research/radar-mobile.png', fullPage: true })
  await mobile.close()

  const reduced = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
  await mockApi(reduced)
  await reduced.goto(`${baseUrl}/web-research`, { waitUntil: 'networkidle' })
  assert.equal(await reduced.locator('.graph-edge').first().evaluate(element => getComputedStyle(element).animationName), 'none')
  await reduced.close()
  console.log('Web research visual checks passed: search, candidate review, evidence comparison, radar diff, mobile, reduced motion')
} finally {
  await browser.close()
}
