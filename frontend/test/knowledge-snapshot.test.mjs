import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { serializeCatalog, catalogPath } from '../../scripts/knowledge/export-catalog.mjs'

test('Mini built-in snapshot exactly matches canonical frontend knowledge projection', async () => {
  assert.equal(await readFile(catalogPath, 'utf8'), serializeCatalog())
})
