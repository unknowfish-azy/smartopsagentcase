import {
  EVENT_CODE,
  ElIcon,
  TypeComponents,
  TypeComponentsMap,
  ValidateComponentsMap,
  addClass,
  addUnit,
  buildProps,
  clamp_default,
  componentSizes,
  computedEager,
  debugWarn,
  definePropType,
  focusElement,
  fromPairs_default,
  getEventCode,
  getStyle,
  hasClass,
  iconPropType,
  isClient,
  isElement,
  isFirefox,
  isFocusable,
  isNil_default,
  isNumber,
  isUndefined,
  mutable,
  obtainAllFocusableElements,
  pick_default,
  removeClass,
  throwError,
  useEventListener,
  useGetDerivedNamespace,
  useGlobalComponentSettings,
  useGlobalConfig,
  useGlobalSize,
  useLocale,
  useNamespace,
  useResizeObserver,
  useSizeProp,
  withInstall,
  withNoopInstall
} from "./chunk-2IC2EAVI.js";
import {
  circle_close_default,
  hide_default,
  loading_default,
  view_default
} from "./chunk-6YEUBRXX.js";
import {
  Fragment,
  NOOP,
  Text,
  Transition,
  computed,
  createBaseVNode,
  createBlock,
  createCommentVNode,
  createElementBlock,
  createTextVNode,
  createVNode,
  defineComponent,
  getCurrentInstance,
  h,
  hasOwn,
  inject,
  isFunction,
  isObject,
  isRef,
  isString,
  isVNode,
  markRaw,
  mergeProps,
  nextTick,
  normalizeClass,
  normalizeStyle,
  onBeforeUnmount,
  onMounted,
  onScopeDispose,
  onUnmounted,
  openBlock,
  provide,
  reactive,
  ref,
  render,
  renderSlot,
  resolveComponent,
  resolveDynamicComponent,
  shallowRef,
  toDisplayString,
  toRef,
  toRefs,
  unref,
  useAttrs,
  useSlots,
  vShow,
  watch,
  watchEffect,
  withCtx,
  withDirectives,
  withKeys,
  withModifiers
} from "./chunk-TC3D7C7U.js";
import "./chunk-AXQFWXYZ.js";

// node_modules/element-plus/es/_virtual/_plugin-vue_export-helper.mjs
var _plugin_vue_export_helper_default = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) target[key] = val;
  return target;
};

// node_modules/element-plus/es/utils/vue/validator.mjs
var isValidComponentSize = (val) => ["", ...componentSizes].includes(val);

// node_modules/element-plus/es/directives/trap-focus/index.mjs
var FOCUSABLE_CHILDREN = "_trap-focus-children";
var FOCUS_STACK = [];
var FOCUS_HANDLER = (e) => {
  if (FOCUS_STACK.length === 0) return;
  const code = getEventCode(e);
  const focusableElement = FOCUS_STACK[FOCUS_STACK.length - 1][FOCUSABLE_CHILDREN];
  if (focusableElement.length > 0 && code === EVENT_CODE.tab) {
    if (focusableElement.length === 1) {
      e.preventDefault();
      if (document.activeElement !== focusableElement[0]) focusableElement[0].focus();
      return;
    }
    const goingBackward = e.shiftKey;
    const isFirst = e.target === focusableElement[0];
    const isLast = e.target === focusableElement[focusableElement.length - 1];
    if (isFirst && goingBackward) {
      e.preventDefault();
      focusableElement[focusableElement.length - 1].focus();
    }
    if (isLast && !goingBackward) {
      e.preventDefault();
      focusableElement[0].focus();
    }
  }
};
var TrapFocus = {
  beforeMount(el) {
    el[FOCUSABLE_CHILDREN] = obtainAllFocusableElements(el);
    FOCUS_STACK.push(el);
    if (FOCUS_STACK.length <= 1) document.addEventListener("keydown", FOCUS_HANDLER);
  },
  updated(el) {
    nextTick(() => {
      el[FOCUSABLE_CHILDREN] = obtainAllFocusableElements(el);
    });
  },
  unmounted() {
    FOCUS_STACK.shift();
    if (FOCUS_STACK.length === 0) document.removeEventListener("keydown", FOCUS_HANDLER);
  }
};

// node_modules/element-plus/es/hooks/use-draggable/index.mjs
var useDraggable = (targetRef, dragRef, draggable, overflow) => {
  const transform = {
    offsetX: 0,
    offsetY: 0
  };
  const isDragging = ref(false);
  const adjustPosition = (moveX, moveY) => {
    if (targetRef.value) {
      const { offsetX, offsetY } = transform;
      const targetRect = targetRef.value.getBoundingClientRect();
      const targetLeft = Math.max(targetRect.left, 0);
      const targetTop = Math.max(targetRect.top, 0);
      const targetWidth = targetRect.width;
      const targetHeight = targetRect.height;
      const clientWidth = document.documentElement.clientWidth;
      const clientHeight = document.documentElement.clientHeight;
      const minLeft = -targetLeft + offsetX;
      const minTop = -targetTop + offsetY;
      const maxLeft = clientWidth - targetLeft - targetWidth + offsetX;
      const maxTop = clientHeight - targetTop - (targetHeight < clientHeight ? targetHeight : 0) + offsetY;
      if (!overflow?.value) {
        moveX = clamp_default(moveX, minLeft, maxLeft);
        moveY = clamp_default(moveY, minTop, maxTop);
      }
      transform.offsetX = moveX;
      transform.offsetY = moveY;
      targetRef.value.style.transform = `translate(${addUnit(moveX)}, ${addUnit(moveY)})`;
    }
  };
  const onMousedown = (e) => {
    const downX = e.clientX;
    const downY = e.clientY;
    const { offsetX, offsetY } = transform;
    const onMousemove = (e2) => {
      if (!isDragging.value) isDragging.value = true;
      adjustPosition(offsetX + e2.clientX - downX, offsetY + e2.clientY - downY);
    };
    const onMouseup = () => {
      isDragging.value = false;
      document.removeEventListener("mousemove", onMousemove);
      document.removeEventListener("mouseup", onMouseup);
    };
    document.addEventListener("mousemove", onMousemove);
    document.addEventListener("mouseup", onMouseup);
  };
  const onDraggable = () => {
    if (dragRef.value && targetRef.value) {
      dragRef.value.addEventListener("mousedown", onMousedown);
      window.addEventListener("resize", updatePosition);
    }
  };
  const offDraggable = () => {
    if (dragRef.value && targetRef.value) {
      dragRef.value.removeEventListener("mousedown", onMousedown);
      window.removeEventListener("resize", updatePosition);
    }
  };
  const resetPosition = () => {
    transform.offsetX = 0;
    transform.offsetY = 0;
    if (targetRef.value) targetRef.value.style.transform = "";
  };
  const updatePosition = () => {
    const { offsetX, offsetY } = transform;
    adjustPosition(offsetX, offsetY);
  };
  onMounted(() => {
    watchEffect(() => {
      if (draggable.value) onDraggable();
      else offDraggable();
    });
  });
  onBeforeUnmount(() => {
    offDraggable();
  });
  return {
    isDragging,
    resetPosition,
    updatePosition
  };
};

// node_modules/element-plus/es/utils/raf.mjs
var rAF = (fn) => isClient ? window.requestAnimationFrame(fn) : setTimeout(fn, 16);
var cAF = (handle) => isClient ? window.cancelAnimationFrame(handle) : clearTimeout(handle);

// node_modules/element-plus/es/utils/dom/scroll.mjs
var scrollBarWidth;
var getScrollBarWidth = (namespace) => {
  if (!isClient) return 0;
  if (scrollBarWidth !== void 0) return scrollBarWidth;
  const outer = document.createElement("div");
  outer.className = `${namespace}-scrollbar__wrap`;
  outer.style.visibility = "hidden";
  outer.style.width = "100px";
  outer.style.position = "absolute";
  outer.style.top = "-9999px";
  document.body.appendChild(outer);
  const widthNoScroll = outer.offsetWidth;
  outer.style.overflow = "scroll";
  const inner = document.createElement("div");
  inner.style.width = "100%";
  outer.appendChild(inner);
  const widthWithScroll = inner.offsetWidth;
  outer.parentNode?.removeChild(outer);
  scrollBarWidth = widthNoScroll - widthWithScroll;
  return scrollBarWidth;
};

// node_modules/element-plus/es/hooks/use-lockscreen/index.mjs
var useLockscreen = (trigger, options = {}) => {
  if (!isRef(trigger)) throwError("[useLockscreen]", "You need to pass a ref param to this function");
  const ns = options.ns || useNamespace("popup");
  const hiddenCls = computed(() => ns.bm("parent", "hidden"));
  let scrollBarWidth2 = 0;
  let withoutHiddenClass = false;
  let bodyWidth = "0";
  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    setTimeout(() => {
      if (typeof document === "undefined") return;
      if (withoutHiddenClass && document) {
        document.body.style.width = bodyWidth;
        removeClass(document.body, hiddenCls.value);
      }
    }, 200);
  };
  watch(trigger, (val) => {
    if (!val) {
      cleanup();
      return;
    }
    cleaned = false;
    withoutHiddenClass = !hasClass(document.body, hiddenCls.value);
    if (withoutHiddenClass) {
      bodyWidth = document.body.style.width;
      addClass(document.body, hiddenCls.value);
    }
    scrollBarWidth2 = getScrollBarWidth(ns.namespace.value);
    const bodyHasOverflow = document.documentElement.clientHeight < document.body.scrollHeight;
    const bodyOverflowY = getStyle(document.body, "overflowY");
    if (scrollBarWidth2 > 0 && (bodyHasOverflow || bodyOverflowY === "scroll") && withoutHiddenClass) document.body.style.width = `calc(100% - ${scrollBarWidth2}px)`;
  });
  onScopeDispose(() => cleanup());
};

// node_modules/element-plus/es/hooks/use-same-target/index.mjs
var useSameTarget = (handleClick) => {
  if (!handleClick) return {
    onClick: NOOP,
    onMousedown: NOOP,
    onMouseup: NOOP
  };
  let mousedownTarget = false;
  let mouseupTarget = false;
  const onClick = (e) => {
    if (mousedownTarget && mouseupTarget) handleClick(e);
    mousedownTarget = mouseupTarget = false;
  };
  const onMousedown = (e) => {
    mousedownTarget = e.target === e.currentTarget;
  };
  const onMouseup = (e) => {
    mouseupTarget = e.target === e.currentTarget;
  };
  return {
    onClick,
    onMousedown,
    onMouseup
  };
};

// node_modules/element-plus/es/hooks/use-id/index.mjs
var defaultIdInjection = {
  prefix: Math.floor(Math.random() * 1e4),
  current: 0
};
var ID_INJECTION_KEY = /* @__PURE__ */ Symbol("elIdInjection");
var useIdInjection = () => {
  return getCurrentInstance() ? inject(ID_INJECTION_KEY, defaultIdInjection) : defaultIdInjection;
};
var useId = (deterministicId) => {
  const idInjection = useIdInjection();
  if (!isClient && idInjection === defaultIdInjection) debugWarn("IdInjection", `Looks like you are using server rendering, you must provide a id provider to ensure the hydration process to be succeed
usage: app.provide(ID_INJECTION_KEY, {
  prefix: number,
  current: number,
})`);
  const namespace = useGetDerivedNamespace();
  return computedEager(() => unref(deterministicId) || `${namespace.value}-id-${idInjection.prefix}-${idInjection.current++}`);
};

// node_modules/element-plus/es/components/focus-trap/src/tokens.mjs
var FOCUS_AFTER_TRAPPED = "focus-trap.focus-after-trapped";
var FOCUS_AFTER_RELEASED = "focus-trap.focus-after-released";
var FOCUSOUT_PREVENTED = "focus-trap.focusout-prevented";
var FOCUS_AFTER_TRAPPED_OPTS = {
  cancelable: true,
  bubbles: false
};
var FOCUSOUT_PREVENTED_OPTS = {
  cancelable: true,
  bubbles: false
};
var ON_TRAP_FOCUS_EVT = "focusAfterTrapped";
var ON_RELEASE_FOCUS_EVT = "focusAfterReleased";
var FOCUS_TRAP_INJECTION_KEY = /* @__PURE__ */ Symbol("elFocusTrap");

// node_modules/element-plus/es/components/focus-trap/src/utils.mjs
var focusReason = ref();
var lastUserFocusTimestamp = ref(0);
var lastAutomatedFocusTimestamp = ref(0);
var focusReasonUserCount = 0;
var obtainAllFocusableElements2 = (element) => {
  const nodes = [];
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_ELEMENT, { acceptNode: (node) => {
    const isHiddenInput = node.tagName === "INPUT" && node.type === "hidden";
    if (node.disabled || node.hidden || isHiddenInput) return NodeFilter.FILTER_SKIP;
    return node.tabIndex >= 0 || node === document.activeElement ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
  } });
  while (walker.nextNode()) nodes.push(walker.currentNode);
  return nodes;
};
var getVisibleElement = (elements, container) => {
  for (const element of elements) if (!isHidden(element, container)) return element;
};
var isHidden = (element, container) => {
  if (getComputedStyle(element).visibility === "hidden") return true;
  while (element) {
    if (container && element === container) return false;
    if (getComputedStyle(element).display === "none") return true;
    element = element.parentElement;
  }
  return false;
};
var getEdges = (container) => {
  const focusable = obtainAllFocusableElements2(container);
  return [getVisibleElement(focusable, container), getVisibleElement(focusable.reverse(), container)];
};
var isSelectable = (element) => {
  return element instanceof HTMLInputElement && "select" in element;
};
var tryFocus = (element, shouldSelect) => {
  if (element) {
    const prevFocusedElement = document.activeElement;
    focusElement(element, { preventScroll: true });
    lastAutomatedFocusTimestamp.value = window.performance.now();
    if (element !== prevFocusedElement && isSelectable(element) && shouldSelect) element.select();
  }
};
function removeFromStack(list, item) {
  const copy = [...list];
  const idx = list.indexOf(item);
  if (idx !== -1) copy.splice(idx, 1);
  return copy;
}
var createFocusableStack = () => {
  let stack = [];
  const push = (layer) => {
    const currentLayer = stack[0];
    if (currentLayer && layer !== currentLayer) currentLayer.pause();
    stack = removeFromStack(stack, layer);
    stack.unshift(layer);
  };
  const remove = (layer) => {
    stack = removeFromStack(stack, layer);
    stack[0]?.resume?.();
  };
  return {
    push,
    remove
  };
};
var focusFirstDescendant = (elements, shouldSelect = false) => {
  const prevFocusedElement = document.activeElement;
  for (const element of elements) {
    tryFocus(element, shouldSelect);
    if (document.activeElement !== prevFocusedElement) return;
  }
};
var focusableStack = createFocusableStack();
var isFocusCausedByUserEvent = () => {
  return lastUserFocusTimestamp.value > lastAutomatedFocusTimestamp.value;
};
var notifyFocusReasonPointer = () => {
  focusReason.value = "pointer";
  lastUserFocusTimestamp.value = window.performance.now();
};
var notifyFocusReasonKeydown = () => {
  focusReason.value = "keyboard";
  lastUserFocusTimestamp.value = window.performance.now();
};
var useFocusReason = () => {
  onMounted(() => {
    if (focusReasonUserCount === 0) {
      document.addEventListener("mousedown", notifyFocusReasonPointer);
      document.addEventListener("touchstart", notifyFocusReasonPointer);
      document.addEventListener("keydown", notifyFocusReasonKeydown);
    }
    focusReasonUserCount++;
  });
  onBeforeUnmount(() => {
    focusReasonUserCount--;
    if (focusReasonUserCount <= 0) {
      document.removeEventListener("mousedown", notifyFocusReasonPointer);
      document.removeEventListener("touchstart", notifyFocusReasonPointer);
      document.removeEventListener("keydown", notifyFocusReasonKeydown);
    }
  });
  return {
    focusReason,
    lastUserFocusTimestamp,
    lastAutomatedFocusTimestamp
  };
};
var createFocusOutPreventedEvent = (detail) => {
  return new CustomEvent(FOCUSOUT_PREVENTED, {
    ...FOCUSOUT_PREVENTED_OPTS,
    detail
  });
};

// node_modules/element-plus/es/hooks/use-escape-keydown/index.mjs
var registeredEscapeHandlers = [];
var cachedHandler = (event) => {
  if (getEventCode(event) === EVENT_CODE.esc) registeredEscapeHandlers.forEach((registeredHandler) => registeredHandler(event));
};
var useEscapeKeydown = (handler) => {
  onMounted(() => {
    if (registeredEscapeHandlers.length === 0) document.addEventListener("keydown", cachedHandler);
    if (isClient) registeredEscapeHandlers.push(handler);
  });
  onBeforeUnmount(() => {
    registeredEscapeHandlers = registeredEscapeHandlers.filter((registeredHandler) => registeredHandler !== handler);
    if (registeredEscapeHandlers.length === 0) {
      if (isClient) document.removeEventListener("keydown", cachedHandler);
    }
  });
};

