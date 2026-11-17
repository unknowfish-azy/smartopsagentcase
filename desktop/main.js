/**
 * SmartOpsAgent 桌面悬浮伴侣 —— Electron 主进程。
 *
 * 职责（P0）：
 * - 悬浮球窗口（置顶/透明/可拖拽）+ 伴侣面板窗口 + 托盘
 * - 圈选截屏（capture.js）→ 图片注入面板
 * - ai-service SSE 代理（ai-client.js）：主进程直发，绕开 CORS，事件经 IPC 转发面板
 *
 * 鉴权（P0）：ai-service 需开启 CHAT_ALLOW_ANONYMOUS=true（本地/内网联调模式），
 * 桌面壳暂无法签发短时 run 令牌（SEC-01 令牌由 Java 边缘签发，单次 run 有效）。
 */

const { app, BrowserWindow, ipcMain, Tray, Menu, screen, nativeImage } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { startSelection, captureRegion, getSelectionDisplay } = require('./capture');
const { streamChat, abortStream, isAbort } = require('./ai-client');

const BALL_SIZE = 64;
const PANEL_SIZE = { width: 360, height: 500 };
const DEFAULT_AI_BASE_URL = process.env.SMARTOPS_AI_URL || 'http://localhost:8001';

/** userData/settings.json：仅存非敏感偏好（AI 地址、默认提问语）。 */
const settingsPath = () => path.join(app.getPath('userData'), 'settings.json');

function loadSettings() {
  try {
    const raw = JSON.parse(fs.readFileSync(settingsPath(), 'utf-8'));
    return {
      aiBaseUrl: String(raw.aiBaseUrl || DEFAULT_AI_BASE_URL).replace(/\/+$/, ''),
      defaultPrompt: String(raw.defaultPrompt || '请解答截图中的内容'),
    };
  } catch {
    return { aiBaseUrl: DEFAULT_AI_BASE_URL, defaultPrompt: '请解答截图中的内容' };
  }
}

function saveSettings(patch) {
  const next = { ...loadSettings(), ...patch };
  fs.mkdirSync(path.dirname(settingsPath()), { recursive: true });
  fs.writeFileSync(settingsPath(), JSON.stringify(next, null, 2), 'utf-8');
  return next;
}

let tray = null;
let ballWin = null;
let panelWin = null;
let iconImage = null;
const getSettings = () => loadSettings();

function createBall() {
  ballWin = new BrowserWindow({
    width: BALL_SIZE,
    height: BALL_SIZE,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    hasShadow: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  ballWin.setAlwaysOnTop(true, 'screen-saver');
  // 初始位置：主屏右上角，避开任务栏
  const { workArea } = screen.getPrimaryDisplay();
  ballWin.setPosition(workArea.x + workArea.width - BALL_SIZE - 24, workArea.y + 120);
  ballWin.loadFile(path.join(__dirname, 'renderer', 'ball.html'));
}

function createPanel() {
  panelWin = new BrowserWindow({
    width: PANEL_SIZE.width,
    height: PANEL_SIZE.height,
    minWidth: 300,
    minHeight: 380,
    frame: false,
    transparent: true,
    resizable: true,
    hasShadow: true,
    skipTaskbar: true,
    alwaysOnTop: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  panelWin.setAlwaysOnTop(true, 'floating');
  panelWin.loadFile(path.join(__dirname, 'renderer', 'panel.html'));
  panelWin.on('blur', () => {
    // 点击面板外部时收起（截图选区/流式输出期间不收起）
    if (panelWin.isVisible() && !panelWin.webContents.isDevToolsOpened()) {
      panelWin.webContents.send('panel:blur-check');
    }
  });
}

/** 面板贴近悬浮球弹出，并夹紧到工作区内。 */
function showPanel() {
  if (!panelWin || panelWin.isDestroyed()) return;
  const ball = ballWin && !ballWin.isDestroyed() ? ballWin.getBounds() : null;
  const display = screen.getDisplayNearestPoint(ball ? { x: ball.x, y: ball.y } : screen.getCursorScreenPoint());
  const wa = display.workArea;
  let x = ball ? ball.x + BALL_SIZE + 10 : wa.x + wa.width - PANEL_SIZE.width - 20;
  let y = ball ? ball.y - 40 : wa.y + 80;
  x = Math.min(Math.max(wa.x, x), wa.x + wa.width - PANEL_SIZE.width);
  y = Math.min(Math.max(wa.y, y), wa.y + wa.height - PANEL_SIZE.height);
  panelWin.setBounds({ x, y, width: PANEL_SIZE.width, height: PANEL_SIZE.height });
  panelWin.show();
  panelWin.focus();
  panelWin.webContents.send('panel:shown');
}

function hidePanel() {
  if (panelWin && !panelWin.isDestroyed() && panelWin.isVisible()) panelWin.hide();
}

function setBallState(state) {
  if (ballWin && !ballWin.isDestroyed()) ballWin.webContents.send('ball:state', state);
}

function createTray() {
  tray = new Tray(iconImage.resize({ width: 16, height: 16 }));
  tray.setToolTip('SmartOps 智维伴侣');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '显示悬浮球', click: () => ballWin && ballWin.show() },
    { label: '打开对话面板', click: showPanel },
    { type: 'separator' },
    { label: '退出', click: () => app.quit() },
  ]));
  tray.on('click', () => ballWin && ballWin.show());
}

