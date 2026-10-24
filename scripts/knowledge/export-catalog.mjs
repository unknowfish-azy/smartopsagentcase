import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import { searchKnowledgeEntries } from '../../frontend/src/views/knowledge/knowledgeCatalog.js'
import { catalogProjection } from '../../frontend/src/views/knowledge/knowledgeModel.js'

export function serializeCatalog() {
  const entries = catalogProjection(searchKnowledgeEntries())
  const contentHash = createHash('sha256').update(JSON.stringify(entries)).digest('hex')
  return JSON.stringify({ schemaVersion: 1, contentHash, entryCount: entries.length, entries }) + '\n'
}

export const catalogPath = new URL('../../backend/src/main/resources/knowledge/catalog.json', import.meta.url)

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const expected = serializeCatalog()
  if (process.argv.includes('--check')) {
    const actual = await readFile(catalogPath, 'utf8').catch(() => '')
    if (actual !== expected) throw new Error('Knowledge snapshot is stale. Run npm run knowledge:export in frontend, then rebuild backend.')
    console.log(`Knowledge snapshot verified: ${JSON.parse(expected).entryCount} entries`)
  } else {
    await mkdir(new URL('.', catalogPath), { recursive: true })
    await writeFile(catalogPath, expected, 'utf8')
    console.log(`Knowledge snapshot exported: ${JSON.parse(expected).entryCount} entries`)
  }
}
