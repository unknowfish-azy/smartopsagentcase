/**
 * 伴侣面板渲染层（P0）。
 * - 流式渲染 thinking/token/done/error 事件（与 Web 端 AiChatPanel 同语义）
 * - 截屏提问：pending 附件 + Enter 发送（空输入用默认提问语）
 * - 视觉不可用等错误如实展示（继承 ai-service「带图绝不降级 mock」铁律）
 */
const $ = (id) => document.getElementById(id);
const messagesEl = $('messages');
const inputEl = $('input');
const attachBar = $('attachBar');
const attachThumb = $('attachThumb');
const statusDot = $('statusDot');
const statusText = $('statusText');
const btnSend = $('btnSend');
const btnStop = $('btnStop');
const btnCapture = $('btnCapture');
const settingsPop = $('settingsPop');

const api = window.smartops.panel;

let conversationId = crypto.randomUUID();
let pendingImage = null;      // dataURL | null
let streaming = false;
let streamEl = null;          // 当前流式 assistant 气泡
let thinkingEl = null;        // 当前思考行
let metaEl = null;

/* ---------- 工具 ---------- */

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function setStatus(state, text) {
  statusDot.className = `panel__dot${state === 'thinking' ? ' panel__dot--thinking' : state === 'error' ? ' panel__dot--error' : ''}`;
  statusText.textContent = text;
}

function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addUserMessage({ text, image }) {
  const el = document.createElement('div');
  el.className = 'msg msg--user';
  if (image) {
    const img = document.createElement('img');
    img.className = 'msg__thumb';
    img.src = image;
    img.alt = '截屏';
    img.addEventListener('click', () => openLightbox(image));
    el.appendChild(img);
  }
  if (text) el.appendChild(document.createTextNode(text));
  messagesEl.appendChild(el);
  scrollBottom();
}

function addErrorBubble(message) {
  const el = document.createElement('div');
  el.className = 'msg msg--error';
  el.textContent = `⚠ ${message}`;
  messagesEl.appendChild(el);
  scrollBottom();
}

function addMetaLine(text) {
  const el = document.createElement('div');
  el.className = 'msg msg--meta';
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollBottom();
}

function startAssistantBubble() {
  const el = document.createElement('div');
  el.className = 'msg msg--assistant msg__stream-caret';
  el.textContent = '';
  messagesEl.appendChild(el);
  streamEl = el;
  scrollBottom();
}

function showThinking() {
  if (thinkingEl && thinkingEl.isConnected) return;
  const el = document.createElement('div');
  el.className = 'msg msg--assistant';
  el.innerHTML = '<span class="msg__thinking"><span class="dot-pulse"></span>识别屏幕内容并思考中…</span>';
  messagesEl.appendChild(el);
  thinkingEl = el;
  scrollBottom();
}

function clearThinking() {
  if (thinkingEl && thinkingEl.isConnected) thinkingEl.remove();
  thinkingEl = null;
}

/* ---------- 发送 ---------- */

async function send() {
  if (streaming) return;
  const image = pendingImage;
  const typed = inputEl.value.trim();
  if (!typed && !image) return;
  const message = typed || apiSettings.defaultPrompt || '请解答截图中的内容';

  inputEl.value = '';
  autoGrow();
  setPendingImage(null);
  addUserMessage({ text: typed, image });
  startAssistantBubble();
  showThinking();
  streaming = true;
  setStatus('thinking', '思考中…');
  btnSend.disabled = true;
  btnStop.hidden = false;

  await api.chat({
    message,
    imageData: image ? [image] : [],
    conversationId,
  });
  // 结束/错误事件由 onAiEvent 统一收尾
}

function finishStream() {
  streaming = false;
  btnSend.disabled = false;
  btnStop.hidden = true;
  clearThinking();
  if (streamEl) {
    streamEl.classList.remove('msg__stream-caret');
    streamEl = null;
  }
  if (thinkingEl) clearThinking();
}

/* ---------- AI 事件 ---------- */

