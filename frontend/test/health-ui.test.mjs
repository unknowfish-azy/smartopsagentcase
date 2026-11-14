import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const root = new URL('../', import.meta.url)
const source = path => readFile(new URL(path, root), 'utf8')

// ---------- 纯函数模块 ----------
import { verdictText, verdictLevel, freshInfo } from '../src/components/diagnostics/conclusionState.js'
import { bannerFlags, hasIncompleteEvidence, EVIDENCE_DISCLAIMER } from '../src/components/diagnostics/evidenceBanner.js'
import { TOOL_DEFAULTS, REQUIRED, TOOL_AUTO_TARGET, requiresParams } from '../src/components/diagnostics/toolParamsSchema.js'

// ============================================================
// §1 结论带 verdict 文案 — 优先级 action > config > unknown > pass
// ============================================================

test('verdictText: empty counts → "尚未检查 · 没有证据"', () => {
  assert.equal(verdictText({}), '尚未检查 · 没有证据')
  assert.equal(verdictText(null), '尚未检查 · 没有证据')
})

test('verdictText: action 第一优先级 → "X 项需要处理"', () => {
  assert.equal(verdictText({ action: 2, config: 5, unknown: 3, pass: 10 }), '2 项需要处理')
  assert.equal(verdictText({ action: 1, pass: 99 }), '1 项需要处理')
})

test('verdictText: 无 action 有 config → "X 项等待配置"', () => {
  assert.equal(verdictText({ config: 3, unknown: 2, pass: 5 }), '3 项等待配置')
})

test('verdictText: 无 action/config 有 unknown → "X 项缺少证据"', () => {
  assert.equal(verdictText({ unknown: 4, pass: 6 }), '4 项缺少证据')
})

test('verdictText: 全过 → "全部通过 · X 项检查"', () => {
  assert.equal(verdictText({ pass: 15 }), '全部通过 · 15 项检查')
})

test('verdictLevel 与 verdictText 同优先级', () => {
  assert.equal(verdictLevel({ action: 1, pass: 10 }), 'action')
  assert.equal(verdictLevel({ config: 2, unknown: 1 }), 'config')
  assert.equal(verdictLevel({ unknown: 3 }), 'unknown')
  assert.equal(verdictLevel({ pass: 7 }), 'pass')
  assert.equal(verdictLevel({}), 'empty')
})

// ============================================================
// §2 新鲜度环 — 5 分钟边界 + ringDeg 线性计算
// ============================================================

const FIVE_MIN = 5 * 60 * 1000

test('freshInfo: 刚检查过 → ringDeg ≈ 360, ringText = "5′"', () => {
  const now = 1_000_000
  const checkedAt = now - 1000 // 1 秒前
  const info = freshInfo({ checkedAt, now, stale: false })
  assert.ok(info.ringDeg >= 358)
  assert.equal(info.ringText, '5′')
  assert.equal(info.ringColorToken, '--ds-semantic-info')
})

test('freshInfo: 正好 5 分钟 → ringDeg = 0, ringText = "过期"', () => {
  const now = 1_000_000
  const checkedAt = now - FIVE_MIN
  const info = freshInfo({ checkedAt, now, stale: false })
  assert.equal(info.ringDeg, 0)
  assert.equal(info.ringText, '过期')
})

test('freshInfo: stale=true 即使未到期也显示 "过期" + warning token', () => {
  const now = 1_000_000
  const checkedAt = now - 60_000 // 1 分钟前，未到期
  const info = freshInfo({ checkedAt, now, stale: true })
  assert.equal(info.ringText, '过期')
  assert.equal(info.ringColorToken, '--ds-semantic-warning')
})

test('freshInfo: checkedAt=null → label = "尚未检查"', () => {
  const info = freshInfo({ checkedAt: null, now: 1_000_000 })
  assert.equal(info.label, '尚未检查')
  assert.match(info.tooltip, /尚未执行检查/)
  assert.equal(info.ringText, '过期')
  assert.equal(info.ringDeg, 0)
})

test('freshInfo: absolute 在 tooltip 里出现，格式可读', () => {
  const now = 1_700_000_000_000
  const checkedAt = now - 120_000
  const info = freshInfo({ checkedAt, now })
  assert.ok(info.absolute && info.absolute.length > 0)
  assert.ok(info.tooltip.includes(info.absolute))
})

// ============================================================
// §3 证据横幅 — 四标志位任意一个为 true 就合并进数组
// ============================================================

test('bannerFlags: 全 false → 空数组', () => {
  assert.deepEqual(bannerFlags({ permissionDenied: false, dataMissing: false, unverified: false, truncated: false }), [])
})

test('bannerFlags: null / undefined → 空数组', () => {
  assert.deepEqual(bannerFlags(null), [])
  assert.deepEqual(bannerFlags(undefined), [])
  assert.deepEqual(bannerFlags({}), [])
})

