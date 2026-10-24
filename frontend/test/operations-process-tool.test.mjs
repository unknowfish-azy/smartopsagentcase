import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const toolsView = await readFile(new URL('../src/views/operations/ToolsView.vue', import.meta.url), 'utf8')
const knowledgeView = await readFile(new URL('../src/views/knowledge/KnowledgeView.vue', import.meta.url), 'utf8')

test('process tool renders knowledge-driven read-only diagnostics', () => {
  assert.match(toolsView, /processDiagnostics\.js/)
  assert.match(toolsView, /processDiagnosticScenarios/)
  assert.match(toolsView, /READ-ONLY COMMAND PREVIEW/)
  assert.match(toolsView, /不读取本机或 SSH 数据，不执行命令/)
})

test('process tool provides a return link to its source knowledge entry', () => {
  assert.match(toolsView, /path: '\/knowledge', query: \{ entry: knowledgeContext \}/)
  assert.match(toolsView, /返回知识详情/)
})

test('process tool does not expose bridge execution controls', () => {
  assert.match(toolsView, /isProcessTool/)
  assert.match(toolsView, /v-if="!isProcessTool && !isDiagnosticTool && !observabilitySource && !isHarborBrowser" type="button"/)
  assert.match(toolsView, /<div v-else-if="isProcessTool" class="process-workspace">/)
  assert.match(toolsView, /<div v-else class="operation-tool-workspace">/)
})

test('knowledge detail links related process knowledge to the process tool', () => {
  assert.match(knowledgeView, /selectedView\.current\.relatedTool/)
  assert.match(knowledgeView, /knowledge: selectedView\.current\.id/)
  assert.match(knowledgeView, /打开进程诊断工具/)
})

test('knowledge view restores a detail selected by the return link', () => {
  assert.match(knowledgeView, /route\.query\.entry/)
  assert.match(knowledgeView, /watch\(\(\) => route\.query\.entry/)
})
