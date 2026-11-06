import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

test('recovery contracts route is registered and discoverable under Memory', async () => {
  const router = await readFile(new URL('../../src/router/index.js', import.meta.url), 'utf8')
  const navigation = await readFile(new URL('../../src/navigation/personalSystemNavigation.js', import.meta.url), 'utf8')
  const metadata = await readFile(new URL('../../src/navigation/routeMetadata.js', import.meta.url), 'utf8')

  assert.match(router, /operations\/recovery/)
  assert.match(router, /RecoveryContractsView\.vue/)
  assert.match(navigation, /RECOVERY/)
  assert.match(navigation, /恢复契约/)
  assert.match(navigation, /\/operations\/recovery/)
  assert.match(metadata, /RecoveryContracts/)
})

test('recovery view renders three cards and keeps fixture honesty banner', async () => {
  const view = await readFile(new URL('../../src/views/operations/RecoveryContractsView.vue', import.meta.url), 'utf8')

  assert.match(view, /ContractCard/)
  assert.match(view, /GapCard/)
  assert.match(view, /ReplayCard/)
  assert.match(view, /VERIFIED_CASE/)
  assert.match(view, /BUSINESS_FALSE_CASE/)
  assert.match(view, /activeCase\.note/)
  // 展示样例页面不得调用任何后端 API 冒充运行证据
  assert.doesNotMatch(view, /from '\.\.\/\.\.\/api\//)
})
