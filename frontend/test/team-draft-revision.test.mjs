// 协作优化 2：草稿乐观锁的前后端契约。
//
// 核心是"不能静默覆盖"：两个人基于同一版本编辑，后者保存必须被拒绝并告知原因，
// 而不是把前一个人的修改悄悄抹掉。

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const service = await readFile(
  new URL('../../backend/src/main/java/com/smartops/service/TeamAgentService.java', import.meta.url), 'utf8')
const controller = await readFile(
  new URL('../../backend/src/main/java/com/smartops/controller/TeamAgentController.java', import.meta.url), 'utf8')

test('draft save accepts an expected revision and rejects stale ones', () => {
  assert.match(service, /Integer expectedRevision/)
  assert.match(service, /revision=revision\+1/, 'saving must advance the revision')
  // 冲突必须是 409 且文案要说明"被别人改了"，不能只说"参数错误"
  assert.match(service, /409,\s*"草稿已被其他人修改/)
})

test('the update is conditional so a race cannot slip through', () => {
  // 先查后改之间可能被插队，因此 UPDATE 必须自带 revision 条件
  assert.match(service, /WHERE id=\? AND \(\? IS NULL OR revision=\?\)/)
  assert.match(service, /if \(changed != 1\)/)
})

test('missing revision column degrades to legacy behaviour', () => {
  // 旧库没有 revision 列时不能整个查询失败
  assert.match(service, /catch \(java\.sql\.SQLException missingColumn\)/)
})

test('controller exposes expectedRevision as an optional field', () => {
  assert.match(controller, /input\.expectedRevision\(\)/)
  assert.match(controller, /Integer expectedRevision/, 'DraftInput must carry the field')
})

test('legacy overloads remain so old clients still work', () => {
  // 不带 revision 的旧签名必须保留，且委托到新签名并传 null（= 不校验）
  assert.match(service, /saveDraft\(SessionUser actor, long agentId, String prompt, String toolsJson\) \{[\s\S]{0,160}saveDraft\(actor, agentId, prompt, toolsJson, null\);/)
})

test('stale revision on a non-existent draft is also rejected', () => {
  // 客户端声称编辑一个不存在的草稿，说明它读到的是过期状态
  assert.match(service, /expectedRevision != null && expectedRevision > 0/)
})
