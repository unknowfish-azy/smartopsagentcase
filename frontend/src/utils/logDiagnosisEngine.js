/**
 * =========================================================
 * 日志诊断确定性规则引擎（纯前端、零依赖、可单测）
 * =========================================================
 *
 * 设计原则（诚实优先）：
 * 1. 无大模型参与：结论只能来自下方规则库的正则指纹命中；
 * 2. 未命中就明说：没有任何规则命中时，输出「未命中已知指纹」的明确结论与通用建议；
 * 3. 证据可回溯：每条命中都保留原始日志行（脱敏后）与行号，不编造样本；
 * 4. 脱敏：命中行与错误样本统一脱敏 Bearer / password / token 等凭据片段。
 */

/* ---------------- 规则库（≥12 条常见运维故障指纹） ---------------- */

export const LOG_DIAGNOSIS_RULES = Object.freeze([
  {
    id: 'oom-memory',
    name: 'OOM / 内存溢出',
    severity: 'CRITICAL',
    category: '内存资源',
    patterns: [/out ?of ?memory/i, /outofmemoryerror/i, /java heap space/i, /GC overhead limit exceeded/i, /malloc.*failed/i],
    reason: 'JVM 或进程申请内存超出可用上限，堆内存耗尽后直接终止；通常由内存泄漏、堆参数过小或并发峰值导致。',
    recommendation: '先通过堆转储（-XX:+HeapDumpOnOutOfMemoryError）定位泄漏对象；核对 -Xmx 与容器内存 limit 是否匹配；确认泄漏来源前不要简单重启掩盖问题。',
    keywords: ['OOM', 'OutOfMemoryError', 'heap dump', '内存泄漏', 'JVM 调优']
  },
  {
    id: 'cpu-overload',
    name: 'CPU 过载',
    severity: 'ERROR',
    category: '计算资源',
    patterns: [/cpu.*(100%|saturat|overload|throttl)/i, /load average.{0,24}(1[5-9]|[2-9]\d)\.\d+/i, /high cpu (usage|utilization)/i],
    reason: 'CPU 长时间打满（负载均值远超核数），常见于低效 SQL、死循环、序列化热点或流量突增，会引发请求排队与超时连锁。',
    recommendation: '用 top / async-profiler 火焰图定位热点线程；区分业务高峰与异常循环；必要时限流扩容，并回查最近发布的热点代码。',
    keywords: ['CPU 过载', 'load average', '火焰图', '限流', '扩容']
  },
  {
    id: 'disk-full',
    name: '磁盘写满',
    severity: 'CRITICAL',
    category: '存储资源',
    patterns: [/no space left on device/i, /\bENOSPC\b/i, /disk.*(full|100%|space)/i, /inode.*(exhaust|full)/i],
    reason: '磁盘或 inode 耗尽，写入失败会导致日志丢失、数据库停写、容器重启等一系列次生故障。',
    recommendation: '立刻定位大文件（du / lsof +L1），清理轮转日志与临时文件；核对日志切割与监控告警为何未提前触发；扩容前先止血。',
    keywords: ['磁盘满', 'ENOSPC', '日志轮转', 'inode', '容量治理']
  },
  {
    id: 'connection-refused',
    name: '连接拒绝',
    severity: 'ERROR',
    category: '网络连通',
    patterns: [/connection refused/i, /\bECONNREFUSED\b/i, /\b111\b.*(refused)/i],
    reason: '目标地址可达但端口没有进程监听（或被防火墙 REJECT），说明服务未启动、已崩溃或监听端口/地址配置错误。',
    recommendation: '确认目标进程存活与监听端口（ss -lntp）；检查防火墙与安全组规则；核对连接串中的 host:port 是否与实际部署一致。',
    keywords: ['connection refused', '端口监听', '防火墙', '服务未启动']
  },
  {
    id: 'timeout',
    name: '连接 / 读超时',
    severity: 'WARN',
    category: '网络连通',
    patterns: [/timed? ?out/i, /\bETIMEDOUT\b/i, /SocketTimeoutException/i, /read timeout/i, /\bECONNRESET\b/i],
    reason: 'TCP 建连或读响应超过超时阈值，可能是网络抖动、对端过载、慢查询或超时参数过小；偶发多为抖动，持续出现需按链路逐段排查。',
    recommendation: '统计超时的目标地址与占比；对下游做健康检查与熔断降级；区分 connect timeout（网络/负载）与 read timeout（对端处理慢）分别处理。',
    keywords: ['timeout', '超时排查', '熔断降级', '慢查询']
  },
  {
    id: 'permission-denied',
    name: '权限拒绝',
    severity: 'ERROR',
    category: '权限配置',
    patterns: [/permission denied/i, /\bEACCES\b/i, /access denied/i, /operation not permitted/i, /\bEPERM\b/i],
    reason: '进程对目标文件、端口或系统资源缺少权限：常见于非 root 用户绑低端口、文件属主错误、SELinux/容器安全上下文限制。',
    recommendation: '核对运行用户与目标资源的属主/权限位；容器场景检查 securityContext 与挂载目录权限；确认 SELinux/AppArmor 拦截记录。',
    keywords: ['permission denied', '文件权限', 'securityContext', 'SELinux']
  },
  {
    id: 'dns-failure',
    name: 'DNS 解析失败',
    severity: 'ERROR',
    category: '域名解析',
    patterns: [/unknown host/i, /name or service not known/i, /\bENOTFOUND\b/i, /\bNXDOMAIN\b/i, /dns.*(fail|resolv)/i],
    reason: '域名无法解析为 IP：记录不存在（拼写/未注册）、解析器不可用，或容器内 /etc/resolv.conf 与 CoreDNS 配置异常。',
    recommendation: '用 nslookup/dig 在同环境复现；核对 /etc/resolv.conf 与上游 DNS；集群内检查 CoreDNS 日志与 Service 名称拼写。',
    keywords: ['DNS', 'NXDOMAIN', 'CoreDNS', 'resolv.conf']
  },
  {
    id: 'tls-certificate',
    name: 'TLS 证书过期 / 校验失败',
    severity: 'ERROR',
    category: '证书安全',
    patterns: [/certificate (has )?expired/i, /SSLHandshakeException/i, /certificate verify failed/i, /PKIX path building failed/i, /unable to verify the first certificate/i, /\bCERT_(DATE_INVALID|HAS_EXPIRED|INVALID)\b/i],
    reason: 'TLS 握手阶段证书过期、域名不匹配或信任链不完整，客户端拒绝不安全连接；自签证书未进信任库也会触发。',
    recommendation: '查看证书有效期与域名（openssl s_client）；续期证书并部署，核对中间链完整；集群内确认 Secret 更新与滚动重启。',
    keywords: ['TLS', '证书过期', 'SSLHandshakeException', '信任链', '证书续期']
  },
  {
    id: 'port-in-use',
    name: '端口占用',
    severity: 'ERROR',
    category: '网络配置',
    patterns: [/address already in use/i, /\bEADDRINUSE\b/i, /port.*(already|is) in use/i, /bind.*failed.*(in use|conflict)/i],
    reason: '绑定监听端口时发现已被其他进程（常见为上一个未退出的实例）占用，新进程启动失败。',
    recommendation: '用 ss/lsof 找到占用进程并确认是否为残留实例；修正重复启动的编排配置；容器场景避免宿主端口冲突。',
    keywords: ['EADDRINUSE', '端口冲突', '进程残留', '重复启动']
  },
  {
    id: 'k8s-crashloop',
    name: 'K8s CrashLoopBackOff',
    severity: 'CRITICAL',
    category: '容器编排',
    patterns: [/crashloopbackoff/i, /back-off restarting failed container/i],
    reason: '容器反复启动崩溃退出，Kubelet 进入指数退避重启；根因通常是应用启动失败（配置错误、依赖不可达、OOM 之外的非 0 退出）。',
    recommendation: 'kubectl describe pod + 上一次容器日志定位崩溃原因；核对启动命令、探针配置与依赖地址；修复前避免无限重启放大故障。',
    keywords: ['CrashLoopBackOff', 'describe pod', '启动失败', '探针配置']
  },
  {
    id: 'k8s-oomkilled',
    name: 'K8s OOMKilled',
    severity: 'CRITICAL',
    category: '容器编排',
    patterns: [/oomkilled/i, /reason:\s*oom/i, /container.*memory limit/i],
    reason: '容器进程内存超过 Pod resources.limits.memory，被内核 cgroup OOM Killer 强制终止，随后进入重启循环。',
    recommendation: '对比容器实际内存用量与 limit；排查内存泄漏或调高 limit 并配合 HPA；注意 JVM 需感知容器内存约束（UseContainerSupport）。',
    keywords: ['OOMKilled', 'memory limit', 'cgroup', 'HPA']
  },
  {
    id: 'retry-storm',
    name: '重试风暴 / 级联失败',
    severity: 'ERROR',
    category: '流量治理',
    patterns: [/retr(y|ies).{0,24}(exhaust|storm|too many)/i, /max retries exceeded/i, /circuit breaker (open|tripped)/i, /cascading failure/i],
    reason: '下游故障触发大量客户端重试，重试流量放大压垮下游形成正反馈；无退避与熔断时会从局部故障演变为级联雪崩。',
    recommendation: '立即对下游限流并打开熔断；为重试加指数退避与抖动；核对重试上限与超时预算，避免跨层重试叠加。',
    keywords: ['重试风暴', '熔断', '指数退避', '级联失败', '限流']
  },
  {
    id: 'db-deadlock',
    name: '数据库死锁 / 锁等待',
    severity: 'CRITICAL',
    category: '数据库',
    patterns: [/deadlock/i, /lock wait timeout exceeded/i, /ORA-00060/i, /lock acquisition timeout/i],
    reason: '多个事务以不同顺序争抢行锁/表锁形成循环等待，被数据库检测后回滚牺牲者；长事务与热点行更新最易触发。',
    recommendation: '导出死锁日志（SHOW ENGINE INNODB STATUS）定位冲突 SQL；统一加锁顺序、缩短事务、为热点行改造为队列化更新。',
    keywords: ['死锁', 'deadlock', 'InnoDB', '长事务', '热点行']
  },
  {
    id: 'queue-backlog',
    name: '队列堆积',
    severity: 'WARN',
    category: '消息队列',
    patterns: [/queue.*(backlog|overflow|full|exceed)/i, /consumer lag/i, /(kafka|rabbitmq|rocketmq).*(lag|backlog)/i, /message queue.*(堆积|积压)/i],
    reason: '生产速率持续高于消费速率，消息积压导致延迟上升乃至 broker 磁盘告警；多为消费端宕机、处理变慢或分区数不足。',
    recommendation: '确认消费端存活与处理耗时；临时扩容消费者实例/分区；必要时按业务优先级丢弃或转移部分消息，事后复盘容量规划。',
    keywords: ['消息积压', 'consumer lag', '分区扩容', '消费降速']
  }
])

