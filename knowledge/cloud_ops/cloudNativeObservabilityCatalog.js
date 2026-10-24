const observability = (id, title, summary, tags, content) => ({
  id: `cloud-native.observability.${id}`, domain: 'cloud-operations', platform: 'Cloud Native', service: 'observability', type: 'OBSERVABILITY RUNBOOK', title, summary, source: 'SmartOpsAgent Cloud Native Observability Pack', section: 'OBSERVABILITY', version: '1.0', risk: '生产告警和采集配置需审核', tags, content: [`# ${title}`, `## 定位\n${summary}`, content, '## 诊断原则\n先确认采集目标、数据源连通性、时间范围和权限，再判断指标或日志是否真的缺失。生产修改前保留当前配置并准备回滚。'].join('\n\n')
})

export const cloudNativeObservabilityEntries = [
  observability('loki', 'Loki 日志聚合与 LogQL 排查', '集中采集 Kubernetes 容器日志，并按标签检索故障证据。', ['Loki', 'LogQL', '日志'], '操作步骤：检查 Promtail 或 Alloy 采集器；确认 Loki Service 和就绪状态；在 Grafana Explore 使用 `{namespace="prod"}` 查询；再用 `{app="api"} |= "error"` 缩小范围。常见原因：标签配置错误、采集器权限不足、日志路径不匹配、Loki 存储不可写。'),
  observability('opentelemetry', 'OpenTelemetry 链路采集与 Trace 排查', '统一采集应用指标、日志和分布式链路。', ['OpenTelemetry', 'Trace', 'Span'], '操作步骤：检查 Collector Deployment 和配置；确认 OTLP HTTP 或 gRPC 端口；验证应用是否注入 OTEL_EXPORTER_OTLP_ENDPOINT；在 Tempo 或 Jaeger 查询 Trace。常见原因：端口协议不匹配、采样率过低、服务名缺失、网络策略阻断。'),
  observability('alertmanager', 'Alertmanager 告警路由与抑制排查', '负责告警分组、路由、静默、抑制和通知发送。', ['Alertmanager', '告警', '通知'], '操作步骤：检查 Alertmanager 集群状态；确认 PrometheusRule 告警为 firing；检查 route、receiver、inhibit_rules；使用静默列表确认是否被抑制。常见原因：路由匹配标签错误、接收器凭据失效、分组等待时间过长、告警被静默。'),
  observability('kube-state-metrics', 'kube-state-metrics 资源状态指标排查', '把 Kubernetes API 对象状态转换成 Prometheus 指标。', ['kube-state-metrics', 'Kubernetes', 'Metrics'], '重点指标包括 Deployment 副本、Pod 状态、Job、PVC 和 Node 条件。检查 ServiceMonitor、RBAC 和目标 UP 状态；若指标缺失，先确认 kube-state-metrics 能访问 API Server，再检查采集端口和标签。'),
  observability('node-exporter', 'Node Exporter 节点资源指标排查', '采集节点 CPU、内存、磁盘、文件系统和网络指标。', ['Node Exporter', '节点', '资源'], '检查 DaemonSet 是否每个节点运行；查询 node_cpu_seconds_total、node_memory_MemAvailable_bytes、node_filesystem_avail_bytes；若单节点无数据，检查 HostPath、端口、节点污点和 Prometheus Targets。')
]
