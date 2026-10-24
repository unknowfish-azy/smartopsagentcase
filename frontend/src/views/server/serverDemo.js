const examples = [
  { id: 'demo:web', name: 'demo-web-gateway-01', host: '192.0.2.11', os: 'Ubuntu 24.04 LTS', status: 'ONLINE', role: 'Web 网关', specification: '4 vCPU / 8 GiB / 100 GiB', uptime: '18 天（模拟）', metrics: { cpu: 23, memory: 42, disk: 38 }, description: '演示：Nginx 网关，模拟稳定运行。', scenario: '观察正常节点的资源占用与服务器配置。' },
  { id: 'demo:mysql', name: 'demo-mysql-primary-01', host: '192.0.2.21', os: 'Rocky Linux 9', status: 'WARNING', role: 'MySQL 主库', specification: '8 vCPU / 32 GiB / 500 GiB', uptime: '42 天（模拟）', metrics: { cpu: 76, memory: 91, disk: 63 }, description: '演示：内存使用率偏高，等待人工排查。', scenario: '模拟数据库内存告警。高使用率仅是线索，不据此判断泄漏或直接重启。' },
  { id: 'demo:redis', name: 'demo-redis-cache-01', host: '192.0.2.31', os: 'Debian 12', status: 'ONLINE', role: 'Redis 缓存', specification: '4 vCPU / 16 GiB / 80 GiB', uptime: '9 天（模拟）', metrics: { cpu: 18, memory: 56, disk: 24 }, description: '演示：缓存节点，模拟正常负载。', scenario: '展示缓存节点的容量配置，不包含真实键、命中率或业务数据。' },
  { id: 'demo:kubernetes', name: 'demo-k8s-worker-01', host: '192.0.2.41', os: 'Ubuntu 24.04 LTS', status: 'ONLINE', role: 'Kubernetes 节点', specification: '16 vCPU / 64 GiB / 300 GiB', uptime: '27 天（模拟）', metrics: { cpu: 46, memory: 61, disk: 49 }, description: '演示：集群工作节点，未接入真实集群。', scenario: '展示节点资源；不虚构 Pod、集群连接或业务健康证明。' },
  { id: 'demo:harbor', name: 'demo-harbor-registry-01', host: '192.0.2.51', os: 'Ubuntu 22.04 LTS', status: 'WARNING', role: 'Harbor 镜像仓库', specification: '8 vCPU / 16 GiB / 1 TiB', uptime: '33 天（模拟）', metrics: { cpu: 32, memory: 47, disk: 92 }, description: '演示：磁盘空间告警，不执行镜像清理。', scenario: '模拟容量预警。删除镜像、修改保留规则均不属于演示功能。' },
  { id: 'demo:offline', name: 'demo-lab-offline-01', host: '192.0.2.61', os: 'Debian 12', status: 'OFFLINE', role: '离线测试机', specification: '2 vCPU / 4 GiB / 60 GiB', uptime: '未知（模拟离线）', metrics: { cpu: null, memory: null, disk: null }, description: '演示：节点离线，不生成正常监控数值。', scenario: '展示未采集状态；不能把缺少数据解释为零负载或健康。' }
]

export const demoServers = Object.freeze(examples.map(server => Object.freeze({ ...server, demo: true, port: 22, createdAt: null, metrics: Object.freeze(server.metrics) })))
export const isDemoServer = server => server?.demo === true || String(server?.id || '').startsWith('demo:')
export const findDemoServer = id => demoServers.find(server => server.id === id) || null
export const serverRowsForMode = (mode, realRows) => mode === 'demo' ? demoServers : realRows
