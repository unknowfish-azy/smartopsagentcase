// Coverage of the user-supplied landscape. These are implementation states,
// never observations of a live host or cloud account.
export const cloudCoverage = [
  { domain: '云基础资源', priority: 1, knowledge: 'ECS / RDS / OSS / VPC / RAM / 生命周期 / IaC', tools: '官方 CLI、OpenAPI / SDK、Terraform、ROS', status: 'Terraform 环境检查已接入；公有云 API 待接入', toolId: 'terraform-environment', next: '配置云账号凭据引用、地域与只读权限，再接资源清单、分页和错误审计；创建、释放和扩缩容单独审批。' },
  { domain: '云网络', priority: 2, knowledge: '子网 / 路由 / NAT / 负载均衡 / 安全组 / DNS / CDN', tools: 'ping、traceroute、mtr、dig、tcpdump、Wireshark', status: '已有网络诊断入口；云网络拓扑待接入', toolId: 'network-diagnostics', next: '关联目标、时间、DNS、端口与链路证据；抓包限定目标、时长和授权。' },
  { domain: '云存储与数据库', priority: 2, knowledge: '对象 / 块 / 文件存储、备份恢复、慢 SQL、连接、锁与复制', tools: 'DBeaver、mysql、redis-cli、mysqltuner、EXPLAIN', status: '已有查询模板；数据库只读适配器待接入', toolId: 'database-readonly', next: '建立实例连接与只读账号、查询超时、行数上限和 SQL 脱敏；备份恢复走独立变更流程。' },
  { domain: '监控告警', priority: 1, knowledge: '延迟 / 流量 / 错误 / 饱和度、时序指标、降噪与闭环', tools: 'Prometheus、Grafana、Zabbix、ELK、Loki、Alertmanager', status: '已有查询入口；数据源需配置并验证', toolId: 'prometheus-query', next: '接入实际监控地址和凭据引用，统一时间窗口；告警抑制与消息发送需要授权。' },
  { domain: '自动化运维', priority: 2, knowledge: 'Shell / Python、批量配置、定时任务、流程编排', tools: 'Ansible、SaltStack、Fabric、Crond', status: '已有受控执行基础；自动化平台待接入', toolId: 'service-restart', next: '固定模板、参数校验、目标清单、并发限制、前后检查与审批；拒绝模型直接提交任意 Shell。' },
  { domain: '云安全与合规', priority: 3, knowledge: '基线、漏洞、访问控制、审计、加密与合规要求', tools: 'OpenVAS、Trivy、云安全中心、堡垒机', status: '扫描与云安全平台待接入', next: '先导入已有扫描报告并保留来源，再提供限定范围的扫描任务；报告不等同于合规认证。' },
  { domain: 'Docker 容器', priority: 1, knowledge: '镜像 / 网络 / 存储 / 生命周期、Dockerfile、多阶段构建', tools: 'Docker、Compose、Harbor、Docker Hub、dive', status: '容器及日志已有；Compose 巡检新增', toolId: 'docker-compose-status', next: '巡检需已授权远程连接和目标 CLI；镜像扫描、仓库盘点后续接入，禁止自动清理镜像和数据卷。' },
  { domain: 'Kubernetes', priority: 1, knowledge: '架构、核心资源、调度、服务发现、RBAC、滚动发布与故障排查', tools: 'kubectl、k9s、kubectx、Helm、Rancher、kubeadm、crictl', status: '已有资源日志；新增 Helm / PVC / RBAC 巡检', toolId: 'helm-releases', next: '执行前确认 Context 与 Namespace；权限不足、CLI 缺失、命令超时都记录为真实失败。' },
  { domain: '云原生可观测性', priority: 3, knowledge: 'Metrics / Logs / Tracing、Exporter、PromQL、日志采集与 APM', tools: 'Node Exporter、cAdvisor、Loki、ELK、OpenTelemetry、SkyWalking、Jaeger', status: '指标日志已有模板；追踪关联待接入', toolId: 'loki-log-query', next: '按服务身份、时间窗与 TraceId 关联证据；观测组件选型和版本需部署时核验。' },
  { domain: 'CI/CD 与 GitOps', priority: 3, knowledge: '持续集成交付、Git 可信源、蓝绿 / 金丝雀 / 灰度、质量门禁', tools: 'Jenkins、GitLab CI、GitHub Actions、Argo CD、Flux CD', status: '已有知识入口；流水线 API 待接入', next: '先查询发布记录和同步差异，再实现绑定版本、目标和审批的发布与回滚，不能自动触发生产变更。' },
  { domain: '云原生安全', priority: 3, knowledge: '镜像漏洞、集群基线、最小权限、运行时与 Pod 安全', tools: 'Trivy、kube-bench、Falco', status: 'RBAC 检查新增；扫描与运行时事件待接入', toolId: 'k8s-rbac-check', next: '保存报告版本与证据来源；高权限基线检查单独授权，不能仅凭扫描结果自动修复。' },
  { domain: '服务网格', priority: 3, knowledge: '流量治理、熔断、降级、限流、灰度与服务间安全', tools: 'Istio、Linkerd、Kiali', status: '组件巡检新增；流量与拓扑 API 待接入', toolId: 'mesh-status', next: '组件状态只是证据之一，进一步关联请求指标和追踪；流量规则修改必须审批并验证。' }
]
