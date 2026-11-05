import assert from 'node:assert/strict'
import test from 'node:test'

import { getKnowledgeNode, getKnowledgePath, knowledgeDomains, knowledgeEntries, knowledgeTree, searchKnowledgeEntries } from '../src/views/knowledge/knowledgeCatalog.js'
import { knowledgeReadApi } from '../src/views/knowledge/knowledgeLibrary.js'

test('returns the Nginx 502 runbook when error code and service match', () => {
  const results = searchKnowledgeEntries({ query: '502', service: 'nginx' })

  assert.equal(results.length, 1)
  assert.equal(results[0].title, '502 Bad Gateway Diagnosis Runbook')
  assert.equal(results[0].type, 'DIAGNOSIS RUNBOOK')
})

test('filters built-in knowledge by platform without relying on an AI provider', () => {
  const results = searchKnowledgeEntries({ platform: 'MySQL' })

  assert.ok(results.length > 0)
  assert.ok(results.every(result => result.platform === 'MySQL'))
})

test('keeps the Personal System knowledge domains in their intended order', () => {
  assert.deepEqual(knowledgeDomains.map(domain => domain.id), [
    'linux', 'cloud-operations', 'docker', 'mysql', 'nginx', 'ubuntu', 'centos'
  ])
})

test('searches the built-in Cloud Operations knowledge pack by full-text content', () => {
  const results = searchKnowledgeEntries({ query: '自动扩缩容' })

  assert.ok(results.some(result => result.title === 'Kubernetes 容器编排'))
})

test('searches Cloud Operations by its domain', () => {
  const results = searchKnowledgeEntries({ domain: 'cloud-operations' })

  assert.ok(results.length >= 5)
  assert.ok(results.every(result => result.domain === 'cloud-operations'))
})

test('indexes the DNS/BIND knowledge pack and evidence rules', () => {
  const dns = searchKnowledgeEntries({ query: 'allow-transfer' })
  assert.ok(dns.some(result => result.id === 'dns.bind.secondary'))
  assert.ok(searchKnowledgeEntries({ query: 'DNS-003' }).some(result => result.id === 'dns.bind.diagnostic-rules'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'dns-bind' }).length >= 10)
})

test('indexes file transfer and synchronization knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: '--delete' }).some(result => result.id === 'linux.sync.delete'))
  assert.ok(searchKnowledgeEntries({ query: 'inotifywait' }).some(result => result.id === 'linux.sync.realtime'))
  assert.ok(searchKnowledgeEntries({ query: 'HOST::module' }).some(result => result.id === 'linux.sync.daemon-module'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'file-sync' }).length >= 10)
})

test('indexes Samba sharing, permissions and CIFS troubleshooting', () => {
  assert.ok(searchKnowledgeEntries({ query: 'smbclient -L' }).some(result => result.id === 'linux.samba.clients'))
  assert.ok(searchKnowledgeEntries({ query: 'writable=yes' }).some(result => result.id === 'linux.samba.permissions'))
  assert.ok(searchKnowledgeEntries({ query: 'mount.cifs' }).some(result => result.id === 'linux.samba.troubleshooting'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'samba' }).length >= 8)
})

test('indexes MySQL 8 installation, recovery and multi-instance knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'ERROR 2002' }).some(result => result.id === 'mysql80.config-socket'))
  assert.ok(searchKnowledgeEntries({ query: '3307' }).some(result => result.id === 'mysql80.multi-instance'))
  assert.ok(searchKnowledgeEntries({ query: 'skip-grant-tables' }).some(result => result.id === 'mysql80.password-recovery'))
  assert.ok(searchKnowledgeEntries({ domain: 'mysql', service: 'mysql' }).length >= 12)
})

test('indexes DataGrip and core MySQL SQL knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'DataGrip' }).some(result => result.id === 'mysql.sql.datagrip-connection'))
  assert.ok(searchKnowledgeEntries({ query: 'GROUP BY' }).some(result => result.id === 'mysql.sql.aggregate-group'))
  assert.ok(searchKnowledgeEntries({ query: 'TRUNCATE' }).some(result => result.id === 'mysql.sql.dml-safety'))
  assert.ok(searchKnowledgeEntries({ domain: 'mysql', service: 'mysql-sql' }).length >= 10)
})

test('indexes Shell variables, text tools and inspection knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'uniq -c' }).some(result => result.id === 'shell.text-tools'))
  assert.ok(searchKnowledgeEntries({ query: 'bash -x' }).some(result => result.id === 'shell.debugging'))
  assert.ok(searchKnowledgeEntries({ query: 'export' }).some(result => result.id === 'shell.variables-env'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'shell' }).length >= 9)
})

