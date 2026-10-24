const examples = [
  {
    id: 'demo-run-k8s-endpoint', traceId: 'DEMO-K8S-ENDPOINT-001',
    toolId: 'k8s.service.diagnose', status: 'FAILED', runtimeId: '演示集群 / dev',
    startedAt: '2026-09-27T09:10:00+08:00', endedAt: '2026-09-27T09:10:03+08:00',
    outputs: [
      { command: 'kubectl get endpoints web-service -n demo', exitCode: 0, stdout: 'NAME          ENDPOINTS   AGE\nweb-service   <none>      12m', stderr: '' },
      { command: 'kubectl get pods -n demo --show-labels', exitCode: 0, stdout: 'web-7d9   1/1   Running   app=web-v2', stderr: '' }
    ],
    evidence: [{ type: '诊断说明', content: 'Service Selector 为 app=web，Pod 标签为 app=web-v2。该示例仅展示证据比对，不代表真实集群状态。' }]
  },
  {
    id: 'demo-run-docker-exit', traceId: 'DEMO-DOCKER-EXIT-002',
    toolId: 'docker.container.diagnose', status: 'FAILED', runtimeId: '演示主机 / docker',
    startedAt: '2026-09-27T09:15:00+08:00', endedAt: '2026-09-27T09:15:02+08:00',
    outputs: [
      { command: 'docker inspect demo-api --format "{{json .State}}"', exitCode: 0, stdout: '{"Status":"exited","ExitCode":1}', stderr: '' },
      { command: 'docker logs --tail 50 demo-api', exitCode: 0, stdout: '', stderr: 'failed to load config /app/config/application.yml: no such file or directory' }
    ],
    evidence: [{ type: '诊断说明', content: '退出码 1 只能证明主进程失败；需结合日志和挂载配置验证文件缺失原因。' }]
  },
  {
    id: 'demo-run-nginx-upstream', traceId: 'DEMO-NGINX-502-003',
    toolId: 'nginx.upstream.diagnose', status: 'FAILED', runtimeId: '演示网关 / nginx',
    startedAt: '2026-09-27T09:20:00+08:00', endedAt: '2026-09-27T09:20:04+08:00',
    outputs: [
      { command: 'curl -I https://demo.example.com/api/health', exitCode: 0, stdout: 'HTTP/2 502', stderr: '' },
      { command: 'ss -lntp', exitCode: 0, stdout: 'LISTEN 0 511 0.0.0.0:443', stderr: '' }
    ],
    evidence: [{ type: '待验证', content: '代理返回 502，尚需核对 Nginx 错误日志、proxy_pass 和上游端口；不能仅凭状态码确认根因。' }]
  },
  {
    id: 'demo-run-linux-storage', traceId: 'DEMO-LINUX-STORAGE-004',
    toolId: 'linux.storage.diagnose', status: 'SUCCESS', runtimeId: '演示主机 / linux',
    startedAt: '2026-09-27T09:25:00+08:00', endedAt: '2026-09-27T09:25:02+08:00',
    outputs: [
      { command: 'df -hT /', exitCode: 0, stdout: '/dev/mapper/demo-root xfs 50G 49G 1G 98% /', stderr: '' },
      { command: 'df -i /', exitCode: 0, stdout: '/dev/mapper/demo-root 100000 25000 75000 25% /', stderr: '' }
    ],
    evidence: [{ type: '诊断说明', content: '命令成功仅代表采集成功；磁盘仍接近满载。清理需确认文件归属、保留策略及备份。' }]
  }
]

export const runHistoryGuides = Object.freeze(examples.map((example) => Object.freeze({
  run: Object.freeze({
    id: example.id, traceId: example.traceId, toolId: example.toolId,
    status: example.status, runtimeId: example.runtimeId, sessionId: null,
    startedAt: example.startedAt, endedAt: example.endedAt,
    commandCount: example.outputs.length,
    failedCommandCount: example.outputs.filter(output => output.exitCode !== 0).length,
    isGuide: true
  }),
  outputs: Object.freeze(example.outputs.map((output, index) => Object.freeze({
    id: `${example.id}-output-${index + 1}`, sequenceNo: index + 1, ...output
  }))),
  evidence: Object.freeze(example.evidence.map((item, index) => Object.freeze({
    id: `${example.id}-evidence-${index + 1}`, sourceRef: example.traceId,
    createdAt: example.endedAt, ...item
  })))
})))

export function runPageWithGuides(page = {}, query = {}) {
  const items = Array.isArray(page.items) ? page.items : []
  if (items.length || Number(page.total) > 0 || Number(query.page || 1) !== 1 ||
    ['traceId', 'toolId', 'status', 'startedFrom', 'startedTo'].some(key => query[key])) {
    return { ...page, items, guideMode: false }
  }
  return { ...page, items: runHistoryGuides.map(guide => guide.run), total: runHistoryGuides.length, guideMode: true }
}

export function findRunHistoryGuide(id) {
  return runHistoryGuides.find(guide => guide.run.id === id) || null
}
