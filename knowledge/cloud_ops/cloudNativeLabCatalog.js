const lab = (id, title, summary, fault, steps) => ({
  id: `cloud-native.lab.${id}`,
  domain: 'cloud-operations',
  platform: 'Cloud Native',
  service: 'kubernetes-lab',
  type: 'KUBERNETES LAB',
  title,
  summary,
  source: 'SmartOpsAgent Kubernetes Lab Pack',
  section: 'KUBERNETES_LAB',
  version: '1.0',
  risk: '仅允许在实验集群执行',
  tags: ['Kubernetes', 'kind', '实验室', '故障注入', fault],
  content: [`# ${title}`, `## 实验目标\n${summary}`, `## 故障场景\n${fault}`, `## 实验步骤\n${steps}`, '## 验收标准\n记录故障现象、kubectl 证据、根因判断、修复命令和修复后验证结果。', '## 安全边界\n实验前确认 kubectl 当前上下文为实验集群；禁止对生产上下文执行故障注入、删除资源或批量修改。'].join('\n\n')
})

export const cloudNativeLabEntries = [
  lab('kind-bootstrap', 'kind 本地 Kubernetes 实验集群创建', '创建可重复销毁的本地 Kubernetes 集群。', '实验集群无法创建或节点未 Ready', 'kind create cluster --name smartops-lab；kubectl cluster-info；kubectl get nodes -o wide；实验结束执行 kind delete cluster --name smartops-lab。'),
  lab('pod-pending', 'Pod Pending 调度故障实验', '理解资源不足、节点选择器和污点导致的调度失败。', 'Pod 长时间 Pending，事件出现 FailedScheduling', '部署带 nodeSelector 或过高 requests 的 Pod；执行 kubectl describe pod；执行 kubectl get events；修正资源或调度条件；确认 Pod Running。'),
  lab('crash-loop', 'CrashLoopBackOff 容器故障实验', '通过错误启动命令分析容器反复重启。', '容器退出码非零，Pod 进入 CrashLoopBackOff', '部署错误 command；执行 kubectl get pod；kubectl logs --previous；kubectl describe pod；修正 command；确认重启次数停止增长。'),
  lab('image-pull', 'ImagePullBackOff 镜像拉取故障实验', '识别镜像名称、仓库认证和网络导致的拉取失败。', 'Pod 事件出现 ErrImagePull 或 ImagePullBackOff', '部署不存在的镜像；查看 kubectl describe pod 事件；修正镜像地址或 imagePullSecret；确认容器成功启动。'),
  lab('service-endpoint', 'Service 无 Endpoint 故障实验', '理解 Selector、Pod Label 和 EndpointSlice 的关系。', 'Service 存在但 endpoints 为空，访问失败', '创建 selector 与 Pod label 不匹配的 Service；执行 kubectl get endpointslice；检查 selector 和 labels；修正后使用 curl 验证。'),
  lab('ingress-host', 'Ingress Host 不匹配故障实验', '验证 Host、IngressClass、Service 和 DNS 入口链路。', '直接访问 IP 命中默认后端，域名访问失败', '创建 Host 规则；使用 curl -H Host:example.test；检查 kubectl describe ingress；修正 hosts 或规则；验证 HTTP 响应。'),
  lab('pvc-pending', 'PVC Pending 存储故障实验', '理解 StorageClass、PV、PVC 和 CSI 的绑定关系。', 'PVC 长时间 Pending，事件提示无法绑定', '创建 PVC；查看 kubectl describe pvc；检查 StorageClass 和 PV；补齐存储配置；确认 PVC Bound 后挂载 Pod。'),
  lab('readiness-probe', 'ReadinessProbe 失败实验', '区分进程存活与业务可接收流量状态。', 'Pod Running 但 Ready 为 0，Service 无可用后端', '配置错误健康检查路径；查看 kubectl describe pod；修正探针路径或端口；确认 Ready 恢复并检查 EndpointSlice。')
]
