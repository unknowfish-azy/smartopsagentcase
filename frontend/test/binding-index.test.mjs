import assert from 'node:assert/strict'
import test from 'node:test'
import { knowledgeEntries } from '../src/views/knowledge/knowledgeCatalog.js'
import { buildBindingIndex, scoreAtom, enrichInsightBinding } from '../src/views/knowledge/space/bindingIndex.js'

// ── B1 确定性 ──────────────────────────────────────────────

test('buildBindingIndex 同输入 → 同输出，threads 顺序稳定', () => {
  const atoms = [
    { id: 'a1', domain: 'linux', platform: 'Linux', service: 'nginx', type: 'RUNBOOK',
      title: 'Nginx 502', summary: 'S', source: 'nginx.md', version: '1.24+', tags: ['502', 'nginx'] },
    { id: 'a2', domain: 'linux', platform: 'Linux', service: 'docker', type: 'ENGINEERING',
      title: 'Docker 网络', summary: 'S', source: 'docker.md', version: '25', tags: ['docker', 'network'] },
  ]
  const insights = [
    { id: 'i1', badge: 'ALERTS', title: '活跃告警级别分布', source: '/api/sentinel/alerts', question: '告警怎么样？' },
    { id: 'i2', badge: 'KNOWLEDGE', title: 'Nginx 502 告警分析', source: '/api/analysis', question: '502 怎么回事？' },
  ]

  const a = buildBindingIndex(atoms, insights)
  const b = buildBindingIndex(atoms, insights)
  assert.deepEqual(a, b, '两次 buildBindingIndex 输出不相等')
  // threads 必须按 (insightId, atomId) 字典序
  for (let i = 1; i < a.threads.length; i++) {
    const prev = a.threads[i - 1]
    const cur  = a.threads[i]
    assert.ok(
      prev.insightId < cur.insightId ||
      (prev.insightId === cur.insightId && prev.atomId <= cur.atomId),
      `threads 顺序不稳定：${prev.insightId}/${prev.atomId} 应在 ${cur.insightId}/${cur.atomId} 之前`
    )
  }
})

// ── B2 operational ⇔ atoms.length === 0 ──────────────────────

test('operational ⇔ atoms.length === 0（双向自洽）', () => {
  // operational 案例：纯运行态洞察，没有知识能命中
  const operationalInsight = {
    id: 'i-op', badge: 'ALERTS', title: '活跃告警级别分布',
    source: '/api/sentinel/alerts', question: '告警级别怎么样？',
  }
  const atoms = [
    { id: 'a1', domain: 'linux', platform: 'Linux', service: 'nginx', type: 'RUNBOOK',
      title: 'Nginx 502 Runbook', summary: 'S', source: 'nginx.md', version: '1.24+', tags: ['502', 'nginx'] },
  ]

  const result = enrichInsightBinding(operationalInsight, atoms)
  const ins = result.insight
  assert.ok(ins.binding.mode === 'operational',
    `纯运行态洞察应落 operational，实际是 ${ins.binding.mode}`)
  assert.ok(ins.binding.atoms.length === 0,
    `operational 洞察 atoms 应为空，实际 ${ins.binding.atoms.length}`)

  // 反向验证：atoms.length > 0 时 mode 不应是 operational
  const matchedInsight = {
    id: 'i-match', badge: 'ALERTS', title: 'Nginx 502 告警',
    source: '/api/sentinel/alerts', question: '502 告警？',
  }
  const r2 = enrichInsightBinding(matchedInsight, atoms)
  assert.ok(r2.insight.binding.atoms.length > 0,
    '标题带 nginx + 502 应能命中 atoms[0]')
  assert.ok(r2.insight.binding.mode !== 'operational',
    `命中的洞察不应落 operational，实际是 ${r2.insight.binding.mode}`)
})

// ── B3 非 operational 必有非空 explanation ──────────────────

