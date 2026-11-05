import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const root = new URL('../', import.meta.url)

async function source(path) {
  return readFile(new URL(path, root), 'utf8')
}

test('vite build separates heavy runtime dependencies into stable vendor chunks', async () => {
  const config = await source('vite.config.js')
  const shared = await source('vite.shared.mjs')

  assert.match(config, /manualChunks/)
  assert.match(shared, /manualChunks/)
  assert.match(shared, /three/)
  assert.match(shared, /echarts/)
  assert.match(shared, /zrender/)
  assert.match(shared, /xterm/)
  assert.doesNotMatch(config, /chunkSizeWarningLimit/)
})

test('dashboard metric chart imports only the ECharts modules it renders', async () => {
  const chart = await source('src/components/dashboard/MetricChart.vue')

  assert.equal(chart.includes("import * as echarts from 'echarts'"), false)
  assert.equal(chart.includes("from 'echarts/core'"), true)
  assert.equal(chart.includes("from 'echarts/charts'"), true)
  assert.equal(chart.includes("from 'echarts/components'"), true)
  assert.equal(chart.includes("from 'echarts/renderers'"), true)
})

test('decorative Three.js components are loaded asynchronously from entry layouts', async () => {
  const mainLayout = await source('src/layouts/MainLayout.vue')
  const login = await source('src/views/auth/LoginView.vue')

  for (const content of [mainLayout, login]) {
    assert.equal(content.includes('import ParticleWhale from'), false)
    assert.equal(content.includes('import MilkyWay from'), false)
    assert.match(content, /defineAsyncComponent/)
  }
})

test('Element Plus is resolved on demand instead of registered globally', async () => {
  const main = await source('src/main.js')
  const config = await source('vite.config.js')
  const packageJson = await source('package.json')

  assert.equal(main.includes("import ElementPlus from 'element-plus'"), false)
  assert.equal(main.includes("element-plus/dist/index.css"), false)
  assert.equal(main.includes('app.use(ElementPlus)'), false)
  assert.match(config, /Components/)
  assert.match(config, /ElementPlusResolver/)
  assert.equal(config.includes("return 'vendor-element-plus'"), false)
  assert.match(packageJson, /unplugin-vue-components/)
})

test('business code imports Element Plus feedback APIs from component modules', async () => {
  const sources = await Promise.all([
    source('src/components/ai/ChatHistory.vue'),
    source('src/views/skills/SkillCenterView.vue'),
    source('src/views/plugins/PluginCenterView.vue'),
    source('src/views/model/ModelSettingsView.vue'),
    source('src/views/server/ServerListView.vue'),
    source('src/composables/useServerDetail.js')
  ])
  const content = sources.join('\n')

  assert.equal(content.includes("from 'element-plus'"), false)
  assert.match(content, /element-plus\/es\/components\/message-box\/index\.mjs/)
  assert.match(content, /element-plus\/es\/components\/message\/index\.mjs/)
})


test('route bootstrap keeps infrequent layouts out of the application entry', async () => {
  const router = await source('src/router/index.js')

  assert.equal(router.includes("import MainLayout from '../layouts/MainLayout.vue'"), false)
  assert.equal(router.includes("import AdminLayout from '../layouts/AdminLayout.vue'"), false)
  assert.equal(router.includes("import LoginView from '../views/auth/LoginView.vue'"), false)
  assert.equal(router.includes("import WorkInProgressView from '../views/portfolio/WorkInProgressView.vue'"), false)
  assert.equal(router.includes("component: () => import('../layouts/MainLayout.vue')"), true)
  assert.equal(router.includes("component: () => import('../layouts/AdminLayout.vue')"), true)
  assert.equal(router.includes("component: () => import('../views/auth/LoginView.vue')"), true)
})

test('main layout does not eagerly load the tools catalog or inquiry drawer', async () => {
  const layout = await source('src/layouts/MainLayout.vue')

  assert.equal(layout.includes("import SmartInquiryDrawer from '../components/investigation/SmartInquiryDrawer.vue'"), false)
  assert.equal(layout.includes("import { operationToolGroups as toolGroups } from '../views/operations/toolCatalog.js'"), false)
  assert.equal(layout.includes("defineAsyncComponent(() => import('../components/investigation/SmartInquiryDrawer.vue'))"), true)
  assert.equal(layout.includes("import('../views/operations/toolCatalog.js')"), true)
})

test('Three.js visual modules use tree-shakeable named imports', async () => {
  const whale = await source('src/components/common/ParticleWhale.vue')
  const galaxy = await source('src/components/ui/milky-way-scene.js')

  for (const content of [whale, galaxy]) {
    assert.equal(content.includes("import * as THREE from 'three'"), false)
    assert.match(content, /from 'three'/)
  }
})

test('chat message list renders a bounded window instead of the full history', async () => {
  const panel = await source('src/components/ai/AiChatPanel.vue')

  assert.equal(panel.includes('v-for="message in messages"'), false)
  assert.match(panel, /v-for="message in visibleMessages"/)
  assert.match(panel, /slice\(-visibleCount\.value\)/)
  assert.match(panel, /MESSAGE_BATCH/)
})

test('ECharts and the knowledge catalog stay behind lazy route boundaries', async () => {
  const router = await source('src/router/index.js')
  const main = await source('src/main.js')
  const mainLayout = await source('src/layouts/MainLayout.vue')

  assert.match(router, /component: \(\) => import\('\.\.\/views\/dashboard\/DashboardView\.vue'\)/)
  assert.match(router, /component: \(\) => import\('\.\.\/views\/model\/ModelAnalyticsView\.vue'\)/)
  assert.match(router, /component: \(\) => import\('\.\.\/views\/knowledge\/KnowledgeView\.vue'\)/)
  assert.match(router, /component: \(\) => import\('\.\.\/views\/knowledge\/QuizView\.vue'\)/)
  for (const content of [main, mainLayout]) {
    assert.equal(content.includes('echarts'), false)
    assert.equal(content.includes('knowledgeCatalog'), false)
  }
})


test('non-home surfaces use Canvas fallbacks and keep Three.js on the dashboard', async () => {
  const mainLayout = await source('src/layouts/MainLayout.vue')
  const login = await source('src/views/auth/LoginView.vue')
  const canvasWhale = await source('src/components/common/CanvasParticleWhale.vue')
  const ambientField = await source('src/components/common/CanvasAmbientField.vue')
  const theme = await source('src/components/common/canvasTheme.js')

  assert.match(mainLayout, /ParticleWhale v-if="showEnhancedHomeVisuals"/)
  assert.match(mainLayout, /CanvasParticleWhale v-if="!showEnhancedHomeVisuals && !isConnectionWorkspace"/)
  assert.ok(mainLayout.includes('\u9009\u62e9\u89c6\u89c9\u6a21\u5f0f'))
  assert.match(mainLayout, /isLightweightVisualMode/)
  assert.match(mainLayout, /route.name === 'Dashboard' && !isLightweightVisualMode.value/)
  assert.equal(login.includes("import('../../components/common/ParticleWhale.vue')"), false)
  assert.equal(login.includes("import('../../components/ui/milky-way.vue')"), false)
  assert.match(login, /CanvasParticleWhale/)
  assert.match(login, /CanvasAmbientField/)
  for (const content of [canvasWhale, ambientField]) {
    assert.equal(content.includes("from 'three'"), false)
    assert.match(content, /readCanvasPalette/)
  }
  assert.match(theme, /MutationObserver/)
  assert.match(theme, /data-theme/)
})