test('bannerFlags: 每一个单独为 true 都进数组', () => {
  for (const key of ['permissionDenied', 'dataMissing', 'unverified', 'truncated']) {
    const input = { permissionDenied: false, dataMissing: false, unverified: false, truncated: false }
    input[key] = true
    const flags = bannerFlags(input)
    assert.equal(flags.length, 1)
    assert.equal(flags[0].key, key)
    assert.ok(flags[0].text && flags[0].why)
  }
})

test('bannerFlags: 任意组合 → 全部合并（按固定顺序）', () => {
  const flags = bannerFlags({ permissionDenied: true, unverified: true, truncated: true })
  assert.equal(flags.length, 3)
  // 顺序是 FLAG_MAP 固定顺序，不是随机
  assert.equal(flags[0].key, 'permissionDenied')
  assert.equal(flags[1].key, 'unverified')
  assert.equal(flags[2].key, 'truncated')
})

test('hasIncompleteEvidence 与 bannerFlags.length 同值', () => {
  assert.equal(hasIncompleteEvidence({}), false)
  assert.equal(hasIncompleteEvidence({ unverified: true }), true)
})

test('EVIDENCE_DISCLAIMER 常量内容正确（模板和 HealthCenterView 共用）', () => {
  assert.ok(EVIDENCE_DISCLAIMER.includes('这不代表目标服务不健康'))
})

// ============================================================
// §4 Tool schema — 默认值 + 必填 + 自动探测
// ============================================================

test('TOOL_DEFAULTS 四个工具都存在，且默认值合理', () => {
  assert.ok(TOOL_DEFAULTS.host, 'host 缺失')
  assert.ok(TOOL_DEFAULTS.kubernetes, 'kubernetes 缺失')
  assert.ok(TOOL_DEFAULTS.network, 'network 缺失')
  assert.ok(TOOL_DEFAULTS.database, 'database 缺失')

  // host 默认 sampleSeconds 2（后端夹紧范围 1..5，默认值在区间内）
  assert.equal(TOOL_DEFAULTS.host.sampleSeconds, 2)
  // network 默认 port 443 + tls true（最常用的 HTTPS 场景）
  assert.equal(TOOL_DEFAULTS.network.port, 443)
  assert.equal(TOOL_DEFAULTS.network.tls, true)
  // k8s 默认 sinceMinutes 60（后端夹紧到 1..1440）
  assert.equal(TOOL_DEFAULTS.kubernetes.sinceMinutes, 60)
})

test('REQUIRED: 每个工具都至少有 runtime（database 例外 — 它用 engine/host/credentialRef）', () => {
  for (const tool of ['host', 'kubernetes', 'network', 'database']) {
    const req = REQUIRED[tool]
    assert.ok(req && req.length > 0, `${tool} REQUIRED 空或缺失`)
  }
  assert.ok(REQUIRED.host.includes('runtimeId'))
  assert.ok(REQUIRED.kubernetes.includes('runtimeId'))
  assert.ok(REQUIRED.network.includes('runtimeId'))
  assert.ok(REQUIRED.network.includes('tls'), 'tls 是必填 — 后端 record 声明为 boolean')
  assert.ok(REQUIRED.database.includes('engine'))
  assert.ok(REQUIRED.database.includes('credentialRef'), '只允许引凭据 ID，不直接传密码')
})

test('TOOL_AUTO_TARGET 只包含 http + certificate（和后端 targets API 对齐）', () => {
  assert.deepEqual([...TOOL_AUTO_TARGET].sort(), ['certificate', 'http'])
})

test('requiresParams: 自动探测 false，复杂工具 true', () => {
  assert.equal(requiresParams('http'), false)
  assert.equal(requiresParams('certificate'), false)
  assert.equal(requiresParams('host'), true)
  assert.equal(requiresParams('kubernetes'), true)
  assert.equal(requiresParams('network'), true)
  assert.equal(requiresParams('database'), true)
  assert.equal(requiresParams('config'), false) // config 没有 diagnose 端点
})

// ============================================================
// §5 路由表完整性 — 每个工具映射到后端 Controller 的实际端点
// ============================================================

test('diagnostics.ts 路由表：config=null，其余 6 个工具全部绑定方法', async () => {
  const apiSrc = await source('src/api/diagnostics.ts')
  assert.match(apiSrc, /TOOL_API_ROUTES/)
  // config 映射到 null（没有 diagnose 端点）
  assert.match(apiSrc, /config:\s*null/)
  // 其余 6 个工具必须有绑定
  assert.match(apiSrc, /host:\s*['"']hostDiagnose['"']/)
  assert.match(apiSrc, /database:\s*['"']databaseDiagnose['"']/)
  assert.match(apiSrc, /kubernetes:\s*['"']kubernetesDiagnose['"']/)
  assert.match(apiSrc, /network:\s*['"']networkDiagnose['"']/)
  assert.match(apiSrc, /http:\s*['"']http['"']/)
  assert.match(apiSrc, /certificate:\s*['"']certificate['"']/)
})

