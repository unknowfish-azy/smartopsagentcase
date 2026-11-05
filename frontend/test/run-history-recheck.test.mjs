import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref, computed } from 'vue'
import { babelParse } from '@vue/compiler-sfc'
import * as helpers from '../src/components/operations/operationRunHistory.js'
import * as guides from '../src/components/operations/runHistoryGuides.js'
const source = readFileSync(new URL('../src/composables/useRunHistory.js', import.meta.url), 'utf8')
function setup(overrides = {}) {
  const deps = {ref, computed, onMounted() {}, onBeforeUnmount() {}, ...helpers, ...guides,
    getOperationRuns: async () => ({items: [], total: 0}), getOperationRun: async () => {throw Error('detail failed')},
    createKnowledgeCandidateFromRun: async () => ({}), navigator: {clipboard: {writeText: async () => {throw Error('denied')}}}, window: globalThis, ...overrides}
  const imports = babelParse(source, { sourceType: 'module' }).program.body.filter(node => node.type === 'ImportDeclaration')
  let script = source
  for (const node of imports.reverse()) script = script.slice(0, node.start) + script.slice(node.end)
  script = script.replace(/^export /gm, '')
  return Function(...Object.keys(deps), script + '\nreturn useRunHistory()')(...Object.values(deps))
}
test('invalid time range keeps existing results and uses form feedback', async () => {
 const vm=setup(); vm.page.value.items=[{id:1}]; vm.filters.value.startedFrom='2026-10-17T16:00'; vm.filters.value.startedTo='2026-10-17T15:00'
 await vm.loadRuns(); assert.equal(vm.error.value,''); assert.ok(vm.formError.value); assert.equal(vm.page.value.items.length,1)
})
test('clipboard rejection is independent of detail loading', async () => {
 const vm=setup(); await vm.copyTrace('trace'); assert.equal(vm.detailError.value,''); assert.equal(vm.copyFailed.value,true)
})
test('null selection never requests a detail', async () => {
 let calls=0; const vm=setup({getOperationRun:async()=>{calls++;return {}}}); await vm.loadDetail(null); assert.equal(calls,0)
})
test('empty filtered result clears stale errors and invalidates pending detail', async () => {
 let resolve; const vm=setup({getOperationRun:()=>new Promise(r=>resolve=r)}); vm.selectedId.value=1
 const pending=vm.loadDetail(1); vm.detailError.value='old'; vm.filters.value.status='FAILED'; await vm.loadRuns(); resolve({run:{id:1}}); await pending
 assert.equal(vm.detailError.value,''); assert.equal(vm.detail.value,null); assert.equal(vm.detailLoading.value,false)
})
test('latest detail wins when replies arrive out of order', async () => {
 const replies={}; const vm=setup({getOperationRun:id=>new Promise(r=>replies[id]=r)})
 const a=vm.loadDetail(1),b=vm.loadDetail(2); replies[2]({run:{id:2}}); await b; replies[1]({run:{id:1}}); await a; assert.equal(vm.detail.value.run.id,2)
})
