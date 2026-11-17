/**
 * 预加载脚本：三个窗口（悬浮球/面板/选区遮罩）共用同一 preload，
 * contextBridge 暴露的 API 按窗口职责划分命名空间，渲染层无 Node 能力。
 */
const { contextBridge, ipcRenderer } = require('electron');

const ON_CHANNELS = [
  'ball:state',
  'panel:capture',
  'panel:capture-error',
  'panel:ai-event',
  'panel:shown',
  'panel:blur-check',
];

contextBridge.exposeInMainWorld('smartops', {
  // —— 悬浮球手势 ——
  ball: {
    menu: () => ipcRenderer.send('ball:menu'),
    togglePanel: () => ipcRenderer.send('ball:panel-toggle'),
    capture: () => ipcRenderer.send('ball:capture'),
    moveStart: () => ipcRenderer.send('ball:move-start'),
    moveBy: (dx, dy) => ipcRenderer.send('ball:move-by', dx, dy),
    moveEnd: () => ipcRenderer.send('ball:move-end'),
    onState: (cb) => ipcRenderer.on('ball:state', (_e, state) => cb(state)),
  },

  // —— 伴侣面板 ——
  panel: {
    hide: () => ipcRenderer.send('panel:hide'),
    stay: () => ipcRenderer.send('panel:stay'),
    chat: (payload) => ipcRenderer.invoke('ai:chat', payload),
    abort: () => ipcRenderer.invoke('ai:abort'),
    getSettings: () => ipcRenderer.invoke('settings:get'),
    setSettings: (patch) => ipcRenderer.invoke('settings:set', patch),
    version: () => ipcRenderer.invoke('app:version'),
    onCapture: (cb) => ipcRenderer.on('panel:capture', (_e, p) => cb(p)),
    onCaptureError: (cb) => ipcRenderer.on('panel:capture-error', (_e, p) => cb(p)),
    onAiEvent: (cb) => ipcRenderer.on('panel:ai-event', (_e, p) => cb(p)),
    onShown: (cb) => ipcRenderer.on('panel:shown', () => cb()),
    onBlurCheck: (cb) => ipcRenderer.on('panel:blur-check', () => cb()),
  },

  // —— 截屏选区遮罩 ——
  overlay: {
    done: (rect) => ipcRenderer.send('overlay:done', rect),
    cancel: () => ipcRenderer.send('overlay:cancel'),
  },
});
