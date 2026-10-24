import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

const mainSource = await readFile(new URL('../src/main.js', import.meta.url), 'utf8')
const layoutSource = await readFile(new URL('../src/layouts/MainLayout.vue', import.meta.url), 'utf8')
const globalStyles = await readFile(new URL('../src/assets/styles/global.css', import.meta.url), 'utf8')
const variables = await readFile(new URL('../src/assets/styles/variables.css', import.meta.url), 'utf8')

test('loads the LGGC package before the SmartOps theme overrides', () => {
  const packageImport = mainSource.indexOf("@guochenwang/lggc/dist/lggc.min.css")
  const themeImport = mainSource.indexOf("./assets/styles/global.css")

  assert.ok(packageImport >= 0)
  assert.ok(themeImport > packageImport)
})

test('marks tool routes as an explicit liquid-glass opt-out', () => {
  assert.match(layoutSource, /'app-layout--tools': isToolsPage/)
  assert.match(layoutSource, /'app-layout--liquid': !isToolsPage/)
  assert.match(layoutSource, /const isToolsPage = computed\(\(\) => route\.name === 'Tools'\)/)
  assert.match(layoutSource, /lggc: !isToolsPage/)
})

test('scopes liquid surfaces to non-tool pages and preserves readable controls', () => {
  assert.match(globalStyles, /\.app-layout--liquid \.sidebar/)
  assert.match(globalStyles, /\.app-layout--liquid \.topbar/)
  assert.match(globalStyles, /\.app-layout--liquid \.el-card/)
  assert.match(globalStyles, /\.app-layout--liquid \.operations-workspace/)
  assert.match(globalStyles, /\.app-layout--liquid \.metric-card/)
  assert.match(globalStyles, /\.app-layout--liquid \.el-input__wrapper/)
  assert.match(globalStyles, /\.app-layout--tools \.sidebar/)
  assert.match(globalStyles, /@supports not \(backdrop-filter: blur\(1px\)\)/)
  assert.match(variables, /--smart-glass-bg:/)
  assert.match(variables, /color-scheme: dark/)
})
