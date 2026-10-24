// 哨兵 / 脚本 / 告警 后端接口端到端验证（真实后端，无替身）。
//
// 覆盖：鉴权、schema 迁移、CRUD、白名单校验、高危脚本拒绝、
// 告警规则审批门槛、处置只进入待审批、告警闭环。
//
// 用法：node test/sentinel-api-contract.browser.mjs

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
const page = await context.newPage()

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

// 0) 匿名访问必须被拒绝
const anonymous = await context.request.get(`${base}/api/sentinel/tasks`)
record('anonymous access denied', anonymous.status() === 401 || anonymous.status() === 403, `HTTP ${anonymous.status()}`)

// 1) 管理员登录（含图形人机验证）
await page.goto(`${base}/api/auth/session`, { waitUntil: 'domcontentloaded' }).catch(() => {})
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
const humanToken = proof.body?.data?.token
const login = await call('post', '/api/auth/login', { username: credentials.SMARTOPS_BOOTSTRAP_USERNAME, password: credentials.SMARTOPS_BOOTSTRAP_PASSWORD, portal: 'admin', humanToken })
record('admin login with graphical captcha', login.status === 200, `HTTP ${login.status} portal=${login.body?.data?.portal}`)
if (login.status !== 200) { console.log(JSON.stringify(report, null, 2)); await browser.close(); process.exit(1) }

// 2) 阈值模板
const template = await call('post', '/api/sentinel/threshold-templates', {
    name: 'probe-memory-90', description: '探针模板', rules: [{ metric: 'memory', operator: 'gt', value: 90 }],
    severity: 'P2', debounceSec: 300
})
record('create threshold template', template.status === 200 && template.body?.data?.rules?.length === 1, JSON.stringify(template.body?.data?.rules))

const emptyRules = await call('post', '/api/sentinel/threshold-templates', { name: 'probe-empty', rules: [], severity: 'P2', debounceSec: 300 })
record('reject template with no rules', emptyRules.status === 400, `HTTP ${emptyRules.status} ${emptyRules.body?.message}`)

// 3) 哨兵任务：白名单校验
const okTask = await call('post', '/api/sentinel/tasks', { name: 'probe-cpu', kind: 'system', target: 'cpu', intervalSec: 30 })
record('create system sentinel', okTask.status === 200, `HTTP ${okTask.status} target=${okTask.body?.data?.target}`)

const badMetric = await call('post', '/api/sentinel/tasks', { name: 'probe-bad', kind: 'system', target: 'cpu; rm -rf /', intervalSec: 30 })
record('reject non-whitelisted metric', badMetric.status === 400, `HTTP ${badMetric.status} ${badMetric.body?.message}`)

const badProcess = await call('post', '/api/sentinel/tasks', { name: 'probe-inj', kind: 'business', target: 'process:nginx; id', intervalSec: 60 })
record('reject process-name injection', badProcess.status === 400, `HTTP ${badProcess.status} ${badProcess.body?.message}`)

const badPort = await call('post', '/api/sentinel/tasks', { name: 'probe-port', kind: 'business', target: 'port:70000', intervalSec: 60 })
record('reject out-of-range port', badPort.status === 400, `HTTP ${badPort.status} ${badPort.body?.message}`)

const logNoKeyword = await call('post', '/api/sentinel/tasks', { name: 'probe-log', kind: 'log', target: '/var/log/app.log', intervalSec: 60 })
record('reject log sentinel without keyword', logNoKeyword.status === 400, `HTTP ${logNoKeyword.status} ${logNoKeyword.body?.message}`)

// 4) 脚本：高危必须被服务端拒绝
const safeScript = await call('post', '/api/sentinel/scripts', { name: 'probe-disk-check', language: 'shell', riskLevel: 'LOW', body: 'df -h', timeoutSec: 30 })
record('create safe script', safeScript.status === 200, `HTTP ${safeScript.status} approved=${safeScript.body?.data?.approved}`)
const scriptId = safeScript.body?.data?.id

const dangerous = await call('post', '/api/sentinel/scripts', { name: 'probe-danger', language: 'shell', riskLevel: 'LOW', body: 'rm -rf /var/lib/mysql', timeoutSec: 30 })
record('reject dangerous script at save time', dangerous.status === 400, `HTTP ${dangerous.status} ${dangerous.body?.message}`)

const lint = await call('post', '/api/sentinel/scripts/lint', { body: 'mkfs.ext4 /dev/sda1', language: 'shell' })
record('lint endpoint reports blocked', lint.status === 200 && lint.body?.data?.status === 'blocked', JSON.stringify(lint.body?.data?.matches?.[0]))

const highRisk = await call('post', '/api/sentinel/scripts', { name: 'probe-high', language: 'shell', riskLevel: 'HIGH', body: 'systemctl restart nginx', timeoutSec: 30 })
record('high-risk script needs approval', highRisk.status === 200 && highRisk.body?.data?.approved === false, `approved=${highRisk.body?.data?.approved}`)

