import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { buildPageContext, cleanEntity, cleanSnapshot } from '../src/domain/chat/pageContext.js'

const panelSource = await readFile(new URL('../src/components/ai/AiChatPanel.vue', import.meta.url), 'utf8')
const storeSource = await readFile(new URL('../src/stores/aiChat.js', import.meta.url), 'utf8')
const streamSource = await readFile(new URL('../src/api/stream.ts', import.meta.url), 'utf8')
const dashboardCardSource = await readFile(new URL('../src/components/dashboard/XiaoyuDashboardCard.vue', import.meta.url), 'utf8')
const dockSource = await readFile(new URL('../src/components/agent/AgentCopilotDock.vue', import.meta.url), 'utf8')
const briefCardSource = await readFile(new URL('../src/components/agent/SecurityBriefCard.vue', import.meta.url), 'utf8')

test('buildPageContext keeps only path and section strings (页面上下文只保留两个白名单字段)', () => {
  const context = buildPageContext({
    path: '/sentinel/inspection',
    name: 'SentinelInspection',
    query: { id: '1' },
    params: { id: '1' },
    meta: { section: '巡检面' },
  })
  assert.deepEqual(context, { path: '/sentinel/inspection', section: '巡检面' })
})

test('buildPageContext falls back to meta.title then route name (栏目取值优先级)', () => {
  assert.equal(buildPageContext({ path: '/a', meta: { title: '监控面' } }).section, '监控面')
  assert.equal(buildPageContext({ path: '/a', meta: {}, name: 'MonitorPlane' }).section, 'MonitorPlane')
})

test('buildPageContext returns null without a section (无栏目时不发送，避免噪音)', () => {
  assert.equal(buildPageContext({ path: '/a', meta: {} }), null)
  assert.equal(buildPageContext({ path: '/a', meta: { title: '   ' } }), null)
  assert.equal(buildPageContext(null), null)
  assert.equal(buildPageContext({}), null)
})

test('buildPageContext strips control chars and caps fields at 200 (非法字符过滤与限长)', () => {
  const context = buildPageContext({ path: `/x${'\u0000\u001f'.repeat(1)}y`, meta: { section: `s${'\u0007'.repeat(5)}t` } })
  assert.deepEqual(context, { path: '/xy', section: 'st' })

  const long = buildPageContext({ path: 'a'.repeat(500), meta: { section: 'b'.repeat(500) } })
  assert.equal(long.path.length, 200)
  assert.equal(long.section.length, 200)
})

test('chat panel wires page context into the streaming send (面板发送时携带页面上下文)', () => {
  assert.match(panelSource, /import \{ buildPageContext \} from '\.\.\/\.\.\/domain\/chat\/pageContext\.js'/)
  assert.match(panelSource, /const route = useRoute\(\)/)
  assert.match(panelSource, /context: buildPageContext\(route\)/)
})

test('chat store treats context as optional and stays compatible with old callers (store 兼容未传 context 的调用方)', () => {
  // XiaoyuDashboardCard 等旧调用方不传 context，默认参数必须保持可选。
  assert.match(storeSource, /context = null/)
  assert.match(storeSource, /normalizePageContext\(context\)/)
  assert.doesNotMatch(dashboardCardSource, /context:/)
})

test('stream client only adds context to the request body when present (仅当存在时进请求体)', () => {
  assert.match(streamSource, /if \(options\.context\) body\.context = options\.context/)
})

test('buildPageContext carries a sanitized entity and read-only snapshot (侧翼携带本页实体)', () => {
  const context = buildPageContext(
    { path: '/sentinel', meta: { section: '哨兵监控' } },
    {
      entity: { type: 'ALERT', id: ' AL-1 ' },
      snapshot: { 指标: 'CPU 90%', 温度: 82, ok: true, bad: { nested: 1 }, '': 'x' },
    },
  )
  assert.deepEqual(context.entity, { type: 'alert', id: 'AL-1' })
  assert.deepEqual(context.snapshot, { 指标: 'CPU 90%', 温度: 82, ok: true })
})

test('cleanEntity rejects unknown types and empty ids (未知实体类型直接丢弃)', () => {
  assert.equal(cleanEntity({ type: 'hacker', id: '1' }), null)
  assert.equal(cleanEntity({ type: 'alert', id: '   ' }), null)
  assert.equal(cleanEntity(null), null)
})

test('cleanSnapshot caps keys and values (摘要白名单限键数限长)', () => {
  const big = {}
  for (let index = 0; index < 40; index += 1) big[`k${index}`] = 'v'
  assert.equal(Object.keys(cleanSnapshot(big)).length, 20)
  assert.equal(cleanSnapshot({ a: 'x'.repeat(1000) }).a.length, 300)
  assert.equal(cleanSnapshot({ a: { b: 1 } }), null)
})

test('copilot dock streams with page context and renders the real security brief (侧翼带上下文并渲染真实简报)', () => {
  assert.match(dockSource, /buildPageContext\(route, \{/)
  assert.match(dockSource, /fetchChatRunToken/)
  assert.match(dockSource, /streamChat\(/)
  assert.match(dockSource, /security_brief/)
  assert.match(dockSource, /<SecurityBriefCard/)
  // 无真实用户数时如实显示"未运行/无数据"，不编造。
  assert.match(briefCardSource, /未运行\/无数据/)
})

test('every W5 page mounts the dock with its entity type (8 个页面均接入且带 entity)', async () => {
  const pages = [
    ['sentinel/SentinelDashboardView.vue', 'alert'],
    ['inspector/InspectorCenterView.vue', 'event'],
    ['knowledge/space/KnowledgeSpaceView.vue', 'doc'],
    ['incident/IncidentCenterView.vue', 'incident'],
    ['robot/RobotConsoleView.vue', 'device'],
    ['server/ServerListView.vue', 'server'],
    ['model/ModelGatewayView.vue', 'connection'],
    ['diagnostics/LogDiagnosisView.vue', 'diagnostic'],
  ]
  const problems = []
  for (const [file, entityType] of pages) {
    const source = await readFile(new URL(`../src/views/${file}`, import.meta.url), 'utf8')
    if (!source.includes('<AgentCopilotDock')) problems.push(`${file}: 未挂载 <AgentCopilotDock>`)
    if (!source.includes(`type: '${entityType}'`)) problems.push(`${file}: 缺少实体类型 ${entityType}`)
    if (!/section="[^"]+"/.test(source)) problems.push(`${file}: 缺少 section`)
  }
  assert.deepEqual(problems, [])
})