/* ---------------- 常量 ---------------- */

const MAX_LOG_CHARS = 200 * 1024            // 超过 200KB 截断并标注
const MAX_MATCH_SAMPLES = 8                 // 每条规则最多保留的命中行样本数
const MAX_MATCH_LINE_NUMBERS = 50           // 每条规则最多记录的行号数
const MAX_UNMATCHED_SAMPLES = 10            // 未解释错误样本最多保留条数

const SEVERITY_ORDER = Object.freeze({ CRITICAL: 3, ERROR: 2, WARN: 1 })

const ERROR_LEVEL_RE = /\b(ERROR|ERR|FATAL|CRITICAL|SEVERE|EXCEPTION|PANIC)\b/i
const WARN_LEVEL_RE = /\b(WARN|WARNING)\b/i
const INFO_LEVEL_RE = /\b(INFO|DEBUG|TRACE)\b/i

/* ---------------- 脱敏 ---------------- */

/* password=/token=/api_key= 等键值对：值允许带引号形式 */
const SECRET_KV_RE = /\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret)\s*([=:])\s*("[^"]*"|'[^']*'|[^\s&"',;]+)/gi

/**
 * 将一行日志中的敏感凭据替换为 ***，按优先级三段处理：
 * 1. Authorization 头整段脱敏（冒号/等号后全部内容都视为凭据，覆盖 Basic/Bearer/Digest 等 scheme）；
 * 2. 裸 Bearer/Basic/Digest 认证片段（无 Authorization 前缀时）；
 * 3. password、token、api_key 等键值对（含 jdbc url 内嵌密码、带引号值）。
 */