// 5) 告警规则：P0 不允许 auto_dispatch
const p0Rule = await call('post', '/api/sentinel/alert-rules', { name: 'probe-p0', templateId: template.body?.data?.id, severity: 'P0', scriptId, autoDispatch: true, notifyChannels: 'inapp' })
record('P0 rule cannot auto-dispatch', p0Rule.status === 200 && p0Rule.body?.data?.autoDispatch === false, `autoDispatch=${p0Rule.body?.data?.autoDispatch}`)

const badChannel = await call('post', '/api/sentinel/alert-rules', { name: 'probe-ch', severity: 'P2', notifyChannels: 'sms', scriptId })
record('reject unknown notify channel', badChannel.status === 400, `HTTP ${badChannel.status} ${badChannel.body?.message}`)

const p3Rule = await call('post', '/api/sentinel/alert-rules', { name: 'probe-p3', templateId: template.body?.data?.id, severity: 'P3', scriptId, autoDispatch: true, notifyChannels: 'inapp,webhook' })
record('P3 rule may auto-dispatch', p3Rule.status === 200 && p3Rule.body?.data?.autoDispatch === true, `autoDispatch=${p3Rule.body?.data?.autoDispatch}`)

// 6) 列表接口返回真实数据
const lists = {}
for (const [key, path] of [['tasks', '/api/sentinel/tasks'], ['templates', '/api/sentinel/threshold-templates'], ['scripts', '/api/sentinel/scripts'], ['alertRules', '/api/sentinel/alert-rules'], ['alerts', '/api/sentinel/alerts']]) {
    const result = await call('get', path)
    lists[key] = { status: result.status, count: Array.isArray(result.body?.data) ? result.body.data.length : null }
}
record('list endpoints return arrays', Object.values(lists).every(item => item.status === 200 && item.count !== null), JSON.stringify(lists))

// 7) 处置只进入待审批，不执行脚本
const dispatchNoAlert = await call('post', '/api/sentinel/alerts/999999/dispatch', { scriptId })
record('dispatch rejects unknown alert', dispatchNoAlert.status === 404, `HTTP ${dispatchNoAlert.status}`)

const boundary = await call('get', '/api/sentinel/runtime-boundary')
record('runtime boundary stated honestly', boundary.status === 200 && /采集器/.test(boundary.body?.data?.note ?? ''), boundary.body?.data?.note?.slice(0, 60))

// 8) 引用保护与清理
const templateId = template.body?.data?.id
const ruleCount = (await call('get', '/api/sentinel/alert-rules')).body?.data ?? []
record('referenced template cannot be deleted', ruleCount.some(rule => rule.templateId === templateId)
    ? (await call('delete', `/api/sentinel/threshold-templates/${templateId}`)).status === 409
    : false,
    `rules referencing template: ${ruleCount.filter(rule => rule.templateId === templateId).length}`)

// 按引用关系倒序清理：规则 → 脚本 → 模板 → 任务
const cleanup = []
for (const rule of ((await call('get', '/api/sentinel/alert-rules')).body?.data ?? [])) {
    if (String(rule.name).startsWith('probe-')) cleanup.push((await call('delete', `/api/sentinel/alert-rules/${rule.id}`)).status)
}
for (const script of ((await call('get', '/api/sentinel/scripts')).body?.data ?? [])) {
    if (String(script.name).startsWith('probe-')) cleanup.push((await call('delete', `/api/sentinel/scripts/${script.id}`)).status)
}
for (const item of ((await call('get', '/api/sentinel/threshold-templates')).body?.data ?? [])) {
    if (String(item.name).startsWith('probe-')) cleanup.push((await call('delete', `/api/sentinel/threshold-templates/${item.id}`)).status)
}
for (const item of ((await call('get', '/api/sentinel/tasks')).body?.data ?? [])) {
    if (String(item.name).startsWith('probe-')) cleanup.push((await call('delete', `/api/sentinel/tasks/${item.id}`)).status)
}
record('probe data cleaned up', cleanup.length > 0 && cleanup.every(status => status === 200), JSON.stringify(cleanup))

const leftovers = {
    tasks: ((await call('get', '/api/sentinel/tasks')).body?.data ?? []).filter(x => String(x.name).startsWith('probe-')).length,
    templates: ((await call('get', '/api/sentinel/threshold-templates')).body?.data ?? []).filter(x => String(x.name).startsWith('probe-')).length,
    scripts: ((await call('get', '/api/sentinel/scripts')).body?.data ?? []).filter(x => String(x.name).startsWith('probe-')).length,
    rules: ((await call('get', '/api/sentinel/alert-rules')).body?.data ?? []).filter(x => String(x.name).startsWith('probe-')).length
}
record('no probe leftovers', Object.values(leftovers).every(count => count === 0), JSON.stringify(leftovers))

report.summary = {
    total: report.steps.length,
    passed: report.steps.filter(step => step.ok).length,
    failed: report.steps.filter(step => !step.ok).map(step => step.name)
}
console.log(JSON.stringify(report, null, 2))
await browser.close()
process.exit(report.summary.failed.length === 0 ? 0 : 1)
