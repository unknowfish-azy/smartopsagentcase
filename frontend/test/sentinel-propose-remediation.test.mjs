// 协作优化 4：告警处置接进团队审批链，但不是新执行通路。
//
// 这条链最容易出问题的地方是"顺手把命令跑了"。这里从三个角度钉住：
// 后端 runner 只创建待审批运行、通用执行入口拒绝该工具、界面文案不暗示已执行。

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const runner = await readFile(
  new URL('../../backend/src/main/java/com/smartops/sentinel/SentinelScriptRunner.java', import.meta.url), 'utf8')
const tools = await readFile(
  new URL('../../backend/src/main/java/com/smartops/service/OperationToolService.java', import.meta.url), 'utf8')
const alertsView = await readFile(
  new URL('../src/views/sentinel/AlertCenterView.vue', import.meta.url), 'utf8')

test('proposal reuses the team run lifecycle instead of executing', () => {
  assert.match(runner, /teamRuns\.create\(/, 'must reuse TeamAgentRunService')
  assert.match(runner, /multiExec\.preview\(/, 'must go through the existing preview')
  assert.doesNotMatch(runner, /multiExec\.execute\(/, 'runner must never execute')
})

test('the tool is registered as non-read-only so it lands in PENDING_APPROVAL', () => {
  // 当前目录通过 mutating(...) 构造器表达 false/readOnly，确保该工具进入审批链。
  assert.match(tools, /add\(entries, mutating\("propose-remediation",/)
  assert.match(tools, /private static Spec mutating\(.*?new Spec\(id, false/s)
  assert.match(tools, /TEAM_REMEDIATION_REQUIRES_SENTINEL_PREVIEW/,
    'generic executor must refuse to run the proposal tool')
})

test('proposal output tells the user where execution actually happens', () => {
  assert.match(runner, /preview 后 approve/, 'must name the approval steps')
  assert.match(runner, /哨兵不直接执行命令/, 'must state that nothing was executed')
})

test('the alert center explains that the team path does not execute', () => {
  assert.match(alertsView, /不会执行命令/)
  assert.match(alertsView, /待审批运行/)
  assert.match(alertsView, /生成预览并创建待审批运行/)
  // 不能出现"立即执行/直接处置"这类误导按钮
  assert.doesNotMatch(alertsView, />\s*(立即执行|直接处置|马上处置)\s*</)
})

test('proposal never claims success before approval', () => {
  // 返回给界面的运行状态只能是待审批
  assert.doesNotMatch(runner, /"teamRunStatus", "APPROVED"/)
  assert.doesNotMatch(runner, /"status", "SUCCEEDED"/)
})
