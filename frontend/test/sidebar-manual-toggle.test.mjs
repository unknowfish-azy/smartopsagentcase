import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const layoutSource = await readFile(new URL('../src/layouts/MainLayout.vue', import.meta.url), 'utf8')

test('desktop sidebar uses explicit expand and collapse controls', () => {
  assert.doesNotMatch(layoutSource, /@pointerenter=|@pointerleave=|sidebarPointerOpen|:focus-within/)
  assert.match(layoutSource, /class="sidebar-expand-control"/)
  assert.doesNotMatch(layoutSource, /v-if="appStore\.sidebarCollapsed" class="sidebar-expand-control"/)
  assert.match(layoutSource, /aria-label="展开主菜单"/)
  assert.match(layoutSource, /class="sidebar-collapse-control"/)
  assert.match(layoutSource, /&lt;&lt;&lt;<\/span>\s*收起/)
  assert.match(layoutSource, /@click="expandSidebar"/)
  assert.match(layoutSource, /@click="collapseSidebar"/)
})

test('desktop sidebar expanded state is driven by the store', () => {
  assert.match(layoutSource, /'sidebar--expanded':\s*!appStore\.sidebarCollapsed/)
  assert.match(layoutSource, /function expandSidebar\(\)\s*{\s*appStore\.expandSidebar\(\)\s*}/)
  assert.match(layoutSource, /function collapseSidebar\(\)\s*{\s*appStore\.collapseSidebar\(\)\s*}/)
})

test('collapse control is a compact bottom-right overlay', () => {
  assert.match(layoutSource, /\.sidebar-collapse-control\s*{[^}]*position:\s*fixed/s)
  /* T19：侧栏用新令牌，收起位置跟随 --ds-sidebar-width-collapsed */
  assert.match(layoutSource, /\.sidebar-collapse-control\s*{[^}]*left:\s*calc\(var\(--ds-sidebar-width-collapsed/s)
  assert.match(layoutSource, /\.sidebar-collapse-control\s*{[^}]*bottom:\s*34px/s)
  assert.match(layoutSource, /\.sidebar-collapse-control\s*{[^}]*width:\s*auto/s)
})

test('sidebar uses a smooth transition driven by the design-system tokens (T19)', () => {
  /* T19：侧栏过渡用新令牌 --ds-duration-micro / --ds-ease-out，带 fallback */
  assert.match(layoutSource, /transition:\s*width var\(--ds-duration-micro, 150ms\) var\(--ds-ease-out, cubic-bezier\(\.22,1,\.36,1\)\)/)
  assert.match(layoutSource, /transition:\s*opacity 180ms ease, visibility 0s linear 180ms/)
  assert.match(layoutSource, /transition:\s*opacity 180ms ease, visibility 0s linear 0s/)
})