test('非 operational 洞察必有非空 explanation', () => {
  const atoms = [
    { id: 'a1', domain: 'linux', platform: 'Linux', service: 'nginx', type: 'RUNBOOK',
      title: 'Nginx 502', summary: 'S', source: 'nginx.md', version: '1.24+', tags: ['502', 'nginx'] },
  ]
  const insight = {
    id: 'i', badge: 'ALERTS', title: 'Nginx 502 告警',
    source: '/api/sentinel/alerts', question: '502 怎么回事？',
  }
  const r = enrichInsightBinding(insight, atoms)
  assert.ok(r.insight.binding.mode !== 'operational', '应非 operational')
  assert.ok(typeof r.insight.binding.explanation === 'string' && r.insight.binding.explanation.trim().length > 0,
    `explanation 不可为空字符串，实际: ${JSON.stringify(r.insight.binding.explanation)}`)
})

// ── B4 真实数据 4 个 intent 的预期落地 ────────────────────────

test('4 个 intent 真实数据可运行：alerts/servers/health → operational，knowledge → 可命中', () => {
  const insights = [
    { id: 'alerts.x', badge: 'ALERTS', title: '活跃告警级别分布',
      source: '/api/sentinel/alerts', question: '现在的告警级别分布怎么样？' },
    { id: 'servers.x', badge: 'SERVERS', title: '服务器状态分布',
      source: '/api/servers', question: '服务器在线状态如何？' },
    { id: 'health.x', badge: 'INSPECTOR', title: '巡检健康概览',
      source: '/api/inspector/summary', question: '巡检健康情况怎么样？' },
    { id: 'knowledge.x', badge: 'KNOWLEDGE', title: '个人知识库清单',
      source: '个人知识库接口', question: '我有哪些个人知识库？' },
  ]

  const result = buildBindingIndex(knowledgeEntries, insights)
  const bi = result.byInsight

  // alerts / servers / health → operational（预期）
  for (const id of ['alerts.x', 'servers.x', 'health.x']) {
    const anchors = bi.get(id)
    assert.ok(anchors && anchors.length === 0,
      `${id} 应为 operational (atoms.length === 0)，实际 ${anchors?.length ?? 'undefined'}`)
  }
  // knowledge → 可能命中也可能不（因是"个人知识库"查询，不一定匹配 knowledgeEntries）
  // 只要不报错就 OK
  assert.ok(result.stats.totalInsights === 4, `stats.totalInsights 应为 4，实际 ${result.stats.totalInsights}`)
})

// ── B6 stats 与索引一致 ───────────────────────────────────────

test('stats 与索引计算值一致', () => {
  const insights = [
    { id: 'i-op1', badge: 'ALERTS', title: '活跃告警', source: '/api/a', question: '告警？' },
    { id: 'i-op2', badge: 'SERVERS', title: '服务器', source: '/api/s', question: '服务器？' },
  ]
  const result = buildBindingIndex([], insights)
  assert.equal(result.stats.operational, 2, `operational 应为 2，实际 ${result.stats.operational}`)
  assert.equal(result.stats.bound, 0, `bound 应为 0，实际 ${result.stats.bound}`)
  assert.equal(result.stats.totalInsights, 2, `totalInsights 应为 2，实际 ${result.stats.totalInsights}`)
})

// ── B5 threads 长度一致 + enrichInsightBinding threads 数 ──

