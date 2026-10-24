import assert from 'node:assert/strict'
import test from 'node:test'
import { createPinia, setActivePinia } from 'pinia'

const values = new Map()
globalThis.localStorage = {
  getItem: key => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
  removeItem: key => values.delete(key)
}

const { useAppStore } = await import('../src/stores/app.js')

test('opens the active parent group for a deep-linked route and persists it', () => {
  values.clear()
  setActivePinia(createPinia())
  const store = useAppStore()

  store.setRouteNavigation('ExecutionTrace')

  assert.deepEqual(store.expandedPersonalSystemGroups, ['agent'])
  assert.deepEqual(JSON.parse(values.get('smartops_personal_system_navigation')), ['agent'])
})

test('keeps mobile navigation separate from the desktop collapsed sidebar state', () => {
  values.clear()
  setActivePinia(createPinia())
  const store = useAppStore()

  store.openMobileNavigation()

  assert.equal(store.mobileNavigationOpen, true)
  assert.equal(store.sidebarCollapsed, false)
  store.closeMobileNavigation()
  assert.equal(store.mobileNavigationOpen, false)
})

test('expands and collapses the desktop sidebar explicitly and persists the choice', () => {
  values.clear()
  setActivePinia(createPinia())
  const store = useAppStore()

  store.collapseSidebar()
  assert.equal(store.sidebarCollapsed, true)
  assert.equal(JSON.parse(values.get('smartops_sidebar_collapsed')), true)

  store.expandSidebar()
  assert.equal(store.sidebarCollapsed, false)
  assert.equal(JSON.parse(values.get('smartops_sidebar_collapsed')), false)
})

test('persists the current workspace context and ignores unknown workspace ids', () => {
  values.clear()
  setActivePinia(createPinia())
  const store = useAppStore()

  assert.equal(store.currentWorkspaceId, 'default-ops')
  store.setCurrentWorkspace('unknown')
  assert.equal(store.currentWorkspaceId, 'default-ops')
  store.setCurrentWorkspace('default-ops')
  assert.equal(JSON.parse(values.get('smartops_current_workspace:anonymous')), 'default-ops')
})
