import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const sourcePath = new URL('../../knowledge/cloud_ops/cloud_computing_ops_kb.md', import.meta.url)

test('keeps the Cloud Operations developer knowledge pack as a versioned source', async () => {
  const source = await readFile(sourcePath, 'utf8')

  assert.match(source, /# SmartOpsAgent Knowledge Base Specification/)
  assert.match(source, /Knowledge.*Question.*Runbook.*Incident/s)
  assert.match(source, /Never recommend \/ 禁止默认推荐[\s\S]*chmod 777/)
})
