import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const drawerSource = await readFile(
  new URL('../src/components/agent/TrustLedgerDrawer.vue', import.meta.url),
  'utf8',
)
const dockSource = await readFile(
  new URL('../src/components/agent/AgentCopilotDock.vue', import.meta.url),
  'utf8',
)
const apiSource = await readFile(new URL('../src/api/trustLedger.ts', import.meta.url), 'utf8')

test('trust ledger drawer performs one-click chain verification with real result fields (一键验链展示真实结果)', () => {
  assert.match(drawerSource, /一键验链/)
  assert.match(drawerSource, /verifyAuditChain/)
  assert.match(drawerSource, /verifyResult\.total_events/)
  assert.match(drawerSource, /verifyResult\.segments/)
  assert.match(drawerSource, /verifyResult\.available/)
})

test('trust ledger drawer replays runs read-only and states missing data honestly (只读回放与无数据口径)', () => {
  assert.match(drawerSource, /只读回放/)
  assert.match(drawerSource, /不重新执行工具/)
  assert.match(drawerSource, /暂无运行记录（未运行\/无数据）/)
  assert.match(drawerSource, /无数据/)
  assert.doesNotMatch(drawerSource, /事件\s*0\b/)
})

test('trust ledger drawer uses design tokens (样式使用 --ds-* 令牌)', () => {
  assert.match(drawerSource, /--ds-surface/)
  assert.match(drawerSource, /--ds-color-muted/)
})

test('copilot dock mounts the trust ledger drawer (侧翼入口挂载账本抽屉)', () => {
  assert.match(dockSource, /import TrustLedgerDrawer from '\.\/TrustLedgerDrawer\.vue'/)
  assert.match(dockSource, /<TrustLedgerDrawer v-model="ledgerOpen" \/>/)
  assert.match(dockSource, /信任账本/)
})

test('trust ledger api exposes list, detail and verify (前端账本 API 三个出口)', () => {
  assert.match(apiSource, /export function listAgentRuns/)
  assert.match(apiSource, /export function getAgentRun/)
  assert.match(apiSource, /export async function verifyAuditChain/)
  assert.match(apiSource, /\/api\/agent\/audit\/verify/)
})
