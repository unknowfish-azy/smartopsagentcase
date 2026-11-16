// 对话板 Markdown 渲染器（无依赖、XSS 安全）。
//
// 设计边界：
// - 先整体 HTML 转义，再做 Markdown 转换：任何输入都不可能注入原始 HTML；
// - 链接只放行 http/https，并强制 target/rel；
// - 支持子集：围栏代码块、1-4 级标题、有序/无序列表、引用、行内代码、
//   加粗、链接、段落与换行——够覆盖运维问答的典型输出，不追求完整 CommonMark。

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, ch => ESCAPES[ch])
}

/** 行内转换：行内代码 → 加粗 → 链接（代码占位避免内容被再次替换）。 */
function renderInline(text) {
  const codes = []
  let out = escapeHtml(text).replace(/`([^`]+)`/g, (_, code) => {
    codes.push(code)
    return `\u0000${codes.length - 1}\u0000`
  })
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
  out = out.replace(/\u0000(\d+)\u0000/g, (_, index) => `<code>${codes[Number(index)]}</code>`)
  return out
}

// 块级起始行不能并入上一段落：否则列表/围栏/标题会被吸进 <p>，
// 行内代码正则还会把连续反引号错误配对，整段塌成普通文本。
function isBlockStart(trimmed) {
  return trimmed.startsWith('```')
    || /^#{1,4}\s+/.test(trimmed)
    || trimmed.startsWith('>')
    || /^[-*]\s+/.test(trimmed)
    || /^\d+[.、]\s*/.test(trimmed)
}

function inlineChildren(lines, start) {
  // 收集同一段落的连续非空行，合并成一个段/列表项内容；
  // 遇到任何块级结构立即停下，交还主循环按块处理。
  let end = start
  while (end < lines.length && lines[end].trim() !== '' && !isBlockStart(lines[end].trim())) end += 1
  return { content: lines.slice(start, end).join('\n'), end }
}

export function renderMarkdown(source = '') {
  const lines = String(source).replace(/\r\n/g, '\n').split('\n')
  const blocks = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    const trimmed = line.trim()

    if (trimmed === '') { index += 1; continue }

    // 围栏代码块 ```（结束围栏允许带语言标注差异，仅按 ``` 判定）
    if (trimmed.startsWith('```')) {
      const body = []
      index += 1
      while (index < lines.length && lines[index].trim() !== '```') { body.push(lines[index]); index += 1 }
      index += 1 // 跳过结束围栏（或越界=未闭合，按已结束处理）
      blocks.push(`<pre><code>${escapeHtml(body.join('\n'))}</code></pre>`)
      continue
    }

    // 标题 # ~ ####
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      const level = heading[1].length
      blocks.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      index += 1
      continue
    }

    // 引用 > ：连续行合并
    if (trimmed.startsWith('>')) {
      const body = []
      while (index < lines.length && lines[index].trim().startsWith('>')) {
        body.push(lines[index].trim().replace(/^>\s?/, ''))
        index += 1
      }
      blocks.push(`<blockquote>${renderInline(body.join('\n'))}</blockquote>`)
      continue
    }

    // 无序列表 - / *
    if (/^[-*]\s+/.test(trimmed)) {
      const items = []
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(`<li>${renderInline(lines[index].trim().replace(/^[-*]\s+/, ''))}</li>`)
        index += 1
      }
      blocks.push(`<ul>${items.join('')}</ul>`)
      continue
    }

    // 有序列表 1. / 1、
    if (/^\d+[.、]\s*/.test(trimmed)) {
      const items = []
      while (index < lines.length && /^\d+[.、]\s*/.test(lines[index].trim())) {
        items.push(`<li>${renderInline(lines[index].trim().replace(/^\d+[.、]\s*/, ''))}</li>`)
        index += 1
      }
      blocks.push(`<ol>${items.join('')}</ol>`)
      continue
    }

    // 普通段落：连续非空行合并（保留单换行为 <br>，贴合聊天阅读习惯）
    const { content, end } = inlineChildren(lines, index)
    blocks.push(`<p>${renderInline(content).replace(/\n/g, '<br>')}</p>`)
    index = end
  }

  return blocks.join('')
}
