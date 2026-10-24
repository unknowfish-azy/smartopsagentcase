import test from 'node:test'
import assert from 'node:assert/strict'
import { parseSkill, installSkill, emptySkills, decodeSkills, skillPrompt } from '../src/domain/skills/workspace.js'
import { normalizeSourceLink, readRemoteSource } from '../src/domain/plugins/remoteSource.js'
const md = '---\nname: test-skill\ndescription: |\n  先收集证据\n  再分析原因\n---\n# 指令\n输出验证步骤。'
test('skill metadata, persistence, explicit activation and prompt use', () => {
  assert.equal(parseSkill(md).name, 'test-skill')
  let state = installSkill(emptySkills(), md, 'https://example.com/SKILL.md')
  assert.equal(skillPrompt(state), '')
  state.skills[0].enabled = true; state.goal = '定位 502'
  assert.match(skillPrompt(state), /定位 502/)
  assert.match(skillPrompt(state), /输出验证步骤/)
  assert.equal(decodeSkills(JSON.stringify(state)).skills[0].enabled, true)
  assert.throws(() => installSkill(state, md), /同名/)
  assert.throws(() => parseSkill('# invalid'))
  assert.throws(() => parseSkill(md.replace('test-skill', '../escape')))
  state.skills[0].instructions = 'x'.repeat(49000)
  assert.throws(() => skillPrompt(state), /48,000/)
})
test('source normalizer supports GitHub file directory root and HTTPS raw links', () => {
  assert.equal(normalizeSourceLink('https://github.com/acme/repo/tree/main/skills/test', 'skill'), 'https://raw.githubusercontent.com/acme/repo/main/skills/test/SKILL.md')
  assert.equal(normalizeSourceLink('https://github.com/acme/repo/blob/main/plugin.json', 'plugin'), 'https://raw.githubusercontent.com/acme/repo/main/plugin.json')
  assert.equal(normalizeSourceLink('https://github.com/acme/repo', 'plugin'), 'https://raw.githubusercontent.com/acme/repo/HEAD/smartops-plugin.json')
  for (const url of ['http://example.com/x', 'https://user:password@example.com/x', 'https://127.0.0.1/x', 'https://localhost/x', 'file:///etc/passwd']) assert.throws(() => normalizeSourceLink(url, 'skill'))
})
test('remote read enforces size and rejects HTML', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response(md)
    assert.equal((await readRemoteSource('https://example.com/SKILL.md', 'skill')).content, md)
    globalThis.fetch = async () => new Response('<!doctype html><html>login</html>')
    await assert.rejects(readRemoteSource('https://example.com/SKILL.md', 'skill'), /网页/)
    globalThis.fetch = async () => new Response('x'.repeat(66000))
    await assert.rejects(readRemoteSource('https://example.com/SKILL.md', 'skill'), /过大/)
  } finally { globalThis.fetch = original }
})