// node_modules/element-plus/es/components/focus-trap/src/focus-trap.vue_vue_type_script_lang.mjs
var focus_trap_vue_vue_type_script_lang_default = defineComponent({
  name: "ElFocusTrap",
  inheritAttrs: false,
  props: {
    loop: Boolean,
    trapped: Boolean,
    focusTrapEl: Object,
    focusStartEl: {
      type: [Object, String],
      default: "first"
    }
  },
  emits: [
    ON_TRAP_FOCUS_EVT,
    ON_RELEASE_FOCUS_EVT,
    "focusin",
    "focusout",
    "focusout-prevented",
    "release-requested"
  ],
  setup(props, { emit }) {
    const forwardRef = ref();
    let lastFocusBeforeTrapped;
    let lastFocusAfterTrapped;
    const { focusReason: focusReason2 } = useFocusReason();
    useEscapeKeydown((event) => {
      if (props.trapped && !focusLayer.paused) emit("release-requested", event);
    });
    const focusLayer = {
      paused: false,
      pause() {
        this.paused = true;
      },
      resume() {
        this.paused = false;
      }
    };
    const onKeydown = (e) => {
      if (!props.loop && !props.trapped) return;
      if (focusLayer.paused) return;
      const { altKey, ctrlKey, metaKey, currentTarget, shiftKey } = e;
      const { loop } = props;
      const isTabbing = getEventCode(e) === EVENT_CODE.tab && !altKey && !ctrlKey && !metaKey;
      const currentFocusingEl = document.activeElement;
      if (isTabbing && currentFocusingEl) {
        const container = currentTarget;
        const [first, last] = getEdges(container);
        if (!(first && last)) {
          if (currentFocusingEl === container) {
            const focusoutPreventedEvent = createFocusOutPreventedEvent({ focusReason: focusReason2.value });
            emit("focusout-prevented", focusoutPreventedEvent);
            if (!focusoutPreventedEvent.defaultPrevented) e.preventDefault();
          }
        } else if (!shiftKey && currentFocusingEl === last) {
          const focusoutPreventedEvent = createFocusOutPreventedEvent({ focusReason: focusReason2.value });
          emit("focusout-prevented", focusoutPreventedEvent);
          if (!focusoutPreventedEvent.defaultPrevented) {
            e.preventDefault();
            if (loop) tryFocus(first, true);
          }
        } else if (shiftKey && [first, container].includes(currentFocusingEl)) {
          const focusoutPreventedEvent = createFocusOutPreventedEvent({ focusReason: focusReason2.value });
          emit("focusout-prevented", focusoutPreventedEvent);
          if (!focusoutPreventedEvent.defaultPrevented) {
            e.preventDefault();
            if (loop) tryFocus(last, true);
          }
        }
      }
    };
    provide(FOCUS_TRAP_INJECTION_KEY, {
      focusTrapRef: forwardRef,
      onKeydown
    });
    watch(() => props.focusTrapEl, (focusTrapEl) => {
      if (focusTrapEl) forwardRef.value = focusTrapEl;
    }, { immediate: true });
    watch([forwardRef], ([forwardRef2], [oldForwardRef]) => {
      if (forwardRef2) {
        forwardRef2.addEventListener("keydown", onKeydown);
        forwardRef2.addEventListener("focusin", onFocusIn);
        forwardRef2.addEventListener("focusout", onFocusOut);
      }
      if (oldForwardRef) {
        oldForwardRef.removeEventListener("keydown", onKeydown);
        oldForwardRef.removeEventListener("focusin", onFocusIn);
        oldForwardRef.removeEventListener("focusout", onFocusOut);
      }
    });
    const trapOnFocus = (e) => {
      emit(ON_TRAP_FOCUS_EVT, e);
    };
    const releaseOnFocus = (e) => emit(ON_RELEASE_FOCUS_EVT, e);
    const onFocusIn = (e) => {
      const trapContainer = unref(forwardRef);
      if (!trapContainer) return;
      const target = e.target;
      const relatedTarget = e.relatedTarget;
      const isFocusedInTrap = target && trapContainer.contains(target);
      if (!props.trapped) {
        if (!(relatedTarget && trapContainer.contains(relatedTarget))) lastFocusBeforeTrapped = relatedTarget;
      }
      if (isFocusedInTrap) emit("focusin", e);
      if (focusLayer.paused) return;
      if (props.trapped) if (isFocusedInTrap) lastFocusAfterTrapped = target;
      else tryFocus(lastFocusAfterTrapped, true);
    };
    const onFocusOut = (e) => {
      const trapContainer = unref(forwardRef);
      if (focusLayer.paused || !trapContainer) return;
      if (props.trapped) {
        const relatedTarget = e.relatedTarget;
        if (!isNil_default(relatedTarget) && !trapContainer.contains(relatedTarget)) setTimeout(() => {
          if (!focusLayer.paused && props.trapped) {
            const focusoutPreventedEvent = createFocusOutPreventedEvent({ focusReason: focusReason2.value });
            emit("focusout-prevented", focusoutPreventedEvent);
            if (!focusoutPreventedEvent.defaultPrevented) tryFocus(lastFocusAfterTrapped, true);
          }
        }, 0);
      } else {
        const target = e.target;
        if (!(target && trapContainer.contains(target))) emit("focusout", e);
      }
    };
    async function startTrap() {
      await nextTick();
      const trapContainer = unref(forwardRef);
      if (trapContainer) {
        focusableStack.push(focusLayer);
        const prevFocusedElement = trapContainer.contains(document.activeElement) ? lastFocusBeforeTrapped : document.activeElement;
        lastFocusBeforeTrapped = prevFocusedElement;
        if (!trapContainer.contains(prevFocusedElement)) {
          const focusEvent = new Event(FOCUS_AFTER_TRAPPED, FOCUS_AFTER_TRAPPED_OPTS);
          trapContainer.addEventListener(FOCUS_AFTER_TRAPPED, trapOnFocus);
          trapContainer.dispatchEvent(focusEvent);
          if (!focusEvent.defaultPrevented) nextTick(() => {
            let focusStartEl = props.focusStartEl;
            if (!isString(focusStartEl)) {
              tryFocus(focusStartEl);
              if (document.activeElement !== focusStartEl) focusStartEl = "first";
            }
            if (focusStartEl === "first") focusFirstDescendant(obtainAllFocusableElements2(trapContainer), true);
            if (document.activeElement === prevFocusedElement || focusStartEl === "container") tryFocus(trapContainer);
          });
        }
      }
    }
    function stopTrap() {
      const trapContainer = unref(forwardRef);
      if (trapContainer) {
        trapContainer.removeEventListener(FOCUS_AFTER_TRAPPED, trapOnFocus);
        const releasedEvent = new CustomEvent(FOCUS_AFTER_RELEASED, {
          ...FOCUS_AFTER_TRAPPED_OPTS,
          detail: { focusReason: focusReason2.value }
        });
        trapContainer.addEventListener(FOCUS_AFTER_RELEASED, releaseOnFocus);
        trapContainer.dispatchEvent(releasedEvent);
        if (!releasedEvent.defaultPrevented && (focusReason2.value == "keyboard" || !isFocusCausedByUserEvent() || trapContainer.contains(document.activeElement))) tryFocus(lastFocusBeforeTrapped ?? document.body);
        trapContainer.removeEventListener(FOCUS_AFTER_RELEASED, releaseOnFocus);
        focusableStack.remove(focusLayer);
        lastFocusBeforeTrapped = null;
        lastFocusAfterTrapped = null;
      }
    }
    onMounted(() => {
      if (props.trapped) startTrap();
      watch(() => props.trapped, (trapped) => {
        if (trapped) startTrap();
        else stopTrap();
      });
    });
    onBeforeUnmount(() => {
      if (props.trapped) stopTrap();
      if (forwardRef.value) {
        forwardRef.value.removeEventListener("keydown", onKeydown);
        forwardRef.value.removeEventListener("focusin", onFocusIn);
        forwardRef.value.removeEventListener("focusout", onFocusOut);
        forwardRef.value = void 0;
      }
      lastFocusBeforeTrapped = null;
      lastFocusAfterTrapped = null;
    });
    return { onKeydown };
  }
});

// node_modules/element-plus/es/components/focus-trap/src/focus-trap.mjs
function _sfc_render(_ctx, _cache, $props, $setup, $data, $options) {
  return renderSlot(_ctx.$slots, "default", { handleKeydown: _ctx.onKeydown });
}
var focus_trap_default = _plugin_vue_export_helper_default(focus_trap_vue_vue_type_script_lang_default, [["render", _sfc_render]]);

// node_modules/element-plus/es/components/focus-trap/index.mjs
var focus_trap_default$1 = focus_trap_default;

// node_modules/element-plus/es/constants/event.mjs
var UPDATE_MODEL_EVENT = "update:modelValue";
var CHANGE_EVENT = "change";
var INPUT_EVENT = "input";

// node_modules/element-plus/es/hooks/use-aria/index.mjs
var ariaProps = buildProps({
  /**
  * @description native `aria-label` attribute
  */
  ariaLabel: String,
  /**
  * @description native `aria-orientation` attribute
  */
  ariaOrientation: {
    type: String,
    values: [
      "horizontal",
      "vertical",
      "undefined"
    ]
  },
  /**
  * @description native `aria-controls` attribute
  */
  ariaControls: String
});
var useAriaProps = (arias) => {
  return pick_default(ariaProps, arias);
};

// node_modules/element-plus/es/components/input/src/input.mjs
var inputProps = buildProps({
  /**
  * @description native input id
  */
  id: {
    type: String,
    default: void 0
  },
  /**
  * @description input box size
  */
  size: useSizeProp,
  /**
  * @description whether to disable
  */
  disabled: {
    type: Boolean,
    default: void 0
  },
  /**
  * @description binding value
  */
  modelValue: {
    type: definePropType([
      String,
      Number,
      Object
    ]),
    default: ""
  },
  /**
  * @description v-model modifiers, reference [Vue modifiers](https://vuejs.org/guide/essentials/forms.html#modifiers)
  */
  modelModifiers: {
    type: definePropType(Object),
    default: () => ({})
  },
  /**
  * @description same as `maxlength` in native input
  */
  maxlength: { type: [String, Number] },
  /**
  * @description same as `minlength` in native input
  */
  minlength: { type: [String, Number] },
  /**
  * @description type of input, see more in [MDN](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/input#Form_%3Cinput%3E_types)
  */
  type: {
    type: definePropType(String),
    default: "text"
  },
  /**
  * @description control the resizability
  */
  resize: {
    type: String,
    values: [
      "none",
      "both",
      "horizontal",
      "vertical"
    ]
  },
  /**
  * @description whether textarea has an adaptive height
  */
  autosize: {
    type: definePropType([Boolean, Object]),
    default: false
  },
  /**
  * @description native input autocomplete
  */
  autocomplete: {
    type: definePropType(String),
    default: "off"
  },
  /**
  * @description format content
  */
  formatter: { type: Function },
  /**
  * @description parse content
  */
  parser: { type: Function },
  /**
  * @description placeholder
  */
  placeholder: { type: String },
  /**
  * @description native input form
  */
  form: { type: String },
  /**
  * @description native input readonly
  */
  readonly: Boolean,
  /**
  * @description whether to show clear button
  */
  clearable: Boolean,
  /**
  * @description custom clear icon component
  */
  clearIcon: {
    type: iconPropType,
    default: circle_close_default
  },
  /**
  * @description toggleable password input
  */
  showPassword: Boolean,
  /**
  * @description word count
  */
  showWordLimit: Boolean,
  /**
  * @description word count position, valid when `show-word-limit` is true
  */
  wordLimitPosition: {
    type: String,
    values: ["inside", "outside"],
    default: "inside"
  },
  /**
  * @description suffix icon
  */
  suffixIcon: { type: iconPropType },
  /**
  * @description prefix icon
  */
  prefixIcon: { type: iconPropType },
  /**
  * @description container role, internal properties provided for use by the picker component
  */
  containerRole: {
    type: String,
    default: void 0
  },
  /**
  * @description input tabindex
  */
  tabindex: {
    type: [String, Number],
    default: 0
  },
  /**
  * @description whether to trigger form validation
  */
  validateEvent: {
    type: Boolean,
    default: true
  },
  /**
  * @description input or textarea element style
  */
  inputStyle: {
    type: definePropType([
      Object,
      Array,
      String,
      Boolean
    ]),
    default: () => mutable({})
  },
  /**
  * @description Count graphemes of input value. If it's set, native maxlength and minlength won't be used.
  */
  countGraphemes: { type: definePropType(Function) },
  /**
  * @description native input autofocus
  */
  autofocus: Boolean,
  rows: {
    type: Number,
    default: 2
  },
  ...useAriaProps(["ariaLabel"]),
  /**
  * @description native input mode for virtual keyboards
  */
  inputmode: {
    type: definePropType(String),
    default: void 0
  },
  /**
  * @description same as `name` in native input
  */
  name: String
});
var inputEmits = {
  [UPDATE_MODEL_EVENT]: (value) => isString(value),
  input: (value) => isString(value),
  change: (value, evt) => isString(value) && (evt instanceof Event || evt === void 0),
  focus: (evt) => evt instanceof FocusEvent,
  blur: (evt) => evt instanceof FocusEvent,
  clear: (evt) => evt === void 0 || evt instanceof MouseEvent,
  mouseleave: (evt) => evt instanceof MouseEvent,
  mouseenter: (evt) => evt instanceof MouseEvent,
  keydown: (evt) => evt instanceof Event,
  compositionstart: (evt) => evt instanceof CompositionEvent,
  compositionupdate: (evt) => evt instanceof CompositionEvent,
  compositionend: (evt) => evt instanceof CompositionEvent
};
var inputPropsDefaults = {
  disabled: void 0,
  modelValue: "",
  modelModifiers: () => ({}),
  type: "text",
  autocomplete: "off",
  clearIcon: markRaw(circle_close_default),
  wordLimitPosition: "inside",
  tabindex: 0,
  validateEvent: true,
  inputStyle: () => ({}),
  rows: 2
};

// node_modules/element-plus/es/hooks/use-attrs/index.mjs
var DEFAULT_EXCLUDE_KEYS = ["class", "style"];
var LISTENER_PREFIX = /^on[A-Z]/;
var useAttrs2 = (params = {}) => {
  const { excludeListeners = false, excludeKeys } = params;
  const allExcludeKeys = computed(() => {
    return (excludeKeys?.value || []).concat(DEFAULT_EXCLUDE_KEYS);
  });
  const instance = getCurrentInstance();
  if (!instance) {
    debugWarn("use-attrs", "getCurrentInstance() returned null. useAttrs() must be called at the top of a setup function");
    return computed(() => ({}));
  }
  return computed(() => fromPairs_default(Object.entries(instance.proxy?.$attrs).filter(([key]) => !allExcludeKeys.value.includes(key) && !(excludeListeners && LISTENER_PREFIX.test(key)))));
};

// node_modules/element-plus/es/hooks/use-cursor/index.mjs
function useCursor(input) {
  let selectionInfo;
  function recordCursor() {
    if (input.value == void 0) return;
    const { selectionStart, selectionEnd, value } = input.value;
    if (selectionStart == null || selectionEnd == null) return;
    selectionInfo = {
      selectionStart,
      selectionEnd,
      value,
      beforeTxt: value.slice(0, Math.max(0, selectionStart)),
      afterTxt: value.slice(Math.max(0, selectionEnd))
    };
  }
  function setCursor() {
    if (input.value == void 0 || selectionInfo == void 0) return;
    const { value } = input.value;
    const { beforeTxt, afterTxt, selectionStart } = selectionInfo;
    if (beforeTxt == void 0 || afterTxt == void 0 || selectionStart == void 0) return;
    let startPos = value.length;
    if (value.endsWith(afterTxt)) startPos = value.length - afterTxt.length;
    else if (value.startsWith(beforeTxt)) startPos = beforeTxt.length;
    else {
      const beforeLastChar = beforeTxt[selectionStart - 1];
      const newIndex = value.indexOf(beforeLastChar, selectionStart - 1);
      if (newIndex !== -1) startPos = newIndex + 1;
    }
    input.value.setSelectionRange(startPos, startPos);
  }
  return [recordCursor, setCursor];
}

// node_modules/element-plus/es/hooks/use-focus-controller/index.mjs
function useFocusController(target, { disabled, beforeFocus, afterFocus, beforeBlur, afterBlur } = {}) {
  const { emit } = getCurrentInstance();
  const wrapperRef = shallowRef();
  const isFocused = ref(false);
  const handleFocus = (event) => {
    const cancelFocus = isFunction(beforeFocus) ? beforeFocus(event) : false;
    if (unref(disabled) || isFocused.value || cancelFocus) return;
    isFocused.value = true;
    emit("focus", event);
    afterFocus?.();
  };
  const handleBlur = (event) => {
    const cancelBlur = isFunction(beforeBlur) ? beforeBlur(event) : false;
    if (unref(disabled) || event.relatedTarget && wrapperRef.value?.contains(event.relatedTarget) || cancelBlur) return;
    isFocused.value = false;
    emit("blur", event);
    afterBlur?.();
  };
  const handleClick = (event) => {
    if (unref(disabled) || isFocusable(event.target) || wrapperRef.value?.contains(document.activeElement) && wrapperRef.value !== document.activeElement) return;
    target.value?.focus();
  };
  watch([wrapperRef, () => unref(disabled)], ([el, disabled2]) => {
    if (!el) return;
    if (disabled2) el.removeAttribute("tabindex");
    else el.setAttribute("tabindex", "-1");
  });
  useEventListener(wrapperRef, "focus", handleFocus, true);
  useEventListener(wrapperRef, "blur", handleBlur, true);
  useEventListener(wrapperRef, "click", handleClick, true);
  return {
    isFocused,
    /** Avoid using wrapperRef and handleFocus/handleBlur together */
    wrapperRef,
    handleFocus,
    handleBlur
  };
}

