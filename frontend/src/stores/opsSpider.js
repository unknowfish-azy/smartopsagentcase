import { defineStore } from 'pinia'
import { clampOpsSpiderPosition, cornerPosition } from '../components/common/opsSpiderState.js'

const STORAGE_KEY = 'smartops_ops_spider_position'

function readPosition() {
  try {
    const value = globalThis.localStorage?.getItem(STORAGE_KEY)
    const parsed = value ? JSON.parse(value) : null
    return Number.isFinite(parsed?.x) && Number.isFinite(parsed?.y) ? parsed : null
  } catch {
    return null
  }
}

function savePosition(position) {
  try { globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(position)) } catch { /* Storage is optional. */ }
}

export const useOpsSpiderStore = defineStore('ops-spider', {
  state: () => ({
    position: readPosition(),
    hidden: false,
    menuOpen: false,
    contextOpen: false,
    sleeping: false,
    lastActivityAt: Date.now()
  }),
  actions: {
    move(position, viewport) {
      this.position = clampOpsSpiderPosition({ ...position, ...viewport })
    },
    setPosition(position, viewport) {
      this.position = clampOpsSpiderPosition({ ...position, ...viewport })
      savePosition(this.position)
    },
    setCorner(corner, viewport) {
      this.position = cornerPosition(corner, viewport)
      savePosition(this.position)
    },
    markActive() { this.sleeping = false; this.lastActivityAt = Date.now() },
    sleep() { this.sleeping = true; this.menuOpen = false; this.contextOpen = false },
    wake() { this.markActive() },
    toggleMenu() { this.menuOpen = !this.menuOpen; this.contextOpen = false },
    toggleContext() { this.contextOpen = !this.contextOpen; this.menuOpen = false },
    closeMenus() { this.menuOpen = false; this.contextOpen = false },
    hide() { this.hidden = true; this.closeMenus() },
    show() { this.hidden = false; this.markActive() }
  }
})
