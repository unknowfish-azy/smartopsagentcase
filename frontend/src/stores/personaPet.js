import { defineStore } from 'pinia'

/** 桌宠浮窗几何常量：展开 232×348 的 3:4 画布加内边距，收起为一颗 44px 小球 */
export const PERSONA_PET_SIZE = { width: 232, height: 348, collapsed: 44 }
/**
 * 缩放档位（2026-11-16 新增）：用户可循环切换 悬浮窗大小。
 * 档位改的是真实布局尺寸（canvas 由 ResizeObserver 跟随重绘），不用 CSS scale 避免模糊。
 */
export const PERSONA_PET_SIZES = Object.freeze({
  compact: Object.freeze({ width: 200, height: 300 }),
  regular: Object.freeze({ width: 232, height: 348 }),
  large: Object.freeze({ width: 288, height: 432 })
})
export const PERSONA_PET_SIZE_ORDER = ['compact', 'regular', 'large']
export const PERSONA_PET_INSET = 20
/** 展开态宽高比 2:3（PERSONA_PET_SIZES 各档均满足），高度驱动收敛 */
export const PERSONA_PET_ASPECT = 2 / 3
/** 各档高度占视口高的收敛上限（视口更高时用设计基准，不放大） */
export const PERSONA_PET_VH_RATIO = Object.freeze({
  compact: 0.34,
  regular: 0.4,
  large: 0.5
})
/** 可读性下限：再小气泡与按钮挤不下；与宽度下限 150 自洽（150 × 3/2 = 225） */
export const PERSONA_PET_MIN_HEIGHT = 225
/** 超窄屏宽度收敛：不超过视口宽 36%，下限 150 防彻底不可用 */
export const PERSONA_PET_MAX_VW_RATIO = 0.36
export const PERSONA_PET_MIN_WIDTH = 150
/** 自由拖拽的高度上限（占视口高）：比 large 档的 0.5 再放宽一档，仍不铺满屏幕 */
export const PERSONA_PET_MAX_VH_RATIO = 0.6

/**
 * 用户拖出来的自定义尺寸（2026-11-17）：连续像素值，不再吸附三档。
 * 只收高度、宽度按 2:3 回算——画布是竖屏全身像，改宽高比会把形象拉扁；
 * 上下限与档位共用（不窄于 150、不高于视口 60%），窄屏下仍然收敛而不是溢出。
 */
export function clampCustomPetSize({ height }, { viewportWidth, viewportHeight }) {
  const maxHeight = Math.max(PERSONA_PET_MIN_HEIGHT, Math.round(viewportHeight * PERSONA_PET_MAX_VH_RATIO))
  const maxWidth = Math.max(PERSONA_PET_MIN_WIDTH, Math.round(viewportWidth * PERSONA_PET_MAX_VW_RATIO))
  let nextHeight = Math.min(maxHeight, Math.max(PERSONA_PET_MIN_HEIGHT, Math.round(Number(height) || 0)))
  let width = Math.round(nextHeight * PERSONA_PET_ASPECT)
  if (width > maxWidth) {
    width = maxWidth
    nextHeight = Math.round(width / PERSONA_PET_ASPECT)
  }
  return { width, height: nextHeight }
}

/**
 * 视口自适应尺寸（2026-11-16 新增）：小屏自动收敛、大屏保持设计基准。
 * 纯函数导出，便于单测。1200×900 及以上视口三档均返回设计基准（既有行为不变）。
 * 传入 customSize 时优先用用户拖出来的尺寸（同样受视口上下限约束）。
 */
export function resolvePetSize(sizeMode, viewport, customSize = null) {
  if (customSize) return clampCustomPetSize(customSize, viewport)
  const size = PERSONA_PET_SIZES[sizeMode] ?? PERSONA_PET_SIZE
  const vhRatio = PERSONA_PET_VH_RATIO[sizeMode] ?? 0.4
  let height = Math.min(size.height, Math.max(PERSONA_PET_MIN_HEIGHT, Math.round(viewport.viewportHeight * vhRatio)))
  let width = Math.round(height * PERSONA_PET_ASPECT)
  const maxWidth = Math.max(PERSONA_PET_MIN_WIDTH, Math.round(viewport.viewportWidth * PERSONA_PET_MAX_VW_RATIO))
  if (width > maxWidth) {
    width = maxWidth
    height = Math.round(width / PERSONA_PET_ASPECT)
  }
  return { width, height }
}

/**
 * 自定义尺寸回到三档时的落点（2026-11-17）：拖过之后点一下手柄继续切档，
 * 要从「当前实际高度」的最近档位往后走，否则会突然跳到毫不相关的大小。
 */
export function nearestPetSizeMode(targetHeight, { viewportWidth, viewportHeight }) {
  let nearest = PERSONA_PET_SIZE_ORDER[0]
  let distance = Infinity
  for (const mode of PERSONA_PET_SIZE_ORDER) {
    const { height } = resolvePetSize(mode, { viewportWidth, viewportHeight })
    const current = Math.abs(height - targetHeight)
    if (current < distance) {
      distance = current
      nearest = mode
    }
  }
  return nearest
}

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
 * 纯函数导出，便于单测。第三参 sizeMode 决定按哪档尺寸钳制（默认 regular），
 * 第四参 customSize 优先（用户拖出来的尺寸）。
 */