// node_modules/element-plus/es/hooks/use-composition/index.mjs
function useComposition({ afterComposition, emit }) {
  const isComposing = ref(false);
  const handleCompositionStart = (event) => {
    emit?.("compositionstart", event);
    isComposing.value = true;
  };
  const handleCompositionUpdate = (event) => {
    emit?.("compositionupdate", event);
    isComposing.value = true;
  };
  const handleCompositionEnd = (event) => {
    emit?.("compositionend", event);
    if (isComposing.value) {
      isComposing.value = false;
      nextTick(() => afterComposition(event));
    }
  };
  const handleComposition = (event) => {
    event.type === "compositionend" ? handleCompositionEnd(event) : handleCompositionUpdate(event);
  };
  return {
    isComposing,
    handleComposition,
    handleCompositionStart,
    handleCompositionUpdate,
    handleCompositionEnd
  };
}

// node_modules/element-plus/es/hooks/use-prop/index.mjs
var useProp = (name) => {
  const vm = getCurrentInstance();
  return computed(() => vm?.proxy?.$props?.[name]);
};

// node_modules/element-plus/es/components/form/src/constants.mjs
var formContextKey = /* @__PURE__ */ Symbol("formContextKey");
var formItemContextKey = /* @__PURE__ */ Symbol("formItemContextKey");

// node_modules/element-plus/es/components/form/src/hooks/use-form-common-props.mjs
var useFormSize = (fallback, ignore = {}) => {
  const emptyRef = ref(void 0);
  const size = ignore.prop ? emptyRef : useProp("size");
  const globalConfig = ignore.global ? emptyRef : useGlobalSize();
  const form = ignore.form ? { size: void 0 } : inject(formContextKey, void 0);
  const formItem = ignore.formItem ? { size: void 0 } : inject(formItemContextKey, void 0);
  return computed(() => size.value || unref(fallback) || formItem?.size || form?.size || globalConfig.value || "");
};
var useFormDisabled = (fallback) => {
  const disabled = useProp("disabled");
  const form = inject(formContextKey, void 0);
  return computed(() => {
    return disabled.value ?? unref(fallback) ?? form?.disabled ?? false;
  });
};

// node_modules/element-plus/es/components/form/src/hooks/use-form-item.mjs
var useFormItem = () => {
  return {
    form: inject(formContextKey, void 0),
    formItem: inject(formItemContextKey, void 0)
  };
};
var useFormItemInputId = (props, { formItemContext, disableIdGeneration, disableIdManagement }) => {
  if (!disableIdGeneration) disableIdGeneration = ref(false);
  if (!disableIdManagement) disableIdManagement = ref(false);
  const instance = getCurrentInstance();
  const inLabel = () => {
    let parent = instance?.parent;
    while (parent) {
      if (parent.type.name === "ElFormItem") return false;
      if (parent.type.name === "ElLabelWrap") return true;
      parent = parent.parent;
    }
    return false;
  };
  const inputId = ref();
  let idUnwatch = void 0;
  const isLabeledByFormItem = computed(() => {
    return !!(!(props.label || props.ariaLabel) && formItemContext && formItemContext.inputIds && formItemContext.inputIds?.length <= 1);
  });
  onMounted(() => {
    idUnwatch = watch([toRef(props, "id"), disableIdGeneration], ([id, disableIdGeneration2]) => {
      const newId = id ?? (!disableIdGeneration2 ? useId().value : void 0);
      if (newId !== inputId.value) {
        if (formItemContext?.removeInputId && !inLabel()) {
          inputId.value && formItemContext.removeInputId(inputId.value);
          if (!disableIdManagement?.value && !disableIdGeneration2 && newId) formItemContext.addInputId(newId);
        }
        inputId.value = newId;
      }
    }, { immediate: true });
  });
  onUnmounted(() => {
    idUnwatch && idUnwatch();
    if (formItemContext?.removeInputId) inputId.value && formItemContext.removeInputId(inputId.value);
  });
  return {
    isLabeledByFormItem,
    inputId
  };
};

// node_modules/element-plus/es/components/input/src/utils.mjs
var hiddenTextarea = void 0;
var HIDDEN_STYLE = {
  height: "0",
  visibility: "hidden",
  overflow: isFirefox() ? "" : "hidden",
  position: "absolute",
  "z-index": "-1000",
  top: "0",
  right: "0"
};
var CONTEXT_STYLE = [
  "letter-spacing",
  "line-height",
  "padding-top",
  "padding-bottom",
  "font-family",
  "font-weight",
  "font-size",
  "text-rendering",
  "text-transform",
  "width",
  "text-indent",
  "padding-left",
  "padding-right",
  "border-width",
  "box-sizing",
  "word-break"
];
var looseToNumber = (val) => {
  const n = Number.parseFloat(val);
  return Number.isNaN(n) ? val : n;
};
function calculateNodeStyling(targetElement) {
  const style = window.getComputedStyle(targetElement);
  const boxSizing = style.getPropertyValue("box-sizing");
  const paddingSize = Number.parseFloat(style.getPropertyValue("padding-bottom")) + Number.parseFloat(style.getPropertyValue("padding-top"));
  const borderSize = Number.parseFloat(style.getPropertyValue("border-bottom-width")) + Number.parseFloat(style.getPropertyValue("border-top-width"));
  return {
    contextStyle: CONTEXT_STYLE.map((name) => [name, style.getPropertyValue(name)]),
    paddingSize,
    borderSize,
    boxSizing
  };
}
function calcTextareaHeight(targetElement, minRows = 1, maxRows) {
  if (!hiddenTextarea) {
    hiddenTextarea = document.createElement("textarea");
    let hostNode = document.body;
    if (!isFirefox() && targetElement.parentNode) hostNode = targetElement.parentNode;
    hostNode.appendChild(hiddenTextarea);
  }
  const { paddingSize, borderSize, boxSizing, contextStyle } = calculateNodeStyling(targetElement);
  contextStyle.forEach(([key, value]) => hiddenTextarea?.style.setProperty(key, value));
  Object.entries(HIDDEN_STYLE).forEach(([key, value]) => hiddenTextarea?.style.setProperty(key, value, "important"));
  hiddenTextarea.value = targetElement.value || targetElement.placeholder || "";
  let height = hiddenTextarea.scrollHeight;
  const result = {};
  if (boxSizing === "border-box") height = height + borderSize;
  else if (boxSizing === "content-box") height = height - paddingSize;
  hiddenTextarea.value = "";
  const singleRowHeight = hiddenTextarea.scrollHeight - paddingSize;
  if (isNumber(minRows)) {
    let minHeight = singleRowHeight * minRows;
    if (boxSizing === "border-box") minHeight = minHeight + paddingSize + borderSize;
    height = Math.max(minHeight, height);
    result.minHeight = `${minHeight}px`;
  }
  if (isNumber(maxRows)) {
    let maxHeight = singleRowHeight * maxRows;
    if (boxSizing === "border-box") maxHeight = maxHeight + paddingSize + borderSize;
    height = Math.min(maxHeight, height);
  }
  result.height = `${height}px`;
  hiddenTextarea.parentNode?.removeChild(hiddenTextarea);
  hiddenTextarea = void 0;
  return result;
}

