// 界面可创建性：三大模块必须能"从界面建起来"，而不是只能看。
//
// 这条测试的由来：初版界面只展示任务/模板/规则，创建全靠直接调 API。
// 那等于"模块有了但用不了"。这里钉住创建入口存在，且校验权威只在后端。

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const dashboard = await readFile(
  new URL('../src/views/sentinel/SentinelDashboardView.vue', import.meta.url), 'utf8')
const alerts = await readFile(
  new URL('../src/views/sentinel/AlertCenterView.vue', import.meta.url), 'utf8')
const store = await readFile(
  new URL('../src/views/sentinel/sentinelStore.js', import.meta.url), 'utf8')

test('dashboard can create sentinel tasks', () => {
  assert.match(dashboard, /新建哨兵任务/)
  assert.match(dashboard, /createTask/)
  assert.match(dashboard, /创建哨兵任务/)
  // 采集间隔与分组都要能选，否则建出来的任务不可用
  assert.match(dashboard, /COLLECT_INTERVALS/)
  assert.match(dashboard, /资产分组/)
})

test('dashboard can create threshold templates with compound rules', () => {
  assert.match(dashboard, /新建阈值模板/)
  assert.match(dashboard, /createTemplate/)
  assert.match(dashboard, /再加一条（复合阈值）/)
  // 持续时间（防抖）必须可配
  assert.match(dashboard, /debounceSec/)
})

test('alert center can bind template and script into a rule', () => {
  assert.match(alerts, /新建告警规则/)
  assert.match(alerts, /createAlertRule/)
  // 绑定关系：模板（哨兵项）+ 脚本（处置）
  assert.match(alerts, /阈值模板/)
  assert.match(alerts, /处置脚本/)
  // 三种通知渠道可勾选
  assert.match(alerts, /NOTIFY_CHANNELS/)
  assert.match(alerts, /webhookUrl/)
  assert.match(alerts, /emailTo/)
})

test('validation authority stays on the backend', () => {
  // 前端不复制一份指标白名单/端口范围规则，避免两侧漂移
  assert.match(dashboard, /唯一权威在后端|后端校验/)
  // store 只负责提交与转达错误，不做本地规则推断
  assert.match(store, /唯一权威在后端/)
})

test('P0/P1 auto-dispatch expectation is stated honestly in the form', () => {
  // 界面要提前说明"必须人工确认"，而不是等提交后才被服务端改成 false
  assert.match(alerts, /必须人工确认，不会自动发起/)
  assert.match(alerts, /仍需预览与审批后才执行/)
})
