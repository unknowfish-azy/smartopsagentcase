const secretKey = /(?:password|passwd|pwd|secret|token|api[_-]?key|authorization|private[_-]?key|client[_-]?secret)/i

export function redactConfigText(text) {
  let privateBlock = false
  let secretIndent = null
  return text.split('\n').map(line => {
    if (/-----BEGIN .*PRIVATE KEY-----/.test(line)) privateBlock = true
    if (privateBlock) {
      if (/-----END .*PRIVATE KEY-----/.test(line)) privateBlock = false
      return '[敏感内容已隐藏]'
    }
    const indent = line.match(/^\s*/)[0].length
    if (secretIndent !== null) {
      if (line.trim() === '' || indent > secretIndent) return '[敏感内容已隐藏]'
      secretIndent = null
    }
    const assignment = line.match(/^(\s*(?:export\s+)?["']?[^:=\s"']+["']?\s*[:=]\s*)(.*)$/)
    if (assignment && secretKey.test(assignment[1])) {
      if (/^[|>][-+]?\s*$/.test(assignment[2])) secretIndent = indent
      return `${assignment[1]}[敏感内容已隐藏]`
    }
    return line.replace(/(["'][^"']*(?:password|secret|token|api[_-]?key|authorization)[^"']*["']\s*:\s*)("(?:\\.|[^"\\])*"|'[^']*'|[^,}\s]+)/gi,
      '$1"[敏感内容已隐藏]"')
      .replace(/(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi, '$1[凭据已隐藏]@')
  }).join('\n')
}
