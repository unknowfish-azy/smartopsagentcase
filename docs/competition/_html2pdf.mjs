// 将 docs/competition/答辩材料-打印合订本.html 导出为 A4 PDF
// 用法：node docs/competition/_html2pdf.mjs
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

const require = createRequire(new URL('../../frontend/package.json', import.meta.url))
const { chromium } = require('playwright')

const source = fileURLToPath(new URL('./答辩材料-打印合订本.html', import.meta.url))
const target = fileURLToPath(new URL('./答辩材料-打印合订本.pdf', import.meta.url))

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage()
  await page.goto(pathToFileURL(source).href, { waitUntil: 'networkidle' })
  await page.emulateMedia({ media: 'print' })
  // 让 PDF 的页边距由 page.pdf 统一控制，避免与 CSS @page margin 叠加
  await page.addStyleTag({ content: '@page{size:A4;margin:0}' })
  await page.pdf({
    path: target,
    format: 'A4',
    printBackground: true,
    margin: { top: '15mm', bottom: '17mm', left: '14mm', right: '14mm' },
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate:
      '<div style="width:100%;font-size:8px;color:#8a97a8;text-align:center;font-family:Microsoft YaHei,sans-serif;">智维Agent 答辩材料 · 第 <span class="pageNumber"></span> / <span class="totalPages"></span> 页</div>',
  })
  console.log('PDF exported:', target)
} finally {
  await browser.close()
}
