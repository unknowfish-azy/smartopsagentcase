import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('mini runtime is local-only, project scoped and hidden', async () => {
  const source = await readFile(new URL('../start-mini.ps1', import.meta.url), 'utf8')
  assert.match(source, /127\.0\.0\.1:11434/)
  assert.match(source, /OLLAMA_NO_CLOUD\s*=\s*'1'/)
  assert.match(source, /OLLAMA_MODELS/)
  assert.match(source, /\.runtime\\mini/)
  assert.match(source, /-WindowStyle Hidden/)
  assert.match(source, /ExecutablePath/)
  assert.match(source, /refusing to stop/i)
  assert.match(source, /LocalAddress/)
  assert.match(source, /not bound to loopback/i)
  assert.doesNotMatch(source, /0\.0\.0\.0|OLLAMA_ORIGINS|SetEnvironmentVariable[^\n]*Machine/)
})

test('backend restart starts an installed local engine without silently downloading models', async () => {
  const source = await readFile(new URL('../restart-local-backend.ps1', import.meta.url), 'utf8')
  assert.match(source, /start-mini\.ps1/)
  assert.match(source, /Test-Path[^\n]*ollama\.exe/)
  assert.doesNotMatch(source, /ollama[^\n]*pull|Invoke-WebRequest/)
})
