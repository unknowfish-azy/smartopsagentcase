function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, character => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  })[character])
}

function renderInline(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}

export function renderKnowledgeMarkdown(source) {
  const output = []
  let listType = null
  let inCode = false
  let codeLanguage = 'text'
  let codeLines = []

  const closeList = () => {
    if (!listType) return
    output.push(`</${listType}>`)
    listType = null
  }

  for (const line of String(source || '').replace(/\r\n?/g, '\n').split('\n')) {
    const trimmed = line.trim()

    if (trimmed.startsWith('```')) {
      if (inCode) {
        output.push(`<pre><code class="language-${escapeHtml(codeLanguage)}">${escapeHtml(codeLines.join('\n'))}</code></pre>`)
        inCode = false
        codeLines = []
      } else {
        closeList()
        inCode = true
        codeLanguage = trimmed.slice(3).trim() || 'text'
      }
      continue
    }

    if (inCode) {
      codeLines.push(line)
      continue
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    const quote = line.match(/^>\s?(.+)$/)
    const listItem = line.match(/^\s*([-*+]\s+|\d+[.)]\s+)(.+)$/)

    if (heading) {
      closeList()
      const level = heading[1].length
      output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      continue
    }

    if (quote) {
      closeList()
      output.push(`<blockquote><p>${renderInline(quote[1])}</p></blockquote>`)
      continue
    }

    if (listItem) {
      const type = /^\d/.test(listItem[1]) ? 'ol' : 'ul'
      if (listType !== type) {
        closeList()
        output.push(`<${type}>`)
        listType = type
      }

      const task = listItem[2].match(/^\[([ xX])\]\s+(.+)$/)
      if (task) {
        const checked = task[1].toLowerCase() === 'x'
        output.push(`<li class="task-list-item"><input type="checkbox" disabled${checked ? ' checked' : ''}>${renderInline(task[2])}</li>`)
      } else {
        output.push(`<li>${renderInline(listItem[2])}</li>`)
      }
      continue
    }

    if (!trimmed) {
      closeList()
      continue
    }

    closeList()
    output.push(`<p>${renderInline(line)}</p>`)
  }

  if (inCode) {
    output.push(`<pre><code class="language-${escapeHtml(codeLanguage)}">${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }
  closeList()
  return output.join('')
}