test('indexes Shell flow control, batching and monitoring knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'while true' }).some(result => result.id === 'shell.flow.while-control'))
  assert.ok(searchKnowledgeEntries({ query: 'ssh-copy-id' }).some(result => result.id === 'shell.flow.batch-ops'))
  assert.ok(searchKnowledgeEntries({ query: 'bc' }).some(result => result.id === 'shell.flow.monitoring'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'shell' }).length >= 20)
})

test('indexes Shell functions, links, regex and Expect automation knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'return' }).some(result => result.id === 'shell.advanced.functions'))
  assert.ok(searchKnowledgeEntries({ query: 'inode' }).some(result => result.id === 'shell.advanced.links-inode'))
  assert.ok(searchKnowledgeEntries({ query: 'grep -P' }).some(result => result.id === 'shell.advanced.regex'))
  assert.ok(searchKnowledgeEntries({ query: 'spawn' }).some(result => result.id === 'shell.advanced.expect-core'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'shell' }).length >= 28)
})

test('indexes Containerd image, task, namespace and Harbor knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'Image、Container、Task' }).some(result => result.id === 'containerd.container-task'))
  assert.ok(searchKnowledgeEntries({ query: 'ctr -n' }).some(result => result.id === 'containerd.namespace'))
  assert.ok(searchKnowledgeEntries({ query: 'hosts.toml' }).some(result => result.id === 'containerd.registry-config'))
  assert.ok(searchKnowledgeEntries({ query: 'Harbor' }).some(result => result.id === 'containerd.harbor'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'containerd' }).length >= 9)
})

test('indexes Kubernetes architecture, kubeadm and troubleshooting knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'API Server' }).some(result => result.id === 'kubernetes.architecture'))
  assert.ok(searchKnowledgeEntries({ query: 'kubeadm init' }).some(result => result.id === 'kubernetes.kubeadm-init-join'))
  assert.ok(searchKnowledgeEntries({ query: 'CrashLoopBackOff' }).some(result => result.id === 'kubernetes.states'))
  assert.ok(searchKnowledgeEntries({ query: 'kubectl describe' }).some(result => result.id === 'kubernetes.evidence-chain'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'kubernetes' }).length >= 10)
})

test('indexes Docker engine, images, containers, Dockerfile and troubleshooting knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'Namespace' }).some(result => result.id === 'docker.architecture'))
  assert.ok(searchKnowledgeEntries({ query: 'docker inspect' }).some(result => result.id === 'docker.container-lifecycle'))
  assert.ok(searchKnowledgeEntries({ query: 'ENTRYPOINT' }).some(result => result.id === 'docker.dockerfile'))
  assert.ok(searchKnowledgeEntries({ query: 'docker.sock' }).some(result => result.id === 'docker.install-daemon'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'docker' }).length >= 11)
})

test('indexes Kubernetes Node, YAML, Pod, Deployment, Service and resource knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'kubectl explain' }).some(result => result.id === 'kubernetes.resource.yaml'))
  assert.ok(searchKnowledgeEntries({ query: 'Deployment、ReplicaSet' }).some(result => result.id === 'kubernetes.resource.deployment'))
  assert.ok(searchKnowledgeEntries({ query: 'EndpointSlice' }).some(result => result.id === 'kubernetes.resource.service'))
  assert.ok(searchKnowledgeEntries({ query: 'readinessProbe' }).some(result => result.id === 'kubernetes.resource.resources-probes'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'kubernetes' }).length >= 20)
})

test('indexes Kubernetes scheduling, lifecycle and probe troubleshooting knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'nodeAffinity' }).some(result => result.id === 'kubernetes.scheduling.constraints'))
  assert.ok(searchKnowledgeEntries({ query: 'NoExecute' }).some(result => result.id === 'kubernetes.scheduling.taints'))
  assert.ok(searchKnowledgeEntries({ query: 'FailedScheduling' }).some(result => result.id === 'kubernetes.scheduling.pending'))
  assert.ok(searchKnowledgeEntries({ query: 'startupProbe' }).some(result => result.id === 'kubernetes.scheduling.probes'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'kubernetes' }).length >= 29)
})

test('indexes Kubernetes controllers, rollout, jobs and Service networking knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'Deployment' }).some(result => result.id === 'kubernetes.controller.deployment'))
  assert.ok(searchKnowledgeEntries({ query: 'Headless Service' }).some(result => result.id === 'kubernetes.controller.headless-dns'))
  assert.ok(searchKnowledgeEntries({ query: 'ipvsadm' }).some(result => result.id === 'kubernetes.controller.proxy-network'))
  assert.ok(searchKnowledgeEntries({ query: 'CronJob' }).some(result => result.id === 'kubernetes.controller.job-cronjob'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'kubernetes' }).length >= 39)
})