api.onAiEvent(({ type, data }) => {
  if (type === 'thinking') {
    showThinking();
    return;
  }
  if (type === 'token') {
    clearThinking();
    if (!streamEl) startAssistantBubble();
    streamEl.textContent += data?.delta || '';
    scrollBottom();
    return;
  }
  if (type === 'inspection') return; // P0 不展示检索细节
  if (type === 'run') return;

  if (type === 'done') {
    finishStream();
    setStatus('idle', '空闲');
    const perf = data?.metadata?.llm_perf || data?.llm_perf;
    if (perf && (perf.ttft_ms != null || perf.model)) {
      const parts = [];
      if (perf.model) parts.push(perf.model);
      if (perf.multimodal) parts.push('视觉');
      if (perf.ttft_ms != null) parts.push(`首字 ${perf.ttft_ms}ms`);
      if (perf.total_ms != null) parts.push(`总耗时 ${perf.total_ms}ms`);
      if (perf.provider) parts.push(perf.provider);
      addMetaLine(parts.join(' · '));
    }
    return;
  }

  if (type === 'error') {
    finishStream();
    setStatus('error', '出错');
    // 如实报错（视觉模型未配置 / 连接失败 / 鉴权失败等），绝不伪造回答
    addErrorBubble(data?.message || 'AI 请求失败，请重试');
    setTimeout(() => setStatus('idle', '空闲'), 2500);
  }
});

/* ---------- 截屏附件 ---------- */

function setPendingImage(dataUrl) {
  pendingImage = dataUrl;
  if (dataUrl) {
    attachThumb.src = dataUrl;
    attachBar.hidden = false;
    inputEl.placeholder = '可补充说明，回车发送；留空则使用默认提问语';
  } else {
    attachBar.hidden = true;
    inputEl.placeholder = '输入问题，或点 ✂ 截屏提问';
  }
}

api.onCapture(({ dataUrl }) => setPendingImage(dataUrl));
api.onCaptureError(({ message }) => addErrorBubble(message));

/* ---------- 设置 ---------- */

let apiSettings = { aiBaseUrl: 'http://localhost:8001', defaultPrompt: '请解答截图中的内容' };

async function loadSettings() {
  apiSettings = await api.getSettings();
  $('setUrl').value = apiSettings.aiBaseUrl;
  $('setPrompt').value = apiSettings.defaultPrompt;
}

$('btnSettings').addEventListener('click', () => { settingsPop.hidden = !settingsPop.hidden; });
$('btnSettingsSave').addEventListener('click', async () => {
  apiSettings = await api.setSettings({
    aiBaseUrl: $('setUrl').value.trim(),
    defaultPrompt: $('setPrompt').value.trim() || '请解答截图中的内容',
  });
  $('setUrl').value = apiSettings.aiBaseUrl;
  $('setPrompt').value = apiSettings.defaultPrompt;
  const msg = $('settingsMsg');
  msg.textContent = '已保存';
  setTimeout(() => { msg.textContent = ''; settingsPop.hidden = true; }, 900);
});

/* ---------- 灯箱 ---------- */

function openLightbox(src) {
  $('lightboxImg').src = src;
  $('lightbox').hidden = false;
}
$('lightbox').addEventListener('click', () => { $('lightbox').hidden = true; });

/* ---------- 输入与按钮 ---------- */

function autoGrow() {
  inputEl.style.height = 'auto';
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 96)}px`;
}

inputEl.addEventListener('input', autoGrow);
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
});
btnSend.addEventListener('click', send);
btnStop.addEventListener('click', () => api.abort());
btnCapture.addEventListener('click', () => window.smartops.ball.capture());
$('btnAttachRemove').addEventListener('click', () => setPendingImage(null));
$('btnClose').addEventListener('click', () => api.hide());

/* 面板内点击时不因 blur 收起 */
document.addEventListener('mousedown', () => api.stay());

/* 失焦收起（主进程 blur 通知）：设置弹层打开或灯箱打开时不收起 */
api.onBlurCheck(() => {
  if (!settingsPop.hidden || !$('lightbox').hidden) return;
  api.hide();
});

/* 面板被唤起时聚焦输入 */
api.onShown(() => {
  inputEl.focus();
  autoGrow();
});

loadSettings();
setStatus('idle', '空闲');