export function clampPersonaPetPosition(
  { x, y, collapsed = false },
  { viewportWidth, viewportHeight },
  sizeMode = 'regular',
  customSize = null
) {
  // 展开尺寸随视口自适应收敛（小屏防溢出；大屏等于设计基准）
  const size = resolvePetSize(sizeMode, { viewportWidth, viewportHeight }, customSize)
  const width = collapsed ? PERSONA_PET_SIZE.collapsed : size.width
  const height = collapsed ? PERSONA_PET_SIZE.collapsed : size.height
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

/** 持久化的自定义尺寸只在数值合法时采纳，并按当前视口重新钳制（换显示器后不会溢出） */
function readCustomSize(raw, viewport) {
  if (!raw || typeof raw !== 'object') return null
  const height = Number(raw.height)
  if (!Number.isFinite(height) || height <= 0) return null
  return clampCustomPetSize({ height }, viewport)
}

/**
 * 数字人桌宠的形态状态：开关、收起、位置。
 * 只管形态，不碰 WebGL 与口型（那些归 PersonaPet.vue / AgentPersona.vue）。
 * 与鲸的互斥在 MainLayout 里由 enabled && !collapsed 推导，不在这里耦合鲸。
 */
export const usePersonaPetStore = defineStore('persona-pet', {
  state: () => {
    const persisted = readPersisted()
    const viewport = {
      viewportWidth: globalThis.innerWidth ?? 1440,
      viewportHeight: globalThis.innerHeight ?? 900
    }
    const customSize = readCustomSize(persisted.customSize, viewport)
    return {
      enabled: persisted.enabled === true,
      collapsed: persisted.collapsed === true,
      /**
       * 神经语音不可用时是否回落浏览器 speechSynthesis 机械音。
       * 默认 false：宁可无声也不跳音色（F5 甜妹音与浏览器音色反差太大，
       * 突然换声比短暂没声音更违和）；开启后按旧行为回落。
       */
      speechFallback: persisted.speechFallback === true,
      sizeMode: PERSONA_PET_SIZES[persisted.sizeMode] ? persisted.sizeMode : 'regular',
      /** 用户拖出来的连续尺寸；null = 用档位。切档会清空它 */
      customSize,
      position: persisted.position
        ? clampPersonaPetPosition(
            { ...persisted.position, collapsed: persisted.collapsed === true },
            viewport,
            persisted.sizeMode,
            customSize
          )
        : defaultPosition()
    }
  },
  getters: {
    /** 当前展开尺寸：拖过就是自定义尺寸，否则是档位（悬浮窗 inline style 用） */
    activeSize(state) {
      return state.customSize ?? PERSONA_PET_SIZES[state.sizeMode] ?? PERSONA_PET_SIZE
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
    /** 浏览器语音兜底开关：false=神经语音不可用时保持无声，true=回落浏览器音色 */
    setSpeechFallback(value) {
      this.speechFallback = value === true
      savePersisted({ speechFallback: this.speechFallback })
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
          viewport,
          this.sizeMode,
          this.customSize
        )
        savePersisted({ position: this.position })
      }
    },
    /** 缩放档位切换：清掉自定义尺寸，重新按档位钳制并落盘 */
    setSizeMode(mode, viewport) {
      if (!PERSONA_PET_SIZES[mode]) return
      this.sizeMode = mode
      this.customSize = null
      savePersisted({ sizeMode: mode, customSize: null })
      if (viewport && !this.collapsed) {
        this.position = clampPersonaPetPosition(
          { ...this.position, collapsed: false },
          viewport,
          mode,
          null
        )
        savePersisted({ position: this.position })
      }
    },
    /**
     * 拖手柄时的尺寸更新：只改内存并同步钳制位置，避免每帧写 localStorage。
     * 落盘由 pointerup 调 setCustomSize 完成。
     */
    applyCustomSize(size, viewport) {
      if (this.collapsed) return
      this.customSize = clampCustomPetSize(size, viewport)
      this.position = clampPersonaPetPosition(
        { ...this.position, collapsed: false },
        viewport,
        this.sizeMode,
        this.customSize
      )
    },
    /** 拖拽结束：把最终尺寸与位置一起落盘 */
    setCustomSize(size, viewport) {
      this.applyCustomSize(size, viewport)
      savePersisted({ customSize: this.customSize, position: this.position })
    },
    /** 循环切换 compact → regular → large → compact（从自定义尺寸出发时先落到最近档位） */
    cycleSize(viewport) {
      const base = this.customSize
        ? nearestPetSizeMode(this.customSize.height, viewport)
        : this.sizeMode
      const index = PERSONA_PET_SIZE_ORDER.indexOf(base)
      const next = PERSONA_PET_SIZE_ORDER[(index + 1) % PERSONA_PET_SIZE_ORDER.length]
      this.setSizeMode(next, viewport)
      return next
    },
    setPosition(position, viewport) {
      this.position = clampPersonaPetPosition(
        { ...position, collapsed: this.collapsed },
        viewport,
        this.sizeMode,
        this.customSize
      )
      savePersisted({ position: this.position })
    },
    /** 拖拽中只改内存，pointerup 才落盘，避免每帧写 localStorage */
    moveBy(deltaX, deltaY, viewport) {
      this.position = clampPersonaPetPosition(
        { x: this.position.x + deltaX, y: this.position.y + deltaY, collapsed: this.collapsed },
        viewport,
        this.sizeMode,
        this.customSize
      )
    }
  }
})
