// 联网研究阶段四 T33b：受控无头渲染器。
// 由后端 LocalPlaywrightRenderer 以受控子进程调用；本脚本不做任何出站策略判断
// （导航目标必须先经 Java 侧 OutboundUrlPolicy 校验），只负责打开页面、提取标题与正文文本。
// 安全约束：仅接受 http/https；禁下载；禁扩展；提取前剥离 script/style/nav/footer/aside/form/iframe；
// 提取文本按不可信资料处理，绝不进入 Agent 指令链。
// Playwright 复用前端既有依赖（frontend/node_modules），后端不新增安装。
//
// 用法：
//   node web-render.mjs render <url> [--state <file>] [--timeout-ms N]
//   node web-render.mjs login <profileDir> [--timeout-ms N]
//     有头窗口由用户手动登录；登录期间每 3s 将 storage state 落 <profileDir>/state.json；
//     用户关闭窗口后脚本退出。明文 state 只存在于 profile 目录，由 Java 侧 finish 后加密并删除。
import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const frontendRequire = createRequire(resolve(here, '../../frontend/package.json'))
const { chromium } = frontendRequire('playwright')

const argv = process.argv.slice(2)
const mode = argv[0]
const flags = {}
for (let i = 1; i < argv.length - 1; i++) {
  if (argv[i].startsWith('--')) flags[argv[i].slice(2)] = argv[i + 1]
}
const positional = argv.slice(1).filter(a => !a.startsWith('--') && !(argv[argv.indexOf(a) - 1] || '').startsWith('--'))
const timeoutMs = Number(flags['timeout-ms'] || 15000)

const LAUNCH_ARGS = ['--disable-extensions', '--no-first-run', '--disable-background-networking']
const fail = code => { console.error(JSON.stringify({ ok: false, code })); process.exit(1) }
const printJson = value => { process.stdout.write(JSON.stringify(value)); process.exit(0) }

if (mode === 'render') {
  const url = positional[0]
  if (!url || !/^https?:\/\//i.test(url)) fail('INVALID_URL')
  let state
  if (flags.state) {
    try { state = readFileSync(flags.state, 'utf8') } catch { fail('STATE_UNREADABLE') }
  }
  const browser = await chromium.launch({ headless: true, args: LAUNCH_ARGS })
  try {
    const context = await browser.newContext({
      storageState: state || undefined,
      acceptDownloads: false,
      serviceWorkers: 'block',
      viewport: { width: 1280, height: 900 }
    })
    const page = await context.newPage()
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: Math.max(timeoutMs, 3000) })
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => {})
    const data = await page.evaluate(() => {
      const body = document.body
      if (!body) return { title: document.title || '', text: '' }
      const clone = body.cloneNode(true)
      clone.querySelectorAll('script,style,noscript,nav,footer,aside,form,iframe,svg,canvas').forEach(el => el.remove())
      const main = clone.querySelector('main,article') || clone
      const text = (main.innerText || main.textContent || '').replace(/\n{3,}/g, '\n\n').trim()
      return { title: document.title || '', text }
    })
    await browser.close()
    printJson({ ok: true, title: (data.title || '').slice(0, 300), text: (data.text || '').slice(0, 20000) })
  } catch (error) {
    await browser.close().catch(() => {})
    fail(error && error.name === 'TimeoutError' ? 'RENDER_TIMEOUT' : 'RENDER_FAILED')
  }
} else if (mode === 'login') {
  const profileDir = resolve(positional[0] || '')
  if (!profileDir) fail('PROFILE_REQUIRED')
  mkdirSync(profileDir, { recursive: true })
  const statePath = join(profileDir, 'state.json')
  const context = await chromium.launchPersistentContext(profileDir, {
    headless: false,
    acceptDownloads: false,
    args: LAUNCH_ARGS
  })
  const page = context.pages()[0] || await context.newPage()
  await page.goto('about:blank').catch(() => {})
  const persist = setInterval(() => {
    context.storageState().then(state => writeFileSync(statePath, JSON.stringify(state))).catch(() => {})
  }, 3000)
  context.on('close', () => { clearInterval(persist); process.exit(0) })
} else {
  fail('MODE_UNSUPPORTED')
}
