import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = await readFile(new URL('../src/views/auth/LoginView.vue', import.meta.url), 'utf8')

test('login view separates its decorative showcase from the accessible auth form', () => {
  assert.match(source, /class="login-glyph"/)
  assert.match(source, /class="login-showcase"/)
  assert.match(source, /class="login-organisms"/)
  assert.match(source, /aria-hidden="true"/)
  assert.match(source, /class="login-form login-form--portal"/)
  assert.doesNotMatch(source, /@pointermove="moveGlyph"|top: 43vh|right: -25px/)
  assert.match(source, /prefers-reduced-motion: reduce/)
})

test('login form retains portal security and account convenience controls', () => {
  assert.match(source, /class="login-form login-form--portal"/)
  assert.match(source, /class="password-visibility-toggle"/)
  assert.match(source, /rememberMe/)
  assert.match(source, /smartops_login_hint/)
  assert.match(source, /class="role-switcher"/)
  assert.match(source, /role="tablist"/)
  assert.match(source, /\.role-switcher button \{[^}]*background: var\(--smart-surface\)/)
  assert.match(source, /loginSession\(form.username, form.password, form.portal, humanState\.token\)/)
  assert.match(source, /loginSession/)
  assert.doesNotMatch(source, /JSON\.stringify\(\{ username: form\.username, role: form\.role/)
})

test('login portal switching routes to the owning service and preserves redirect context', () => {
  // 两个入口是两个独立前端服务：跨端口必须整页跳转，而不是只改一个变量。
  assert.match(source, /switchPortal\(entry\.id\)/)
  assert.match(source, /resolvePortalSwitch/)
  assert.match(source, /window\.location\.assign\(decision\.url\)/)
  // 同源时才走 SPA 替换，并保留 redirect 等上下文。
  assert.match(source, /syncPortalUrl/)
  assert.match(source, /router\.replace\(\{ path: '\/login', query: \{ \.\.\.route\.query, portal \} \}\)/)
})

test('login appearance reuses the application preferences without loading Three', () => {
  assert.match(source, /setThemeMode/)
  assert.match(source, /setVisualMode/)
  assert.match(source, /:motion-mode="visualMode"/)
  assert.doesNotMatch(source, /from ['"]three|import\(['"].*milky-way/)
})

test('login glass is decorative, bounded and has reduced-motion and opaque fallbacks', () => {
  assert.match(source, /backdrop-filter: blur\(var\(--login-glass-blur\)\)/)
  assert.match(source, /@pointermove="moveGlassLight"/)
  assert.match(source, /\.login-form::before[\s\S]*pointer-events: none/)
  assert.match(source, /@supports not \(backdrop-filter: blur\(1px\)\)/)
  assert.match(source, /cancelAnimationFrame\(glassFrame\)/)
})
