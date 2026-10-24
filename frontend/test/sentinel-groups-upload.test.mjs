// 资产分组启停与脚本上传的契约测试。
//
// 两件事要钉住：
//   1. 分组批量启停必须限定在当前用户范围内（不能误改他人任务）；
//   2. 上传不能成为绕过预检的缝隙——它必须复用 createScript 的同一条路径。

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const service = await readFile(
  new URL('../../backend/src/main/java/com/smartops/sentinel/SentinelService.java', import.meta.url), 'utf8')
const controller = await readFile(
  new URL('../../backend/src/main/java/com/smartops/sentinel/SentinelController.java', import.meta.url), 'utf8')
const dashboard = await readFile(
  new URL('../src/views/sentinel/SentinelDashboardView.vue', import.meta.url), 'utf8')
const library = await readFile(
  new URL('../src/views/sentinel/ScriptLibraryView.vue', import.meta.url), 'utf8')

test('group toggle is scoped to the current user', () => {
  // 少一个 user_id 条件就会批量改到别人的任务
  assert.match(service, /UPDATE sentinel_task SET enabled=\? WHERE user_id=\? AND group_label=\?/)
})

test('group toggle returns a count instead of failing on empty groups', () => {
  // 分组没有任务属于正常状态，不该报错
  assert.match(service, /public int setGroupEnabled/)
  assert.match(service, /return jdbc\.update\("UPDATE sentinel_task SET enabled/)
})

test('upload reuses createScript so it cannot bypass lint', () => {
  // 关键：上传必须委托给 createScript，那里才有高危预检
  assert.match(service, /return createScript\(actor, scriptName, language, "从文件 /)
  // 上传本身也要拒绝二进制与超大文件
  assert.match(service, /脚本文件超过 1 MiB/)
  assert.match(service, /看起来是二进制/)
})

test('upload refuses unknown extensions instead of guessing', () => {
  assert.match(service, /无法从扩展名判断脚本语言/)
  // 路径片段不能进入名称
  assert.match(service, /lastIndexOf\('\/'\)/)
})

test('dashboard exposes group bulk toggles', () => {
  assert.match(dashboard, /资产分组批量启停/)
  assert.match(dashboard, /toggleGroup/)
  assert.match(dashboard, /全部启用/)
  assert.match(dashboard, /全部停用/)
})

test('script library exposes file import with honest limits', () => {
  assert.match(library, /从文件导入脚本/)
  assert.match(library, /同一条预检路径/)
  assert.match(library, /1 MiB/)
  assert.match(library, /accept="\.sh,\.bash,\.py,\.bat,\.cmd,\.ps1,\.psm1"/)
})

test('group endpoints are present', () => {
  assert.match(controller, /@GetMapping\("\/task-groups"\)/)
  assert.match(controller, /@PatchMapping\("\/task-groups\/\{label\}\/enabled"\)/)
  assert.match(controller, /@PostMapping\("\/scripts\/upload"\)/)
})