// node_modules/element-plus/es/components/input/src/input.vue_vue_type_script_setup_true_lang.mjs
var _hoisted_1 = [
  "id",
  "name",
  "minlength",
  "maxlength",
  "type",
  "disabled",
  "readonly",
  "autocomplete",
  "tabindex",
  "aria-label",
  "placeholder",
  "form",
  "autofocus",
  "role",
  "inputmode"
];
var _hoisted_2 = ["aria-label"];
var _hoisted_3 = [
  "id",
  "name",
  "minlength",
  "maxlength",
  "tabindex",
  "disabled",
  "readonly",
  "autocomplete",
  "aria-label",
  "placeholder",
  "form",
  "autofocus",
  "rows",
  "role",
  "inputmode"
];
var _hoisted_4 = ["aria-label"];
var COMPONENT_NAME = "ElInput";
var input_vue_vue_type_script_setup_true_lang_default = defineComponent({
  name: COMPONENT_NAME,
  inheritAttrs: false,
  __name: "input",
  props: inputProps,
  emits: inputEmits,
  setup(__props, { expose: __expose, emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const rawAttrs = useAttrs();
    const slots = useSlots();
    const containerKls = computed(() => [
      props.type === "textarea" ? nsTextarea.b() : nsInput.b(),
      nsInput.m(inputSize.value),
      nsInput.is("disabled", inputDisabled.value),
      nsInput.is("exceed", inputExceed.value),
      {
        [nsInput.b("group")]: slots.prepend || slots.append,
        [nsInput.m("prefix")]: slots.prefix || props.prefixIcon,
        [nsInput.m("suffix")]: slots.suffix || props.suffixIcon || props.clearable || props.showPassword,
        [nsInput.bm("suffix", "password-clear")]: showClear.value && showPwdVisible.value,
        [nsInput.b("hidden")]: props.type === "hidden"
      },
      rawAttrs.class
    ]);
    const wrapperKls = computed(() => [nsInput.e("wrapper"), nsInput.is("focus", isFocused.value)]);
    const attrs = useAttrs2();
    const maxlength = computed(() => props.maxlength?.toString());
    const { form: elForm, formItem: elFormItem } = useFormItem();
    const { inputId } = useFormItemInputId(props, { formItemContext: elFormItem });
    const inputSize = useFormSize();
    const inputDisabled = useFormDisabled();
    const nsInput = useNamespace("input");
    const nsTextarea = useNamespace("textarea");
    const { t } = useLocale();
    const input = shallowRef();
    const textarea = shallowRef();
    const hovering = ref(false);
    const passwordVisible = ref(false);
    const countStyle = ref();
    const clearIconStyle = ref();
    const textareaCalcStyle = shallowRef(props.inputStyle);
    const saveValue = ref("");
    let passwordFocusValue;
    const textareaHeight = ref();
    const _ref = computed(() => input.value || textarea.value);
    const { wrapperRef, isFocused, handleFocus, handleBlur } = useFocusController(_ref, {
      disabled: inputDisabled,
      afterFocus() {
        if (props.showPassword) passwordFocusValue = _ref.value?.value;
      },
      beforeBlur(event) {
        if (props.showPassword) {
          const target = _ref.value;
          if (event.relatedTarget && target?.parentElement?.contains(event.relatedTarget)) return;
          const value = target?.value;
          if (!isNil_default(value) && !isNil_default(passwordFocusValue) && value !== passwordFocusValue) target?.dispatchEvent(new Event("change", { bubbles: true }));
          passwordFocusValue = void 0;
        }
      },
      afterBlur() {
        if (props.validateEvent) elFormItem?.validate?.("blur").catch(NOOP);
      }
    });
    const needStatusIcon = computed(() => elForm?.statusIcon ?? false);
    const validateState = computed(() => elFormItem?.validateState || "");
    const validateIcon = computed(() => validateState.value && ValidateComponentsMap[validateState.value]);
    const passwordIcon = computed(() => passwordVisible.value ? view_default : hide_default);
    const containerStyle = computed(() => [rawAttrs.style]);
    const textareaStyle = computed(() => [
      props.inputStyle,
      textareaCalcStyle.value,
      { resize: props.resize },
      textareaHeight.value ? { height: textareaHeight.value } : void 0
    ]);
    const nativeInputValue = computed(() => isNil_default(props.modelValue) ? "" : String(props.modelValue));
    const renderClear = computed(() => props.clearable && !inputDisabled.value && !props.readonly);
    const showClear = computed(() => renderClear.value && !!nativeInputValue.value && (isFocused.value || hovering.value));
    const showPwdVisible = computed(() => props.showPassword && !inputDisabled.value && !!nativeInputValue.value);
    const isWordLimitVisible = computed(() => props.showWordLimit && !!maxlength.value && (props.type === "text" || props.type === "textarea") && !inputDisabled.value && !props.readonly && !props.showPassword);
    const textLength = computed(() => {
      if (props.countGraphemes && props.showWordLimit) return props.countGraphemes(nativeInputValue.value);
      return nativeInputValue.value.length;
    });
    const wordLimitLabel = computed(() => t("el.input.characters", {
      count: textLength.value,
      max: maxlength.value ?? ""
    }));
    const inputExceed = computed(() => !!isWordLimitVisible.value && textLength.value > Number(maxlength.value));
    const suffixVisible = computed(() => !!slots.suffix || !!props.suffixIcon || props.clearable || props.showPassword || isWordLimitVisible.value || !!validateState.value && needStatusIcon.value);
    const hasModelModifiers = computed(() => !!Object.keys(props.modelModifiers).length);
    const [recordCursor, setCursor] = useCursor(input);
    let rAFId;
    useResizeObserver(textarea, (entries) => {
      onceInitSizeTextarea();
      if (!isWordLimitVisible.value && !renderClear.value || props.resize !== "both" && props.resize !== "horizontal") return;
      const { width } = entries[0].target.getBoundingClientRect();
      const updateStyle = () => {
        rAFId = void 0;
        countStyle.value = {
          /** right: 100% - (width - right(10)) */
          right: `calc(100% - ${width - 10}px)`
        };
        clearIconStyle.value = {
          /** right: 100% - (width - right(11)) */
          right: `calc(100% - ${width - 11}px)`
        };
      };
      rAFId && cAF(rAFId);
      rAFId = rAF(updateStyle);
    });
    const resizeTextarea = () => {
      const { type, autosize } = props;
      if (!isClient || type !== "textarea" || !textarea.value) return;
      if (autosize) {
        const minRows = isObject(autosize) ? autosize.minRows : void 0;
        const maxRows = isObject(autosize) ? autosize.maxRows : void 0;
        const textareaStyle2 = calcTextareaHeight(textarea.value, minRows, maxRows);
        textareaCalcStyle.value = {
          overflowY: "hidden",
          ...textareaStyle2
        };
        nextTick(() => {
          textarea.value.offsetHeight;
          textareaCalcStyle.value = textareaStyle2;
        });
      } else textareaCalcStyle.value = { minHeight: calcTextareaHeight(textarea.value).minHeight };
    };
    const createOnceInitResize = (resizeTextarea2) => {
      let isInit = false;
      return () => {
        if (isInit || !props.autosize) {
          if (props.resize !== "none") setTimeout(() => {
            textareaHeight.value = textarea.value?.style.height;
          });
          return;
        }
        if (!(textarea.value?.offsetParent === null)) {
          setTimeout(resizeTextarea2);
          isInit = true;
        }
      };
    };
    const onceInitSizeTextarea = createOnceInitResize(resizeTextarea);
    const setNativeInputValue = () => {
      const input2 = _ref.value;
      const formatterValue = props.formatter ? props.formatter(nativeInputValue.value) : nativeInputValue.value;
      if (!input2 || input2.value === formatterValue || props.type === "file") return;
      input2.value = formatterValue;
    };
    const formatValue = (value) => {
      const { trim, number } = props.modelModifiers;
      if (trim) value = value.trim();
      if (number) value = `${looseToNumber(value)}`;
      if (props.formatter && props.parser) value = props.parser(value);
      return value;
    };
    const handleInput = async (event) => {
      if (isComposing.value) return;
      const { lazy } = props.modelModifiers;
      let { value } = event.target;
      let shouldForceNativeUpdate = false;
      if (lazy) {
        emit(INPUT_EVENT, value);
        return;
      }
      value = formatValue(value);
      if (props.countGraphemes && maxlength.value != null) {
        const limit = Number(maxlength.value);
        const graphemes = props.countGraphemes(value);
        const saveGraphemes = props.countGraphemes(saveValue.value);
        if (graphemes > limit && graphemes > saveGraphemes) if (saveGraphemes > limit) {
          value = saveValue.value;
          shouldForceNativeUpdate = true;
        } else {
          const prevValue = saveValue.value;
          const nextValue = value;
          let prefixLen = 0;
          while (prefixLen < prevValue.length && prefixLen < nextValue.length && prevValue[prefixLen] === nextValue[prefixLen]) prefixLen++;
          let prevSuffixIndex = prevValue.length;
          let nextSuffixIndex = nextValue.length;
          while (prevSuffixIndex > prefixLen && nextSuffixIndex > prefixLen && prevValue[prevSuffixIndex - 1] === nextValue[nextSuffixIndex - 1]) {
            prevSuffixIndex--;
            nextSuffixIndex--;
          }
          const before = nextValue.slice(0, prefixLen);
          const removed = prevValue.slice(prefixLen, prevSuffixIndex);
          const inserted = nextValue.slice(prefixLen, nextSuffixIndex);
          const after = nextValue.slice(nextSuffixIndex);
          const baseCount = saveGraphemes - props.countGraphemes(removed);
          const availableInserted = Math.max(0, limit - baseCount);
          let acceptedInserted = "";
          if (availableInserted > 0) if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
            const segmenter = new Intl.Segmenter(void 0, { granularity: "grapheme" });
            for (const { segment } of segmenter.segment(inserted)) {
              const candidate = acceptedInserted + segment;
              if (props.countGraphemes(candidate) > availableInserted) break;
              acceptedInserted = candidate;
            }
          } else for (const char of Array.from(inserted)) {
            const candidate = acceptedInserted + char;
            if (props.countGraphemes(candidate) > availableInserted) break;
            acceptedInserted = candidate;
          }
          value = before + acceptedInserted + after;
          shouldForceNativeUpdate = true;
        }
      }
      if (String(value) === nativeInputValue.value) {
        if (props.formatter || shouldForceNativeUpdate) {
          const target = event.target;
          const blockedValue = target.value;
          const selectionStart = target.selectionStart;
          const selectionEnd = target.selectionEnd;
          setNativeInputValue();
          if (shouldForceNativeUpdate && _ref.value && selectionStart != null && selectionEnd != null) {
            const restoredValue = _ref.value.value;
            const afterTxt = blockedValue.slice(Math.max(0, selectionEnd));
            let caretPos = Math.min(selectionStart, restoredValue.length);
            if (afterTxt && restoredValue.endsWith(afterTxt)) caretPos = restoredValue.length - afterTxt.length;
            _ref.value.setSelectionRange(caretPos, caretPos);
          }
        }
        return;
      }
      saveValue.value = value;
      recordCursor();
      emit(UPDATE_MODEL_EVENT, value);
      emit(INPUT_EVENT, value);
      await nextTick();
      if (props.formatter && props.parser || !hasModelModifiers.value) setNativeInputValue();
      setCursor();
    };
    const handleChange = async (event) => {
      let { value } = event.target;
      if (props.showPassword) passwordFocusValue = value;
      value = formatValue(value);
      if (props.modelModifiers.lazy) emit(UPDATE_MODEL_EVENT, value);
      emit(CHANGE_EVENT, value, event);
      await nextTick();
      setNativeInputValue();
    };
    const { isComposing, handleCompositionStart, handleCompositionUpdate, handleCompositionEnd } = useComposition({
      emit,
      afterComposition: handleInput
    });
    const handlePasswordVisible = () => {
      passwordVisible.value = !passwordVisible.value;
    };
    const focus = () => _ref.value?.focus();
    const blur = () => _ref.value?.blur();
    const handleMouseLeave = (evt) => {
      hovering.value = false;
      emit("mouseleave", evt);
    };
    const handleMouseEnter = (evt) => {
      hovering.value = true;
      emit("mouseenter", evt);
    };
    const handleKeydown = (evt) => {
      emit("keydown", evt);
    };
    const select = () => {
      _ref.value?.select();
    };
    const clear = (evt) => {
      emit(UPDATE_MODEL_EVENT, "");
      passwordFocusValue = "";
      emit(CHANGE_EVENT, "");
      emit("clear", evt);
      emit(INPUT_EVENT, "");
    };
    watch(() => props.modelValue, () => {
      nextTick(() => {
        resizeTextarea();
        if (props.autosize) textareaHeight.value = void 0;
      });
      if (props.validateEvent) elFormItem?.validate?.("change").catch(NOOP);
    });
    watch(() => nativeInputValue.value, (val) => {
      saveValue.value = val;
    }, { immediate: true });
    watch(nativeInputValue, (newValue) => {
      if (!_ref.value) return;
      const { trim, number } = props.modelModifiers;
      const elValue = _ref.value.value;
      const displayValue = (number || props.type === "number") && !/^0\d/.test(elValue) ? `${looseToNumber(elValue)}` : elValue;
      if (displayValue === newValue) return;
      if (document.activeElement === _ref.value && _ref.value.type !== "range") {
        if (trim && displayValue.trim() === newValue) return;
      }
      setNativeInputValue();
    });
    watch(() => props.type, async () => {
      await nextTick();
      setNativeInputValue();
      resizeTextarea();
    });
    onMounted(() => {
      if (!props.formatter && props.parser) debugWarn(COMPONENT_NAME, "If you set the parser, you also need to set the formatter.");
      setNativeInputValue();
      nextTick(resizeTextarea);
    });
    onBeforeUnmount(() => {
      rAFId && cAF(rAFId);
    });
    __expose({
      /** @description HTML input element */
      input,
      /** @description HTML textarea element */
      textarea,
      /** @description HTML element, input or textarea */
      ref: _ref,
      /** @description style of textarea. */
      textareaStyle,
      /** @description from props (used on unit test) */
      autosize: toRef(props, "autosize"),
      /** @description is input composing */
      isComposing,
      /** @description whether the password is visible */
      passwordVisible,
      /** @description HTML input element native method */
      focus,
      /** @description HTML input element native method */
      blur,
      /** @description HTML input element native method */
      select,
      /** @description clear input value */
      clear,
      /** @description resize textarea. */
      resizeTextarea
    });
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", {
        class: normalizeClass([containerKls.value, {
          [unref(nsInput).bm("group", "append")]: _ctx.$slots.append,
          [unref(nsInput).bm("group", "prepend")]: _ctx.$slots.prepend
        }]),
        style: normalizeStyle(containerStyle.value),
        onMouseenter: handleMouseEnter,
        onMouseleave: handleMouseLeave
      }, [createCommentVNode(" input "), __props.type !== "textarea" ? (openBlock(), createElementBlock(Fragment, { key: 0 }, [
        createCommentVNode(" prepend slot "),
        _ctx.$slots.prepend ? (openBlock(), createElementBlock("div", {
          key: 0,
          class: normalizeClass(unref(nsInput).be("group", "prepend"))
        }, [renderSlot(_ctx.$slots, "prepend")], 2)) : createCommentVNode("v-if", true),
        createBaseVNode("div", {
          ref_key: "wrapperRef",
          ref: wrapperRef,
          class: normalizeClass(wrapperKls.value)
        }, [
          createCommentVNode(" prefix slot "),
          _ctx.$slots.prefix || __props.prefixIcon ? (openBlock(), createElementBlock("span", {
            key: 0,
            class: normalizeClass(unref(nsInput).e("prefix"))
          }, [createBaseVNode("span", { class: normalizeClass(unref(nsInput).e("prefix-inner")) }, [renderSlot(_ctx.$slots, "prefix"), __props.prefixIcon ? (openBlock(), createBlock(unref(ElIcon), {
            key: 0,
            class: normalizeClass(unref(nsInput).e("icon"))
          }, {
            default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(__props.prefixIcon)))]),
            _: 1
          }, 8, ["class"])) : createCommentVNode("v-if", true)], 2)], 2)) : createCommentVNode("v-if", true),
          createBaseVNode("input", mergeProps({
            id: unref(inputId),
            ref_key: "input",
            ref: input,
            class: unref(nsInput).e("inner")
          }, unref(attrs), {
            name: __props.name,
            minlength: __props.countGraphemes ? void 0 : __props.minlength,
            maxlength: __props.countGraphemes ? void 0 : maxlength.value,
            type: __props.showPassword ? passwordVisible.value ? "text" : "password" : __props.type,
            disabled: unref(inputDisabled),
            readonly: __props.readonly,
            autocomplete: __props.autocomplete,
            tabindex: __props.tabindex,
            "aria-label": __props.ariaLabel,
            placeholder: __props.placeholder,
            style: __props.inputStyle,
            form: __props.form,
            autofocus: __props.autofocus,
            role: __props.containerRole,
            inputmode: __props.inputmode,
            onCompositionstart: _cache[0] || (_cache[0] = (...args) => unref(handleCompositionStart) && unref(handleCompositionStart)(...args)),
            onCompositionupdate: _cache[1] || (_cache[1] = (...args) => unref(handleCompositionUpdate) && unref(handleCompositionUpdate)(...args)),
            onCompositionend: _cache[2] || (_cache[2] = (...args) => unref(handleCompositionEnd) && unref(handleCompositionEnd)(...args)),
            onInput: handleInput,
            onChange: handleChange,
            onKeydown: handleKeydown
          }), null, 16, _hoisted_1),
          createCommentVNode(" suffix slot "),
          suffixVisible.value ? (openBlock(), createElementBlock("span", {
            key: 1,
            class: normalizeClass(unref(nsInput).e("suffix"))
          }, [createBaseVNode("span", { class: normalizeClass(unref(nsInput).e("suffix-inner")) }, [
            renderClear.value ? (openBlock(), createBlock(unref(ElIcon), {
              key: 0,
              class: normalizeClass([unref(nsInput).e("icon"), unref(nsInput).e("clear")]),
              style: normalizeStyle({ visibility: showClear.value ? "visible" : "hidden" }),
              onMousedown: withModifiers(unref(NOOP), ["prevent"]),
              onClick: clear
            }, {
              default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(__props.clearIcon)))]),
              _: 1
            }, 8, [
              "class",
              "style",
              "onMousedown"
            ])) : createCommentVNode("v-if", true),
            !showClear.value || !showPwdVisible.value || !isWordLimitVisible.value ? (openBlock(), createElementBlock(Fragment, { key: 1 }, [renderSlot(_ctx.$slots, "suffix"), __props.suffixIcon ? (openBlock(), createBlock(unref(ElIcon), {
              key: 0,
              class: normalizeClass(unref(nsInput).e("icon"))
            }, {
              default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(__props.suffixIcon)))]),
              _: 1
            }, 8, ["class"])) : createCommentVNode("v-if", true)], 64)) : createCommentVNode("v-if", true),
            showPwdVisible.value ? (openBlock(), createBlock(unref(ElIcon), {
              key: 2,
              class: normalizeClass([unref(nsInput).e("icon"), unref(nsInput).e("password")]),
              onClick: handlePasswordVisible,
              onMousedown: withModifiers(unref(NOOP), ["prevent"]),
              onMouseup: withModifiers(unref(NOOP), ["prevent"])
            }, {
              default: withCtx(() => [renderSlot(_ctx.$slots, "password-icon", { visible: passwordVisible.value }, () => [(openBlock(), createBlock(resolveDynamicComponent(passwordIcon.value)))])]),
              _: 3
            }, 8, [
              "class",
              "onMousedown",
              "onMouseup"
            ])) : createCommentVNode("v-if", true),
            isWordLimitVisible.value ? (openBlock(), createElementBlock("span", {
              key: 3,
              class: normalizeClass([unref(nsInput).e("count"), unref(nsInput).is("outside", __props.wordLimitPosition === "outside")]),
              "aria-label": wordLimitLabel.value,
              role: "status"
            }, [createBaseVNode("span", { class: normalizeClass(unref(nsInput).e("count-inner")) }, toDisplayString(textLength.value) + " / " + toDisplayString(maxlength.value), 3)], 10, _hoisted_2)) : createCommentVNode("v-if", true),
            validateState.value && validateIcon.value && needStatusIcon.value ? (openBlock(), createBlock(unref(ElIcon), {
              key: 4,
              class: normalizeClass([
                unref(nsInput).e("icon"),
                unref(nsInput).e("validateIcon"),
                unref(nsInput).is("loading", validateState.value === "validating")
              ])
            }, {
              default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(validateIcon.value)))]),
              _: 1
            }, 8, ["class"])) : createCommentVNode("v-if", true)
          ], 2)], 2)) : createCommentVNode("v-if", true)
        ], 2),
        createCommentVNode(" append slot "),
        _ctx.$slots.append ? (openBlock(), createElementBlock("div", {
          key: 1,
          class: normalizeClass(unref(nsInput).be("group", "append"))
        }, [renderSlot(_ctx.$slots, "append")], 2)) : createCommentVNode("v-if", true)
      ], 64)) : (openBlock(), createElementBlock(Fragment, { key: 1 }, [
        createCommentVNode(" textarea "),
        createBaseVNode("textarea", mergeProps({
          id: unref(inputId),
          ref_key: "textarea",
          ref: textarea,
          class: [
            unref(nsTextarea).e("inner"),
            unref(nsInput).is("focus", unref(isFocused)),
            unref(nsTextarea).is("clearable", __props.clearable)
          ]
        }, unref(attrs), {
          name: __props.name,
          minlength: __props.countGraphemes ? void 0 : __props.minlength,
          maxlength: __props.countGraphemes ? void 0 : maxlength.value,
          tabindex: __props.tabindex,
          disabled: unref(inputDisabled),
          readonly: __props.readonly,
          autocomplete: __props.autocomplete,
          style: textareaStyle.value,
          "aria-label": __props.ariaLabel,
          placeholder: __props.placeholder,
          form: __props.form,
          autofocus: __props.autofocus,
          rows: __props.rows,
          role: __props.containerRole,
          inputmode: __props.inputmode,
          onCompositionstart: _cache[3] || (_cache[3] = (...args) => unref(handleCompositionStart) && unref(handleCompositionStart)(...args)),
          onCompositionupdate: _cache[4] || (_cache[4] = (...args) => unref(handleCompositionUpdate) && unref(handleCompositionUpdate)(...args)),
          onCompositionend: _cache[5] || (_cache[5] = (...args) => unref(handleCompositionEnd) && unref(handleCompositionEnd)(...args)),
          onInput: handleInput,
          onFocus: _cache[6] || (_cache[6] = (...args) => unref(handleFocus) && unref(handleFocus)(...args)),
          onBlur: _cache[7] || (_cache[7] = (...args) => unref(handleBlur) && unref(handleBlur)(...args)),
          onChange: handleChange,
          onKeydown: handleKeydown
        }), null, 16, _hoisted_3),
        showClear.value ? (openBlock(), createBlock(unref(ElIcon), {
          key: 0,
          class: normalizeClass([unref(nsTextarea).e("icon"), unref(nsTextarea).e("clear")]),
          style: normalizeStyle(clearIconStyle.value),
          onMousedown: withModifiers(unref(NOOP), ["prevent"]),
          onClick: clear
        }, {
          default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(__props.clearIcon)))]),
          _: 1
        }, 8, [
          "class",
          "style",
          "onMousedown"
        ])) : createCommentVNode("v-if", true),
        isWordLimitVisible.value ? (openBlock(), createElementBlock("span", {
          key: 1,
          style: normalizeStyle(countStyle.value),
          class: normalizeClass([unref(nsInput).e("count"), unref(nsInput).is("outside", __props.wordLimitPosition === "outside")]),
          "aria-label": wordLimitLabel.value,
          role: "status"
        }, toDisplayString(textLength.value) + " / " + toDisplayString(maxlength.value), 15, _hoisted_4)) : createCommentVNode("v-if", true)
      ], 64))], 38);
    };
  }
});

// node_modules/element-plus/es/components/input/src/input2.mjs
var input_default = input_vue_vue_type_script_setup_true_lang_default;

// node_modules/element-plus/es/components/input/index.mjs
var ElInput = withInstall(input_default);

// node_modules/element-plus/es/components/button/src/button.mjs
var buttonTypes = [
  "default",
  "primary",
  "success",
  "warning",
  "info",
  "danger",
  "text",
  ""
];
var buttonNativeTypes = [
  "button",
  "submit",
  "reset"
];
var buttonProps = buildProps({
  /**
  * @description button size
  */
  size: useSizeProp,
  /**
  * @description disable the button
  */
  disabled: {
    type: Boolean,
    default: void 0
  },
  /**
  * @description button type
  */
  type: {
    type: String,
    values: buttonTypes,
    default: ""
  },
  /**
  * @description icon component
  */
  icon: { type: iconPropType },
  /**
  * @description native button type
  */
  nativeType: {
    type: String,
    values: buttonNativeTypes,
    default: "button"
  },
  /**
  * @description determine whether it's loading
  */
  loading: Boolean,
  /**
  * @description customize loading icon component
  */
  loadingIcon: {
    type: iconPropType,
    default: () => loading_default
  },
  /**
  * @description determine whether it's a plain button
  */
  plain: {
    type: Boolean,
    default: void 0
  },
  /**
  * @description determine whether it's a text button
  */
  text: {
    type: Boolean,
    default: void 0
  },
  /**
  * @description determine whether it's a link button
  */
  link: Boolean,
  /**
  * @description determine whether the text button background color is always on
  */
  bg: Boolean,
  /**
  * @description native button autofocus
  */
  autofocus: Boolean,
  /**
  * @description determine whether it's a round button
  */
  round: {
    type: Boolean,
    default: void 0
  },
  /**
  * @description determine whether it's a circle button
  */
  circle: Boolean,
  /**
  * @description determine whether it's a dashed button
  */
  dashed: {
    type: Boolean,
    default: void 0
  },
  /**
  * @description custom button color, automatically calculate `hover` and `active` color
  */
  color: String,
  /**
  * @description dark mode, which automatically converts `color` to dark mode colors
  */
  dark: Boolean,
  /**
  * @description automatically insert a space between two chinese characters
  */
  autoInsertSpace: {
    type: Boolean,
    default: void 0
  },
  /**
  * @description custom element tag
  */
  tag: {
    type: definePropType([String, Object]),
    default: "button"
  }
});
var buttonEmits = { click: (evt) => evt instanceof MouseEvent };

