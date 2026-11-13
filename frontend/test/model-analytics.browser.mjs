import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

// 两层前端拆分后门户端口可配；默认仍指向 5173 用户层 dev server
const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
await mkdir('test-artifacts/model-analytics', { recursive: true })
try {
  for (const width of [375, 768, 1024, 1440, 1920]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
    const errors = [], requests = [], saved = []
    let fail = false, failSave = false, budget = 30000, empty = false, delayMonth = ''
    page.on('pageerror', error => errors.push(error.message))
    // 防回归：mounted hook 的未处理错误会被 Vue 降级成 warning，但会污染 post flush 队列、
    // 让父组件后续更新全部丢失（曾导致 error-panel 不渲染）——必须一条都没有
    const vueWarnings = []
    page.on('console', message => { if (message.type() === 'warning' && /Unhandled error during execution/.test(message.text())) vueWarnings.push(message.text().slice(0, 120)) })
    await page.addInitScript(() => {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'analytics-check' }))
      localStorage.setItem('smartops_theme', 'dark')
    })
    const metric = { calls: 12, successes: 9, failures: 2, pendingCalls: 1, unknownUsageCalls: 2, knownTokens: 28410, inputTokens: 18000, outputTokens: 10410, successRate: 81.82, averageLatencyMs: 1280 }
    const report = month => ({
      month, timezone: 'UTC', budget, budgetUsedTokens: 28410, budgetUnknownCalls: 3,
      summary: empty ? { ...metric, calls: 0, successes: 0, failures: 0, pendingCalls: 0, unknownUsageCalls: 0, knownTokens: 0, inputTokens: 0, outputTokens: 0, successRate: null, averageLatencyMs: null } : metric,
      models: empty ? [] : [
        { ...metric, connectionId: 1, modelName: 'ops-reasoner' },
        { ...metric, connectionId: 2, modelName: 'lite-helper', calls: 5, successes: 4, failures: 1, pendingCalls: 0, unknownUsageCalls: 1, knownTokens: 12000, inputTokens: 8000, outputTokens: 4000, successRate: 80, averageLatencyMs: 640 }
      ],
      daily: Array.from({ length: 30 }, (_, i) => ({ date: `${month}-${String(i + 1).padStart(2, '0')}`, calls: 1,
        knownTokens: empty ? 0 : i === 10 ? null : i === 0 ? 0 : 500 + (i * 197 % 1800),
        inputTokens: empty ? 0 : i === 10 ? null : i === 0 ? 0 : 300 + (i * 127 % 1100),
        outputTokens: empty ? 0 : i === 10 ? null : i === 0 ? 0 : 200 + (i * 70 % 700),
        successRate: empty || i === 10 ? null : i % 5 === 0 ? 75 : 100,
        averageLatencyMs: empty || i === 10 ? null : 800 + (i * 137 % 1200)
      }))
    })
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET,PUT,OPTIONS' }
    // 单一路由内部分支（后注册的 route 优先级更高，不可分开注册）；
    // /api/auth/session 由 loadSession() 主动请求，未 mock 时会被守卫重定向到登录页。
    await page.route('**/api/**', async route => {
      const req = route.request(), url = new URL(req.url()), path = url.pathname
      if (!path.startsWith('/api/')) return route.continue()
      if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers })
      if (path === '/api/auth/session') {
        return route.fulfill({ headers, json: { code: 200, data: { user: { id: 1, username: 'analytics-check', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'analytics-csrf' } } })
      }
      if (path.startsWith('/api/model-connections')) return route.fulfill({ headers, json: [{ id: 1, name: '运维推理模型' }, { id: 2, name: '轻量助手' }] })
      if (path.startsWith('/api/model-analytics')) {
        if (req.method() === 'PUT') {
          if (failSave) return route.fulfill({ status: 503, headers, json: { message: 'unavailable' } })
          const body = req.postDataJSON(); saved.push(body); budget = body.tokenLimit
          return route.fulfill({ headers, json: report(body.month) })
        }
        requests.push(Object.fromEntries(url.searchParams))
        if (fail) return route.fulfill({ status: 503, headers, json: { message: 'unavailable' } })
        const month = url.searchParams.get('month')
        if (month === delayMonth) await new Promise(resolve => setTimeout(resolve, 1000))
        return route.fulfill({ headers, json: report(month) })
      }
      await route.fulfill({ headers, json: { code: 200, data: [] } })
    })
    await page.goto(`${base}/token-usage`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: 'Token 用量与额度', exact: true }).waitFor()
    await page.locator('.line-chart canvas').waitFor()
    assert.match(await page.locator('.metric-grid').innerText(), /28,410/)
    assert.match(await page.locator('.budget-warning').innerText(), /3 次调用/)
    // 环形配额：28,410 / 30,000 ≈ 94.7% → critical 档，aria-valuenow 取整
    assert.equal(await page.locator('.quota-ring').getAttribute('aria-valuenow'), '95')
    assert.match(await page.locator('.quota-ring').getAttribute('aria-label'), /已用 95%/)
    // 每日用量构成堆叠柱状图（配方 B）
    assert.equal(await page.locator('.stack-panel .stack-chart canvas').count(), 1)
    // ── 周期三档（claude-usage 配方）：今日 / 近 7 天 / 本月，期望值按 mock 现算（兼容任意运行日期）──
    const todayIso = new Date().toISOString().slice(0, 10)
    const todayIdx = Number(todayIso.slice(8, 10)) - 1
    const tokenAt = i => (i === 10 ? null : i === 0 ? 0 : 500 + (i * 197 % 1800))
    const zh = value => value.toLocaleString('zh-CN')
    if (todayIdx >= 0 && todayIdx < 30 && todayIdx !== 10) {
      await page.getByRole('button', { name: '今日', exact: true }).click()
      await page.waitForFunction(() => document.querySelector('.period-switch button[aria-pressed=true]')?.textContent === '今日')
      assert.match(await page.locator('.metric-grid').innerText(), new RegExp(zh(tokenAt(todayIdx))))
      // ── 环比徽标（tremor KPI delta badge）：今日档对昨日；无基数/未知时不渲染 ──
      const yesterdayIdx = todayIdx - 1
      if (yesterdayIdx >= 0 && yesterdayIdx !== 10 && tokenAt(yesterdayIdx) > 0 && tokenAt(todayIdx) != null) {
        const change = (tokenAt(todayIdx) - tokenAt(yesterdayIdx)) / tokenAt(yesterdayIdx) * 100
        const badge = page.locator('.metric-grid .metric-card').first().locator('.metric-delta')
        await badge.waitFor()
        assert.match(await badge.innerText(), /较上一日/)
        assert.match(await badge.innerText(), new RegExp(change > 0.05 ? '↑' : change < -0.05 ? '↓' : '持平'))
        if (Math.abs(change) > 0.05) assert.match(await badge.innerText(), new RegExp(`${Math.abs(change).toFixed(1)}%`))
      } else {
        // 昨日为 0/未知：不猜方向，徽标缺席
        assert.equal(await page.locator('.metric-grid .metric-card').first().locator('.metric-delta').count(), 0)
      }
    }
    const lastIdx = Math.min(todayIdx, 29)
    const weekSum = Array.from({ length: 7 }, (_, k) => lastIdx - 6 + k)
      .filter(i => i >= 0 && i <= lastIdx).map(i => tokenAt(i))
      .filter(value => value != null && value > 0).reduce((sum, value) => sum + value, 0)
    await page.getByRole('button', { name: '近 7 天', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('.period-switch button[aria-pressed=true]')?.textContent === '近 7 天')
    assert.match(await page.locator('.metric-grid').innerText(), new RegExp(zh(weekSum)))
    await page.getByRole('button', { name: '本月', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('.period-switch button[aria-pressed=true]')?.textContent === '本月')
    assert.match(await page.locator('.metric-grid').innerText(), /28,410/)
    // month 档：接口不提供上月 summary，不跨月拼凑 → 无环比徽标
    assert.equal(await page.locator('.metric-delta').count(), 0)
    // ── 模型消耗榜（tokscale 排行榜卡片）：降序 + 占比 + 徽章位 ──
    assert.equal(await page.locator('.leader-row').count(), 2)
    assert.match(await page.locator('.leader-row').first().innerText(), /ops-reasoner/)
    assert.match(await page.locator('.leader-row').first().innerText(), /28,410/)
    assert.match(await page.locator('.leader-row').first().innerText(), /70\.3%/) // 28,410 / 40,410
    assert.match(await page.locator('.leader-row').nth(1).innerText(), /lite-helper/)
    assert.equal(await page.locator('.leader-row').first().locator('.leader-rank').getAttribute('data-rank'), 'gold')
    // ── 模型份额环图（tremor DonutChart 复刻）：单霓虹色阶 + 图例 + 数据表 ──
    assert.equal(await page.locator('.share-donut-panel .donut-chart canvas').count(), 1)
    assert.equal(await page.locator('.donut-legend li').count(), 2)
    assert.match(await page.locator('.donut-legend').innerText(), /ops-reasoner/)
    assert.match(await page.locator('.donut-legend').innerText(), /70\.3%/) // 28,410 / 40,410
    assert.match(await page.locator('.donut-total').innerText(), /40,410/)
    await page.getByText('查看份额数据', { exact: true }).click()
    assert.match(await page.locator('.share-donut-panel .chart-data tbody tr').first().innerText(), /28,410\s+70\.3%/)
    await page.getByText('查看份额数据', { exact: true }).click()
    // 明细表新增输入 / 输出列（TokenTracker 列定义）
    assert.match(await page.locator('.model-breakdown table').innerText(), /18,000/)
    assert.match(await page.locator('.model-breakdown table').innerText(), /10,410/)
    // ── 用量构成 × 调用质量双栏（sniffly 版式）──
    assert.match(await page.locator('.quality-panel').innerText(), /用量构成与调用质量/)
    assert.match(await page.locator('.quality-panel').innerText(), /18,000/)
    assert.match(await page.locator('.quality-panel').innerText(), /10,410/)
    // ── 消耗速率与全月预计（token-monitor 配方）：28,410 / 已过去天数，线性外推 ──
    const paceDays = new Date(Date.UTC(Number(todayIso.slice(0, 4)), Number(todayIso.slice(5, 7)), 0)).getUTCDate()
    const elapsed = Number(todayIso.slice(8, 10))
    const projected = Math.round(28410 / elapsed * paceDays)
    assert.match(await page.locator('.pace-readout').innerText(), new RegExp(zh(projected)))
    assert.match(await page.locator('.pace-readout').innerText(), new RegExp((28410 / elapsed * paceDays / 30000 * 100).toFixed(1)))
    const daysToLimit = Math.ceil(30000 / (28410 / elapsed))
    if (daysToLimit <= paceDays) assert.match(await page.locator('.pace-readout').innerText(), new RegExp(`${todayIso.slice(5, 7)}-${String(daysToLimit).padStart(2, '0')}`))
    // 额度节奏线说明（markLine 本体不逐像素断言，说明文案 + 图表存在性足够）
    assert.match(await page.locator('.trend-panel').innerText(), /额度节奏线/)
    // ── 自动刷新（Claude-Code-Agent-Monitor 的轮询适配）：时间戳 + 静默刷新不清空内容 ──
    assert.match(await page.locator('.refresh-stamp').innerText(), /更新于 \d{2}:\d{2}:\d{2}/)
    await page.getByLabel('自动刷新 60 秒').check()
    await page.waitForFunction(() => document.querySelector('.refresh-stamp')?.textContent?.includes('更新于'))
    assert.match(await page.locator('.metric-grid').innerText(), /28,410/) // 静默刷新不清空 KPI
    await page.getByLabel('自动刷新 60 秒').uncheck()
    await page.getByText('查看每日数据', { exact: true }).click()
    assert.match(await page.locator('.chart-data tbody tr').first().innerText(), /0\s+0\s+0/)
    assert.match(await page.locator('.chart-data tbody tr').nth(10).innerText(), /—/)
    await page.getByText('查看每日数据', { exact: true }).click()
    await page.getByLabel('模型连接', { exact: true }).selectOption('1')
    await page.waitForFunction(() => !document.querySelector('.model-analytics[aria-busy=true]'))
    assert.equal(requests.at(-1).connectionId, '1')
    assert.match(await page.locator('.budget-panel').innerText(), /全部模型共享/)
    await page.getByLabel('设置本月额度（Token）').fill('0')
    await page.getByRole('button', { name: '保存额度', exact: true }).click()
    await page.getByText('本月额度已保存。', { exact: true }).waitFor()
    assert.equal(saved.at(-1).tokenLimit, 0)
    assert.match(await page.locator('.budget-remaining').innerText(), /超出 28,410/)
    assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'), '100')
    await page.getByLabel('设置本月额度（Token）').fill('1.5')
    await page.getByRole('button', { name: '保存额度', exact: true }).click()
    await page.locator('.budget-form [role=alert]').waitFor()
    assert.equal(saved.length, 1)
    await page.getByLabel('设置本月额度（Token）').fill('40000')
    failSave = true
    await page.getByRole('button', { name: '保存额度', exact: true }).click()
    await page.locator('.budget-form [role=alert]').waitFor()
    assert.match(await page.locator('.budget-remaining').innerText(), /超出 28,410/)
    failSave = false
    await page.getByRole('button', { name: '保存额度', exact: true }).click()
    await page.getByText('本月额度已保存。', { exact: true }).waitFor()
    assert.match(await page.locator('.budget-remaining').innerText(), /11,590/)
    await page.getByLabel('设置本月额度（Token）').fill('')
    await page.getByRole('button', { name: '保存额度', exact: true }).click()
    await page.getByText('已取消本月额度。', { exact: true }).waitFor()
    assert.equal(saved.at(-1).tokenLimit, null)
    await page.getByLabel('设置本月额度（Token）').fill('40000')
    await page.getByRole('button', { name: '保存额度', exact: true }).click()
    await page.getByText('本月额度已保存。', { exact: true }).waitFor()
    await page.reload({ waitUntil: 'networkidle' })
    assert.equal(await page.getByLabel('设置本月额度（Token）').inputValue(), '40000')
    delayMonth = '2026-08'
    await page.getByLabel('统计月份', { exact: true }).fill('2026-08')
    await page.waitForTimeout(100)
    await page.getByLabel('统计月份', { exact: true }).fill('2026-07')
    await page.waitForTimeout(1300)
    assert.match(await page.locator('.model-breakdown .unit-label').innerText(), /2026-07/)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: `test-artifacts/model-analytics/tokens-${width}-dark.png`, fullPage: true })
    await page.getByLabel('选择主题模式').selectOption('light')
    await page.screenshot({ path: `test-artifacts/model-analytics/tokens-${width}-light.png`, fullPage: true })
    await page.locator('.analytics-tabs').getByRole('link', { name: '模型强度', exact: true }).click()
    await page.getByRole('heading', { name: '模型强度', exact: true }).waitFor()
    assert.equal(await page.locator('.line-chart canvas').count(), 2)
    assert.match(await page.locator('.metric-grid').innerText(), /81.8/)
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: `test-artifacts/model-analytics/strength-${width}-light.png`, fullPage: true })
    if (width === 375) {
      await page.getByRole('button', { name: '切换导航', exact: true }).click()
      await page.locator('.personal-system-navigation').getByRole('link', { name: /TOKEN USAGE/ }).click()
      await page.getByRole('heading', { name: 'Token 用量与额度', exact: true }).waitFor()
    }
    else {
      // 1440px 分支此时停在模型强度 tab，空态断言只对 Token 页的 donut 有意义，先切回
      await page.locator('.analytics-tabs').getByRole('link', { name: 'Token 用量与额度', exact: true }).click()
      await page.getByRole('heading', { name: 'Token 用量与额度', exact: true }).waitFor()
    }
    empty = true
    await page.getByRole('button', { name: '刷新统计', exact: true }).click()
    await page.locator('.empty-notice').waitFor()
    assert.match(await page.locator('.share-donut-panel').innerText(), /无法计算模型份额/) // 全未知时不给空环图
    fail = true
    await page.getByRole('button', { name: '刷新统计', exact: true }).click()
    await page.getByRole('heading', { name: '暂时无法读取统计', exact: true }).waitFor()
    assert.equal(await page.locator('.metric-grid').count(), 0)
    fail = false
    await page.getByRole('button', { name: '重新加载', exact: true }).click()
    await page.locator('.empty-notice').waitFor()
    assert.deepEqual(errors, [])
    assert.deepEqual(vueWarnings, [])
    console.log(`PASS ${width}px analytics: charts, themes, filters, request races, budget validation/save/reload, empty/error states and navigation (mock API)`)
    await page.close()
  }
} finally { await browser.close() }