test('diagnostics.ts 真实端点路径（来自后端 Controller）', async () => {
  const apiSrc = await source('src/api/diagnostics.ts')
  // 健康快照
  assert.match(apiSrc, /\/api\/diagnostics\/health/)
  assert.match(apiSrc, /\/api\/diagnostics\/admin\/health/)
  assert.match(apiSrc, /\/api\/diagnostics\/targets/)
  assert.match(apiSrc, /\/api\/diagnostics\/http/)
  assert.match(apiSrc, /\/api\/diagnostics\/certificate/)
  // /api/operations 域（真实诊断）
  assert.match(apiSrc, /\/api\/operations\/host\/diagnose/)
  assert.match(apiSrc, /\/api\/operations\/database\/diagnose/)
  assert.match(apiSrc, /\/api\/operations\/kubernetes\/diagnose/)
  assert.match(apiSrc, /\/api\/operations\/network\/diagnose/)
})

test('DiagnosisResultPanel 按 severity 排序 findings（high → medium → low → info）', async () => {
  const panel = await source('src/components/diagnostics/DiagnosisResultPanel.vue')
  // 排序规则必须明确声明 SEV_ORDER 常量，high=0 最前
  assert.match(panel, /SEV_ORDER\s*=\s*\{[^}]*high\s*:\s*0/)
  assert.match(panel, /medium\s*:\s*1/)
  assert.match(panel, /low\s*:\s*2/)
  assert.match(panel, /info\s*:\s*3/)
})

// ============================================================
// §6 架构契约守门（字符串匹配 — 防止回归）
// ============================================================

test('三层架构核心文件互相引用：组件 → 纯函数模块（不是 inline）', async () => {
  const bar = await source('src/components/diagnostics/ConclusionBar.vue')
  const ebanner = await source('src/components/diagnostics/EvidenceBanner.vue')
  const params = await source('src/components/diagnostics/ToolParamsForm.vue')

  assert.match(bar, /from '\.\/conclusionState\.js'/)
  assert.match(ebanner, /from '\.\/evidenceBanner\.js'/)
  assert.match(params, /from '\.\/toolParamsSchema\.js'/)

  // 旧的 FIVE_MINUTES_MS 直接 import 必须已消失（改为 freshInfo 统一入口）
  assert.doesNotMatch(bar, /import.*FIVE_MINUTES_MS.*healthState/)
})

test('DiagnosisResultPanel 对 blockedBy 用中性色不是故障红（§8.4 硬约束）', async () => {
  const panel = await source('src/components/diagnostics/DiagnosisResultPanel.vue')
  // blockedBy 渲染走 hc-blocked 样式 — 背景中性，边框中性，不出现 --ds-semantic-danger
  assert.match(panel, /hc-blocked/)
  assert.match(panel, /被阻断（不是故障）/)
  assert.doesNotMatch(panel.match(/hc-blocked[\s\S]*?}\s*\}/)?.[0] || '', /--ds-semantic-danger/)
})

test('DiagnosisResultPanel 失败态含"这不代表目标服务不健康"（§8.4 硬约束）', async () => {
  const panel = await source('src/components/diagnostics/DiagnosisResultPanel.vue')
  assert.match(panel, /这不代表目标服务不健康/)
})

test('HealthCenterView buildPayload 自动/手动分支完整', async () => {
  const view = await source('src/views/diagnostics/HealthCenterView.vue')
  assert.match(view, /TOOL_AUTO_TARGET\.includes\(toolId\)/)
  assert.match(view, /requestParams\.value\[toolId\]/)
  assert.match(view, /normalizeDiagnosticFailure/)
})

test('HealthCenterView 切工具重置结果（防止残留）', async () => {
  const view = await source('src/views/diagnostics/HealthCenterView.vue')
  assert.match(view, /watch\(activeTool/)
})

test('HealthCenterView 显式暴露 setRequestParams 给外部调用（defineExpose）', async () => {
  const view = await source('src/views/diagnostics/HealthCenterView.vue')
  assert.match(view, /defineExpose.*setRequestParams/)
})

test('rerunActiveTool 失败时保留旧 result（诚实做法 §5）', async () => {
  const view = await source('src/views/diagnostics/HealthCenterView.vue')
  // 不能有 response = null; activeDiagnosisResult.value = null 在 catch 里
  // （让旧结果留着让用户对照）
  const catchBlock = view.match(/catch \(failure\) \{[\s\S]*?\n {2}\}/)?.[0] || ''
  assert.ok(catchBlock.length > 20, '找不到 catch 块')
  assert.doesNotMatch(catchBlock, /activeDiagnosisResult\.value = null/)
  assert.match(catchBlock, /normalizeDiagnosticFailure/)
})
