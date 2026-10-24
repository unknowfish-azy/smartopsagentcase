import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts', { recursive: true })
const sleep = delay => new Promise(resolve => setTimeout(resolve, delay))
const listing = items => ({ items, total: items.length, page: 1, pageSize: 20, traceId: 'mock-foundation-trace' })

async function assertNoOverflow(page, selector) {
  assert.equal(await page.locator(selector).evaluate(element => element.getBoundingClientRect().right > innerWidth + 1), false, `${selector} overflows viewport`)
}

try {
  for (const width of [375, 1440]) {
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } })
      page.setDefaultTimeout(15000)
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      await page.addInitScript(theme => {
        localStorage.setItem('smartops_theme', theme)
        localStorage.setItem('smartops_visual_mode', 'reduced-motion')
      }, theme)
      let checkState = 'READABLE', oldCheck = false, slowRepositories = false, unexpectedWrites = 0
      await page.route('**/api/**', async route => {
        const url = new URL(route.request().url())
        if (!url.pathname.startsWith('/api/')) return route.continue()
        if (route.request().method() !== 'GET') unexpectedWrites++
        let data = []
        if (url.pathname === '/api/auth/session') data = { user: { id: 17, username: 'foundation-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'mock-csrf' }
        if (url.pathname === '/api/harbor/status') data = { configured: true, credentialsConfigured: true }
        if (url.pathname === '/api/harbor/connection-check') data = { state: checkState, checkedAt: new Date(Date.now() - (oldCheck ? 360000 : 0)).toISOString(), message: '当前凭据读取验证' }
        if (url.pathname === '/api/harbor/projects') data = listing([{ name: 'demo', repositoryCount: 1 }, { name: 'other', repositoryCount: 1 }])
        if (url.pathname.endsWith('/demo/repositories')) {
          if (slowRepositories) await sleep(600)
          data = listing([{ name: 'demo/team/image', artifactCount: 1 }])
        }
        if (url.pathname.endsWith('/other/repositories')) data = listing([{ name: 'other/new-image', artifactCount: 1 }])
        if (url.pathname.endsWith('/demo/artifacts')) {
          assert.equal(url.searchParams.get('repository'), 'team/image')
          data = listing([{ digest: 'sha256:foundation-example', tags: ['v1'], size: 1048576, platforms: ['linux/amd64'], type: 'IMAGE', pushedAt: '2026-10-02T10:00:00Z' }])
        }
        await route.fulfill({ json: { code: 200, data } })
      })
      await page.goto(`${base}/harbor`, { waitUntil: 'networkidle' })
      const harbor = page.locator('.harbor-browser')
      await harbor.getByText('项目读取成功', { exact: true }).waitFor()
      await harbor.getByRole('button', { name: /^demo / }).click()
      await harbor.getByRole('button', { name: /^demo\/team\/image / }).click()
      await harbor.locator('.artifact-card').waitFor()
      assert.match(await harbor.locator('.artifact-card').innerText(), /linux\/amd64/)
      await harbor.getByLabel('筛选当前页 Tag / Digest').fill('not-found')
      assert.equal(await harbor.locator('.artifact-card').count(), 0)
      await harbor.getByLabel('筛选当前页 Tag / Digest').fill('v1')
      await harbor.locator('.artifact-card').waitFor()
      await assertNoOverflow(page, '.harbor-browser')
      await page.screenshot({ path: `test-artifacts/foundation-harbor-${theme}-${width}.png`, fullPage: true })
      slowRepositories = true
      await harbor.getByRole('button', { name: /^demo / }).click()
      await harbor.getByRole('button', { name: /^other / }).click()
      await harbor.getByRole('button', { name: /^other\/new-image / }).waitFor()
      await sleep(700)
      assert.equal(await harbor.getByRole('button', { name: /^demo\/team\/image / }).count(), 0)
      assert.equal(await harbor.locator('.artifact-panel').count(), 0)
      oldCheck = true
      await harbor.getByRole('button', { name: '重新检查连接' }).click()
      await harbor.getByText('检查结果已过期', { exact: true }).waitFor()
      checkState = 'AUTHENTICATION'; oldCheck = false
      await harbor.getByRole('button', { name: '重新检查连接' }).click()
      await harbor.getByText('认证失败', { exact: true }).waitFor()

      await page.goto(`${base}/cloud-native`, { waitUntil: 'networkidle' })
      await page.getByRole('combobox', { name: '环境', exact: true }).selectOption('production')
      await page.getByLabel('集群 Context', { exact: true }).fill('prod-east')
      await page.getByLabel('Namespace', { exact: true }).fill('orders')
      await page.getByRole('button', { name: '应用上下文' }).click()
      await page.getByText('目标意图已保存，尚未连接集群。').waitFor()
      await page.getByRole('button', { name: /容器与集群/ }).click()
      await page.getByRole('button', { name: /Kubernetes 资源检查/ }).click()
      await page.locator('.cloud-detail .markdown-note').waitFor()
      assert.equal(await page.getByRole('dialog').count(), 0)
      await assertNoOverflow(page, '.cloud-workbench')
      await page.screenshot({ path: `test-artifacts/foundation-cloud-${theme}-${width}.png`, fullPage: true })
      await page.getByRole('link', { name: /进入只读工具/ }).click()
      await page.locator('.cloud-context-notice').waitFor()
      assert.match(await page.locator('.cloud-context-notice').innerText(), /prod-east.*orders/)
      assert.equal(await page.locator('.cloud-context-notice input').isChecked(), false)
      assert.equal((await page.locator('.tool-parameters input').evaluateAll(inputs => inputs.map(input => input.value))).includes('orders'), false)
      await page.locator('.cloud-context-notice input').check()
      await page.locator('.tool-nav a[href*="k8s-logs"]').click()
      assert.equal(new URL(page.url()).searchParams.get('cloudNamespace'), 'orders')
      assert.equal(await page.locator('.cloud-context-notice input').isChecked(), false)
      await page.getByRole('link', { name: '返回云原生工作台' }).click()
      assert.equal(await page.getByLabel('Namespace', { exact: true }).inputValue(), 'orders')
      await page.getByRole('button', { name: /容器与集群/ }).click()
      await page.getByRole('combobox', { name: '环境', exact: true }).selectOption('development')
      await page.getByRole('button', { name: '应用上下文' }).click()
      await page.waitForFunction(() => !document.querySelector('.cloud-detail'))

      await page.goto(`${base}/knowledge`, { waitUntil: 'networkidle' })
      assert.equal(await page.locator('.result-row').count(), 30)
      const firstTitle = await page.locator('.result-row h3').first().innerText()
      await page.getByRole('button', { name: '下一页资料' }).click()
      assert.notEqual(await page.locator('.result-row h3').first().innerText(), firstTitle)
      await page.locator('#knowledge-query').fill('镜像拉不下来')
      await page.getByRole('button', { name: 'SEARCH', exact: true }).click()
      assert.ok(await page.locator('.knowledge-match').count() > 0)
      assert.match(await page.locator('.knowledge-verification').first().innerText(), /未人工核验/)
      await assertNoOverflow(page, '.knowledge-toolbar')
      await page.screenshot({ path: `test-artifacts/foundation-knowledge-${theme}-${width}.png`, fullPage: true })
      assert.deepEqual(errors, [])
      assert.equal(unexpectedWrites, 0)
      console.log(`PASS ${theme} ${width}px: artifacts, stale/auth states, request race, cloud intent, single detail, knowledge aliases; mocked APIs, no writes`)
      await page.close()
    }
  }
} finally { await browser.close() }