export function maskSecrets(line) {
  if (!line) return ''
  return String(line)
    .replace(/\b(authorization)\s*([=:])[^\n]*/gi, '$1$2***')
    .replace(/\b(Bearer|Basic|Digest)\s+\S+/gi, '$1 ***')
    .replace(SECRET_KV_RE, '$1$2***')
}

/* ---------------- 主分析入口 ---------------- */

/**
 * 分析日志文本，返回确定性诊断结果。
 * @param {string} text 原始日志文本
 * @returns {{
 *   issues: Array<{ruleId,name,severity,category,reason,recommendation,keywords,matches:string[],lineNumbers:number[],matchCount:number}>,
 *   stats: {totalLines:number,errorLines:number,levelDist:{ERROR:number,WARN:number,INFO:number},truncated:boolean,matchedLines:number},
 *   summary: string,
 *   unmatchedErrorSamples: string[],
 *   unmatchedErrorCount: number
 * }}
 */
export function analyzeLog(text) {
  const source = typeof text === 'string' ? text : ''
  const truncated = source.length > MAX_LOG_CHARS
  const effective = truncated ? source.slice(0, MAX_LOG_CHARS) : source
  const lines = effective.length === 0 ? [] : effective.split(/\r?\n/)

  /* 级别统计与逐行预脱敏（每行只脱敏一次，规则命中时直接复用） */
  const levelDist = { ERROR: 0, WARN: 0, INFO: 0 }
  const errorLines = []
  const maskedLines = new Array(lines.length)
  for (let i = 0; i < lines.length; i++) {
    const masked = maskSecrets(lines[i])
    maskedLines[i] = masked
    if (ERROR_LEVEL_RE.test(masked)) {
      levelDist.ERROR++
      errorLines.push(i)
    } else if (WARN_LEVEL_RE.test(masked)) {
      levelDist.WARN++
    } else if (INFO_LEVEL_RE.test(masked)) {
      levelDist.INFO++
    }
  }

  /* 规则匹配：逐条规则逐行扫描，证据全部来自真实日志行 */
  const issues = []
  const matchedLineIndexes = new Set()
  for (const rule of LOG_DIAGNOSIS_RULES) {
    const lineNumbers = []
    const matches = []
    let matchCount = 0
    for (let i = 0; i < lines.length; i++) {
      const hit = rule.patterns.some(re => re.test(lines[i]))
      if (!hit) continue
      matchCount++
      matchedLineIndexes.add(i)
      if (lineNumbers.length < MAX_MATCH_LINE_NUMBERS) lineNumbers.push(i + 1)
      if (matches.length < MAX_MATCH_SAMPLES) matches.push(maskedLines[i])
    }
    if (matchCount > 0) {
      issues.push({
        ruleId: rule.id,
        name: rule.name,
        severity: rule.severity,
        category: rule.category,
        reason: rule.reason,
        recommendation: rule.recommendation,
        keywords: rule.keywords,
        matches,
        lineNumbers,
        matchCount
      })
    }
  }

  /* 严重级别降序排序，同级别保持规则库顺序 */
  issues.sort((a, b) => SEVERITY_ORDER[b.severity] - SEVERITY_ORDER[a.severity])

  /* 未被任何指纹解释的错误样本（诚实呈现规则盲区） */
  const unmatchedSamples = []
  for (const index of errorLines) {
    if (matchedLineIndexes.has(index)) continue
    if (unmatchedSamples.length >= MAX_UNMATCHED_SAMPLES) break
    unmatchedSamples.push(maskedLines[index])
  }

  const summary = buildSummary(issues, lines.length, errorLines.length, truncated, unmatchedSamples.length)

  return {
    issues,
    stats: {
      totalLines: lines.length,
      errorLines: errorLines.length,
      levelDist,
      truncated,
      matchedLines: matchedLineIndexes.size
    },
    summary,
    unmatchedErrorSamples: unmatchedSamples,
    unmatchedErrorCount: Math.max(0, errorLines.length - matchedLineIndexes.size)
  }
}

