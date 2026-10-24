// 脚本执行界面与平台变量的契约测试。
//
// 两件事必须被钉住：
//   1. 前端的变量清单不能与后端 `SentinelVariables.SUPPORTED` 漂移，
//      否则会出现"界面能填、后端说不认识"的割裂；
//   2. 三种触发模式必须共用同一个准备入口，且文案不得暗示"自动执行"。

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { PLATFORM_VARIABLES, TRIGGER_MODES } from '../src/views/sentinel/sentinelModel.js'

const backendVariables = await readFile(
  new URL('../../backend/src/main/java/com/smartops/sentinel/SentinelVariables.java', import.meta.url), 'utf8')
const scriptView = await readFile(
  new URL('../src/views/sentinel/ScriptLibraryView.vue', import.meta.url), 'utf8')
const runner = await readFile(
  new URL('../../backend/src/main/java/com/smartops/sentinel/SentinelScriptRunner.java', import.meta.url), 'utf8')

/** 从后端 Java 里提取 SUPPORTED 列表的字符串字面量。 */
function backendSupported(source) {
  const block = /SUPPORTED\s*=\s*List\.of\(([\s\S]*?)\);/.exec(source)
  assert.ok(block, 'SentinelVariables.SUPPORTED not found')
  return [...block[1].matchAll(/"([^"]+)"/g)].map(match => match[1])
}

test('frontend variable list matches the backend authority exactly', () => {
  const backend = backendSupported(backendVariables).slice().sort()
  const frontend = PLATFORM_VARIABLES.map(variable => variable.key).slice().sort()
  assert.deepEqual(frontend, backend,
    'PLATFORM_VARIABLES must mirror SentinelVariables.SUPPORTED; the backend is authoritative')
})

test('every platform variable renders as a ${...} token', () => {
  for (const variable of PLATFORM_VARIABLES) {
    const expected = '${' + variable.key + '}'
    assert.equal(variable.token, expected, `token must be ${expected} for ${variable.key}`)
    assert.ok(variable.label && variable.description, `missing label/description for ${variable.key}`)
  }
})

test('three trigger modes map onto the backend constants', () => {
  assert.deepEqual(TRIGGER_MODES.map(mode => mode.id), ['MANUAL', 'SCHEDULE', 'ALERT'])
  for (const mode of TRIGGER_MODES) {
    assert.ok(runner.includes(`TRIGGER_${mode.id}`), `backend missing constant for ${mode.id}`)
  }
})

test('the script page only generates a preview and says so', () => {
  assert.match(scriptView, /prepareScriptRun/)
  // 页面上必须明确"不执行"，否则用户会以为点了就在跑
  assert.match(scriptView, /只生成预览、不执行命令/)
  assert.match(scriptView, /既有多机执行接口/)
  // 不得出现任何"立即执行/直接执行"的按钮文案
  assert.doesNotMatch(scriptView, />\s*(立即执行|直接执行|马上执行)\s*</)
})

test('backend runner has no second execution path', () => {
  assert.match(runner, /multiExec\.preview\(/)
  assert.doesNotMatch(runner, /multiExec\.execute\(/, 'runner must never execute directly')
  // 定时模式也不能直接执行：它同样只生成预览
  const scheduleBlock = runner.slice(runner.indexOf('fireDueSchedules'), runner.indexOf('recordResult'))
  assert.match(scheduleBlock, /multiExec\.preview\(/)
  assert.doesNotMatch(scheduleBlock, /multiExec\.execute\(/)
})
