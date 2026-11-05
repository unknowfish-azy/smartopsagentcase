import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/domain/chat/history.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
const { restoreHistory } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'))

test('restored history retains safe failure correlation and drops arbitrary metadata', () => {
  const run = { schema_version: '1.0.0', event_id: 'ev-1', request_id: 'req-1', task_id: 'task-1', run_id: 'run-1', step_id: null, status: 'failed', source: 'ai-service', timestamp: '2026-11-04T00:00:00Z' }
  const raw = JSON.stringify({ version: 1, activeId: 'chat-1', conversations: [{ id: 'chat-1', messages: [{ role: 'assistant', content: 'partial answer', error: true, metadata: { run_event: { ...run, api_key: 'never-copy' }, api_key: 'never-copy', degraded: true, effective_provider: 'mock' } }] }] })
  const restored = restoreHistory(raw)
  const message = restored.conversations[0].messages[0]
  assert.deepEqual(message.metadata.run_event, run)
  assert.equal(message.metadata.degraded, true)
  assert.equal(message.error, true)
  assert.equal(message.content, 'partial answer')
  assert.ok(!JSON.stringify(restored).includes('never-copy'))
})
