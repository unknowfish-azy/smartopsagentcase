// 浏览器回归套件：统一拉起一个 Vite dev server，按顺序执行关键 browser 脚本。
// 只收"自带 API mock / 不依赖后端"的脚本，保证不启动完整的 start-all 也能跑；
// 需要真实后端的脚本（team-workspace、login-layout 等）请用 start-all + SMARTOPS_BROWSER_BASE_URL 手工执行。
// 依赖：playwright + 本机 Edge（脚本内部用 msedge），只在本机/ nightly 跑，不进主测试流水线。
import { spawn } from 'node:child_process'

const port = 4300 + Math.floor(Math.random() * 100)
const base = `http://127.0.0.1:${port}`
const suite = [
  'test/visual-check.mjs',
  'test/diagnostic-tools.browser.mjs',
  'test/model-analytics.browser.mjs',
  'test/product-quality.browser.mjs',
  'test/chat-retry.browser.mjs',
  'test/chat-focus.browser.mjs',
  'test/chat-diagnostics.browser.mjs',
]

const vite = spawn(
  process.execPath,
  ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'],
  { stdio: 'ignore' },
)

const stop = () => {
  if (!vite.killed) vite.kill()
}

const waitForServer = async () => {
  for (let attempt = 0; attempt < 150; attempt += 1) {
    try {
      const response = await fetch(base)
      if (response.ok) return
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  throw new Error(`Vite dev server did not start on ${base}`)
}

const run = (script) =>
  new Promise((resolve) => {
    const child = spawn(process.execPath, [script], {
      stdio: 'inherit',
      env: { ...process.env, SMARTOPS_BROWSER_BASE_URL: base, SMARTOPS_VISUAL_BASE_URL: base },
    })
    child.on('exit', (code) => resolve(code ?? 1))
    child.on('error', () => resolve(1))
  })

try {
  await waitForServer()
  const failed = []
  for (const script of suite) {
    process.stdout.write(`\n=== ${script}\n`)
    const code = await run(script)
    if (code !== 0) failed.push(script)
  }
  if (failed.length) {
    console.error(`\nvisual suite failed: ${failed.join(', ')}`)
    process.exitCode = 1
  } else {
    console.log(`\nvisual suite passed: ${suite.length}/${suite.length}`)
  }
} finally {
  stop()
}
