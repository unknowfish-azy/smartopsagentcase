import { defineStore } from 'pinia'

/** 桌宠浮窗几何常量：展开 220×300 的 3:4 画布加内边距，收起为一颗 44px 小球 */
export const PERSONA_PET_SIZE = { width: 232, height: 348, collapsed: 44 }
export const PERSONA_PET_INSET = 20

const STORAGE_KEY = 'smartops_persona_pet'

function readPersisted() {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY)
    const value = raw ? JSON.parse(raw) : null
    return value && typeof value === 'object' ? value : {}
  } catch {
    return {}
  }
}

function savePersisted(patch) {
  try {
    const next = { ...readPersisted(), ...patch }
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // Storage 可选（隐私模式），静默降级为不记忆
  }
}

/**
 * 把浮窗位置钳制在视口内：拖拽出界、窗口缩小后都要拉回来。
 * 纯函数导出，便于单测。
 */
export function clampPersonaPetPosition(
  { x, y, collapsed = false },
  { viewportWidth, viewportHeight }
) {
  const width = collapsed ? PERSONA_PET_SIZE.collapsed : PERSONA_PET_SIZE.width
  const height = collapsed ? PERSONA_PET_SIZE.collapsed : PERSONA_PET_SIZE.height
  const maxX = Math.max(PERSONA_PET_INSET, viewportWidth - PERSONA_PET_INSET - width)
  const maxY = Math.max(PERSONA_PET_INSET, viewportHeight - PERSONA_PET_INSET - height)
  return {
    x: Math.min(maxX, Math.max(PERSONA_PET_INSET, Math.round(x))),
    y: Math.min(maxY, Math.max(PERSONA_PET_INSET, Math.round(y)))
  }
}

function defaultPosition() {
  return clampPersonaPetPosition(
    { x: globalThis.innerWidth ? globalThis.innerWidth - PERSONA_PET_INSET - PERSONA_PET_SIZE.width : 1200, y: 320 },
    { viewportWidth: globalThis.innerWidth ?? 1440, viewportHeight: globalThis.innerHeight ?? 900 }
  )
}

/**
 * 数字人桌宠的形态状态：开关、收起、位置。
 * 只管形态，不碰 WebGL 与口型（那些归 PersonaPet.vue / AgentPersona.vue）。
 * 与鲸的互斥在 MainLayout 里由 enabled && !collapsed 推导，不在这里耦合鲸。
 */
export const usePersonaPetStore = defineStore('persona-pet', {
  state: () => {
    const persisted = readPersisted()
    return {
      enabled: persisted.enabled === true,
      collapsed: persisted.collapsed === true,
      position: persisted.position
        ? clampPersonaPetPosition(
            { ...persisted.position, collapsed: persisted.collapsed === true },
            { viewportWidth: globalThis.innerWidth ?? 1440, viewportHeight: globalThis.innerHeight ?? 900 }
          )
        : defaultPosition()
    }
  },
  actions: {
    enable() {
      this.enabled = true
      savePersisted({ enabled: true })
    },
    disable() {
      this.enabled = false
      savePersisted({ enabled: false })
    },
    toggle() {
      this.enabled ? this.disable() : this.enable()
    },
    /** 收起/展开改变浮窗尺寸，需要调用方传入当前视口做重新钳制 */
    setCollapsed(value, viewport) {
      this.collapsed = value
      savePersisted({ collapsed: value })
      if (viewport) {
        this.position = clampPersonaPetPosition(
          { ...this.position, collapsed: value },
          viewport
        )
        savePersisted({ position: this.position })
      }
    },
    setPosition(position, viewport) {
      this.position = clampPersonaPetPosition({ ...position, collapsed: this.collapsed }, viewport)
      savePersisted({ position: this.position })
    },
    /** 拖拽中只改内存，pointerup 才落盘，避免每帧写 localStorage */
    moveBy(deltaX, deltaY, viewport) {
      this.position = clampPersonaPetPosition(
        { x: this.position.x + deltaX, y: this.position.y + deltaY, collapsed: this.collapsed },
        viewport
      )
    }
  }
})
