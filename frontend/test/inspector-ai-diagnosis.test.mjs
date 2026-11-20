import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const diagnosis = await readFile(
  new URL('../src/components/inspector/InspectorAiDiagnosis.vue', import.meta.url), 'utf8')
const centerView = await readFile(
  new URL('../src/views/inspector/InspectorCenterView.vue', import.meta.url), 'utf8')

test('AI 初诊卡片只展示 REVIEW 且 requiresHuman 的事件', () => {
  assert.match(diagnosis, /event\?\.status === 'REVIEW'/)
  assert.match(diagnosis, /event\?\.requiresHuman === true/)
  assert.match(diagnosis, /slice\(0, 3\)/)
})

test('AI 初诊卡片是只读的，不提供任何执行入口', () => {
  // 人工确认前不可执行：卡片只读展示，不出现执行/处置按钮或 API 调用。
  assert.doesNotMatch(diagnosis, /<button/i)
  assert.doesNotMatch(diagnosis, /@click/)
  assert.doesNotMatch(diagnosis, /api\//)
  assert.match(diagnosis, /仅只读/)
})

test('无数据时如实展示空态而不是编造结论', () => {
  assert.match(diagnosis, /暂无 AI 初诊事件/)
  assert.match(diagnosis, /v-if="!items\.length"/)
})

test('纠察中心已挂载 AI 初诊卡片', () => {
  assert.match(centerView, /import InspectorAiDiagnosis from '\.\.\/\.\.\/components\/inspector\/InspectorAiDiagnosis\.vue'/)
  assert.match(centerView, /<InspectorAiDiagnosis[^>]*:events="displayEvents"/)
})
