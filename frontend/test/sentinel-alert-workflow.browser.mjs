// 告警研判 / 通知 / 知识沉淀：可验证的接口边界（真实后端，无替身）。
//
// 完整链路（产生告警 → 研判 → 处置 → 沉淀）需要**已授权的 SSH 运行连接**才能产生真实告警。
// 没有真实目标机时，本脚本不去伪造一条告警来"凑"测试通过，而是验证：
//   - 接口在未登录时被拒绝；
//   - 不存在的告警返回 404，而不是 500；
//   - 采集边界被如实说明；
// 研判逻辑由 SentinelAdvisorTest 覆盖，告警落库与闭环由 SentinelAlertWorkflowTest 覆盖。
//
// 用法：node test/sentinel-alert-workflow.browser.mjs

import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BACKEND_URL || 'http://127.0.0.1:8080'
const bootstrap = await readFile(new URL('../../.runtime/secrets/bootstrap.env', import.meta.url), 'utf8')
const credentials = Object.fromEntries(bootstrap.trim().split(/\r?\n/).map(line => {
    const separator = line.indexOf('=')
    return [line.slice(0, separator), line.slice(separator + 1)]
}))

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext()
const report = { steps: [] }
const record = (name, ok, detail) => report.steps.push({ name, ok, detail })

const csrf = async () => (await (await context.request.get(`${base}/api/auth/session`)).json()).data.csrfToken
const call = async (method, path, data) => {
    const token = await csrf()
    const response = await context.request[method](`${base}${path}`, {
        headers: { 'X-CSRF-TOKEN': token },
        ...(data === undefined ? {} : { data })
    })
    let body = null
    try { body = await response.json() } catch { body = null }
    return { status: response.status(), body }
}

// 1) 未登录时，新接口必须被拒绝（不能因为加了功能就漏掉鉴权）
const anonymousAnalyze = await context.request.post(`${base}/api/sentinel/alerts/1/analyze`)
record('anonymous analyze denied', anonymousAnalyze.status() === 401 || anonymousAnalyze.status() === 403,
    `HTTP ${anonymousAnalyze.status()}`)
const anonymousKnowledge = await context.request.get(`${base}/api/sentinel/knowledge-candidates`)
record('anonymous knowledge denied', anonymousKnowledge.status() === 401 || anonymousKnowledge.status() === 403,
    `HTTP ${anonymousKnowledge.status()}`)

// 2) 管理员登录（图形人机验证）
const policy = (await (await context.request.get(`${base}/api/auth/human-verification?action=admin_login`)).json()).data
const attr = (element, name) => new RegExp(`\\b${name}="([^"]*)"`).exec(element)?.[1] ?? null
const marks = []
for (const m of policy.scene.matchAll(/<circle\b[^>]*>/g)) marks.push({ at: m.index, x: +attr(m[0], 'cx'), y: +attr(m[0], 'cy'), color: attr(m[0], 'fill'), letter: '' })
for (const m of policy.scene.matchAll(/<rect\b[^>]*>/g)) { const w = +attr(m[0], 'width'), h = +attr(m[0], 'height'); if (w >= 300 && h >= 200) continue; marks.push({ at: m.index, x: +attr(m[0], 'x') + w / 2, y: +attr(m[0], 'y') + h / 2, color: attr(m[0], 'fill'), letter: '' }) }
for (const m of policy.scene.matchAll(/<polygon\b[^>]*>/g)) { const pts = [...attr(m[0], 'points').matchAll(/(-?\d+),(-?\d+)/g)]; const xs = pts.map(p => +p[1]), ys = pts.map(p => +p[2]); marks.push({ at: m.index, x: Math.round(xs.reduce((a, c) => a + c, 0) / xs.length), y: Math.round(ys.reduce((a, c) => a + c, 0) / ys.length), color: attr(m[0], 'fill'), letter: '' }) }
const letters = [...policy.scene.matchAll(/dominant-baseline="central">(\w)<\/text>/g)].map(m => m[1])
marks.sort((a, c) => a.at - c.at).forEach((m, i) => m.letter = letters[i])
const color = /#[0-9a-f]{6}/i.exec(policy.prompt)
let wanted = color ? marks.filter(m => m.color === color[0].toLowerCase()) : [...policy.prompt].flatMap(t => marks.filter(m => m.letter === t))
if (!wanted.length) wanted = marks.slice(0, policy.targets)
await new Promise(resolve => setTimeout(resolve, 900))
const proof = await call('post', '/api/auth/human-verification/verify', { action: 'admin_login', nonce: policy.challenge, clicks: wanted.map(m => ({ x: m.x, y: m.y })) })
const login = await call('post', '/api/auth/login', {
    username: credentials.SMARTOPS_BOOTSTRAP_USERNAME, password: credentials.SMARTOPS_BOOTSTRAP_PASSWORD,
    portal: 'admin', humanToken: proof.body?.data?.token
})
record('admin login', login.status === 200, `HTTP ${login.status}`)
if (login.status !== 200) {
    report.summary = { total: report.steps.length, passed: report.steps.filter(s => s.ok).length, failed: ['admin login'] }
    console.log(JSON.stringify(report, null, 2))
    await browser.close()
    process.exit(1)
}

// 3) 不存在的告警：404 而不是 500（错误语义要准，便于前端给出正确提示）
const missingAnalyze = await call('post', '/api/sentinel/alerts/999999/analyze')
record('analyze unknown alert -> 404', missingAnalyze.status === 404, `HTTP ${missingAnalyze.status}`)
const missingKnowledge = await call('post', '/api/sentinel/alerts/999999/knowledge')
record('knowledge unknown alert -> 404', missingKnowledge.status === 404, `HTTP ${missingKnowledge.status}`)

// 4) 知识候选列表可用（空数组也是有效结果，不是错误）
const candidates = await call('get', '/api/sentinel/knowledge-candidates')
record('knowledge candidate list available', candidates.status === 200 && Array.isArray(candidates.body?.data),
    `HTTP ${candidates.status} count=${Array.isArray(candidates.body?.data) ? candidates.body.data.length : 'n/a'}`)

// 5) 采集边界如实说明：会话级连接 → 常驻采集需要独立采集器
const boundary = await call('get', '/api/sentinel/runtime-boundary')
const note = boundary.body?.data?.note ?? ''
record('runtime boundary stated honestly', boundary.status === 200 && /采集器/.test(note) && /会话级/.test(note),
    note.slice(0, 70))

report.summary = {
    total: report.steps.length,
    passed: report.steps.filter(step => step.ok).length,
    failed: report.steps.filter(step => !step.ok).map(step => step.name),
    note: '完整告警链路需要已授权的 SSH 运行连接才能产生真实告警；'
        + '研判逻辑由 SentinelAdvisorTest 覆盖，告警落库与「仅关闭后可沉淀」由 SentinelAlertWorkflowTest 覆盖。'
}
console.log(JSON.stringify(report, null, 2))
await browser.close()
process.exit(report.summary.failed.length === 0 ? 0 : 1)