function popupBallMenu() {
  if (!ballWin) return;
  const b = ballWin.getBounds();
  const menu = Menu.buildFromTemplate([
    { label: '展开对话', click: showPanel },
    { label: '截屏提问', click: () => startSelection(ballWin, { onDone: handleCaptureDone }) },
    { type: 'separator' },
    { label: '退出悬浮球', click: () => app.quit() },
  ]);
  menu.popup({ window: ballWin, x: 0, y: b.height + 4 });
}

/** 圈选完成：裁剪截屏 → 打开面板 → 注入待发送图片。 */
async function handleCaptureDone(rectDip) {
  if (!rectDip) return;
  try {
    // 选区坐标相对创建遮罩时的显示器，必须用同一 display 裁剪
    const display = getSelectionDisplay()
      || screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
    const dataUrl = await captureRegion(rectDip, display);
    if (!dataUrl) return;
    showPanel();
    panelWin.webContents.send('panel:capture', { dataUrl });
  } catch (err) {
    showPanel();
    panelWin.webContents.send('panel:capture-error', {
      message: `截屏失败：${err && err.message ? err.message : err}`,
    });
  }
}

function registerIpc() {
  // —— 悬浮球手势 ——
  ipcMain.on('ball:menu', popupBallMenu);
  ipcMain.on('ball:panel-toggle', () => {
    if (!panelWin) return;
    if (panelWin.isVisible()) hidePanel(); else showPanel();
  });
  ipcMain.on('ball:capture', () => startSelection(ballWin, { onDone: handleCaptureDone }));
  ipcMain.on('ball:move-start', () => {
    if (!ballWin) return;
    const b = ballWin.getBounds();
    const cursor = screen.getCursorScreenPoint();
    ballWin.__drag = { offX: cursor.x - b.x, offY: cursor.y - b.y };
    hidePanel(); // 拖拽期间收起面板，避免遮挡
  });
  ipcMain.on('ball:move-by', () => {
    if (!ballWin || !ballWin.__drag) return;
    const { x, y } = screen.getCursorScreenPoint();
    ballWin.setPosition(x - ballWin.__drag.offX, y - ballWin.__drag.offY);
  });
  ipcMain.on('ball:move-end', () => { if (ballWin) ballWin.__drag = null; });

  // —— 面板 ——
  ipcMain.on('panel:hide', hidePanel);
  ipcMain.on('panel:stay', () => { /* 面板内交互占位，防止误收起 */ });
  ipcMain.handle('settings:get', () => getSettings());
  ipcMain.handle('settings:set', (_e, patch) => saveSettings(patch || {}));
  ipcMain.handle('app:version', () => app.getVersion());

  // —— 截屏选区 ——
  ipcMain.on('overlay:cancel', () => require('./capture').cancelSelection());
  ipcMain.on('overlay:done', (_e, rect) => require('./capture').finishSelection(rect));

  // —— AI 流式对话（主进程直发 SSE，绕开 CORS；事件转发面板） ——
  ipcMain.handle('ai:chat', async (_e, payload) => {
    const { message, imageData = [], conversationId } = payload || {};
    if (!message || !String(message).trim()) {
      panelWin && panelWin.webContents.send('panel:ai-event', { type: 'error', data: { message: '消息不能为空' } });
      return;
    }
    setBallState('thinking');
    try {
      await streamChat({
        baseUrl: getSettings().aiBaseUrl,
        message: String(message),
        imageData: Array.isArray(imageData) ? imageData : [],
        conversationId: conversationId ? String(conversationId) : undefined,
      }, (evt) => {
        if (panelWin && !panelWin.isDestroyed()) {
          panelWin.webContents.send('panel:ai-event', evt);
        }
        if (evt.type === 'done' || evt.type === 'error') setBallState('idle');
      });
    } catch (err) {
      setBallState('idle');
      if (panelWin && !panelWin.isDestroyed()) {
        if (isAbort(err)) {
          // 用户主动停止：保留已输出的部分回答，不给错误气泡
          panelWin.webContents.send('panel:ai-event', { type: 'done', data: {} });
        } else {
          panelWin.webContents.send('panel:ai-event', {
            type: 'error',
            data: { message: err && err.message ? err.message : String(err) },
          });
        }
      }
    }
  });
  ipcMain.handle('ai:abort', () => abortStream());
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  // 透明置顶窗口在远程桌面/虚拟机/无 GPU 环境下用软件渲染更稳，
  // 避免 GPU 进程初始化失败导致启动即崩溃
  app.disableHardwareAcceleration();

  app.on('second-instance', () => ballWin && ballWin.show());

  app.whenReady().then(() => {
    iconImage = nativeImage.createFromPath(path.join(__dirname, 'assets', 'icon.png'));
    registerIpc();
    createTray();
    createPanel();
    createBall();
  });

  app.on('window-all-closed', () => {
    // 托盘常驻：仅当托盘也被销毁时才退出（P0 简化：托盘存在则不退出）
    if (!tray) app.quit();
  });
}
