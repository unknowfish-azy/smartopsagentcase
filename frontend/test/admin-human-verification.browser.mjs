// 管理员层门户在人机验证上的行为核验。
//
// 目标：确认管理员层登录确实经过人机验证环节，且服务端策略返回的 provider 与前端渲染一致。
// 只读取策略与控件状态，不提交任何写操作。

import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_ADMIN_BASE_URL || 'http://127.0.0.1:5174'
const bootstrap = await readFile(new URL('../../.runtime/secrets/bootstrap.env', import.meta.url), 'utf8')
const credentials = Object.fromEntries(bootstrap.trim().split(/\r?\n/).map(line => {
    const separator = line.indexOf('=')
    return [line.slice(0, separator), line.slice(separator + 1)]
}))

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
page.setDefaultTimeout(20000)
const errors = []
page.on('pageerror', error => errors.push(`pageerror: ${error.message}`))

// 第三方脚本必须为零：离线可用是本次人机验证改造的硬要求。
// 注意：frontend/src/assets/styles/global.css 顶部有项目既有的 Google Fonts @import，
// 那是用户层与管理员层共用的既有字体依赖，不属于人机验证链路，本次未改动它。
// 因此这里把字体请求单独归类，用于区分"验证组件的外部依赖"与"既有字体依赖"。
const externalRequests = []
page.on('request', request => {
    const url = request.url()
    if (url.startsWith(base) || url.startsWith('data:')) return
    externalRequests.push(url)
})
const isFontRequest = url => /fonts\.(googleapis|gstatic)\.com/.test(url)
const isVerificationScript = url => /turnstile|cloudflare|hcaptcha|recaptcha|geetest/i.test(url)

await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' })
await page.locator('.login-form').waitFor()
await page.waitForTimeout(1200)

const policies = {}
for (const action of ['login', 'admin_login', 'register']) {
    const policy = await (await page.request.get(`${base}/api/auth/human-verification?action=${action}`)).json()
    const data = policy.data ?? {}
    policies[action] = {
        enabled: data.enabled,
        available: data.available,
        required: data.required,
        provider: data.provider,
        targets: data.targets,
        tolerance: data.tolerance,
        prompt: data.prompt,
        hasSvg: typeof data.svg === 'string' && data.svg.length > 0,
        svgLength: typeof data.svg === 'string' ? data.svg.length : 0,
        challengeLength: data.challenge?.length ?? 0
    }
}

const widget = {
    present: await page.locator('.human-verification').count(),
    status: await page.locator('.human-verification__heading span').textContent().catch(() => null),
    message: await page.locator('.human-verification p').textContent().catch(() => null)
}

// 管理员层真实登录是否仍能成功（当前后端策略下）
await page.getByPlaceholder('输入运维账号').fill(credentials.SMARTOPS_BOOTSTRAP_USERNAME)
await page.getByPlaceholder('输入访问密码').fill(credentials.SMARTOPS_BOOTSTRAP_PASSWORD)
await page.getByRole('button', { name: '进入智维Agent', exact: true }).click()
let loginOutcome
try {
    await page.locator('.admin-layout').waitFor({ timeout: 12000 })
    loginOutcome = { landed: 'admin-layout', url: page.url() }
} catch {
    loginOutcome = { landed: 'none', url: page.url(), error: await page.locator('.login-form__error').textContent().catch(() => null) }
}

const uniqueExternal = [...new Set(externalRequests)]
console.log(JSON.stringify({
    policies,
    widget,
    loginOutcome,
    external: {
        all: uniqueExternal,
        fonts: uniqueExternal.filter(isFontRequest),
        verificationProviders: uniqueExternal.filter(isVerificationScript)
    },
    errors: errors.slice(0, 10)
}, null, 2))
await browser.close()
