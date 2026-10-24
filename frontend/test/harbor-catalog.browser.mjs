import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import { mockSession } from './helpers/session.mjs'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage()
  await mockSession(page)
  page.setDefaultTimeout(10000)
  await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'test' })))
  let configured = false
  let fail = false
  let projectRequests = 0
  await page.route('**/api/harbor/status', route => route.fulfill({ json: { code: 200, data: { configured, credentialsConfigured: configured } } }))
  await page.route('**/api/harbor/connection-check', route => route.fulfill({ json: { code: 200, data: { state: 'READABLE', checkedAt: new Date().toISOString(), traceId: 'mock-connection-trace' } } }))
  await page.route('**/api/harbor/projects?page=*', route => {
    projectRequests++
    return route.fulfill({ json: fail ? { code: 502, message: 'Harbor 不可达' } : { code: 200, data: {
      items: [{ name: 'demo', publicAccess: false, repositoryCount: 1 }], total: 1, page: 1, pageSize: 20, traceId: 'project-trace'
    } } })
  })
  await page.route('**/api/harbor/projects/demo/repositories?page=*', route => route.fulfill({ json: { code: 200, data: {
    items: [{ name: 'demo/nginx', artifactCount: 2 }], total: 1, page: 1, pageSize: 20, traceId: 'repository-trace'
  } } }))
  await page.goto('http://127.0.0.1:5173/tools/harbor-browser')
  const panel = page.locator('.harbor-browser')
  await panel.getByText('尚未配置 Harbor').waitFor()
  assert.equal(projectRequests, 0)
  configured = true
  await panel.getByRole('button', { name: '重新检查连接' }).click()
  await panel.getByRole('button', { name: 'demo' }).waitFor()
  await panel.getByRole('button', { name: 'demo' }).click()
  await panel.getByText('demo/nginx').waitFor()
  assert.match(await panel.innerText(), /2/)
  fail = true
  await panel.getByRole('button', { name: '刷新项目' }).click()
  await panel.getByRole('alert').filter({ hasText: 'Harbor 不可达' }).waitFor()
  assert.equal(await panel.getByRole('button', { name: 'demo' }).count(), 0)
  console.log('PASS: Harbor unconfigured, projects, repositories, and error states')
} finally { await browser.close() }