test('indexes Kubernetes Ingress, TLS, Traefik and DNS routing knowledge', () => {
  assert.ok(searchKnowledgeEntries({ query: 'Ingress Controller' }).some(result => result.id === 'kubernetes.ingress.model'))
  assert.ok(searchKnowledgeEntries({ query: 'TLS Secret' }).some(result => result.id === 'kubernetes.ingress.tls'))
  assert.ok(searchKnowledgeEntries({ query: 'Traefik' }).some(result => result.id === 'kubernetes.ingress.traefik-rbac'))
  assert.ok(searchKnowledgeEntries({ query: 'RBAC' }).some(result => result.id === 'kubernetes.ingress.traefik-rbac'))
  assert.ok(searchKnowledgeEntries({ query: 'DNS' }).some(result => result.id === 'kubernetes.ingress.dns'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'kubernetes' }).length >= 49)
})

test('indexes the SmartOpsAgent developer knowledge specification', () => {
  const results = searchKnowledgeEntries({ query: 'Knowledge Base Specification' })

  assert.ok(results.some(result => result.id === 'smartops-developer-knowledge-spec'))
})

test('indexes Ansible automation, Linux access control, Nginx and MySQL administration packs', () => {
  assert.ok(searchKnowledgeEntries({ query: 'ansible-inventory' }).some(result => result.id === 'ansible.inventory'))
  assert.ok(searchKnowledgeEntries({ query: 'setfacl' }).some(result => result.id === 'linux.access.acl'))
  assert.ok(searchKnowledgeEntries({ query: 'proxy_cache_key' }).some(result => result.id === 'nginx.ops.caching'))
  assert.ok(searchKnowledgeEntries({ query: '--single-transaction' }).some(result => result.id === 'mysql8.admin.backup-logical'))
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'ansible' }).length >= 11)
  assert.ok(searchKnowledgeEntries({ domain: 'linux', service: 'identity-access' }).length >= 9)
  assert.ok(searchKnowledgeEntries({ domain: 'nginx', service: 'nginx' }).length >= 10)
  assert.ok(searchKnowledgeEntries({ domain: 'mysql', service: 'mysql-admin' }).length >= 11)
})

test('indexes the cloud native tool roadmap without changing existing operational packs', () => {
  const helm = searchKnowledgeEntries({ query: 'Helm' }).find(result => result.id === 'cloud-native.tool.helm')
  const argocd = searchKnowledgeEntries({ query: 'Argo CD' }).find(result => result.id === 'cloud-native.tool.argocd')

  assert.equal(helm?.service, 'cloud-native-tools')
  assert.equal(argocd?.section, 'DELIVERY')
  assert.ok(searchKnowledgeEntries({ domain: 'cloud-operations', service: 'cloud-native-tools' }).length >= 15)
  assert.ok(searchKnowledgeEntries({ query: 'CrashLoopBackOff' }).some(result => result.id === 'kubernetes-crashloopbackoff'))
})

test('indexes detailed cloud native tool runbooks in Chinese', () => {
  for (const [query, id, terms] of [
    ['helm upgrade', 'cloud-native.helm.operations', ['操作步骤', '升级失败', '回滚']],
    ['kustomization.yaml', 'cloud-native.kustomize.operations', ['overlay', '构建', '常见报错']],
    ['argocd app sync', 'cloud-native.argocd.operations', ['同步', '漂移', '回滚']],
    ['PromQL', 'cloud-native.prometheus.operations', ['指标', 'PromQL', '告警']],
    ['Grafana Dashboard', 'cloud-native.grafana.operations', ['数据源', 'Dashboard', '权限']]
  ]) {
    const entry = searchKnowledgeEntries({ query }).find(result => result.id === id)
    assert.ok(entry, id)
    for (const term of terms) assert.match(entry.content, new RegExp(term, 'i'), `${id}:${term}`)
  }
})

test('indexes Kubernetes lab scenarios with safety boundaries', () => {
  const lab = searchKnowledgeEntries({ query: 'Pod Pending' }).find(result => result.id === 'cloud-native.lab.pod-pending')
  assert.ok(lab)
  assert.match(lab.content, /实验集群/)
  assert.match(lab.content, /kubectl describe pod/)
  assert.match(lab.content, /禁止对生产上下文执行/)
  assert.ok(searchKnowledgeEntries({ domain: 'cloud-operations', service: 'kubernetes-lab' }).length >= 8)
})

test('indexes cloud native observability components', () => {
  for (const [query, id] of [['LogQL', 'cloud-native.observability.loki'], ['OTLP', 'cloud-native.observability.opentelemetry'], ['Alertmanager', 'cloud-native.observability.alertmanager'], ['node_cpu_seconds_total', 'cloud-native.observability.node-exporter']]) {
    assert.ok(searchKnowledgeEntries({ query }).some(result => result.id === id), id)
  }
  assert.ok(searchKnowledgeEntries({ domain: 'cloud-operations', service: 'observability' }).length >= 5)
})

