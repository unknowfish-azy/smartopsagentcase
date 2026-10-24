// 端到端：人机验证的「风险升级 → 图形点选 → 登录成功」完整链路。
//
// 这是真实的运行时路径，不依赖任何测试钩子：
//   1. 全新会话下 required=false，控件不要求作答（按风险触发）；
//   2. 连续失败登录达到阈值后，服务端把 required 升级为 true；
//   3. 此时界面真实渲染图形场景，在画布上按提示点选；
//   4. 自动兑换一次性 token → 登录成功进入管理台。

import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_ADMIN_BASE_URL || 'http://127.0.0.1:5174'
const bootstrap = await readFile(new URL('../../.runtime/secrets/bootstrap.env', import.meta.url), 'utf8')
const credentials = Object.fromEntries(bootstrap.trim().split(/\r?\n/).map(line => {
    const separator = line.indexOf('=')
    return [line.slice(0, separator), line.slice(separator + 1)]
}))

const VIEW = { width: 300, height: 200 }
const COLOR_NAMES = [['红色', '#e2453c'], ['蓝色', '#2f6fe0'], ['绿色', '#2f9e5f'], ['橙色', '#e88b1f'], ['紫色', '#8b5cf6'], ['青色', '#0ea5b7']]
const attrIn = (element, name) => new RegExp(`\\b${name}="([^"]*)"`).exec(element)?.[1] ?? null

function parseScene(svg) {
    const marks = []
    for (const match of svg.matchAll(/<circle\b[^>]*>/g)) {
        marks.push({ at: match.index, x: Number(attrIn(match[0], 'cx')), y: Number(attrIn(match[0], 'cy')), color: attrIn(match[0], 'fill'), letter: '' })
    }
    for (const match of svg.matchAll(/<rect\b[^>]*>/g)) {
        const width = Number(attrIn(match[0], 'width'))
        const height = Number(attrIn(match[0], 'height'))
        if (width >= VIEW.width && height >= VIEW.height) continue
        marks.push({ at: match.index, x: Number(attrIn(match[0], 'x')) + width / 2, y: Number(attrIn(match[0], 'y')) + height / 2, color: attrIn(match[0], 'fill'), letter: '' })
    }
    for (const match of svg.matchAll(/<polygon\b[^>]*>/g)) {
        const points = [...(attrIn(match[0], 'points') ?? '').matchAll(/(-?\d+),(-?\d+)/g)]
        const xs = points.map(point => Number(point[1]))
        const ys = points.map(point => Number(point[2]))
        marks.push({ at: match.index, x: Math.round(xs.reduce((sum, value) => sum + value, 0) / xs.length), y: Math.round(ys.reduce((sum, value) => sum + value, 0) / ys.length), color: attrIn(match[0], 'fill'), letter: '' })
    }
    const letters = [...svg.matchAll(/dominant-baseline="central">(\w)<\/text>/g)].map(match => match[1])
    if (letters.length !== marks.length) throw new Error(`图形与字符数量不一致：${marks.length} vs ${letters.length}`)
    marks.sort((left, right) => left.at - right.at)
    return marks.map((mark, index) => ({ ...mark, letter: letters[index] }))
}

function solution(prompt, marks) {
    const color = /#[0-9a-f]{6}/i.exec(prompt)
    if (color) return marks.filter(mark => mark.color === color[0].toLowerCase())
    const byLetter = [...prompt].flatMap(token => marks.filter(mark => mark.letter === token))
    if (byLetter.length) return byLetter
    return COLOR_NAMES
        .map(([name, hex], index) => ({ index: prompt.indexOf(name), hex }))
        .filter(entry => entry.index >= 0)
        .sort((left, right) => left.index - right.index)
        .flatMap(entry => marks.filter(mark => mark.color === entry.hex))
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
const page = await context.newPage()
page.setDefaultTimeout(20000)
const errors = []
page.on('pageerror', error => errors.push(error.message))

const report = {}
const policyFor = async action => (await (await context.request.get(`${base}/api/auth/human-verification?action=${action}`)).json()).data
const csrfToken = async () => (await (await context.request.get(`${base}/api/auth/session`)).json()).data.csrfToken

await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' })
await page.locator('.login-form').waitFor()
await page.waitForTimeout(1200)

// 1) 未升级：不要求作答
report.initialPolicy = { required: (await policyFor('admin_login')).required }
report.initialCanvasVisible = await page.locator('.human-verification__canvas').isVisible().catch(() => false)

// 2) 用错误密码触发升级（服务端按 IP/账号失败次数强制人机验证）
const csrf = await csrfToken()
for (let attempt = 0; attempt < 3; attempt++) {
    await context.request.post(`${base}/api/auth/login`, {
        headers: { 'X-CSRF-TOKEN': csrf },
        data: { username: credentials.SMARTOPS_BOOTSTRAP_USERNAME, password: 'deliberately-wrong', portal: 'admin' }
    })
}
const escalated = await policyFor('admin_login')
report.escalatedPolicy = { required: escalated.required, provider: escalated.provider, targets: escalated.targets, prompt: escalated.prompt }

// 3) 重新进入登录页：界面必须真实渲染图形场景
await page.goto(`${base}/login?portal=admin`, { waitUntil: 'domcontentloaded' })
await page.locator('.login-form').waitFor()
const canvas = page.locator('.human-verification__canvas')
await canvas.waitFor({ state: 'visible', timeout: 20000 })
report.widget = {
    status: await page.locator('.human-verification__heading span').textContent(),
    prompt: await page.locator('.human-verification__prompt').textContent(),
    hint: await page.locator('.human-verification__hint').textContent(),
    svgRendered: await page.locator('.human-verification__scene svg').count()
}

// 场景来自当前会话的本次挑战：重新取一份并确认与界面提示一致
const live = await policyFor('admin_login')
report.promptMatchesServer = live.prompt === report.widget.prompt
const marks = parseScene(live.scene)
const wanted = solution(live.prompt, marks)
report.wanted = wanted.map(mark => ({ color: mark.color, letter: mark.letter }))

// 4) 真实画布点选
const box = await canvas.boundingBox()
report.canvas = { width: Math.round(box.width), height: Math.round(box.height), ratio: +(box.width / box.height).toFixed(3) }
for (const mark of wanted) {
    await canvas.click({ position: { x: mark.x / VIEW.width * box.width, y: mark.y / VIEW.height * box.height } })
    await page.waitForTimeout(350)
}
await page.locator('.human-verification__heading span').filter({ hasText: '已通过' }).waitFor({ timeout: 15000 })
report.afterPicking = {
    status: await page.locator('.human-verification__heading span').textContent(),
    message: await page.locator('.human-verification p').first().textContent(),
    marksShown: await page.locator('.human-verification__mark').count()
}

// 5) 提交登录（现在必须携带已通过验证的状态）
await page.getByPlaceholder('输入运维账号').fill(credentials.SMARTOPS_BOOTSTRAP_USERNAME)
await page.getByPlaceholder('输入访问密码').fill(credentials.SMARTOPS_BOOTSTRAP_PASSWORD)
await page.getByRole('button', { name: '进入智维Agent', exact: true }).click()
await page.locator('.admin-layout').waitFor({ timeout: 20000 })
report.login = { landed: page.url(), adminLayout: await page.locator('.admin-layout').count() }
report.session = (await (await context.request.get(`${base}/api/auth/session`)).json()).data.user

report.errors = errors.slice(0, 10)
console.log(JSON.stringify(report, null, 2))
await browser.close()
