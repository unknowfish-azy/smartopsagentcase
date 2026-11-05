// 无障碍与响应式验证（P1-UX-02）：375/768/1440 × 浅色/深色 × 关键页面，
// 检查 axe WCAG A/AA serious+critical、横向溢出、200% 缩放代理、键盘焦点可见性、reduced-motion。
// 边界：无真实 Provider / 无真实账号，全部使用 API fixture；人工读屏复核仍需人工完成，本脚本不替代。
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { execSync } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const axePath = require.resolve('axe-core/axe.min.js')

const root = process.cwd().replace(/\\frontend$/, '')
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '')
const artifact = `${root}\\.runtime\\accessibility-${stamp}`
await mkdir(artifact, { recursive: true })

const externalBase = process.env.SMARTOPS_BROWSER_BASE_URL
const port = 4500 + Math.floor(Math.random() * 80)
const base = externalBase || `http://127.0.0.1:${port}`

let vite = null
if (!externalBase) {
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
    cwd: `${root}\\frontend`,
    stdio: 'ignore'
  })
  for (let attempt = 0; attempt < 150; attempt++) {
    try { const response = await fetch(base); if (response.ok) break } catch {}
    await new Promise(resolve => setTimeout(resolve, 100))
  }
}

const pages = [
  { path: '/', name: 'dashboard' },
  { path: '/chat', name: 'chat' },
  { path: '/servers', name: 'servers' },
  { path: '/operations/runs', name: 'run-history' }
]

async function preparePage(browser, { width, height, theme, reducedMotion = 'no-preference' }) {
  const context = await browser.newContext({ viewport: { width, height }, reducedMotion })
  const page = await context.newPage()
  page.setDefaultTimeout(15000)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))

  const json = (data) => ({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })

  await page.route(url => url.pathname.startsWith('/api/') || url.pathname.startsWith('/ai/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/session')) return route.fulfill(json({ user: { id: 77, username: 'a11y-user', role: 'operator' }, csrfToken: 'a11y-csrf' }))
    if (path.endsWith('/auth/registration')) return route.fulfill(json({ enabled: false }))
    if (path.endsWith('/assistant/options')) {
      return route.fulfill(json({ selectedKey: 'mini', options: [{ key: 'mini', name: '智维 Mini', kind: 'builtin', model: 'fixture', enabled: true, available: true, status: 'ready' }] }))
    }
    if (path.endsWith('/ai/api/chat/stream')) {
      return route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream; charset=utf-8' }, body: 'event: done\ndata: {"status":"succeeded","content":"检查磁盘使用率。","run_event":{"run_id":"run-a11y","status":"succeeded","schema_version":"1.0.0"}}\n' })
    }
    // 其余接口统一返回空列表，保证视图能渲染出外壳而不是空白或抛错。
    return route.fulfill(json([]))
  })
  await page.routeWebSocket('**/*', socket => socket.close())
  await page.addInitScript((currentTheme) => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 77, username: 'a11y-user', role: 'operator' }))
    localStorage.setItem('smartops_theme', currentTheme)
  }, theme)
  return { context, page, errors }
}

async function settle(page) {
  // 页面外壳是否真的渲染出来；失败不抛错，由报告记录 blank，避免整轮中断。
  try {
    await page.waitForFunction(() => document.body.scrollHeight > 300, { timeout: 12000 })
    await page.waitForFunction(() => !document.querySelector('[aria-busy="true"]'), { timeout: 8000 }).catch(() => {})
    return true
  } catch {
    return false
  }
}

// Vite 首次编译路由模块时可能返回动态导入失败，重试一次即可区分环境抖动与真实空白。
async function open(page, path) {
  for (let attempt = 0; attempt < 2; attempt++) {
    await page.goto(`${base}${path}`, { waitUntil: 'domcontentloaded' })
    if (await settle(page)) return true
  }
  return false
}

async function axeScan(page) {
  await page.addScriptTag({ path: axePath })
  return page.evaluate(async () => {
    const result = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } })
    return result.violations.map(violation => ({
      id: violation.id,
      impact: violation.impact,
      count: violation.nodes.length,
      targets: violation.nodes.slice(0, 3).map(node => node.target.join(' '))
    }))
  })
}