// node_modules/element-plus/es/components/button/src/constants.mjs
var buttonGroupContextKey = /* @__PURE__ */ Symbol("buttonGroupContextKey");

// node_modules/element-plus/es/hooks/use-deprecated/index.mjs
var useDeprecated = ({ from, replacement, scope, version, ref: ref2, type = "API" }, condition) => {
  watch(() => unref(condition), (val) => {
    if (val) debugWarn(scope, `[${type}] ${from} is about to be deprecated in version ${version}, please use ${replacement} instead.
For more detail, please visit: ${ref2}
`);
  }, { immediate: true });
};

// node_modules/element-plus/es/components/button/src/use-button.mjs
var useButton = (props, emit) => {
  useDeprecated({
    from: "type.text",
    replacement: "link",
    version: "3.0.0",
    scope: "props",
    ref: "https://element-plus.org/en-US/component/button.html#button-attributes"
  }, computed(() => props.type === "text"));
  const buttonGroupContext = inject(buttonGroupContextKey, void 0);
  const globalConfig = useGlobalConfig("button");
  const { form } = useFormItem();
  const _size = useFormSize(computed(() => buttonGroupContext?.size));
  const _disabled = useFormDisabled();
  const _ref = ref();
  const slots = useSlots();
  const _type = computed(() => props.type || buttonGroupContext?.type || globalConfig.value?.type || "");
  const autoInsertSpace = computed(() => props.autoInsertSpace ?? globalConfig.value?.autoInsertSpace ?? false);
  const _plain = computed(() => props.plain ?? globalConfig.value?.plain ?? false);
  const _round = computed(() => props.round ?? globalConfig.value?.round ?? false);
  const _text = computed(() => props.text ?? globalConfig.value?.text ?? false);
  const _dashed = computed(() => props.dashed ?? globalConfig.value?.dashed ?? false);
  const _props = computed(() => {
    if (props.tag === "button") return {
      ariaDisabled: _disabled.value || props.loading,
      disabled: _disabled.value || props.loading,
      autofocus: props.autofocus,
      type: props.nativeType
    };
    return {};
  });
  const shouldAddSpace = computed(() => {
    const defaultSlot = slots.default?.();
    if (autoInsertSpace.value && defaultSlot?.length === 1) {
      const slot = defaultSlot[0];
      if (slot?.type === Text) {
        const text = slot.children;
        return new RegExp("^\\p{Unified_Ideograph}{2}$", "u").test(text.trim());
      }
    }
    return false;
  });
  const handleClick = (evt) => {
    if (_disabled.value || props.loading) {
      evt.stopPropagation();
      return;
    }
    if (props.nativeType === "reset") form?.resetFields();
    emit("click", evt);
  };
  return {
    _disabled,
    _size,
    _type,
    _ref,
    _props,
    _plain,
    _round,
    _text,
    _dashed,
    shouldAddSpace,
    handleClick
  };
};

// node_modules/@ctrl/tinycolor/dist/module/util.js
function bound01(n, max) {
  if (isOnePointZero(n)) {
    n = "100%";
  }
  const isPercent = isPercentage(n);
  n = max === 360 ? n : Math.min(max, Math.max(0, parseFloat(n)));
  if (isPercent) {
    n = parseInt(String(n * max), 10) / 100;
  }
  if (Math.abs(n - max) < 1e-6) {
    return 1;
  }
  if (max === 360) {
    n = (n < 0 ? n % max + max : n % max) / max;
  } else {
    n = n % max / max;
  }
  return n;
}
function clamp01(val) {
  return Math.min(1, Math.max(0, val));
}
function isOnePointZero(n) {
  return typeof n === "string" && n.indexOf(".") !== -1 && parseFloat(n) === 1;
}
function isPercentage(n) {
  return typeof n === "string" && n.indexOf("%") !== -1;
}
function boundAlpha(a) {
  a = parseFloat(a);
  if (isNaN(a) || a < 0 || a > 1) {
    a = 1;
  }
  return a;
}
function convertToPercentage(n) {
  if (Number(n) <= 1) {
    return `${Number(n) * 100}%`;
  }
  return n;
}
function pad2(c) {
  return c.length === 1 ? "0" + c : String(c);
}

