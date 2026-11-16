// 将 docs/competition/technical-document.html 导出为 A4 PDF
// 用法：node docs/competition/_techdoc2pdf.mjs
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

const require = createRequire(new URL('../../frontend/package.json', import.meta.url))
const { chromium } = require('playwright')

const source = fileURLToPath(new URL('./technical-document.html', import.meta.url))
const target = fileURLToPath(new URL('./technical-document.pdf', import.meta.url))

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage()
  await page.goto(pathToFileURL(source).href, { waitUntil: 'networkidle' })
  await page.emulateMedia({ media: 'print' })
  await page.waitForFunction(() => Array.from(document.images).every(img => img.complete && img.naturalWidth > 0))
  // HTML 已按 A4 单页设计并内置页脚；PDF 不再叠加页边距或浏览器页脚
  await page.addStyleTag({ content: '@page{size:A4;margin:0}' })
  await page.pdf({
    path: target,
    format: 'A4',
    preferCSSPageSize: true,
    printBackground: true,
    margin: { top: '0', bottom: '0', left: '0', right: '0' },
    displayHeaderFooter: false,
  })
  console.log('PDF exported:', target)
} finally {
  await browser.close()
}