test('indexes GitOps delivery, drift, canary and rollback runbooks', () => {
  for (const [query, id] of [['argocd app sync', 'cloud-native.gitops.application-sync'], ['OutOfSync', 'cloud-native.gitops.drift-detection'], ['ApplicationSet', 'cloud-native.gitops.multi-environment'], ['kubectl argo rollouts', 'cloud-native.gitops.canary-rollout'], ['argocd app rollback', 'cloud-native.gitops.rollback']]) {
    assert.ok(searchKnowledgeEntries({ query }).some(result => result.id === id), id)
  }
  const entries = searchKnowledgeEntries({ domain: 'cloud-operations', service: 'gitops-delivery' })
  assert.ok(entries.length >= 6)
  assert.ok(entries.every(item => /生产发布|发布/.test(item.risk)))
})

test('indexes cloud native supply chain security runbooks', () => {
  for (const [query, id] of [
    ['trivy image', 'cloud-native.supply-chain.trivy-image-scan'],
    ['CycloneDX', 'cloud-native.supply-chain.sbom-governance'],
    ['cosign verify', 'cloud-native.supply-chain.image-signing'],
    ['Harbor robot account', 'cloud-native.supply-chain.harbor-governance'],
    ['ClusterImagePolicy', 'cloud-native.supply-chain.admission-policy'],
    ['kubectl get certificate', 'cloud-native.supply-chain.cert-manager'],
    ['镜像供应链事件', 'cloud-native.supply-chain.incident-response']
  ]) {
    assert.ok(searchKnowledgeEntries({ query }).some(result => result.id === id), id)
  }

  const entries = searchKnowledgeEntries({ domain: 'cloud-operations', service: 'supply-chain-security' })
  assert.ok(entries.length >= 7)
  assert.ok(entries.every(item => item.content.includes('## 验证') && item.content.includes('## 常见报错原因')))
})

test('includes the enterprise operation brain fault library', () => {
  const results = searchKnowledgeEntries({ query: 'CrashLoopBackOff' })

  assert.ok(results.some(result => result.id === 'kubernetes-crashloopbackoff'))
})

test('includes senior Linux and MySQL troubleshooting references', () => {
  const linux = searchKnowledgeEntries({ query: 'iostat' })
  const mysql = searchKnowledgeEntries({ query: 'show processlist' })

  assert.ok(linux.some(result => result.id === 'linux-cpu-high'))
  assert.ok(mysql.some(result => result.id === 'mysql-too-many-connections'))
})

test('indexes Linux process management by module id and diagnostic terms', () => {
  for (const query of ['LINUX-PROCESS-001', 'D state', 'ps aux']) {
    const results = searchKnowledgeEntries({ query })
    assert.ok(results.some(result => result.id === 'linux-process-management'), query)
  }
})

test('includes the complete Linux process diagnostic content', () => {
  const entry = searchKnowledgeEntries({ query: 'LINUX-PROCESS-001' }).find(result => result.id === 'linux-process-management')
  assert.ok(entry)
  for (const term of ['SIGTERM', 'SIGKILL', 'iostat', 'zombie', '/proc']) assert.match(entry.content, new RegExp(term.replace('/', '\\/'), 'i'))
})

test('builds a nested read-only tree and resolves paths for agent access', () => {
  assert.equal(knowledgeTree.kind, 'root')
  const nginx = getKnowledgeNode('nginx-502-diagnosis')
  assert.equal(nginx.kind, 'entry')
  assert.deepEqual(getKnowledgePath(nginx.id).map(node => node.kind), ['root', 'folder', 'folder', 'folder', 'entry'])
  assert.equal(knowledgeReadApi.node(nginx.id).id, nginx.id)
  assert.ok(knowledgeReadApi.search({ query: '502' }).some(entry => entry.id === nginx.id))
  assert.equal(Object.keys(knowledgeReadApi).includes('create'), false)
})

test('every knowledge entry has one explicit directory path in the tree', () => {
  const leaves = new Map()
  const visit = node => {
    if (node.kind === 'entry') leaves.set(node.id, node)
    for (const child of node.children || []) visit(child)
  }
  visit(knowledgeTree)
  assert.equal(leaves.size, new Set(knowledgeEntries.map(entry => entry.id)).size)
  for (const entry of knowledgeEntries) {
    const leaf = leaves.get(entry.id)
    assert.ok(leaf, entry.id)
    assert.equal(leaf.directory.pathKey, `${entry.domain}/${entry.service || 'general'}/${entry.section || 'general'}`)
    assert.equal(getKnowledgePath(entry.id).at(-1).id, entry.id)
  }
})
