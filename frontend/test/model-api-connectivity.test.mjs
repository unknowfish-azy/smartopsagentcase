import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

test('development API uses same-origin requests with a backend proxy', async () => {
  const request = await readFile(new URL('../src/utils/request.ts', import.meta.url), 'utf8')
  const vite = await readFile(new URL('../vite.config.js', import.meta.url), 'utf8')
  // 代理实现位于共享工厂 vite.shared.mjs，入口只做装配。
  const shared = await readFile(new URL('../vite.shared.mjs', import.meta.url), 'utf8')
  assert.match(request, /VITE_API_BASE_URL\s*\|\|\s*['"]['"]|VITE_API_BASE_URL\s*\?\?\s*['"]['"]|VITE_API_BASE_URL\s*\|\|\s*['"]\s*['"]+/)
  assert.match(vite, /proxy:\s*devProxy\(backendOrigin\(\)\)/)
  assert.match(shared, /['"]\/api['"]/)
  assert.match(shared, /127\.0\.0\.1:8080/)
})