const overflowOf = page => page.evaluate(() => ({
  scrollWidth: document.documentElement.scrollWidth,
  clientWidth: document.documentElement.clientWidth
}))

const browser = await chromium.launch({
  executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  headless: true
})

const report = {
  task: 'P1-UX-02',
  fixture: true,
  provider_e2e: false,
  note: '自动化只覆盖 axe/溢出/焦点/动效；人工读屏与真实设备复核需人工完成。',
  commit: 'unknown',
  matrix: [],
  axeViolations: [],
  overflow: [],
  zoom200: [],
  keyboard: [],
  reducedMotion: [],
  pageErrors: []
}
try { report.commit = execSync('git rev-parse HEAD', { cwd: root }).toString().trim() } catch {}

try {
  for (const viewport of [{ width: 375, height: 812 }, { width: 768, height: 1024 }, { width: 1440, height: 1000 }]) {
    for (const theme of ['light', 'dark']) {
      for (const target of pages) {
        const { context, page, errors } = await preparePage(browser, { ...viewport, theme })
        const rendered = await open(page, target.path)
        const violations = await axeScan(page)
        const overflow = await overflowOf(page)
        report.matrix.push({ viewport: `${viewport.width}x${viewport.height}`, theme, page: target.name, rendered, violations: violations.length, overflow: overflow.scrollWidth > overflow.clientWidth + 1 })
        for (const violation of violations) {
          if (violation.impact === 'serious' || violation.impact === 'critical') {
            report.axeViolations.push({ ...violation, viewport: `${viewport.width}x${viewport.height}`, theme, page: target.name })
          }
        }
        if (overflow.scrollWidth > overflow.clientWidth + 1) {
          report.overflow.push({ ...overflow, viewport: `${viewport.width}x${viewport.height}`, theme, page: target.name })
        }
        report.pageErrors.push(...errors.map(message => ({ page: target.name, viewport: viewport.width, theme, message })))
        await context.close()
      }
    }
  }

  // 200% 缩放代理：1440 物理像素下把 CSS 视口减半到 720x500。
  for (const target of pages) {
    const { context, page, errors } = await preparePage(browser, { width: 720, height: 500, theme: 'light' })
    const rendered = await open(page, target.path)
    const overflow = await overflowOf(page)
    const violations = await axeScan(page)
    report.zoom200.push({
      page: target.name,
      rendered,
      overflow: overflow.scrollWidth > overflow.clientWidth + 1,
      seriousCritical: violations.filter(violation => ['serious', 'critical'].includes(violation.impact)).length
    })
    report.pageErrors.push(...errors.map(message => ({ page: target.name, viewport: 720, theme: 'light', message })))
    await context.close()
  }

  // 键盘可达性与焦点可见性：Tab 遍历聊天页，记录每个落点是否有可见焦点指示。
  {
    const { context, page, errors } = await preparePage(browser, { width: 1440, height: 1000, theme: 'light' })
    await open(page, '/chat')
    // 先输入内容，否则发送按钮处于 disabled，无法进入 Tab 序列（这不是缺陷）。
    const composer = page.getByLabel('输入消息', { exact: true })
    await composer.fill('键盘可达性检查')

    // 定向断言：输入框一次 Tab 后应落在发送按钮。
    await composer.focus()
    await page.keyboard.press('Tab')
    const afterComposer = await page.evaluate(() => {
      const element = document.activeElement
      return { tag: element.tagName, name: (element.getAttribute('aria-label') || element.textContent || '').trim().slice(0, 24) }
    })

    const stops = []
    await page.evaluate(() => document.activeElement.blur())
    for (let index = 0; index < 60; index++) {
      await page.keyboard.press('Tab')
      stops.push(await page.evaluate(() => {
        const element = document.activeElement
        const style = getComputedStyle(element)
        // Element Plus 的输入框焦点环画在外层 wrapper 上，因此按元素自身判断会误报；
        // 原生 input/textarea 单独用焦点前后差异校验。
        const isNativeField = element.tagName === 'INPUT' || element.tagName === 'TEXTAREA'
        return {
          tag: element.tagName,
          name: (element.getAttribute('aria-label') || element.textContent || '').trim().slice(0, 24),
          visibleFocus: isNativeField ? true : (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0) || style.boxShadow !== 'none'
        }
      }))
    }
    // 输入框焦点环是否真的可见：比较聚焦前后的组合指示（textarea 自身 + 外层 composer）。
    const ringProbe = () => page.evaluate(() => {
      const textarea = document.querySelector('.ai-chat-composer textarea')
      const wrapper = document.querySelector('.ai-chat-composer')
      const style = getComputedStyle(textarea)
      const wrapperStyle = getComputedStyle(wrapper)
      return [style.outlineStyle, style.outlineWidth, style.boxShadow, wrapperStyle.borderColor, wrapperStyle.boxShadow].join('|')
    })
    await page.evaluate(() => document.activeElement.blur())
    const shadowBefore = await ringProbe()
    await composer.focus()
    const shadowAfter = await ringProbe()

    const reachedInput = stops.some(stop => stop.name.includes('输入消息'))
    const reachedSend = stops.some(stop => stop.name.includes('发送')) || afterComposer.name.includes('发送')
    const invisible = stops.filter(stop => !stop.visibleFocus && stop.tag !== 'BODY').map(stop => `${stop.tag}:${stop.name}`)
    report.keyboard.push({
      stops, afterComposer, reachedInput, reachedSend, invisible,
      composerFocusRing: { before: shadowBefore, after: shadowAfter, changed: shadowBefore !== shadowAfter }
    })
    report.pageErrors.push(...errors.map(message => ({ page: 'chat', viewport: 'keyboard', theme: 'light', message })))
    await context.close()
  }

  // reduced-motion：列表页不应存在 >100ms 的持续动画。
  {
    const { context, page, errors } = await preparePage(browser, { width: 1440, height: 1000, theme: 'light', reducedMotion: 'reduce' })
    await open(page, '/')
    const animated = await page.evaluate(() => {
      const offenders = []
      for (const element of document.querySelectorAll('*')) {
        const style = getComputedStyle(element)
        const duration = parseFloat(style.animationDuration) || 0
        if (style.animationName !== 'none' && duration > 0.1) {
          offenders.push(`${element.tagName.toLowerCase()}.${String(element.className || '').split(' ')[0]}`)
        }
      }
      return { count: offenders.length, sample: offenders.slice(0, 8), prefersReducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches }
    })
    report.reducedMotion.push({ page: 'dashboard', ...animated })
    report.pageErrors.push(...errors.map(message => ({ page: 'dashboard', viewport: 'reduced-motion', theme: 'light', message })))
    await context.close()
  }
} finally {
  await browser.close()
  if (vite && !vite.killed) vite.kill()
}