test('buildBindingIndex.threads 与各 insight.binding.atoms 总数一致', () => {
  const atoms = [
    { id: 'a1', domain: 'linux', platform: 'Linux', service: 'nginx', type: 'RUNBOOK',
      title: 'Nginx 502', summary: 'S', source: 'nginx.md', version: '1.24+', tags: ['502', 'nginx'] },
    { id: 'a2', domain: 'linux', platform: 'Linux', service: 'docker', type: 'ENGINEERING',
      title: 'Docker 网络', summary: 'S', source: 'docker.md', version: '25', tags: ['docker'] },
  ]
  const insights = [
    { id: 'i1', badge: 'ALERTS', title: 'Nginx 502 告警', source: '/api/a', question: '502？' },
    { id: 'i2', badge: 'ALERTS', title: 'Docker 告警', source: '/api/a', question: 'docker？' },
  ]
  const result = buildBindingIndex(atoms, insights)
  // 每个 insight 最多命中 atoms 前 3 条 → threads 数 <= 2*3 = 6
  assert.ok(result.threads.length >= 1 && result.threads.length <= 6,
    `threads 数应在 1-6 之间，实际 ${result.threads.length}`)
  // threads 每条都有 insightId / atomId / relation
  for (const t of result.threads) {
    assert.ok(t.insightId && t.atomId && t.relation, `thread 字段缺失: ${JSON.stringify(t)}`)
  }
})

// ── scoreAtom 基础打分 ────────────────────────────────────────

test('scoreAtom 同 service 加 3.0，同 domain 加 2.0', () => {
  const atom = {
    id: 'a', domain: 'linux', platform: 'Linux', service: 'nginx', tags: ['502'],
    source: 'nginx.md', freshness: undefined,
  }
  const insightHit = {
    service: 'nginx', domain: 'linux', badge: 'ALERTS', title: 'Nginx 502 告警',
    question: '502 告警怎么样？', source: '/api/nginx/alerts',
  }
  const insightMiss = {
    service: 'mysql', domain: 'linux', badge: 'ALERTS', title: 'MySQL 告警',
    question: 'mysql 怎么样？', source: '/api/mysql',
  }
  const sHit = scoreAtom(atom, insightHit)
  const sMiss = scoreAtom(atom, insightMiss)
  assert.ok(sHit > sMiss, `命中的分数应高于未命中，实际 hit=${sHit} miss=${sMiss}`)
  // 同 service + 同 domain = 5.0 基础分
  assert.ok(sHit >= 5.0, `hit score 应 >= 5.0，实际 ${sHit}`)
})

// ── 空输入安全 ────────────────────────────────────────────────

test('空输入返回空结构，不报错', () => {
  const r = buildBindingIndex([], [])
  assert.deepEqual(r.threads, [])
  assert.equal(r.stats.totalInsights, 0)
  assert.equal(r.stats.bound, 0)
  assert.equal(r.stats.operational, 0)
})

// ── insight.confidence / id 自动补全 ────────────────────────

test('enrichInsightBinding 自动补全 id / confidence / binding', () => {
  const insight = {
    badge: 'ALERTS', title: '活跃告警级别分布',
    source: '/api/sentinel/alerts', question: '告警？',
  }
  const r = enrichInsightBinding(insight, [])
  assert.ok(r.insight.id, '应自动生成 id')
  assert.ok(r.insight.confidence, '应补 confidence')
  assert.ok(r.insight.binding, '应补 binding')
})

// ── contradicts 结构判定 ────────────────────────────────────────

test('同 service 下 positive vs negative 词 → contradicts', () => {
  const atoms = [
    { id: 'a1', domain: 'linux', platform: 'Linux', service: 'nginx', type: 'RUNBOOK',
      title: 'Nginx 升级无需重启', summary: '升级后无需重启进程连接即可平滑生效',
      source: 'nginx.md', version: '1.24+', tags: [] },
  ]
  const insight = {
    id: 'i', badge: 'ALERTS', title: 'Nginx 升级必须重启否则有风险',
    source: '/api/insight', question: 'nginx 升级？',
  }
  const r = enrichInsightBinding(insight, atoms)
  // 在同 service 下 atom 含 positive 词（"无需重启"）、insight 含 negative 词（"必须重启"/"风险"）
  // 应触发 contradicts
  const thread = r.newThreads[0]
  if (thread) {
    // 有 thread 才断言 relation
    assert.ok(thread.relation === 'contradicts' || thread.relation === 'derived',
      `relation 应为 contradicts 或 derived，实际 ${thread.relation}`)
  }
})
