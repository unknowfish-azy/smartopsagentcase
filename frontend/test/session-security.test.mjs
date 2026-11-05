import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('development authentication uses the same-origin proxy and credentials', async () => {
  const request = await readFile(new URL('../src/utils/request.ts', import.meta.url), 'utf8')
  assert.match(request, /import\.meta\.env\.DEV\s*\?\s*''/)
  assert.match(request, /withCredentials:\s*true/)
})

test('terminal development traffic shares the authenticated origin', async () => {
  const terminal = await readFile(new URL('../src/components/operations/OperationsTerminal.vue', import.meta.url), 'utf8')
  const vite = await readFile(new URL('../vite.config.js', import.meta.url), 'utf8')
  // 代理已收敛到 vite.shared.mjs：入口配置只允许引用共享工厂，避免两端口各写一份。
  const shared = await readFile(new URL('../vite.shared.mjs', import.meta.url), 'utf8')
  assert.match(terminal, /import\.meta\.env\.DEV\s*\?\s*''/)
  assert.match(vite, /proxy:\s*devProxy\(backendOrigin\(\)\)/)
  assert.match(shared, /['"]\/ws['"]\s*:\s*\{\s*target,\s*ws:\s*true\s*\}/)
})

test('navigation verifies the server session rather than trusting preview storage', async () => {
  const router = await readFile(new URL('../src/router/index.js', import.meta.url), 'utf8')
  assert.match(router, /await loadSession\(/)
  assert.doesNotMatch(router, /if \(!localStorage\.getItem\('smartops_preview_auth'\)\)/)
})

test('browser model invocations use the user boundary, not the internal endpoint', async () => {
  const model = await readFile(new URL('../src/api/model.ts', import.meta.url), 'utf8')
  assert.ok(model.includes('/api/chat/connections/${id}/invoke'))
  assert.ok(!model.includes('/api/model-connections/${id}/invoke'))
})
