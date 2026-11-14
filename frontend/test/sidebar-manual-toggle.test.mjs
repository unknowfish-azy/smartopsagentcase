import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const layoutSource = await readFile(new URL('../src/layouts/MainLayout.vue', import.meta.url), 'utf8')

test('desktop sidebar uses one compact toggle with explicit state semantics', () => {
  assert.doesNotMatch(layoutSource, /@pointerenter=|@pointerleave=|sidebarPointerOpen|:focus-within/)
  assert.match(layoutSource, /class="sidebar-toggle"/)
  assert.match(layoutSource, /:aria-label="appStore\.sidebarCollapsed \? '展开主菜单' : '收起主菜单'"/)
  assert.match(layoutSource, /:aria-expanded="!appStore\.sidebarCollapsed"/)
  assert.match(layoutSource, /@click="appStore\.toggleSidebar\(\)"/)
  assert.match(layoutSource, /class="sidebar-toggle__icon"/)
  /* 旧的悬浮双按钮与固定像素定位已退休 */
  assert.doesNotMatch(layoutSource, /\.sidebar-expand-control|\.sidebar-collapse-control/)
})

test('toggle has bounded dimensions so the SVG never falls back to 300x150', () => {
  assert.match(layoutSource, /\.sidebar-toggle\s*{[^}]*width:\s*28px/s)
  assert.match(layoutSource, /\.sidebar-toggle\s*{[^}]*height:\s*28px/s)
  assert.match(layoutSource, /\.sidebar-toggle\s*{[^}]*border:\s*0/s)
  assert.match(layoutSource, /\.sidebar-toggle__icon\s*{[^}]*width:\s*16px/s)
})

test('toggle stays reachable while the long navigation rail is scrolled', () => {
  assert.match(layoutSource, /\.sidebar-toggle\s*{[^}]*position:\s*(sticky|fixed)/s)
  assert.match(layoutSource, /\.sidebar-toggle\s*{[^}]*z-index:\s*3/s)
})

test('fish pet switch lives in the topbar next to TOOLS, not in the sidebar footer', () => {
  assert.match(layoutSource, /class="persona-pet-toggle persona-pet-toggle--topbar"/)
  assert.match(layoutSource, /aria-pressed="personaPetStore\.enabled"/)
  assert.match(layoutSource, /\.persona-pet-toggle--topbar\s*{/s)
  assert.match(layoutSource, /\.persona-pet-toggle__dot\s*{/s)
  const statusLine = layoutSource.split('\n').find(line => line.includes('class="system-status"')) || ''
  assert.doesNotMatch(statusLine, /persona-pet-toggle/)
})

test('sidebar expanded state is driven by the store', () => {
  assert.match(layoutSource, /'sidebar--expanded':\s*!appStore\.sidebarCollapsed/)
})

test('sidebar uses a smooth transition driven by the design-system tokens (T19)', () => {
  /* T19：侧栏过渡用新令牌 --ds-duration-micro / --ds-ease-out，带 fallback */
  assert.match(layoutSource, /transition:\s*width var\(--ds-duration-micro, 150ms\) var\(--ds-ease-out, cubic-bezier\(\.22,1,\.36,1\)\)/)
  assert.match(layoutSource, /transition:\s*opacity 180ms ease, visibility 0s linear 180ms/)
  assert.match(layoutSource, /transition:\s*opacity 180ms ease, visibility 0s linear 0s/)
})