/* ---------------- 摘要生成 ---------------- */

function buildSummary(issues, totalLines, errorLines, truncated, unmatchedCount) {
  const parts = []
  if (truncated) parts.push('日志超长，仅分析前 200KB 内容，统计与结论基于截断后的文本。')
  if (issues.length > 0) {
    const maxSeverity = issues.reduce((top, item) => SEVERITY_ORDER[item.severity] > SEVERITY_ORDER[top] ? item.severity : top, 'WARN')
    parts.push(`命中 ${issues.length} 条已知故障指纹（最严重级别 ${maxSeverity}）：${issues.map(item => item.name).join('、')}。`)
    if (unmatchedCount > 0) parts.push(`另有 ${unmatchedCount} 个错误行未被任何指纹解释，见「未解释错误样本」，需人工排查。`)
    parts.push('以上结论均为规则指纹匹配结果，处置前请结合原始日志上下文核对。')
  } else {
    parts.push(`未命中任何已知故障指纹（规则库共 ${LOG_DIAGNOSIS_RULES.length} 条，不编造结论）。`)
    if (errorLines > 0) parts.push(`日志中存在 ${errorLines} 个错误级别行，但不符合已知指纹特征，请人工排查。`)
    parts.push('通用建议：核对故障时间线与近期变更记录；确认日志级别配置完整；补充系统资源指标（CPU/内存/磁盘/网络）后再分析。')
  }
  if (totalLines === 0) parts.push('输入为空，未分析任何内容。')
  return parts.join(' ')
}

