import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

// Execute the production TS after the same type erasure used by the build.
const source = await readFile(new URL('../src/api/stream.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source.replaceAll('import.meta.env', '({})'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }
}).outputText
const { streamChat } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'))

function mockStream(t, pieces) {
  t.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({
    start(controller) {
      for (const text of pieces) controller.enqueue(new TextEncoder().encode(text))
      controller.close()
    }
  }), { headers: { 'Content-Type': 'text/event-stream' } }))
}

test('SSE CRLF and split delimiters preserve tokens and completion', async t => {
  mockStream(t, ['event: token\r\ndata: {"delta":"真实"}\r', '\n\r\nevent: done\r\ndata: {"model":"local"}\r\n\r\n'])
  const tokens = [], done = []
  await streamChat('question', { onToken: value => tokens.push(value), onDone: value => done.push(value) })
  assert.deepEqual(tokens, ['真实'])
  assert.deepEqual(done, [{ model: 'local' }])
})

test('server error rejects with partial tokens preserved and no done', async t => {
  mockStream(t, ['event: token\ndata: {"delta":"partial"}\n\nevent: error\ndata: {"message":"interrupted"}\n\n'])
  const tokens = [], errors = [], done = []
  await assert.rejects(streamChat('question', { onToken: value => tokens.push(value), onError: error => errors.push(error.message), onDone: value => done.push(value) }), /interrupted/)
  assert.deepEqual(tokens, ['partial'])
  assert.deepEqual(errors, ['interrupted'])
  assert.deepEqual(done, [])
})

test('EOF before done rejects even when a token was received', async t => {
  mockStream(t, ['event: token\ndata: {"delta":"partial"}\n\n'])
  await assert.rejects(streamChat('question'), /结束|中断/)
})

test('malformed JSON is not converted into empty success', async t => {
  mockStream(t, ['event: done\ndata: invalid\n\n'])
  await assert.rejects(streamChat('question'), /JSON|格式/)
})

test('LF stream and final event without separator remain compatible', async t => {
  mockStream(t, ['event: token\ndata: {"delta":"ok"}\n\nevent: done\ndata: {}'])
  const tokens = [], done = []
  await streamChat('question', { onToken: value => tokens.push(value), onDone: value => done.push(value) })
  assert.deepEqual(tokens, ['ok'])
  assert.deepEqual(done, [{}])
})

test('AbortError propagates without reporting a service fault', async t => {
  t.mock.method(globalThis, 'fetch', async () => { throw new DOMException('cancelled', 'AbortError') })
  const errors = []
  await assert.rejects(streamChat('question', { onError: error => errors.push(error) }), { name: 'AbortError' })
  assert.deepEqual(errors, [])
})

test('run and terminal error preserve correlation without treating it as completion', async t => {
  const run = { request_id: 'req-1', task_id: 'task-1', run_id: 'run-1', status: 'started' }
  mockStream(t, [`event: run\ndata: ${JSON.stringify(run)}\n\nevent: token\ndata: {"delta":"partial"}\n\nevent: error\ndata: ${JSON.stringify({ message: 'interrupted', run_event: { ...run, status: 'failed' } })}\n\n`])
  const seen = [], completed = []
  await assert.rejects(streamChat('question', { onRun: value => seen.push(value), onDone: value => completed.push(value) }), error => error.runEvent?.run_id === 'run-1')
  assert.deepEqual(seen, [run])
  assert.deepEqual(completed, [])
})

test('outbound request carries correlation without permitting approval metadata', async t => {
  let body, headers
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    body = JSON.parse(options.body)
    headers = options.headers
    return new Response('event: done\ndata: {}\n\n')
  })
  await streamChat('question', {}, { correlation: { request_id: 'req-2', task_id: 'task-2', approval_granted: true } })
  assert.deepEqual(body.metadata, { request_id: 'req-2', task_id: 'task-2' })
  assert.equal(headers['X-Request-ID'], 'req-2')
  assert.equal(headers['X-Task-ID'], 'task-2')
})

test('non-success done preserves partial reply and terminal correlation without completing', async t => {
  for (const status of ['denied', 'failed', 'dry_run']) {
    const run = { request_id: 'req-3', task_id: 'task-3', run_id: 'run-3', status }
    mockStream(t, [`event: token\ndata: {"delta":"partial"}\n\nevent: done\ndata: ${JSON.stringify({ status, metadata: { run_event: run } })}\n\n`])
    const tokens = [], done = [], errors = []
    await assert.rejects(streamChat('question', {
      onToken: value => tokens.push(value), onDone: value => done.push(value), onError: error => errors.push(error)
    }), error => error.runEvent?.status === status)
    assert.deepEqual(tokens, ['partial'])
    assert.deepEqual(done, [])
    assert.equal(errors.length, 1)
    t.mock.restoreAll()
  }
})
