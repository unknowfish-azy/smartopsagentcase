import assert from 'node:assert/strict'
import test from 'node:test'

import { renderMarkdown } from '../src/components/ai/markdown.js'

test('纯文本保持为单个段落，不引入任何标签注入', () => {
  assert.equal(renderMarkdown('已收到：诊断 CPU 过载'), '<p>已收到：诊断 CPU 过载</p>')
})

test('HTML 输入全部转义，script/img 注入无效', () => {
  const out = renderMarkdown('<script>alert(1)</script> and <img src=x onerror=alert(1)>')
  assert.doesNotMatch(out, /<script|<img/)
  assert.match(out, /&lt;script&gt;/)
})

test('加粗、行内代码与链接按子集转换，链接仅放行 http(s)', () => {
  const out = renderMarkdown('先看 **传播数** 指标，再跑 `nvidia-smi`，参考 [官方文档](https://docs.example.com/a) 与 [坏链接](javascript:alert(1))')
  assert.match(out, /<strong>传播数<\/strong>/)
  assert.match(out, /<code>nvidia-smi<\/code>/)
  assert.match(out, /<a href="https:\/\/docs\.example\.com\/a" target="_blank" rel="noopener noreferrer">官方文档<\/a>/)
  // 非法协议链接不被转换成 <a>，只保留原文字面（不产生可点击入口）
  assert.doesNotMatch(out, /<a href="javascript:/)
})

test('有序列表、无序列表与围栏代码块转成对应块级结构', () => {
  const out = renderMarkdown('1. **传播数**：看吞吐\n2. 查利用率\n- 指标 A\n- 指标 B\n```bash\nnvidia-smi dmon -s u\n<script>x</script>\n```')
  assert.match(out, /<ol><li><strong>传播数<\/strong>：看吞吐<\/li><li>查利用率<\/li><\/ol>/)
  assert.match(out, /<ul><li>指标 A<\/li><li>指标 B<\/li><\/ul>/)
  assert.match(out, /<pre><code>nvidia-smi dmon -s u\n&lt;script&gt;x&lt;\/script&gt;<\/code><\/pre>/)
})

test('围栏紧跟段落/列表时不被吸入段落（截图运维指令场景）', () => {
  const source = [
    '以下是一些简单的运维操作指令，适用于日常运维工作：',
    '1. **查看系统状态**',
    '```bash',
    'systemctl status <service>',
    '```',
    '- 用于查看某个服务是否正在运行。',
    '2. **查看进程信息**',
    '```bash',
    'ps aux',
    '```'
  ].join('\n')
  const out = renderMarkdown(source)
  assert.match(out, /<p>以下是一些简单的运维操作指令，适用于日常运维工作：<\/p>/)
  assert.match(out, /<ol><li><strong>查看系统状态<\/strong><\/li><\/ol>/)
  assert.match(out, /<pre><code>systemctl status &lt;service&gt;<\/code><\/pre>/)
  assert.match(out, /<ul><li>用于查看某个服务是否正在运行。<\/li><\/ul>/)
  assert.match(out, /<ol><li><strong>查看进程信息<\/strong><\/li><\/ol>/)
  assert.match(out, /<pre><code>ps aux<\/code><\/pre>/)
  assert.ok(!out.includes('``<code>'), '连续反引号不得被行内代码正则错误配对')
  assert.doesNotMatch(out, /<p>[\s\S]*systemctl status[\s\S]*<\/p>/, '不得把围栏内容塌缩进单个段落')
})

test('标题与引用层级正确，未闭合围栏不丢内容', () => {
  const out = renderMarkdown('## 排查步骤\n> 先看日志\n```bash\nsystemctl status nginx')
  assert.match(out, /<h2>排查步骤<\/h2>/)
  assert.match(out, /<blockquote>先看日志<\/blockquote>/)
  assert.match(out, /<pre><code>systemctl status nginx<\/code><\/pre>/)
})

// ── 全对话出口一致性：所有 AI Chat 助手回复都按 Markdown 渲染 ──────────────
import { readFile } from 'node:fs/promises'

const readSrc = (path) => readFile(new URL(path, import.meta.url), 'utf8')

test('三处 AI 对话出口都接入同一安全渲染器', async () => {
  for (const path of [
    '../src/components/ai/AiChatPanel.vue',
    '../src/components/dashboard/XiaoyuDashboardCard.vue',
    '../src/components/common/OpsSpiderPet.vue'
  ]) {
    const source = await readSrc(path)
    assert.match(source, /import\s*\{\s*renderMarkdown\s*\}/, `${path} 应导入 renderMarkdown`)
    assert.match(source, /v-html="renderMarkdown\(/, `${path} 应以 Markdown 渲染助手消息`)
    assert.match(source, /ai-chat-markdown/, `${path} 应使用统一 markdown 样式类`)
  }
})

test('markdown 样式为全局文件，可命中 v-html 生成的后代元素', async () => {
  const css = await readSrc('../src/components/ai/markdown.css')
  assert.match(css, /\.ai-chat-markdown p\s*\{[^}]*white-space:\s*normal/)
  assert.match(css, /\.ai-chat-markdown pre\s*\{/)
  assert.match(css, /\.ai-chat-markdown strong\s*\{/)
  // 若把样式写回 scoped，v-html 后代不匹配；组件须保持全局 import。
  for (const path of [
    '../src/components/ai/AiChatPanel.vue',
    '../src/components/dashboard/XiaoyuDashboardCard.vue',
    '../src/components/common/OpsSpiderPet.vue'
  ]) {
    assert.match(await readSrc(path), /import '\.\/markdown\.css'|import '\.\.\/ai\/markdown\.css'/)
  }
})

test('流式中的助手消息保持逐字纯文本，完成后才渲染 Markdown', async () => {
  const panel = await readSrc('../src/components/ai/AiChatPanel.vue')
  const card = await readSrc('../src/components/dashboard/XiaoyuDashboardCard.vue')
  assert.match(panel, /v-if="message\.streaming"[\s\S]{0,120}\{\{ message\.content \}\}/)
  assert.match(card, /!msg\.streaming[\s\S]{0,120}renderMarkdown/)
})
