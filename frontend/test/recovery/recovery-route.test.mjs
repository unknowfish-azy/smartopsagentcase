import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { liveCaseFromDetail, receiptBadge } from '../../src/components/operations/recovery/liveCase.js'

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

test('recovery view reads the platform API by default and keeps fixtures isolated', async () => {
  const view = await readFile(new URL('../../src/views/operations/RecoveryContractsView.vue', import.meta.url), 'utf8')

  assert.match(view, /ContractCard/)
  assert.match(view, /GapCard/)
  assert.match(view, /ReplayCard/)
  // 默认真实数据模式，且真实读取走平台接口
  assert.match(view, /mode = ref\('live'\)/)
  assert.match(view, /listRecoveryContracts/)
  assert.match(view, /getRecoveryContract/)
  // 演示样例必须能切换出来，但仍带 fixture 标注
  assert.match(view, /VERIFIED_CASE/)
  assert.match(view, /activeCase\.note/)
  assert.match(view, /fixture-banner/)
  // 空态不得回退到样例填充
  assert.match(view, /暂无已登记的恢复契约/)
})

test('live adapter maps platform detail without inventing verdict or receipt', () => {
  const detail = {
    contract: { id: 'ctr-1', obligations: [{ id: 'obl-1' }], budgets: { max_probe_calls: 12 } },
    claim: { id: 'claim-1' },
    receipt: {
      receiptId: 'rcpt-1',
      verdict: 'CONTRADICTED',
      receiptState: 'NOT_ISSUED',
      receipt: { id: 'rcpt-1', receipt_state: 'NOT_ISSUED' },
      obligationResults: [{ obligation_id: 'obl-1', value: 'FALSE' }],
      probeDecision: null
    },
    observations: [],
    replays: [
      { bundleId: 'b1', bundle: { bundle_id: 'b1' }, replayResult: { verdict: 'CONTRADICTED' } }
    ]
  }

  const view = liveCaseFromDetail(detail)
  assert.equal(view.source, 'live')
  assert.equal(view.verdict, 'CONTRADICTED')
  assert.equal(view.action, 'NOT_PERFORMED', '平台不执行修复动作')
  assert.equal(view.inspection_passed, null, '纠察轴未提供时不得猜测')
  assert.equal(view.authorization, null, '授权轴未提供时不得猜测')
  assert.deepEqual(view.obligation_results, [{ obligation_id: 'obl-1', value: 'FALSE' }])
  assert.equal(view.replay_bundle.bundle_id, 'b1')
  assert.equal(view.replay.verdict, 'CONTRADICTED')
})

test('live adapter returns null when the platform has no contract', () => {
  assert.equal(liveCaseFromDetail(null), null)
  assert.equal(liveCaseFromDetail({}), null)
})

test('live adapter treats a contract without receipt as unverified', () => {
  const view = liveCaseFromDetail({ contract: { id: 'ctr-2' }, receipt: null, replays: [] })
  assert.equal(view.receipt, null)
  assert.equal(view.verdict, null)
  assert.deepEqual(view.obligation_results, [])

  const badge = receiptBadge({ verdict: null, receiptState: null })
  assert.equal(badge.state, 'NOT_ISSUED')
})
