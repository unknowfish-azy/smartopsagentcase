// 将 docs/competition/technical-document.html 导出为 PDF（A4）。
// 用法：cd frontend && node ../scripts/export-technical-pdf.mjs
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium } = require('playwright')

const source = fileURLToPath(new URL('../docs/competition/technical-document.html', import.meta.url))
const target = fileURLToPath(new URL('../docs/competition/technical-document.pdf', import.meta.url))

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage()
  await page.goto('file:///' + source.replaceAll('\\', '/'))
  await page.pdf({ path: target, format: 'A4', printBackground: true })
  console.log('PDF exported:', target)
} finally {
  await browser.close()
}