/* ---------------- 报告导出（Markdown） ---------------- */

/**
 * 将诊断结果渲染为 Markdown 报告，用于复制与沉淀知识候选。
 * @param {ReturnType<typeof analyzeLog>} result analyzeLog 的返回值
 */
export function toMarkdown(result) {
  const { issues, stats, summary, unmatchedErrorSamples } = result
  const body = []
  body.push('# 日志诊断报告')
  body.push('')
  body.push('> 确定性规则归因 · 无大模型参与 · 不编造结论。以下内容均来自日志指纹命中与真实日志行（已脱敏）。')
  body.push('')
  body.push('## 统计')
  body.push('')
  body.push(`- 总行数：${stats.totalLines}`)
  body.push(`- 错误行数：${stats.errorLines}`)
  body.push(`- 级别分布：ERROR ${stats.levelDist.ERROR} / WARN ${stats.levelDist.WARN} / INFO ${stats.levelDist.INFO}`)
  if (stats.truncated) body.push('- ⚠️ 日志超长，已截断至前 200KB，结论仅基于截断内容')
  body.push('')
  body.push('## 摘要')
  body.push('')
  body.push(summary)
  body.push('')

  if (issues.length > 0) {
    body.push('## 命中的故障指纹')
    for (const issue of issues) {
      body.push('')
      body.push(`### [${issue.severity}] ${issue.name}（${issue.category}）`)
      body.push('')
      body.push(`- 成因：${issue.reason}`)
      body.push(`- 处置建议：${issue.recommendation}`)
      body.push(`- 检索关键词：${issue.keywords.join('、')}`)
      body.push(`- 命中行号：${issue.lineNumbers.join(', ')}${issue.matchCount > issue.lineNumbers.length ? `（共 ${issue.matchCount} 处，仅列出前 ${issue.lineNumbers.length} 处）` : `（共 ${issue.matchCount} 处）`}`)
      if (issue.matches.length > 0) {
        body.push('')
        body.push('命中行（已脱敏）：')
        body.push('')
        body.push('```text')
        for (const line of issue.matches) body.push(line)
        body.push('```')
      }
    }
    body.push('')
  } else {
    body.push('## 结论')
    body.push('')
    body.push('**未命中任何已知故障指纹。**本引擎不编造结论，请人工排查；建议结合时间线、变更记录与资源指标定位。')
    body.push('')
  }

  if (unmatchedErrorSamples.length > 0) {
    body.push('## 未解释错误样本（规则盲区，需人工排查）')
    body.push('')
    body.push('以下错误级别日志行不符合任何已知指纹，仅如实列出：')
    body.push('')
    body.push('```text')
    for (const line of unmatchedErrorSamples) body.push(line)
    body.push('```')
    body.push('')
  }
  return body.join('\n')
}