// node_modules/@ctrl/tinycolor/dist/module/conversion.js
function rgbToRgb(r, g, b) {
  return {
    r: bound01(r, 255) * 255,
    g: bound01(g, 255) * 255,
    b: bound01(b, 255) * 255
  };
}
function rgbToHsl(r, g, b) {
  r = bound01(r, 255);
  g = bound01(g, 255);
  b = bound01(b, 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h2 = 0;
  let s = 0;
  const l = (max + min) / 2;
  if (max === min) {
    s = 0;
    h2 = 0;
  } else {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r:
        h2 = (g - b) / d + (g < b ? 6 : 0);
        break;
      case g:
        h2 = (b - r) / d + 2;
        break;
      case b:
        h2 = (r - g) / d + 4;
        break;
      default:
        break;
    }
    h2 /= 6;
  }
  return { h: h2, s, l };
}
function hue2rgb(p, q, t) {
  if (t < 0) {
    t += 1;
  }
  if (t > 1) {
    t -= 1;
  }
  if (t < 1 / 6) {
    return p + (q - p) * (6 * t);
  }
  if (t < 1 / 2) {
    return q;
  }
  if (t < 2 / 3) {
    return p + (q - p) * (2 / 3 - t) * 6;
  }
  return p;
}
function hslToRgb(h2, s, l) {
  let r;
  let g;
  let b;
  h2 = bound01(h2, 360);
  s = bound01(s, 100);
  l = bound01(l, 100);
  if (s === 0) {
    g = l;
    b = l;
    r = l;
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h2 + 1 / 3);
    g = hue2rgb(p, q, h2);
    b = hue2rgb(p, q, h2 - 1 / 3);
  }
  return { r: r * 255, g: g * 255, b: b * 255 };
}
function rgbToHsv(r, g, b) {
  r = bound01(r, 255);
  g = bound01(g, 255);
  b = bound01(b, 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h2 = 0;
  const v = max;
  const d = max - min;
  const s = max === 0 ? 0 : d / max;
  if (max === min) {
    h2 = 0;
  } else {
    switch (max) {
      case r:
        h2 = (g - b) / d + (g < b ? 6 : 0);
        break;
      case g:
        h2 = (b - r) / d + 2;
        break;
      case b:
        h2 = (r - g) / d + 4;
        break;
      default:
        break;
    }
    h2 /= 6;
  }
  return { h: h2, s, v };
}
function hsvToRgb(h2, s, v) {
  h2 = bound01(h2, 360) * 6;
  s = bound01(s, 100);
  v = bound01(v, 100);
  const i = Math.floor(h2);
  const f = h2 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  const mod = i % 6;
  const r = [v, q, p, p, t, v][mod];
  const g = [t, v, v, q, p, p][mod];
  const b = [p, p, t, v, v, q][mod];
  return { r: r * 255, g: g * 255, b: b * 255 };
}
function rgbToHex(r, g, b, allow3Char) {
  const rHex = pad2(Math.round(r).toString(16));
  const gHex = pad2(Math.round(g).toString(16));
  const bHex = pad2(Math.round(b).toString(16));
  if (allow3Char && rHex.startsWith(rHex.charAt(1)) && gHex.startsWith(gHex.charAt(1)) && bHex.startsWith(bHex.charAt(1))) {
    return rHex.charAt(0) + gHex.charAt(0) + bHex.charAt(0);
  }
  return rHex + gHex + bHex;
}
function rgbaToHex(r, g, b, a, allow4Char) {
  const rHex = pad2(Math.round(r).toString(16));
  const gHex = pad2(Math.round(g).toString(16));
  const bHex = pad2(Math.round(b).toString(16));
  const aHex = pad2(convertDecimalToHex(a));
  if (allow4Char && rHex.startsWith(rHex.charAt(1)) && gHex.startsWith(gHex.charAt(1)) && bHex.startsWith(bHex.charAt(1)) && aHex.startsWith(aHex.charAt(1))) {
    return rHex.charAt(0) + gHex.charAt(0) + bHex.charAt(0) + aHex.charAt(0);
  }
  return rHex + gHex + bHex + aHex;
}
function cmykToRgb(c, m, y, k) {
  const cConv = c / 100;
  const mConv = m / 100;
  const yConv = y / 100;
  const kConv = k / 100;
  const r = 255 * (1 - cConv) * (1 - kConv);
  const g = 255 * (1 - mConv) * (1 - kConv);
  const b = 255 * (1 - yConv) * (1 - kConv);
  return { r, g, b };
}
function rgbToCmyk(r, g, b) {
  let c = 1 - r / 255;
  let m = 1 - g / 255;
  let y = 1 - b / 255;
  let k = Math.min(c, m, y);
  if (k === 1) {
    c = 0;
    m = 0;
    y = 0;
  } else {
    c = (c - k) / (1 - k) * 100;
    m = (m - k) / (1 - k) * 100;
    y = (y - k) / (1 - k) * 100;
  }
  k *= 100;
  return {
    c: Math.round(c),
    m: Math.round(m),
    y: Math.round(y),
    k: Math.round(k)
  };
}
function convertDecimalToHex(d) {
  return Math.round(parseFloat(d) * 255).toString(16);
}
function convertHexToDecimal(h2) {
  return parseIntFromHex(h2) / 255;
}
function parseIntFromHex(val) {
  return parseInt(val, 16);
}
function numberInputToObject(color) {
  return {
    r: color >> 16,
    g: (color & 65280) >> 8,
    b: color & 255
  };
}

// node_modules/@ctrl/tinycolor/dist/module/css-color-names.js
var names = {
  aliceblue: "#f0f8ff",
  antiquewhite: "#faebd7",
  aqua: "#00ffff",
  aquamarine: "#7fffd4",
  azure: "#f0ffff",
  beige: "#f5f5dc",
  bisque: "#ffe4c4",
  black: "#000000",
  blanchedalmond: "#ffebcd",
  blue: "#0000ff",
  blueviolet: "#8a2be2",
  brown: "#a52a2a",
  burlywood: "#deb887",
  cadetblue: "#5f9ea0",
  chartreuse: "#7fff00",
  chocolate: "#d2691e",
  coral: "#ff7f50",
  cornflowerblue: "#6495ed",
  cornsilk: "#fff8dc",
  crimson: "#dc143c",
  cyan: "#00ffff",
  darkblue: "#00008b",
  darkcyan: "#008b8b",
  darkgoldenrod: "#b8860b",
  darkgray: "#a9a9a9",
  darkgreen: "#006400",
  darkgrey: "#a9a9a9",
  darkkhaki: "#bdb76b",
  darkmagenta: "#8b008b",
  darkolivegreen: "#556b2f",
  darkorange: "#ff8c00",
  darkorchid: "#9932cc",
  darkred: "#8b0000",
  darksalmon: "#e9967a",
  darkseagreen: "#8fbc8f",
  darkslateblue: "#483d8b",
  darkslategray: "#2f4f4f",
  darkslategrey: "#2f4f4f",
  darkturquoise: "#00ced1",
  darkviolet: "#9400d3",
  deeppink: "#ff1493",
  deepskyblue: "#00bfff",
  dimgray: "#696969",
  dimgrey: "#696969",
  dodgerblue: "#1e90ff",
  firebrick: "#b22222",
  floralwhite: "#fffaf0",
  forestgreen: "#228b22",
  fuchsia: "#ff00ff",
  gainsboro: "#dcdcdc",
  ghostwhite: "#f8f8ff",
  goldenrod: "#daa520",
  gold: "#ffd700",
  gray: "#808080",
  green: "#008000",
  greenyellow: "#adff2f",
  grey: "#808080",
  honeydew: "#f0fff0",
  hotpink: "#ff69b4",
  indianred: "#cd5c5c",
  indigo: "#4b0082",
  ivory: "#fffff0",
  khaki: "#f0e68c",
  lavenderblush: "#fff0f5",
  lavender: "#e6e6fa",
  lawngreen: "#7cfc00",
  lemonchiffon: "#fffacd",
  lightblue: "#add8e6",
  lightcoral: "#f08080",
  lightcyan: "#e0ffff",
  lightgoldenrodyellow: "#fafad2",
  lightgray: "#d3d3d3",
  lightgreen: "#90ee90",
  lightgrey: "#d3d3d3",
  lightpink: "#ffb6c1",
  lightsalmon: "#ffa07a",
  lightseagreen: "#20b2aa",
  lightskyblue: "#87cefa",
  lightslategray: "#778899",
  lightslategrey: "#778899",
  lightsteelblue: "#b0c4de",
  lightyellow: "#ffffe0",
  lime: "#00ff00",
  limegreen: "#32cd32",
  linen: "#faf0e6",
  magenta: "#ff00ff",
  maroon: "#800000",
  mediumaquamarine: "#66cdaa",
  mediumblue: "#0000cd",
  mediumorchid: "#ba55d3",
  mediumpurple: "#9370db",
  mediumseagreen: "#3cb371",
  mediumslateblue: "#7b68ee",
  mediumspringgreen: "#00fa9a",
  mediumturquoise: "#48d1cc",
  mediumvioletred: "#c71585",
  midnightblue: "#191970",
  mintcream: "#f5fffa",
  mistyrose: "#ffe4e1",
  moccasin: "#ffe4b5",
  navajowhite: "#ffdead",
  navy: "#000080",
  oldlace: "#fdf5e6",
  olive: "#808000",
  olivedrab: "#6b8e23",
  orange: "#ffa500",
  orangered: "#ff4500",
  orchid: "#da70d6",
  palegoldenrod: "#eee8aa",
  palegreen: "#98fb98",
  paleturquoise: "#afeeee",
  palevioletred: "#db7093",
  papayawhip: "#ffefd5",
  peachpuff: "#ffdab9",
  peru: "#cd853f",
  pink: "#ffc0cb",
  plum: "#dda0dd",
  powderblue: "#b0e0e6",
  purple: "#800080",
  rebeccapurple: "#663399",
  red: "#ff0000",
  rosybrown: "#bc8f8f",
  royalblue: "#4169e1",
  saddlebrown: "#8b4513",
  salmon: "#fa8072",
  sandybrown: "#f4a460",
  seagreen: "#2e8b57",
  seashell: "#fff5ee",
  sienna: "#a0522d",
  silver: "#c0c0c0",
  skyblue: "#87ceeb",
  slateblue: "#6a5acd",
  slategray: "#708090",
  slategrey: "#708090",
  snow: "#fffafa",
  springgreen: "#00ff7f",
  steelblue: "#4682b4",
  tan: "#d2b48c",
  teal: "#008080",
  thistle: "#d8bfd8",
  tomato: "#ff6347",
  turquoise: "#40e0d0",
  violet: "#ee82ee",
  wheat: "#f5deb3",
  white: "#ffffff",
  whitesmoke: "#f5f5f5",
  yellow: "#ffff00",
  yellowgreen: "#9acd32"
};

// node_modules/@ctrl/tinycolor/dist/module/format-input.js
function inputToRGB(color) {
  let rgb = { r: 0, g: 0, b: 0 };
  let a = 1;
  let s = null;
  let v = null;
  let l = null;
  let ok = false;
  let format = false;
  if (typeof color === "string") {
    color = stringInputToObject(color);
  }
  if (typeof color === "object") {
    if (isValidCSSUnit(color.r) && isValidCSSUnit(color.g) && isValidCSSUnit(color.b)) {
      rgb = rgbToRgb(color.r, color.g, color.b);
      ok = true;
      format = String(color.r).substr(-1) === "%" ? "prgb" : "rgb";
    } else if (isValidCSSUnit(color.h) && isValidCSSUnit(color.s) && isValidCSSUnit(color.v)) {
      s = convertToPercentage(color.s);
      v = convertToPercentage(color.v);
      rgb = hsvToRgb(color.h, s, v);
      ok = true;
      format = "hsv";
    } else if (isValidCSSUnit(color.h) && isValidCSSUnit(color.s) && isValidCSSUnit(color.l)) {
      s = convertToPercentage(color.s);
      l = convertToPercentage(color.l);
      rgb = hslToRgb(color.h, s, l);
      ok = true;
      format = "hsl";
    } else if (isValidCSSUnit(color.c) && isValidCSSUnit(color.m) && isValidCSSUnit(color.y) && isValidCSSUnit(color.k)) {
      rgb = cmykToRgb(color.c, color.m, color.y, color.k);
      ok = true;
      format = "cmyk";
    }
    if (Object.prototype.hasOwnProperty.call(color, "a")) {
      a = color.a;
    }
  }
  a = boundAlpha(a);
  return {
    ok,
    format: color.format || format,
    r: Math.min(255, Math.max(rgb.r, 0)),
    g: Math.min(255, Math.max(rgb.g, 0)),
    b: Math.min(255, Math.max(rgb.b, 0)),
    a
  };
}
var CSS_INTEGER = "[-\\+]?\\d+%?";
var CSS_NUMBER = "[-\\+]?\\d*\\.\\d+%?";
var CSS_UNIT = "(?:" + CSS_NUMBER + ")|(?:" + CSS_INTEGER + ")";
var PERMISSIVE_MATCH3 = "[\\s|\\(]+(" + CSS_UNIT + ")[,|\\s]+(" + CSS_UNIT + ")[,|\\s]+(" + CSS_UNIT + ")\\s*\\)?";
var PERMISSIVE_MATCH4 = (
  // eslint-disable-next-line prettier/prettier
  "[\\s|\\(]+(" + CSS_UNIT + ")[,|\\s]+(" + CSS_UNIT + ")[,|\\s]+(" + CSS_UNIT + ")[,|\\s]+(" + CSS_UNIT + ")\\s*\\)?"
);
var matchers = {
  hex: /^[0-9a-fA-F]+$/,
  CSS_UNIT: new RegExp(CSS_UNIT),
  rgb: new RegExp("rgb" + PERMISSIVE_MATCH3),
  rgba: new RegExp("rgba" + PERMISSIVE_MATCH4),
  hsl: new RegExp("hsl" + PERMISSIVE_MATCH3),
  hsla: new RegExp("hsla" + PERMISSIVE_MATCH4),
  hsv: new RegExp("hsv" + PERMISSIVE_MATCH3),
  hsva: new RegExp("hsva" + PERMISSIVE_MATCH4),
  cmyk: new RegExp("cmyk" + PERMISSIVE_MATCH4),
  hex3: /^#?([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})$/,
  hex6: /^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/,
  hex4: /^#?([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})$/,
  hex8: /^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/
};
function stringInputToObject(color) {
  color = color.trim().toLowerCase();
  if (color.length === 0) {
    return false;
  }
  let named = false;
  if (names[color]) {
    color = names[color];
    named = true;
  } else if (color === "transparent") {
    return { r: 0, g: 0, b: 0, a: 0, format: "name" };
  }
  let match;
  if (typeof color === "string" && color.length <= 9 && (color.startsWith("#") || matchers.hex.test(color))) {
    match = matchers.hex8.exec(color);
    if (match) {
      return {
        r: parseIntFromHex(match[1]),
        g: parseIntFromHex(match[2]),
        b: parseIntFromHex(match[3]),
        a: convertHexToDecimal(match[4]),
        format: named ? "name" : "hex8"
      };
    }
    match = matchers.hex6.exec(color);
    if (match) {
      return {
        r: parseIntFromHex(match[1]),
        g: parseIntFromHex(match[2]),
        b: parseIntFromHex(match[3]),
        format: named ? "name" : "hex"
      };
    }
    match = matchers.hex4.exec(color);
    if (match) {
      return {
        r: parseIntFromHex(match[1] + match[1]),
        g: parseIntFromHex(match[2] + match[2]),
        b: parseIntFromHex(match[3] + match[3]),
        a: convertHexToDecimal(match[4] + match[4]),
        format: named ? "name" : "hex8"
      };
    }
    match = matchers.hex3.exec(color);
    if (match) {
      return {
        r: parseIntFromHex(match[1] + match[1]),
        g: parseIntFromHex(match[2] + match[2]),
        b: parseIntFromHex(match[3] + match[3]),
        format: named ? "name" : "hex"
      };
    }
  }
  match = matchers.rgb.exec(color);
  if (match) {
    return { r: match[1], g: match[2], b: match[3] };
  }
  match = matchers.rgba.exec(color);
  if (match) {
    return { r: match[1], g: match[2], b: match[3], a: match[4] };
  }
  match = matchers.hsl.exec(color);
  if (match) {
    return { h: match[1], s: match[2], l: match[3] };
  }
  match = matchers.hsla.exec(color);
  if (match) {
    return { h: match[1], s: match[2], l: match[3], a: match[4] };
  }
  match = matchers.hsv.exec(color);
  if (match) {
    return { h: match[1], s: match[2], v: match[3] };
  }
  match = matchers.hsva.exec(color);
  if (match) {
    return { h: match[1], s: match[2], v: match[3], a: match[4] };
  }
  match = matchers.cmyk.exec(color);
  if (match) {
    return {
      c: match[1],
      m: match[2],
      y: match[3],
      k: match[4]
    };
  }
  return false;
}
function isValidCSSUnit(color) {
  if (typeof color === "number") {
    return !Number.isNaN(color);
  }
  return matchers.CSS_UNIT.test(color);
}

// node_modules/@ctrl/tinycolor/dist/module/index.js
var TinyColor = class _TinyColor {
  constructor(color = "", opts = {}) {
    if (color instanceof _TinyColor) {
      return color;
    }
    if (typeof color === "number") {
      color = numberInputToObject(color);
    }
    this.originalInput = color;
    const rgb = inputToRGB(color);
    this.originalInput = color;
    this.r = rgb.r;
    this.g = rgb.g;
    this.b = rgb.b;
    this.a = rgb.a;
    this.roundA = Math.round(100 * this.a) / 100;
    this.format = opts.format ?? rgb.format;
    this.gradientType = opts.gradientType;
    if (this.r < 1) {
      this.r = Math.round(this.r);
    }
    if (this.g < 1) {
      this.g = Math.round(this.g);
    }
    if (this.b < 1) {
      this.b = Math.round(this.b);
    }
    this.isValid = rgb.ok;
  }
  isDark() {
    return this.getBrightness() < 128;
  }
  isLight() {
    return !this.isDark();
  }
  /**
   * Returns the perceived brightness of the color, from 0-255.
   */
  getBrightness() {
    const rgb = this.toRgb();
    return (rgb.r * 299 + rgb.g * 587 + rgb.b * 114) / 1e3;
  }
  /**
   * Returns the perceived luminance of a color, from 0-1.
   */
  getLuminance() {
    const rgb = this.toRgb();
    let R;
    let G;
    let B;
    const RsRGB = rgb.r / 255;
    const GsRGB = rgb.g / 255;
    const BsRGB = rgb.b / 255;
    if (RsRGB <= 0.03928) {
      R = RsRGB / 12.92;
    } else {
      R = Math.pow((RsRGB + 0.055) / 1.055, 2.4);
    }
    if (GsRGB <= 0.03928) {
      G = GsRGB / 12.92;
    } else {
      G = Math.pow((GsRGB + 0.055) / 1.055, 2.4);
    }
    if (BsRGB <= 0.03928) {
      B = BsRGB / 12.92;
    } else {
      B = Math.pow((BsRGB + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * R + 0.7152 * G + 0.0722 * B;
  }
  /**
   * Returns the alpha value of a color, from 0-1.
   */
  getAlpha() {
    return this.a;
  }
  /**
   * Sets the alpha value on the current color.
   *
   * @param alpha - The new alpha value. The accepted range is 0-1.
   */
  setAlpha(alpha) {
    this.a = boundAlpha(alpha);
    this.roundA = Math.round(100 * this.a) / 100;
    return this;
  }
  /**
   * Returns whether the color is monochrome.
   */
  isMonochrome() {
    const { s } = this.toHsl();
    return s === 0;
  }
  /**
   * Returns the object as a HSVA object.
   */
  toHsv() {
    const hsv = rgbToHsv(this.r, this.g, this.b);
    return { h: hsv.h * 360, s: hsv.s, v: hsv.v, a: this.a };
  }
  /**
   * Returns the hsva values interpolated into a string with the following format:
   * "hsva(xxx, xxx, xxx, xx)".
   */
  toHsvString() {
    const hsv = rgbToHsv(this.r, this.g, this.b);
    const h2 = Math.round(hsv.h * 360);
    const s = Math.round(hsv.s * 100);
    const v = Math.round(hsv.v * 100);
    return this.a === 1 ? `hsv(${h2}, ${s}%, ${v}%)` : `hsva(${h2}, ${s}%, ${v}%, ${this.roundA})`;
  }
  /**
   * Returns the object as a HSLA object.
   */
  toHsl() {
    const hsl = rgbToHsl(this.r, this.g, this.b);
    return { h: hsl.h * 360, s: hsl.s, l: hsl.l, a: this.a };
  }
  /**
   * Returns the hsla values interpolated into a string with the following format:
   * "hsla(xxx, xxx, xxx, xx)".
   */
  toHslString() {
    const hsl = rgbToHsl(this.r, this.g, this.b);
    const h2 = Math.round(hsl.h * 360);
    const s = Math.round(hsl.s * 100);
    const l = Math.round(hsl.l * 100);
    return this.a === 1 ? `hsl(${h2}, ${s}%, ${l}%)` : `hsla(${h2}, ${s}%, ${l}%, ${this.roundA})`;
  }
  /**
   * Returns the hex value of the color.
   * @param allow3Char will shorten hex value to 3 char if possible
   */
  toHex(allow3Char = false) {
    return rgbToHex(this.r, this.g, this.b, allow3Char);
  }
  /**
   * Returns the hex value of the color -with a # prefixed.
   * @param allow3Char will shorten hex value to 3 char if possible
   */
  toHexString(allow3Char = false) {
    return "#" + this.toHex(allow3Char);
  }
  /**
   * Returns the hex 8 value of the color.
   * @param allow4Char will shorten hex value to 4 char if possible
   */
  toHex8(allow4Char = false) {
    return rgbaToHex(this.r, this.g, this.b, this.a, allow4Char);
  }
  /**
   * Returns the hex 8 value of the color -with a # prefixed.
   * @param allow4Char will shorten hex value to 4 char if possible
   */
  toHex8String(allow4Char = false) {
    return "#" + this.toHex8(allow4Char);
  }
  /**
   * Returns the shorter hex value of the color depends on its alpha -with a # prefixed.
   * @param allowShortChar will shorten hex value to 3 or 4 char if possible
   */
  toHexShortString(allowShortChar = false) {
    return this.a === 1 ? this.toHexString(allowShortChar) : this.toHex8String(allowShortChar);
  }
  /**
   * Returns the object as a RGBA object.
   */
  toRgb() {
    return {
      r: Math.round(this.r),
      g: Math.round(this.g),
      b: Math.round(this.b),
      a: this.a
    };
  }
  /**
   * Returns the RGBA values interpolated into a string with the following format:
   * "RGBA(xxx, xxx, xxx, xx)".
   */
  toRgbString() {
    const r = Math.round(this.r);
    const g = Math.round(this.g);
    const b = Math.round(this.b);
    return this.a === 1 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${this.roundA})`;
  }
  /**
   * Returns the object as a RGBA object.
   */
  toPercentageRgb() {
    const fmt = (x) => `${Math.round(bound01(x, 255) * 100)}%`;
    return {
      r: fmt(this.r),
      g: fmt(this.g),
      b: fmt(this.b),
      a: this.a
    };
  }
  /**
   * Returns the RGBA relative values interpolated into a string
   */
  toPercentageRgbString() {
    const rnd = (x) => Math.round(bound01(x, 255) * 100);
    return this.a === 1 ? `rgb(${rnd(this.r)}%, ${rnd(this.g)}%, ${rnd(this.b)}%)` : `rgba(${rnd(this.r)}%, ${rnd(this.g)}%, ${rnd(this.b)}%, ${this.roundA})`;
  }
  toCmyk() {
    return {
      ...rgbToCmyk(this.r, this.g, this.b)
    };
  }
  toCmykString() {
    const { c, m, y, k } = rgbToCmyk(this.r, this.g, this.b);
    return `cmyk(${c}, ${m}, ${y}, ${k})`;
  }
  /**
   * The 'real' name of the color -if there is one.
   */
  toName() {
    if (this.a === 0) {
      return "transparent";
    }
    if (this.a < 1) {
      return false;
    }
    const hex = "#" + rgbToHex(this.r, this.g, this.b, false);
    for (const [key, value] of Object.entries(names)) {
      if (hex === value) {
        return key;
      }
    }
    return false;
  }
  toString(format) {
    const formatSet = Boolean(format);
    format = format ?? this.format;
    let formattedString = false;
    const hasAlpha = this.a < 1 && this.a >= 0;
    const needsAlphaFormat = !formatSet && hasAlpha && (format.startsWith("hex") || format === "name");
    if (needsAlphaFormat) {
      if (format === "name" && this.a === 0) {
        return this.toName();
      }
      return this.toRgbString();
    }
    if (format === "rgb") {
      formattedString = this.toRgbString();
    }
    if (format === "prgb") {
      formattedString = this.toPercentageRgbString();
    }
    if (format === "hex" || format === "hex6") {
      formattedString = this.toHexString();
    }
    if (format === "hex3") {
      formattedString = this.toHexString(true);
    }
    if (format === "hex4") {
      formattedString = this.toHex8String(true);
    }
    if (format === "hex8") {
      formattedString = this.toHex8String();
    }
    if (format === "name") {
      formattedString = this.toName();
    }
    if (format === "hsl") {
      formattedString = this.toHslString();
    }
    if (format === "hsv") {
      formattedString = this.toHsvString();
    }
    if (format === "cmyk") {
      formattedString = this.toCmykString();
    }
    return formattedString || this.toHexString();
  }
  toNumber() {
    return (Math.round(this.r) << 16) + (Math.round(this.g) << 8) + Math.round(this.b);
  }
  clone() {
    return new _TinyColor(this.toString());
  }
  /**
   * Lighten the color a given amount. Providing 100 will always return white.
   * @param amount - valid between 1-100
   */
  lighten(amount = 10) {
    const hsl = this.toHsl();
    hsl.l += amount / 100;
    hsl.l = clamp01(hsl.l);
    return new _TinyColor(hsl);
  }
  /**
   * Brighten the color a given amount, from 0 to 100.
   * @param amount - valid between 1-100
   */
  brighten(amount = 10) {
    const rgb = this.toRgb();
    rgb.r = Math.max(0, Math.min(255, rgb.r - Math.round(255 * -(amount / 100))));
    rgb.g = Math.max(0, Math.min(255, rgb.g - Math.round(255 * -(amount / 100))));
    rgb.b = Math.max(0, Math.min(255, rgb.b - Math.round(255 * -(amount / 100))));
    return new _TinyColor(rgb);
  }
  /**
   * Darken the color a given amount, from 0 to 100.
   * Providing 100 will always return black.
   * @param amount - valid between 1-100
   */
  darken(amount = 10) {
    const hsl = this.toHsl();
    hsl.l -= amount / 100;
    hsl.l = clamp01(hsl.l);
    return new _TinyColor(hsl);
  }
  /**
   * Mix the color with pure white, from 0 to 100.
   * Providing 0 will do nothing, providing 100 will always return white.
   * @param amount - valid between 1-100
   */
  tint(amount = 10) {
    return this.mix("white", amount);
  }
  /**
   * Mix the color with pure black, from 0 to 100.
   * Providing 0 will do nothing, providing 100 will always return black.
   * @param amount - valid between 1-100
   */
  shade(amount = 10) {
    return this.mix("black", amount);
  }
  /**
   * Desaturate the color a given amount, from 0 to 100.
   * Providing 100 will is the same as calling greyscale
   * @param amount - valid between 1-100
   */
  desaturate(amount = 10) {
    const hsl = this.toHsl();
    hsl.s -= amount / 100;
    hsl.s = clamp01(hsl.s);
    return new _TinyColor(hsl);
  }
  /**
   * Saturate the color a given amount, from 0 to 100.
   * @param amount - valid between 1-100
   */
  saturate(amount = 10) {
    const hsl = this.toHsl();
    hsl.s += amount / 100;
    hsl.s = clamp01(hsl.s);
    return new _TinyColor(hsl);
  }
  /**
   * Completely desaturates a color into greyscale.
   * Same as calling `desaturate(100)`
   */
  greyscale() {
    return this.desaturate(100);
  }
  /**
   * Spin takes a positive or negative amount within [-360, 360] indicating the change of hue.
   * Values outside of this range will be wrapped into this range.
   */
  spin(amount) {
    const hsl = this.toHsl();
    const hue = (hsl.h + amount) % 360;
    hsl.h = hue < 0 ? 360 + hue : hue;
    return new _TinyColor(hsl);
  }
  /**
   * Mix the current color a given amount with another color, from 0 to 100.
   * 0 means no mixing (return current color).
   */
  mix(color, amount = 50) {
    const rgb1 = this.toRgb();
    const rgb2 = new _TinyColor(color).toRgb();
    const p = amount / 100;
    const rgba = {
      r: (rgb2.r - rgb1.r) * p + rgb1.r,
      g: (rgb2.g - rgb1.g) * p + rgb1.g,
      b: (rgb2.b - rgb1.b) * p + rgb1.b,
      a: (rgb2.a - rgb1.a) * p + rgb1.a
    };
    return new _TinyColor(rgba);
  }
  analogous(results = 6, slices = 30) {
    const hsl = this.toHsl();
    const part = 360 / slices;
    const ret = [this];
    for (hsl.h = (hsl.h - (part * results >> 1) + 720) % 360; --results; ) {
      hsl.h = (hsl.h + part) % 360;
      ret.push(new _TinyColor(hsl));
    }
    return ret;
  }
  /**
   * taken from https://github.com/infusion/jQuery-xcolor/blob/master/jquery.xcolor.js
   */
  complement() {
    const hsl = this.toHsl();
    hsl.h = (hsl.h + 180) % 360;
    return new _TinyColor(hsl);
  }
  monochromatic(results = 6) {
    const hsv = this.toHsv();
    const { h: h2 } = hsv;
    const { s } = hsv;
    let { v } = hsv;
    const res = [];
    const modification = 1 / results;
    while (results--) {
      res.push(new _TinyColor({ h: h2, s, v }));
      v = (v + modification) % 1;
    }
    return res;
  }
  splitcomplement() {
    const hsl = this.toHsl();
    const { h: h2 } = hsl;
    return [
      this,
      new _TinyColor({ h: (h2 + 72) % 360, s: hsl.s, l: hsl.l }),
      new _TinyColor({ h: (h2 + 216) % 360, s: hsl.s, l: hsl.l })
    ];
  }
  /**
   * Compute how the color would appear on a background
   */
  onBackground(background) {
    const fg = this.toRgb();
    const bg = new _TinyColor(background).toRgb();
    const alpha = fg.a + bg.a * (1 - fg.a);
    return new _TinyColor({
      r: (fg.r * fg.a + bg.r * bg.a * (1 - fg.a)) / alpha,
      g: (fg.g * fg.a + bg.g * bg.a * (1 - fg.a)) / alpha,
      b: (fg.b * fg.a + bg.b * bg.a * (1 - fg.a)) / alpha,
      a: alpha
    });
  }
  /**
   * Alias for `polyad(3)`
   */
  triad() {
    return this.polyad(3);
  }
  /**
   * Alias for `polyad(4)`
   */
  tetrad() {
    return this.polyad(4);
  }
  /**
   * Get polyad colors, like (for 1, 2, 3, 4, 5, 6, 7, 8, etc...)
   * monad, dyad, triad, tetrad, pentad, hexad, heptad, octad, etc...
   */
  polyad(n) {
    const hsl = this.toHsl();
    const { h: h2 } = hsl;
    const result = [this];
    const increment = 360 / n;
    for (let i = 1; i < n; i++) {
      result.push(new _TinyColor({ h: (h2 + i * increment) % 360, s: hsl.s, l: hsl.l }));
    }
    return result;
  }
  /**
   * compare color vs current color
   */
  equals(color) {
    const comparedColor = new _TinyColor(color);
    if (this.format === "cmyk" || comparedColor.format === "cmyk") {
      return this.toCmykString() === comparedColor.toCmykString();
    }
    return this.toRgbString() === comparedColor.toRgbString();
  }
};

// node_modules/element-plus/es/components/button/src/button-custom.mjs
function darken(color, amount = 20) {
  return color.mix("#141414", amount).toString();
}
function useButtonCustomStyle(props) {
  const _disabled = useFormDisabled();
  const ns = useNamespace("button");
  return computed(() => {
    let styles = {};
    let buttonColor = props.color;
    if (buttonColor) {
      const match = buttonColor.match(/var\((.*?)\)/);
      if (match) buttonColor = window.getComputedStyle(window.document.documentElement).getPropertyValue(match[1]);
      const color = new TinyColor(buttonColor);
      const activeBgColor = props.dark ? color.tint(20).toString() : darken(color, 20);
      if (props.plain) {
        styles = ns.cssVarBlock({
          "bg-color": props.dark ? darken(color, 90) : color.tint(90).toString(),
          "text-color": buttonColor,
          "border-color": props.dark ? darken(color, 50) : color.tint(50).toString(),
          "hover-text-color": `var(${ns.cssVarName("color-white")})`,
          "hover-bg-color": buttonColor,
          "hover-border-color": buttonColor,
          "active-bg-color": activeBgColor,
          "active-text-color": `var(${ns.cssVarName("color-white")})`,
          "active-border-color": activeBgColor
        });
        if (_disabled.value) {
          styles[ns.cssVarBlockName("disabled-bg-color")] = props.dark ? darken(color, 90) : color.tint(90).toString();
          styles[ns.cssVarBlockName("disabled-text-color")] = props.dark ? darken(color, 50) : color.tint(50).toString();
          styles[ns.cssVarBlockName("disabled-border-color")] = props.dark ? darken(color, 80) : color.tint(80).toString();
        }
      } else if (props.link || props.text) {
        const hoverColor = props.dark ? darken(color, 30) : color.tint(30).toString();
        styles = ns.cssVarBlock({
          "text-color": buttonColor,
          "hover-text-color": hoverColor,
          "active-text-color": activeBgColor
        });
        if (props.link) {
          styles[ns.cssVarBlockName("hover-link-text-color")] = hoverColor;
          styles[ns.cssVarBlockName("active-color")] = activeBgColor;
        }
        if (_disabled.value) {
          const disabledColor = props.dark ? darken(color, 50) : color.tint(50).toString();
          styles[ns.cssVarBlockName("disabled-bg-color")] = "transparent";
          styles[ns.cssVarBlockName("disabled-text-color")] = disabledColor;
          styles[ns.cssVarBlockName("disabled-border-color")] = "transparent";
        }
      } else {
        const hoverBgColor = props.dark ? darken(color, 30) : color.tint(30).toString();
        const textColor = color.isDark() ? `var(${ns.cssVarName("color-white")})` : `var(${ns.cssVarName("color-black")})`;
        styles = ns.cssVarBlock({
          "bg-color": buttonColor,
          "text-color": textColor,
          "border-color": buttonColor,
          "hover-bg-color": hoverBgColor,
          "hover-text-color": textColor,
          "hover-border-color": hoverBgColor,
          "active-bg-color": activeBgColor,
          "active-border-color": activeBgColor
        });
        if (_disabled.value) {
          const disabledButtonColor = props.dark ? darken(color, 50) : color.tint(50).toString();
          styles[ns.cssVarBlockName("disabled-bg-color")] = disabledButtonColor;
          styles[ns.cssVarBlockName("disabled-text-color")] = props.dark ? "rgba(255, 255, 255, 0.5)" : `var(${ns.cssVarName("color-white")})`;
          styles[ns.cssVarBlockName("disabled-border-color")] = disabledButtonColor;
        }
      }
    }
    return styles;
  });
}

// node_modules/element-plus/es/components/button/src/button.vue_vue_type_script_setup_true_lang.mjs
var button_vue_vue_type_script_setup_true_lang_default = defineComponent({
  name: "ElButton",
  __name: "button",
  props: buttonProps,
  emits: buttonEmits,
  setup(__props, { expose: __expose, emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const buttonStyle = useButtonCustomStyle(props);
    const ns = useNamespace("button");
    const { _ref, _size, _type, _disabled, _props, _plain, _round, _text, _dashed, shouldAddSpace, handleClick } = useButton(props, emit);
    const buttonKls = computed(() => [
      ns.b(),
      ns.m(_type.value),
      ns.m(_size.value),
      ns.is("disabled", _disabled.value),
      ns.is("loading", props.loading),
      ns.is("plain", _plain.value),
      ns.is("round", _round.value),
      ns.is("circle", props.circle),
      ns.is("text", _text.value),
      ns.is("dashed", _dashed.value),
      ns.is("link", props.link),
      ns.is("has-bg", props.bg)
    ]);
    __expose({
      /** @description button html element */
      ref: _ref,
      /** @description button size */
      size: _size,
      /** @description button type */
      type: _type,
      /** @description button disabled */
      disabled: _disabled,
      /** @description whether adding space */
      shouldAddSpace
    });
    return (_ctx, _cache) => {
      return openBlock(), createBlock(resolveDynamicComponent(__props.tag), mergeProps({
        ref_key: "_ref",
        ref: _ref
      }, unref(_props), {
        class: buttonKls.value,
        style: unref(buttonStyle),
        onClick: unref(handleClick)
      }), {
        default: withCtx(() => [__props.loading ? (openBlock(), createElementBlock(Fragment, { key: 0 }, [_ctx.$slots.loading ? renderSlot(_ctx.$slots, "loading", { key: 0 }) : (openBlock(), createBlock(unref(ElIcon), {
          key: 1,
          class: normalizeClass(unref(ns).is("loading"))
        }, {
          default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(__props.loadingIcon)))]),
          _: 1
        }, 8, ["class"]))], 64)) : __props.icon || _ctx.$slots.icon ? (openBlock(), createBlock(unref(ElIcon), { key: 1 }, {
          default: withCtx(() => [__props.icon ? (openBlock(), createBlock(resolveDynamicComponent(__props.icon), { key: 0 })) : renderSlot(_ctx.$slots, "icon", { key: 1 })]),
          _: 3
        })) : createCommentVNode("v-if", true), _ctx.$slots.default ? (openBlock(), createElementBlock("span", {
          key: 2,
          class: normalizeClass({ [unref(ns).em("text", "expand")]: unref(shouldAddSpace) })
        }, [renderSlot(_ctx.$slots, "default")], 2)) : createCommentVNode("v-if", true)]),
        _: 3
      }, 16, [
        "class",
        "style",
        "onClick"
      ]);
    };
  }
});

// node_modules/element-plus/es/components/button/src/button2.mjs
var button_default = button_vue_vue_type_script_setup_true_lang_default;

// node_modules/element-plus/es/components/button/src/button-group.mjs
var buttonGroupProps = {
  /**
  * @description control the size of buttons in this button-group
  */
  size: buttonProps.size,
  /**
  * @description control the type of buttons in this button-group
  */
  type: buttonProps.type,
  /**
  * @description display direction
  */
  direction: {
    type: definePropType(String),
    values: ["horizontal", "vertical"],
    default: "horizontal"
  }
};

// node_modules/element-plus/es/components/button/src/button-group.vue_vue_type_script_setup_true_lang.mjs
var button_group_vue_vue_type_script_setup_true_lang_default = defineComponent({
  name: "ElButtonGroup",
  __name: "button-group",
  props: buttonGroupProps,
  setup(__props) {
    const props = __props;
    provide(buttonGroupContextKey, reactive({
      size: toRef(props, "size"),
      type: toRef(props, "type")
    }));
    const ns = useNamespace("button");
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", { class: normalizeClass([unref(ns).b("group"), unref(ns).bm("group", props.direction)]) }, [renderSlot(_ctx.$slots, "default")], 2);
    };
  }
});

// node_modules/element-plus/es/components/button/src/button-group2.mjs
var button_group_default = button_group_vue_vue_type_script_setup_true_lang_default;

// node_modules/element-plus/es/components/button/index.mjs
var ElButton = withInstall(button_default, { ButtonGroup: button_group_default });
var ElButtonGroup = withNoopInstall(button_group_default);

// node_modules/element-plus/es/utils/vue/vnode.mjs
var PatchFlags = (function(PatchFlags2) {
  PatchFlags2[PatchFlags2["TEXT"] = 1] = "TEXT";
  PatchFlags2[PatchFlags2["CLASS"] = 2] = "CLASS";
  PatchFlags2[PatchFlags2["STYLE"] = 4] = "STYLE";
  PatchFlags2[PatchFlags2["PROPS"] = 8] = "PROPS";
  PatchFlags2[PatchFlags2["FULL_PROPS"] = 16] = "FULL_PROPS";
  PatchFlags2[PatchFlags2["HYDRATE_EVENTS"] = 32] = "HYDRATE_EVENTS";
  PatchFlags2[PatchFlags2["STABLE_FRAGMENT"] = 64] = "STABLE_FRAGMENT";
  PatchFlags2[PatchFlags2["KEYED_FRAGMENT"] = 128] = "KEYED_FRAGMENT";
  PatchFlags2[PatchFlags2["UNKEYED_FRAGMENT"] = 256] = "UNKEYED_FRAGMENT";
  PatchFlags2[PatchFlags2["NEED_PATCH"] = 512] = "NEED_PATCH";
  PatchFlags2[PatchFlags2["DYNAMIC_SLOTS"] = 1024] = "DYNAMIC_SLOTS";
  PatchFlags2[PatchFlags2["HOISTED"] = -1] = "HOISTED";
  PatchFlags2[PatchFlags2["BAIL"] = -2] = "BAIL";
  return PatchFlags2;
})({});

// node_modules/element-plus/es/components/overlay/src/overlay.mjs
var overlayProps = buildProps({
  mask: {
    type: Boolean,
    default: true
  },
  customMaskEvent: Boolean,
  overlayClass: {
    type: definePropType([
      String,
      Array,
      Object,
      Boolean
    ]),
    default: void 0
  },
  zIndex: { type: definePropType([String, Number]) }
});
var overlayEmits = { click: (evt) => evt instanceof MouseEvent };
var BLOCK = "overlay";
var overlay_default = defineComponent({
  name: "ElOverlay",
  props: overlayProps,
  emits: overlayEmits,
  setup(props, { slots, emit }) {
    const ns = useNamespace(BLOCK);
    const onMaskClick = (e) => {
      emit("click", e);
    };
    const { onClick, onMousedown, onMouseup } = useSameTarget(props.customMaskEvent ? void 0 : onMaskClick);
    return () => {
      return props.mask ? createVNode("div", {
        class: [ns.b(), props.overlayClass],
        style: { zIndex: props.zIndex },
        onClick,
        onMousedown,
        onMouseup
      }, [renderSlot(slots, "default")], 14, [
        "onClick",
        "onMouseup",
        "onMousedown"
      ]) : h("div", {
        class: props.overlayClass,
        style: {
          zIndex: props.zIndex,
          position: "fixed",
          top: "0px",
          right: "0px",
          bottom: "0px",
          left: "0px"
        }
      }, [renderSlot(slots, "default")]);
    };
  }
});

// node_modules/element-plus/es/components/overlay/index.mjs
var ElOverlay = overlay_default;

// node_modules/element-plus/es/components/message-box/src/index.vue_vue_type_script_lang.mjs
var index_vue_vue_type_script_lang_default = defineComponent({
  name: "ElMessageBox",
  directives: { TrapFocus },
  components: {
    ElButton,
    ElFocusTrap: focus_trap_default$1,
    ElInput,
    ElOverlay,
    ElIcon,
    ...TypeComponents
  },
  inheritAttrs: false,
  props: {
    buttonSize: {
      type: String,
      validator: isValidComponentSize
    },
    modal: {
      type: Boolean,
      default: true
    },
    lockScroll: {
      type: Boolean,
      default: true
    },
    showClose: {
      type: Boolean,
      default: true
    },
    closeOnClickModal: {
      type: Boolean,
      default: true
    },
    closeOnPressEscape: {
      type: Boolean,
      default: true
    },
    closeOnHashChange: {
      type: Boolean,
      default: true
    },
    center: Boolean,
    draggable: Boolean,
    overflow: Boolean,
    roundButton: Boolean,
    container: {
      type: String,
      default: "body"
    },
    boxType: {
      type: String,
      default: ""
    }
  },
  emits: ["vanish", "action"],
  setup(props, { emit }) {
    const { locale, zIndex, ns, size: btnSize } = useGlobalComponentSettings("message-box", computed(() => props.buttonSize));
    const { t } = locale;
    const { nextZIndex } = zIndex;
    const visible = ref(false);
    const state = reactive({
      autofocus: true,
      beforeClose: null,
      callback: null,
      cancelButtonText: "",
      cancelButtonClass: "",
      confirmButtonText: "",
      confirmButtonClass: "",
      cancelButtonType: "",
      confirmButtonType: "primary",
      customClass: "",
      customStyle: {},
      dangerouslyUseHTMLString: false,
      distinguishCancelAndClose: false,
      icon: "",
      closeIcon: "",
      inputPattern: null,
      inputPlaceholder: "",
      inputType: "text",
      inputValue: "",
      inputValidator: void 0,
      inputErrorMessage: "",
      message: "",
      modalFade: true,
      modalClass: "",
      showCancelButton: false,
      showConfirmButton: true,
      type: "",
      title: void 0,
      showInput: false,
      action: "",
      confirmButtonLoading: false,
      cancelButtonLoading: false,
      confirmButtonLoadingIcon: markRaw(loading_default),
      cancelButtonLoadingIcon: markRaw(loading_default),
      confirmButtonDisabled: false,
      editorErrorMessage: "",
      validateError: false,
      zIndex: nextZIndex()
    });
    const typeClass = computed(() => {
      const type = state.type;
      return { [ns.bm("icon", type)]: type && TypeComponentsMap[type] };
    });
    const contentId = useId();
    const inputId = useId();
    const iconComponent = computed(() => {
      const type = state.type;
      return state.icon || type && TypeComponentsMap[type] || "";
    });
    const hasMessage = computed(() => !!state.message);
    const rootRef = ref();
    const headerRef = ref();
    const focusStartRef = ref();
    const inputRef = ref();
    const confirmRef = ref();
    const confirmButtonClasses = computed(() => state.confirmButtonClass);
    watch(() => state.inputValue, async (val) => {
      await nextTick();
      if (props.boxType === "prompt" && val) validate();
    }, { immediate: true });
    watch(() => visible.value, (val) => {
      if (val) {
        if (props.boxType !== "prompt") if (state.autofocus) focusStartRef.value = confirmRef.value?.$el ?? rootRef.value;
        else focusStartRef.value = rootRef.value;
        state.zIndex = nextZIndex();
      }
      if (props.boxType !== "prompt") return;
      if (val) nextTick().then(() => {
        if (inputRef.value && inputRef.value.$el) if (state.autofocus) focusStartRef.value = getInputElement() ?? rootRef.value;
        else focusStartRef.value = rootRef.value;
      });
      else {
        state.editorErrorMessage = "";
        state.validateError = false;
      }
    });
    const { isDragging } = useDraggable(rootRef, headerRef, computed(() => props.draggable), computed(() => props.overflow));
    onMounted(async () => {
      await nextTick();
      if (props.closeOnHashChange) window.addEventListener("hashchange", doClose);
    });
    onBeforeUnmount(() => {
      if (props.closeOnHashChange) window.removeEventListener("hashchange", doClose);
    });
    function doClose() {
      if (!visible.value) return;
      visible.value = false;
      nextTick(() => {
        if (state.action) emit("action", state.action);
      });
    }
    const handleWrapperClick = () => {
      if (props.closeOnClickModal) handleAction2(state.distinguishCancelAndClose ? "close" : "cancel");
    };
    const overlayEvent = useSameTarget(handleWrapperClick);
    const handleInputEnter = (e) => {
      if (state.inputType !== "textarea" && !inputRef.value?.isComposing) {
        e.preventDefault();
        return handleAction2("confirm");
      }
    };
    const handleAction2 = (action) => {
      if (props.boxType === "prompt" && action === "confirm" && !validate()) return;
      state.action = action;
      if (state.beforeClose) state.beforeClose?.(action, state, doClose);
      else doClose();
    };
    const validate = () => {
      if (props.boxType === "prompt") {
        const inputPattern = state.inputPattern;
        if (inputPattern && !inputPattern.test(state.inputValue || "")) {
          state.editorErrorMessage = state.inputErrorMessage || t("el.messagebox.error");
          state.validateError = true;
          return false;
        }
        const inputValidator = state.inputValidator;
        if (isFunction(inputValidator)) {
          const validateResult = inputValidator(state.inputValue);
          if (validateResult === false) {
            state.editorErrorMessage = state.inputErrorMessage || t("el.messagebox.error");
            state.validateError = true;
            return false;
          }
          if (isString(validateResult)) {
            state.editorErrorMessage = validateResult;
            state.validateError = true;
            return false;
          }
        }
      }
      state.editorErrorMessage = "";
      state.validateError = false;
      return true;
    };
    const getInputElement = () => {
      const inputRefs = inputRef.value?.$refs;
      return inputRefs?.input ?? inputRefs?.textarea;
    };
    const handleClose = () => {
      handleAction2("close");
    };
    const onCloseRequested = () => {
      if (props.closeOnPressEscape) handleClose();
    };
    if (props.lockScroll) useLockscreen(visible, { ns });
    return {
      ...toRefs(state),
      ns,
      overlayEvent,
      visible,
      hasMessage,
      typeClass,
      contentId,
      inputId,
      btnSize,
      iconComponent,
      confirmButtonClasses,
      rootRef,
      focusStartRef,
      headerRef,
      inputRef,
      isDragging,
      confirmRef,
      doClose,
      handleClose,
      onCloseRequested,
      handleWrapperClick,
      handleInputEnter,
      handleAction: handleAction2,
      t
    };
  }
});

// node_modules/element-plus/es/components/message-box/src/index.mjs
var _hoisted_12 = ["aria-label", "aria-describedby"];
var _hoisted_22 = ["aria-label"];
var _hoisted_32 = ["id"];
function _sfc_render2(_ctx, _cache, $props, $setup, $data, $options) {
  const _component_el_icon = resolveComponent("el-icon");
  const _component_el_input = resolveComponent("el-input");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_focus_trap = resolveComponent("el-focus-trap");
  const _component_el_overlay = resolveComponent("el-overlay");
  return openBlock(), createBlock(Transition, {
    name: "fade-in-linear",
    onAfterLeave: _cache[11] || (_cache[11] = ($event) => _ctx.$emit("vanish")),
    persisted: ""
  }, {
    default: withCtx(() => [withDirectives(createVNode(_component_el_overlay, {
      "z-index": _ctx.zIndex,
      "overlay-class": [_ctx.ns.is("message-box"), _ctx.modalClass],
      mask: _ctx.modal
    }, {
      default: withCtx(() => [createBaseVNode("div", {
        role: "dialog",
        "aria-label": _ctx.title,
        "aria-modal": "true",
        "aria-describedby": !_ctx.showInput ? _ctx.contentId : void 0,
        class: normalizeClass(`${_ctx.ns.namespace.value}-overlay-message-box`),
        onClick: _cache[8] || (_cache[8] = (...args) => _ctx.overlayEvent.onClick && _ctx.overlayEvent.onClick(...args)),
        onMousedown: _cache[9] || (_cache[9] = (...args) => _ctx.overlayEvent.onMousedown && _ctx.overlayEvent.onMousedown(...args)),
        onMouseup: _cache[10] || (_cache[10] = (...args) => _ctx.overlayEvent.onMouseup && _ctx.overlayEvent.onMouseup(...args))
      }, [createVNode(_component_el_focus_trap, {
        loop: "",
        trapped: _ctx.visible,
        "focus-trap-el": _ctx.rootRef,
        "focus-start-el": _ctx.focusStartRef,
        onReleaseRequested: _ctx.onCloseRequested
      }, {
        default: withCtx(() => [createBaseVNode("div", {
          ref: "rootRef",
          class: normalizeClass([
            _ctx.ns.b(),
            _ctx.customClass,
            _ctx.ns.is("draggable", _ctx.draggable),
            _ctx.ns.is("dragging", _ctx.isDragging),
            { [_ctx.ns.m("center")]: _ctx.center }
          ]),
          style: normalizeStyle(_ctx.customStyle),
          tabindex: "-1",
          onClick: _cache[7] || (_cache[7] = withModifiers(() => {
          }, ["stop"]))
        }, [
          _ctx.title !== null && _ctx.title !== void 0 ? (openBlock(), createElementBlock("div", {
            key: 0,
            ref: "headerRef",
            class: normalizeClass([_ctx.ns.e("header"), { "show-close": _ctx.showClose }])
          }, [createBaseVNode("div", { class: normalizeClass(_ctx.ns.e("title")) }, [_ctx.iconComponent && _ctx.center ? (openBlock(), createBlock(_component_el_icon, {
            key: 0,
            class: normalizeClass([_ctx.ns.e("status"), _ctx.typeClass])
          }, {
            default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(_ctx.iconComponent)))]),
            _: 1
          }, 8, ["class"])) : createCommentVNode("v-if", true), createBaseVNode("span", null, toDisplayString(_ctx.title), 1)], 2), _ctx.showClose ? (openBlock(), createElementBlock("button", {
            key: 0,
            type: "button",
            class: normalizeClass(_ctx.ns.e("headerbtn")),
            "aria-label": _ctx.t("el.messagebox.close"),
            onClick: _cache[0] || (_cache[0] = ($event) => _ctx.handleAction(_ctx.distinguishCancelAndClose ? "close" : "cancel")),
            onKeydown: _cache[1] || (_cache[1] = withKeys(withModifiers(($event) => _ctx.handleAction(_ctx.distinguishCancelAndClose ? "close" : "cancel"), ["prevent"]), ["enter"]))
          }, [createVNode(_component_el_icon, { class: normalizeClass(_ctx.ns.e("close")) }, {
            default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(_ctx.closeIcon || "close")))]),
            _: 1
          }, 8, ["class"])], 42, _hoisted_22)) : createCommentVNode("v-if", true)], 2)) : createCommentVNode("v-if", true),
          createBaseVNode("div", {
            id: _ctx.contentId,
            class: normalizeClass(_ctx.ns.e("content"))
          }, [createBaseVNode("div", { class: normalizeClass(_ctx.ns.e("container")) }, [_ctx.iconComponent && !_ctx.center && _ctx.hasMessage ? (openBlock(), createBlock(_component_el_icon, {
            key: 0,
            class: normalizeClass([_ctx.ns.e("status"), _ctx.typeClass])
          }, {
            default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(_ctx.iconComponent)))]),
            _: 1
          }, 8, ["class"])) : createCommentVNode("v-if", true), _ctx.hasMessage ? (openBlock(), createElementBlock("div", {
            key: 1,
            class: normalizeClass(_ctx.ns.e("message"))
          }, [renderSlot(_ctx.$slots, "default", {}, () => [!_ctx.dangerouslyUseHTMLString ? (openBlock(), createBlock(resolveDynamicComponent(_ctx.showInput ? "label" : "p"), {
            key: 0,
            for: _ctx.showInput ? _ctx.inputId : void 0,
            textContent: toDisplayString(_ctx.message)
          }, null, 8, ["for", "textContent"])) : (openBlock(), createBlock(resolveDynamicComponent(_ctx.showInput ? "label" : "p"), {
            key: 1,
            for: _ctx.showInput ? _ctx.inputId : void 0,
            innerHTML: _ctx.message
          }, null, 8, ["for", "innerHTML"]))])], 2)) : createCommentVNode("v-if", true)], 2), withDirectives(createBaseVNode("div", { class: normalizeClass(_ctx.ns.e("input")) }, [createVNode(_component_el_input, {
            id: _ctx.inputId,
            ref: "inputRef",
            modelValue: _ctx.inputValue,
            "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => _ctx.inputValue = $event),
            type: _ctx.inputType,
            placeholder: _ctx.inputPlaceholder,
            "aria-invalid": _ctx.validateError,
            class: normalizeClass({ invalid: _ctx.validateError }),
            onKeydown: withKeys(_ctx.handleInputEnter, ["enter"])
          }, null, 8, [
            "id",
            "modelValue",
            "type",
            "placeholder",
            "aria-invalid",
            "class",
            "onKeydown"
          ]), createBaseVNode("div", {
            class: normalizeClass(_ctx.ns.e("errormsg")),
            style: normalizeStyle({ visibility: !!_ctx.editorErrorMessage ? "visible" : "hidden" })
          }, toDisplayString(_ctx.editorErrorMessage), 7)], 2), [[vShow, _ctx.showInput]])], 10, _hoisted_32),
          _ctx.showCancelButton || _ctx.showConfirmButton ? (openBlock(), createElementBlock("div", {
            key: 1,
            class: normalizeClass(_ctx.ns.e("btns"))
          }, [_ctx.showCancelButton ? (openBlock(), createBlock(_component_el_button, {
            key: 0,
            type: _ctx.cancelButtonType === "text" ? "" : _ctx.cancelButtonType,
            text: _ctx.cancelButtonType === "text",
            loading: _ctx.cancelButtonLoading,
            "loading-icon": _ctx.cancelButtonLoadingIcon,
            class: normalizeClass([_ctx.cancelButtonClass]),
            round: _ctx.roundButton,
            size: _ctx.btnSize,
            onClick: _cache[3] || (_cache[3] = ($event) => _ctx.handleAction("cancel")),
            onKeydown: _cache[4] || (_cache[4] = withKeys(withModifiers(($event) => _ctx.handleAction("cancel"), ["prevent"]), ["enter"]))
          }, {
            default: withCtx(() => [createTextVNode(toDisplayString(_ctx.cancelButtonText || _ctx.t("el.messagebox.cancel")), 1)]),
            _: 1
          }, 8, [
            "type",
            "text",
            "loading",
            "loading-icon",
            "class",
            "round",
            "size"
          ])) : createCommentVNode("v-if", true), withDirectives(createVNode(_component_el_button, {
            ref: "confirmRef",
            type: _ctx.confirmButtonType === "text" ? "" : _ctx.confirmButtonType,
            text: _ctx.confirmButtonType === "text",
            loading: _ctx.confirmButtonLoading,
            "loading-icon": _ctx.confirmButtonLoadingIcon,
            class: normalizeClass([_ctx.confirmButtonClasses]),
            round: _ctx.roundButton,
            disabled: _ctx.confirmButtonDisabled,
            size: _ctx.btnSize,
            onClick: _cache[5] || (_cache[5] = ($event) => _ctx.handleAction("confirm")),
            onKeydown: _cache[6] || (_cache[6] = withKeys(withModifiers(($event) => _ctx.handleAction("confirm"), ["prevent"]), ["enter"]))
          }, {
            default: withCtx(() => [createTextVNode(toDisplayString(_ctx.confirmButtonText || _ctx.t("el.messagebox.confirm")), 1)]),
            _: 1
          }, 8, [
            "type",
            "text",
            "loading",
            "loading-icon",
            "class",
            "round",
            "disabled",
            "size"
          ]), [[vShow, _ctx.showConfirmButton]])], 2)) : createCommentVNode("v-if", true)
        ], 6)]),
        _: 3
      }, 8, [
        "trapped",
        "focus-trap-el",
        "focus-start-el",
        "onReleaseRequested"
      ])], 42, _hoisted_12)]),
      _: 3
    }, 8, [
      "z-index",
      "overlay-class",
      "mask"
    ]), [[vShow, _ctx.visible]])]),
    _: 3
  });
}
var src_default = _plugin_vue_export_helper_default(index_vue_vue_type_script_lang_default, [["render", _sfc_render2]]);

// node_modules/element-plus/es/components/message-box/src/messageBox.mjs
var messageInstance = /* @__PURE__ */ new Map();
var getAppendToElement = (props) => {
  let appendTo = document.body;
  if (props.appendTo) {
    if (isString(props.appendTo)) appendTo = document.querySelector(props.appendTo);
    if (isElement(props.appendTo)) appendTo = props.appendTo;
    if (!isElement(appendTo)) {
      debugWarn("ElMessageBox", "the appendTo option is not an HTMLElement. Falling back to document.body.");
      appendTo = document.body;
    }
  }
  return appendTo;
};
var handleAction = (vnode, action) => {
  const vm = vnode.component?.proxy;
  return () => vm.handleAction(action);
};
var initInstance = (props, container, appContext = null) => {
  const vnode = createVNode(src_default, props, isFunction(props.message) || isVNode(props.message) ? { default: isFunction(props.message) ? () => props.message({
    confirm: handleAction(vnode, "confirm"),
    cancel: handleAction(vnode, "cancel"),
    close: handleAction(vnode, "close")
  }) : () => props.message } : null);
  vnode.appContext = appContext;
  render(vnode, container);
  getAppendToElement(props).appendChild(container.firstElementChild);
  return vnode.component;
};
var genContainer = () => {
  return document.createElement("div");
};
var showMessage = (options, appContext) => {
  const container = genContainer();
  options.onVanish = () => {
    render(null, container);
    messageInstance.delete(vm);
  };
  options.onAction = (action) => {
    const currentMsg = messageInstance.get(vm);
    let resolve;
    if (options.showInput) resolve = {
      value: vm.inputValue,
      action
    };
    else resolve = action;
    if (options.callback) options.callback(resolve, instance.proxy);
    else if (action === "cancel" || action === "close") if (options.distinguishCancelAndClose && action !== "cancel") currentMsg.reject("close");
    else currentMsg.reject("cancel");
    else currentMsg.resolve(resolve);
  };
  const instance = initInstance(options, container, appContext);
  const vm = instance.proxy;
  for (const prop in options) if (hasOwn(options, prop) && !hasOwn(vm.$props, prop)) if (prop === "closeIcon" && isObject(options[prop])) vm[prop] = markRaw(options[prop]);
  else vm[prop] = options[prop];
  vm.visible = true;
  return vm;
};
function MessageBox(options, appContext = null) {
  if (!isClient) return Promise.reject();
  let callback;
  if (isString(options) || isVNode(options)) options = { message: options };
  else callback = options.callback;
  return new Promise((resolve, reject) => {
    const vm = showMessage(options, appContext ?? MessageBox._context);
    messageInstance.set(vm, {
      options,
      callback,
      resolve,
      reject
    });
  });
}
var MESSAGE_BOX_VARIANTS = [
  "alert",
  "confirm",
  "prompt"
];
var MESSAGE_BOX_DEFAULT_OPTS = {
  alert: {
    closeOnPressEscape: false,
    closeOnClickModal: false
  },
  confirm: { showCancelButton: true },
  prompt: {
    showCancelButton: true,
    showInput: true
  }
};
MESSAGE_BOX_VARIANTS.forEach((boxType) => {
  MessageBox[boxType] = messageBoxFactory(boxType);
});
function messageBoxFactory(boxType) {
  return (message, title, options, appContext) => {
    let titleOrOpts = "";
    if (isObject(title)) {
      options = title;
      titleOrOpts = "";
    } else if (isUndefined(title)) titleOrOpts = "";
    else titleOrOpts = title;
    return MessageBox(Object.assign({
      title: titleOrOpts,
      message,
      type: "",
      ...MESSAGE_BOX_DEFAULT_OPTS[boxType]
    }, options, { boxType }), appContext);
  };
}
MessageBox.close = () => {
  messageInstance.forEach((_, vm) => {
    vm.doClose();
  });
  messageInstance.clear();
};
MessageBox._context = null;

// node_modules/element-plus/es/components/message-box/index.mjs
var _MessageBox = MessageBox;
_MessageBox.install = (app) => {
  _MessageBox._context = app._context;
  app.config.globalProperties.$msgbox = _MessageBox;
  app.config.globalProperties.$messageBox = _MessageBox;
  app.config.globalProperties.$alert = _MessageBox.alert;
  app.config.globalProperties.$confirm = _MessageBox.confirm;
  app.config.globalProperties.$prompt = _MessageBox.prompt;
};
var ElMessageBox = _MessageBox;
export {
  ElMessageBox,
  _MessageBox as default
};
//# sourceMappingURL=element-plus_es_components_message-box_index__mjs.js.map
