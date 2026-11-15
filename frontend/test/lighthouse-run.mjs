import lighthouse from 'lighthouse'
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'

const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const url = process.env.LH_URL || 'http://127.0.0.1:5173/'
const outDir = 'D:\\SmartOpsAgent\\.runtime\\lighthouse-20261115'
const port = 9333

// 自己起 Edge（headless=new + 远程调试端口），Lighthouse 连已起好的浏览器，避免其自带 --headless 与 Edge 157 不兼容。
const edge = spawn(edgePath, ['--headless=new', `--remote-debugging-port=${port}`, '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-proxy-server', '--proxy-bypass-list=*', 'about:blank'], { stdio: 'ignore' })
let ready = false
for (let i = 0; i < 60; i++) {
  try { const r = await fetch(`http://127.0.0.1:${port}/json/version`); if (r.ok) { ready = true; break } } catch {}
  await new Promise(r => setTimeout(r, 200))
}
if (!ready) { console.error('Edge debug port not ready'); process.exit(1) }

await mkdir(outDir, { recursive: true })

async function run(formFactor) {
  const isMobile = formFactor === 'mobile'
  const flags = {
    port,
    output: 'json',
    onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
    formFactor,
    screenEmulation: isMobile ? undefined : { disabled: true },
    chromeFlags: ['--no-sandbox', '--disable-gpu'],
  }
  const result = await lighthouse(url, flags)
  const cats = result.lhr.categories
  const scores = {}
  for (const [k, v] of Object.entries(cats)) scores[k] = Math.round((v.score ?? 0) * 100)
  const audits = result.lhr.audits
  const perf = {
    FCP: audits['first-contentful-paint']?.displayValue,
    LCP: audits['largest-contentful-paint']?.displayValue,
    TBT: audits['total-blocking-time']?.displayValue,
    CLS: audits['cumulative-layout-shift']?.displayValue,
    SI: audits['speed-index']?.displayValue,
  }
  await writeFile(`${outDir}\\${formFactor}.json`, JSON.stringify(result.lhr, null, 2))
  return { formFactor, scores, perf }
}

try {
  const summary = { url, desktop: await run('desktop'), mobile: await run('mobile') }
  console.log(JSON.stringify(summary, null, 2))
  await writeFile(`${outDir}\\summary.json`, JSON.stringify(summary, null, 2))
} finally {
  if (!edge.killed) edge.kill()
}
