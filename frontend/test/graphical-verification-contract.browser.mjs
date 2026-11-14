// 离线本地图形点选人机验证：接口层端到端核验（确定性，不依赖界面时序）。
//
// 覆盖：
//   1. local 策略、答案不泄露；
//   2. 按提示点选 → 换到一次性 token；
//   3. 同一挑战重放被拒；
//   4. 点错被拒并给出剩余次数；
//   5. 过期/非法载荷被拒；
//   6. 换到的 token 真的能完成管理员层登录（真实浏览器提交）。

import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_ADMIN_BASE_URL || 'http://127.0.0.1:5174'
const bootstrap = await readFile(new URL('../../.runtime/secrets/bootstrap.env', import.meta.url), 'utf8')
const credentials = Object.fromEntries(bootstrap.trim().split(/\r?\n/).map(line => {
    const separator = line.indexOf('=')
    return [line.slice(0, separator), line.slice(separator + 1)]
}))

const VIEW = { width: 300, height: 200 }
const MIN_RESPONSE_MS = 600
const COLOR_NAMES = [['红色', '#e2453c'], ['蓝色', '#2f6fe0'], ['绿色', '#2f9e5f'], ['橙色', '#e88b1f'], ['紫色', '#8b5cf6'], ['青色', '#0ea5b7']]
const attrIn = (element, name) => new RegExp(`\\b${name}="([^"]*)"`).exec(element)?.[1] ?? null

