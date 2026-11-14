/**
 * 数字人真机验收（runner 侧）。
 *
 * 起一个只跑验收页的 Vite 服务，把地址打印成局域网 URL；真机打开后页面自动跑完
 * 首帧 / 稳态帧时 / 真实渲染帧率 / 自动降级 / 上下文丢失五项，POST 回本进程。
 * 结果落到 .runtime/persona-device-<时间戳>/device-report.json，任一硬性项失败则退出码 1。
 *
 * 用法：
 *   npm run persona:device
 *   SMARTOPS_ACCEPTANCE_PORT=5188 npm run persona:device
 *   SMARTOPS_ACCEPTANCE_TIMEOUT_MS=300000 npm run persona:device
 *
 * 真机与开发机须在同一局域网；手机浏览器打开打印出的 http://<内网IP>:5188/...
 */
import { createServer } from 'vite'
import { mkdir, writeFile } from 'node:fs/promises'
import { networkInterfaces } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = path.resolve(frontendRoot, '..')
const port = Number(process.env.SMARTOPS_ACCEPTANCE_PORT || 5188)
const timeoutMs = Number(process.env.SMARTOPS_ACCEPTANCE_TIMEOUT_MS || 240000)
const pagePath = '/test/persona-device-acceptance.html'
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '')
const artifact = path.join(repositoryRoot, '.runtime', `persona-device-${stamp}`)

let deliver = () => {}
let delivered = false
const deviceReport = new Promise((resolve) => {
  deliver = resolve
})

/** 接收页面回传；重复上报只回 ok，不覆盖第一份结果 */
const reportPlugin = {
  name: 'persona-device-report',
  configureServer(server) {
    server.middlewares.use('/__acceptance/report', (request, response) => {
      if (request.method !== 'POST') {
        response.statusCode = 405
        response.end('POST only')
        return
      }
      let body = ''
      request.on('data', (chunk) => {
        body += chunk
        if (body.length > 2 * 1048576) request.destroy()
      })
      request.on('end', () => {
        if (delivered) {
          response.setHeader('content-type', 'application/json')
          response.end('{"ok":true,"duplicate":true}')
          return
        }
        try {
          const payload = JSON.parse(body)
          delivered = true
          response.setHeader('content-type', 'application/json')
          response.end('{"ok":true}')
          deliver(payload)
        } catch (error) {
          response.statusCode = 400
          response.end(`invalid json: ${error.message}`)
        }
      })
    })
  }
}

const server = await createServer({
  root: frontendRoot,
  configFile: false,
  logLevel: 'warn',
  // 只扫描验收页，避免把应用入口（.vue）拉进依赖预构建——这里没有 Vue 插件
  optimizeDeps: { entries: ['test/persona-device-acceptance.html'] },
  server: { host: '0.0.0.0', port, strictPort: true },
  plugins: [reportPlugin]
})
await server.listen()

const addresses = []
for (const entries of Object.values(networkInterfaces())) {
  for (const entry of entries ?? []) {
    if (entry && entry.family === 'IPv4' && !entry.internal) addresses.push(entry.address)
  }
}

console.log('\n数字人真机验收服务已启动')
console.log('在真机浏览器打开（手机与本机须在同一局域网）：')
if (addresses.length === 0) console.log(`  http://<本机内网 IP>:${port}${pagePath}`)
for (const address of addresses) console.log(`  http://${address}:${port}${pagePath}`)
console.log(`\n本机自检：http://127.0.0.1:${port}${pagePath}`)
console.log(`等待设备回传结果，最长 ${Math.round(timeoutMs / 1000)} 秒（Ctrl+C 退出）…`)

const report = await Promise.race([
  deviceReport,
  new Promise((resolve) => setTimeout(() => resolve(null), timeoutMs))
])

if (!report) {
  console.error(`\n超时：${Math.round(timeoutMs / 1000)} 秒内没有收到设备回传。`)
  console.error('检查手机是否与服务在同一网段、地址是否被防火墙拦截，或页面是否进入了后台。')
  await server.close()
  process.exitCode = 1
} else {
  await mkdir(artifact, { recursive: true })
  const file = path.join(artifact, 'device-report.json')
  await writeFile(file, JSON.stringify(report, null, 2))

  const device = report.device ?? {}
  const steady = report.steady ?? {}
  if (report.timings?.warmupMs !== 8000) {
    console.warn('注意：本次使用了缩短的采样窗口（调试参数），数据不能作为正式验收结论。')
  }
  console.log('\n—— 设备 ——')
  console.log(`  ${device.gpu ?? 'GPU 未知'}`)
  console.log(`  视口 ${device.viewport ?? '—'} @${device.dpr ?? '?'}x · ${device.hardwareConcurrency ?? '?'} 核 · ${device.userAgent ?? '—'}`)
  console.log('\n—— 关键指标 ——')
  console.log(`  首帧 ${report.firstFrameMs ?? '—'} ms · 真实渲染 ${steady.renderFps ?? '—'} fps · 帧时 P50/P90 ${steady.frameP50Ms ?? '—'}/${steady.frameP90Ms ?? '—'} ms`)
  console.log(`  draw call ${steady.drawCalls ?? '—'} · JS 堆 ${steady.heapMB ?? '不可读'} MB · 像素比 ${report.pixelRatioAtReady ?? '—'} → ${steady.degraded ? 1 : '未降级'}`)
  if (report.degrade?.triggered) {
    console.log(`  自动降级：${report.degrade.waitMs} ms 触发，${steady.renderFps} → ${report.degrade.renderFpsAfter} fps`)
  }

  console.log('\n—— 验收项 ——')
  for (const check of report.checks ?? []) {
    const verdict = String(check.verdict).toUpperCase().padEnd(6, ' ')
    console.log(`  ${verdict} ${check.label}：${check.actual}（预算 ${check.budget}）`)
  }

  const failed = (report.checks ?? []).filter((check) => check.verdict === 'fail')
  console.log(`\n结果文件：${file}`)
  if (report.fatal) console.error(`中止原因：${report.fatal}`)
  if (failed.length) {
    console.error(`\n未通过 ${failed.length} 项：${failed.map((check) => check.label).join('、')}`)
    process.exitCode = 1
  } else {
    console.log('\n真机验收通过（标为 EXEMPT 的项属占位模型例外，见 PERF.md §3.1）。')
  }
  await server.close()
}