report.summary = {
  blank: report.matrix.filter(item => !item.rendered).length,
  seriousCritical: report.axeViolations.length,
  overflow: report.overflow.length,
  zoom200Failures: report.zoom200.filter(item => item.overflow || item.seriousCritical > 0).length,
  keyboard: { reachedInput: report.keyboard[0]?.reachedInput, reachedSend: report.keyboard[0]?.reachedSend, invisibleCount: report.keyboard[0]?.invisible.length, focusRingChanged: report.keyboard[0]?.composerFocusRing?.changed },
  reducedMotionOffenders: report.reducedMotion[0]?.count,
  pageErrors: report.pageErrors.length
}

await writeFile(`${artifact}\\report.json`, JSON.stringify(report, null, 2))
console.log(JSON.stringify({ artifact, summary: report.summary, axeViolations: report.axeViolations.slice(0, 10) }, null, 2))

const failed = report.summary.blank > 0 ||
  report.summary.seriousCritical > 0 ||
  report.summary.overflow > 0 ||
  report.summary.zoom200Failures > 0 ||
  report.summary.keyboard.reachedInput === false ||
  report.summary.keyboard.reachedSend === false ||
  report.summary.keyboard.focusRingChanged === false ||
  report.summary.reducedMotionOffenders > 0 ||
  report.summary.pageErrors > 0
process.exitCode = failed ? 1 : 0
