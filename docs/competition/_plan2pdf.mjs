// 将《四件套万全之策-打印版.html》导出为 A4 PDF（带页眉页脚页码）
// 用法：node docs/competition/_plan2pdf.mjs
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

const require = createRequire(new URL('../../frontend/package.json', import.meta.url))
const { chromium } = require('playwright')

const source = fileURLToPath(new URL('./四件套万全之策-打印版.html', import.meta.url))
const target = fileURLToPath(new URL('./四件套万全之策-打印版.pdf', import.meta.url))

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage()
  await page.goto(pathToFileURL(source).href, { waitUntil: 'networkidle' })
  await page.emulateMedia({ media: 'print' })
  await page.addStyleTag({ content: '@page{size:A4;margin:0}' })
  await page.pdf({
    path: target,
    format: 'A4',
    printBackground: true,
    // 上下 24/22mm 留出页眉页脚；左右 21mm 远离打印机不可印区（约 3-5mm）
    margin: { top: '24mm', bottom: '22mm', left: '21mm', right: '21mm' },
    displayHeaderFooter: true,
    headerTemplate:
      '<div style="width:100%;padding:7mm 21mm 0;font-size:8px;color:#93a2b4;font-family:Microsoft YaHei,sans-serif;display:flex;justify-content:space-between;">'
      + '<span>智维 Agent · 提交材料四件套作战方案</span><span>内部文档 v1.0</span></div>',
    footerTemplate:
      '<div style="width:100%;padding:0 21mm 7mm;font-size:8px;color:#93a2b4;font-family:Microsoft YaHei,sans-serif;display:flex;justify-content:space-between;">'
      + '<span>2026 算法创新赛 · 河南赛区</span>'
      + '<span>第 <span class="pageNumber"></span> / <span class="totalPages"></span> 页</span></div>',
  })
  console.log('PDF exported:', target)
} finally {
  await browser.close()
}
