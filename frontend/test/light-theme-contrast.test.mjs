import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parse, compileStyle } from '@vue/compiler-sfc'

const variables = await readFile(new URL('../src/assets/styles/variables.css', import.meta.url), 'utf8')
const globalStyles = await readFile(new URL('../src/assets/styles/global.css', import.meta.url), 'utf8')
const orbitCarousel = await readFile(new URL('../src/components/ui/home-orbit-carousel.vue', import.meta.url), 'utf8')
const milkyWay = await readFile(new URL('../src/components/ui/milky-way.vue', import.meta.url), 'utf8')

test('effect theme selectors never dim the document root', async () => {
  for (const name of ['AtcShaderBackground', 'LivingJellyfish']) {
    const filename = `${name}.vue`
    const source = await readFile(new URL(`../src/components/common/${filename}`, import.meta.url), 'utf8')
    const { descriptor } = parse(source, { filename })
    for (const style of descriptor.styles) {
      const result = compileStyle({ source: style.content, filename, id: 'data-v-theme-test', scoped: style.scoped })
      assert.deepEqual(result.errors, [])
      assert.doesNotMatch(result.code, /\[data-theme=['"]light['"]\]\s*\{/, filename)
    }
  }
})

test('light theme uses opaque, high-contrast semantic tokens', () => {
  assert.match(variables, /\[data-theme='light'\][\s\S]*--smart-text:\s*#10212b;/)
  assert.match(variables, /\[data-theme='light'\][\s\S]*--smart-muted:\s*#4d606c;/)
  assert.match(variables, /\[data-theme='light'\][\s\S]*--smart-border:\s*rgba\(16, 53, 70, \.22\);/)
  assert.match(variables, /\[data-theme='light'\][\s\S]*--smart-glass-bg:\s*rgba\(255, 255, 255, \.96\);/)
})

test('light theme keeps cards and controls readable over decorative backgrounds', () => {
  assert.match(globalStyles, /:root\[data-theme\] \.el-card\s*\{\s*transition-property: box-shadow, transform;/)
  assert.match(globalStyles, /:root\[data-theme\] \.el-table \.el-table__cell\s*\{\s*transition-property: none;/)
  assert.match(globalStyles, /:root\[data-theme\] \.el-button\s*\{\s*transition-property: border-color, box-shadow, transform;/)
  assert.match(globalStyles, /\[data-theme='light'\][\s\S]*\.app-layout--liquid \.el-card[\s\S]*background: var\(--smart-card\) !important;/)
  assert.match(globalStyles, /\[data-theme='light'\][\s\S]*\.app-layout--liquid \.el-input__wrapper[\s\S]*background: var\(--smart-surface\) !important;/)
  assert.match(globalStyles, /\[data-theme='light'\][\s\S]*\.app-layout--liquid \.el-table__body-wrapper[\s\S]*color: var\(--smart-text\) !important;/)
  assert.doesNotMatch(globalStyles, /\[data-theme='light'\][\s\S]*background: rgba\(255, 255, 255, \.72\) !important;/)
})

test('light theme keeps the home stage and orbit cards readable', () => {
  assert.ok(orbitCarousel.includes(":global([data-theme='light'] .orbit-card)"))
  assert.ok(orbitCarousel.includes('background: var(--smart-card)'))
  assert.ok(orbitCarousel.includes(":global([data-theme='light'] .card-description)"))
  assert.ok(orbitCarousel.includes(":global([data-theme='light'] .card-body h2)"))
  assert.ok(milkyWay.includes(":global([data-theme='light'] .milky-way)"))
  assert.ok(milkyWay.includes(":global([data-theme='light'] .milky-way canvas)"))
  assert.match(milkyWay, /background: linear-gradient/)
  assert.match(milkyWay, /visibility: hidden/)
  assert.doesNotMatch(milkyWay, /\[data-theme='light'\] \.milky-way canvas\)[^}]*visibility:\s*hidden/)
  assert.match(milkyWay, /observeCanvasTheme/)
})
