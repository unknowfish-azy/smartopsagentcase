/**
 * 厘米秀式互动手感（纯逻辑，不依赖 DOM，可被 node:test 直测）。
 *
 * 蒸馏自 QQ 厘米秀的互动范式——只取交互设计、不碰任何腾讯资产：
 *  - createClickClassifier：单击 / 双击 / 连击（戳）三态分级；
 *  - createIdleScheduler：挂机彩蛋（静默伸懒腰 → 打瞌睡 → 循环），交互即唤醒。
 *
 * 两个工厂都接受可注入的 schedule/cancel（默认 setTimeout/clearTimeout），
 * 测试用假时钟推进即可，不产生真实定时器。
 */

/** 单击/双击/连击共用的判定窗：窗内再点一次算连击，窗到点按累计次数结算 */
export const CLICK_WINDOW_MS = 320
/** 长按判定：按住超过该时长未移动 = 疑惑歪头 */
export const LONG_PRESS_MS = 600
/** 挂机第一段：静默多久后伸懒腰 */
export const IDLE_STRETCH_MS = 90000
/** 挂机第二段及循环间隔：再静默多久后打瞌睡（之后循环打瞌睡） */
export const IDLE_SLEEP_MS = 90000
/** 连击多少次判定为"戳" */
export const POKE_THRESHOLD = 4

/**
 * 点击分级状态机。
 * 单击被延迟一个判定窗触发（厘米秀同款手感的前提）：窗内第 2 次点击改判双击，
 * 累计 ≥ pokeThreshold 次改判为"戳"。窗到点按当次累计结算并清零。
 *
 * @param {{onSingle?: () => void, onDouble?: () => void, onPoke?: (count: number) => void}} handlers
 * @param {{windowMs?: number, pokeThreshold?: number, schedule?: Function, cancel?: Function}} [options]
 */
export function createClickClassifier(handlers, {
  windowMs = CLICK_WINDOW_MS,
  pokeThreshold = POKE_THRESHOLD,
  schedule = (fn, ms) => setTimeout(fn, ms),
  cancel = (id) => clearTimeout(id)
} = {}) {
  const { onSingle, onDouble, onPoke } = handlers
  let count = 0
  let timer = null

  function flush() {
    timer = null
    const n = count
    count = 0
    if (n >= pokeThreshold) onPoke?.(n)
    else if (n === 2) onDouble?.()
    else onSingle?.() // 单击与 3 连击失手都回落为单击反馈，不出现"点了没反应"
  }

  return {
    /** 每次点击喂一次；判定窗内连续喂会重置窗口 */
    feed() {
      count += 1
      if (timer !== null) cancel(timer)
      timer = schedule(flush, windowMs)
    },
    /** 立刻结算当前累计（如语音/播报即将接管时，防止回调迟到抢动作） */
    flushNow() {
      if (timer !== null) {
        cancel(timer)
        flush()
      }
    },
    /** 丢弃累计并撤销窗口（卸载/休眠时调用，不触发回调） */
    dispose() {
      if (timer !== null) cancel(timer)
      timer = null
      count = 0
    }
  }
}

/**
 * 挂机彩蛋调度器：reset 后静默 stretchMs 触发 onStretch（stage 1），
 * 再静默 sleepMs 触发 onSleep（stage 2），之后每 sleepMs 循环打瞌睡。
 * 回调是否真的播动作由组件侧判断（语音中/收起/隐藏/降级时跳过），
 * 调度器只负责时间轴与阶段标记。stage 供"唤醒致意"读取。
 *
 * @param {{onStretch?: () => void, onSleep?: () => void}} handlers
 * @param {{stretchMs?: number, sleepMs?: number, schedule?: Function, cancel?: Function}} [options]
 */
export function createIdleScheduler(handlers, {
  stretchMs = IDLE_STRETCH_MS,
  sleepMs = IDLE_SLEEP_MS,
  schedule = (fn, ms) => setTimeout(fn, ms),
  cancel = (id) => clearTimeout(id)
} = {}) {
  const { onStretch, onSleep } = handlers
  let stage = 0 // 0 活跃 / 1 已伸过懒腰 / 2 打瞌睡中
  let timer = null

  function arm(nextStage, ms, fire) {
    stage = nextStage
    timer = schedule(() => {
      timer = null
      fire?.()
      // 活跃段走完 → 下一站打瞌睡段；瞌睡段自循环（保持 stage 2）
      arm(nextStage >= 1 ? 2 : 1, sleepMs, onSleep)
    }, ms)
  }

  return {
    /** 任意交互/播报开始时调用：从当前阶段回到活跃并重新计时 */
    reset() {
      if (timer !== null) cancel(timer)
      timer = null
      arm(0, stretchMs, onStretch)
    },
    /** 停止调度（收起/卸载时调用），stage 归零 */
    stop() {
      if (timer !== null) cancel(timer)
      timer = null
      stage = 0
    },
    get stage() {
      return stage
    }
  }
}
