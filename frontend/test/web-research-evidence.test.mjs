import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { addEvidencePage, toggleEvidenceTask } from '../src/components/research/evidenceSelection.js'

const component = readFileSync(new URL('../src/components/research/EvidenceCompare.vue', import.meta.url), 'utf8')
const radar = readFileSync(new URL('../src/views/research/RadarView.vue', import.meta.url), 'utf8')

test('evidence basket deduplicates tasks and keeps the newest four pages selected', () => {
  let pages = [], selected = []
  for (const taskId of [1, 2, 3, 4, 5, 3]) {
    const next = addEvidencePage(pages, selected, { taskId, title: `Page ${taskId}` })
    pages = next.pages
    selected = next.selectedTaskIds
  }
  assert.deepEqual(pages.map(page => page.taskId), [2, 4, 5, 3])
  assert.deepEqual(selected, [2, 4, 5, 3])
})

test('evidence selection toggles off and never exceeds four tasks', () => {
  const pages = [1, 2, 3, 4, 5].map(taskId => ({ taskId }))
  assert.deepEqual(toggleEvidenceTask(pages, [1, 2, 3, 4], 5), [1, 2, 3, 4])
  assert.deepEqual(toggleEvidenceTask(pages, [1, 2, 3, 4], 2), [1, 3, 4])
  assert.deepEqual(toggleEvidenceTask(pages, [1, 2], 5), [1, 2, 5])
})

test('comparison UI labels uncertainty and does not present a truth score', () => {
  assert.match(component, /不输出真伪评分/)
  assert.match(component, /来源信号/)
  assert.match(component, /文本重合度/)
  assert.match(component, /UNKNOWN: '未核验'/)
  assert.doesNotMatch(component, /可信度评分|真实性得分|判定为真|判定为假/)
})

test('radar exposes adjacent field and line differences without claiming correctness', () => {
  assert.match(radar, /对比上一版/)
  assert.match(radar, /正文行差异/)
  assert.match(radar, /getKnowledgeCrawlPageDiff/)
  assert.match(radar, /不自动判断哪个版本正确|diffs\[page.id\].note/)
})