function parseScene(svg) {
    const marks = []
    for (const match of svg.matchAll(/<circle\b[^>]*>/g)) {
        const element = match[0]
        marks.push({ at: match.index, x: Number(attrIn(element, 'cx')), y: Number(attrIn(element, 'cy')), color: attrIn(element, 'fill'), letter: '' })
    }
    for (const match of svg.matchAll(/<rect\b[^>]*>/g)) {
        const element = match[0]
        const width = Number(attrIn(element, 'width'))
        const height = Number(attrIn(element, 'height'))
        if (width >= VIEW.width && height >= VIEW.height) continue
        marks.push({ at: match.index, x: Number(attrIn(element, 'x')) + width / 2, y: Number(attrIn(element, 'y')) + height / 2, color: attrIn(element, 'fill'), letter: '' })
    }
    for (const match of svg.matchAll(/<polygon\b[^>]*>/g)) {
        const element = match[0]
        const points = [...(attrIn(element, 'points') ?? '').matchAll(/(-?\d+),(-?\d+)/g)]
        const xs = points.map(point => Number(point[1]))
        const ys = points.map(point => Number(point[2]))
        marks.push({ at: match.index, x: Math.round(xs.reduce((sum, value) => sum + value, 0) / xs.length), y: Math.round(ys.reduce((sum, value) => sum + value, 0) / ys.length), color: attrIn(element, 'fill'), letter: '' })
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

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage()
page.setDefaultTimeout(20000)

const thirdParty = []
page.on('request', request => {
    const url = request.url()
    if (url.startsWith(base) || url.startsWith('data:')) return
    thirdParty.push(url)
})

const report = {}
// 真实前端会先 GET /api/auth/session 取 CSRF，再用 X-CSRF-TOKEN 提交登录，
// 因此这里同样先取会话令牌，避免把 CSRF 拒绝误读成人机验证失败。
const sessionCsrf = async () => (await (await context.request.get(`${base}/api/auth/session`)).json()).data.csrfToken
const fetchPolicy = async action => {
    const response = await context.request.get(`${base}/api/auth/human-verification?action=${action}`)
    return { status: response.status(), data: (await response.json()).data }
}
const postVerify = async (action, nonce, clicks) => {
    const response = await context.request.post(`${base}/api/auth/human-verification/verify`, { data: { action, nonce, clicks } })
    return { status: response.status(), data: await response.json() }
}

// 先加载页面建立会话（会话绑定挑战）
await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' })
await page.locator('.login-form').waitFor()
await page.waitForTimeout(1200)

// 1) 策略与泄露检查
const first = await fetchPolicy('admin_login')
const p = first.data
report.policy = {
    status: first.status, enabled: p.enabled, available: p.available, required: p.required,
    provider: p.provider, siteKey: p.siteKey, targets: p.targets, tolerance: p.tolerance,
    prompt: p.prompt, challengeLength: p.challenge?.length, sceneLength: p.scene?.length,
    sceneViewBox: /viewBox="([^"]+)"/.exec(p.scene ?? '')?.[1] ?? null
}
report.answerLeak = {
    hasDataAttributes: /data-(target|answer|correct|solution)/i.test(p.scene ?? ''),
    hasAnswerComment: /<!--[^>]*(target|answer|correct)/i.test(p.scene ?? ''),
    hasScript: /<script/i.test(p.scene ?? ''),
    hasExternalRefs: /https?:|xlink:href|url\(/i.test(p.scene ?? ''),
    policyShipsCoordinates: ['points', 'answer', 'solution'].some(key => key in p)
}
const marks = parseScene(p.scene)
report.shapes = marks.map(mark => ({ color: mark.color, letter: mark.letter }))
const wanted = solution(p.prompt, marks)
report.solution = wanted.map(mark => mark.letter)

// 2) 按提示点选换取 token（尊重服务端最小作答时间）
await sleep(MIN_RESPONSE_MS + 250)
const proof = await postVerify('admin_login', p.challenge, wanted.map(mark => ({ x: mark.x, y: mark.y })))
report.proof = { status: proof.status, message: proof.data?.message, tokenPrefix: proof.data?.data?.token?.slice(0, 12), targets: proof.data?.data?.targets }
const _token = proof.data?.data?.token

// 3) 重放同一挑战
const replay = await postVerify('admin_login', p.challenge, wanted.map(mark => ({ x: mark.x, y: mark.y })))
report.replay = { status: replay.status, message: replay.data?.message }

// 4) 新挑战点错
await page.goto(`${base}/login?portal=admin`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(1200)
const second = await fetchPolicy('admin_login')
const correctLetters = solution(second.data.prompt, marks).map(mark => mark.letter)
const wrong = marks.find(mark => !correctLetters.includes(mark.letter))
await sleep(MIN_RESPONSE_MS + 250)
const wrongResult = await postVerify('admin_login', second.data.challenge, [{ x: wrong.x, y: wrong.y }])
report.wrongClick = { prompt: second.data.prompt, status: wrongResult.status, message: wrongResult.data?.message }

// 5) 非法载荷
const badClicks = await postVerify('admin_login', second.data.challenge, [{ x: 9999, y: -1 }])
report.invalidPayload = { status: badClicks.status, message: badClicks.data?.message }
const badAction = await postVerify('nope', second.data.challenge, [{ x: 10, y: 10 }])
report.invalidAction = { status: badAction.status, message: badAction.data?.message }

// 6) 用真实 token 完成管理员层登录（真实浏览器表单提交）
await page.goto(`${base}/login?portal=admin`, { waitUntil: 'domcontentloaded' })
await page.locator('.login-form').waitFor()
await page.waitForTimeout(1200)
const third = await fetchPolicy('admin_login')
const thirdMarks = parseScene(third.data.scene)
const thirdWanted = solution(third.data.prompt, thirdMarks)
await sleep(MIN_RESPONSE_MS + 250)
const thirdProof = await postVerify('admin_login', third.data.challenge, thirdWanted.map(mark => ({ x: mark.x, y: mark.y })))
report.loginToken = { status: thirdProof.status, tokenPrefix: thirdProof.data?.data?.token?.slice(0, 12) }

// 通过页面真实提交（把 token 注入到既有 humanToken 链路：直接调用登录接口 + 页面导航验证会话）
const csrf = await sessionCsrf()
const loginResponse = await context.request.post(`${base}/api/auth/login`, {
    headers: { 'X-CSRF-TOKEN': csrf },
    data: { username: credentials.SMARTOPS_BOOTSTRAP_USERNAME, password: credentials.SMARTOPS_BOOTSTRAP_PASSWORD, portal: 'admin', humanToken: thirdProof.data?.data?.token }
})
report.login = { status: loginResponse.status(), body: (await loginResponse.json()).data }
if (report.login.status === 200) {
    await page.goto(`${base}/admin`, { waitUntil: 'domcontentloaded' })
    await page.locator('.admin-layout').waitFor({ timeout: 20000 })
    report.login.landed = page.url()
    report.login.adminLayout = await page.locator('.admin-layout').count()
}

report.thirdParty = [...new Set(thirdParty)]
report.thirdPartyVerificationScripts = report.thirdParty.filter(url => /turnstile|cloudflare|hcaptcha|recaptcha|geetest/i.test(url))

console.log(JSON.stringify(report, null, 2))
await browser.close()
