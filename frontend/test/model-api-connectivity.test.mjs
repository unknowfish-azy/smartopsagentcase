import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

test('development API uses same-origin requests with a backend proxy', async () => {
  const request = await readFile(new URL('../src/utils/request.js', import.meta.url), 'utf8')
  const vite = await readFile(new URL('../vite.config.js', import.meta.url), 'utf8')
  assert.match(request, /VITE_API_BASE_URL\s*\|\|\s*['"]['"]|VITE_API_BASE_URL\s*\?\?\s*['"]['"]|VITE_API_BASE_URL\s*\|\|\s*['"]\s*['"]+/)
  assert.match(vite, /proxy/)
  assert.match(vite, /['"]\/api['"]/)
  assert.match(vite, /8080/)
})
