const gitopsEntry = (id, title, summary, tags, sections) => ({
  id: `cloud-native.gitops.${id}`,
  domain: 'cloud-operations',
  platform: 'Cloud Native',
  service: 'gitops-delivery',
  type: 'GITOPS DELIVERY RUNBOOK',
  title,
  summary,
  source: 'SmartOpsAgent GitOps Delivery Pack',
  section: 'GITOPS_DELIVERY',
  version: '1.0',
  risk: '生产发布与回滚必须确认目标集群和变更范围',
  tags: ['GitOps', 'Argo CD', 'Helm', 'Kustomize', ...tags],
  content: [`# ${title}`, `## 目标\n${summary}`, ...sections, '## 发布证据\n保留 Git Commit、应用版本、目标集群、同步结果、资源健康状态、验证结果、操作者和 TraceId。'].join('\n\n')
})

export const cloudNativeGitOpsEntries = [
  gitopsEntry('application-sync', 'Argo CD 应用同步标准流程', '从 Git 变更检查到集群同步、健康验证和发布记录。', ['同步', '发布'], [
    '## 前置检查\n确认仓库、分支、目标集群、Namespace、Application Project 和当前版本。执行 argocd app diff APP_NAME 查看实际变更。',
    '## 操作步骤\n1. 合并经过审核的 Git 变更。\n2. 执行 argocd app get APP_NAME。\n3. 执行 argocd app sync APP_NAME。\n4. 执行 argocd app wait APP_NAME --sync --health --timeout 300。\n5. 使用 kubectl get deploy,pod,svc,endpointslice -n NAMESPACE 验证。',
    '## 常见报错原因\n仓库凭据失效、路径或 Revision 错误、Helm Values 渲染失败、Kustomize Patch 不匹配、RBAC 不足、资源健康检查失败。'
  ]),
  gitopsEntry('drift-detection', 'GitOps 配置漂移检测与处置', '识别 Git 期望状态与集群实际状态的差异。', ['漂移', 'OutOfSync'], [
    '## 观测证据\nArgo CD 显示 OutOfSync；argocd app diff APP_NAME 展示字段差异；Kubernetes 审计日志可能记录手工变更。',
    '## 处置步骤\n先确认差异来自人工修改、默认字段、控制器回写还是 Git 变更。合法变更回写 Git；非法变更通过同步恢复。忽略差异规则必须限定资源和字段。',
    '## 风险\n自动同步可能覆盖紧急现场修复。处置前保存当前资源 YAML，并确认是否存在正在进行的 Incident。'
  ]),
  gitopsEntry('multi-environment', 'GitOps 多环境发布设计', '使用目录、分支或 ApplicationSet 管理开发、测试和生产环境。', ['ApplicationSet', '多环境'], [
    '## 推荐结构\n应用 Chart 或 Base 保持复用；dev、test、prod 只保存环境差异；镜像版本使用明确 Tag 或 Digest；生产变更经过独立审核。',
    '## 操作步骤\n先在开发环境验证，再提升到测试环境；保存测试证据后更新生产环境声明；Argo CD 分环境同步并验证。',
    '## 常见问题\n环境参数复制导致漂移、生产引用 latest、Secret 混入 Git、多个环境共享可变 Values 文件。'
  ]),
  gitopsEntry('canary-rollout', 'Argo Rollouts 金丝雀发布与自动回滚', '按流量比例逐步发布新版本，并根据指标决定继续或回滚。', ['Argo Rollouts', 'Canary', '灰度'], [
    '## 发布步骤\n配置 Rollout、stableService、canaryService 和流量步骤；先发布少量流量；观察错误率、延迟、资源和业务指标；达到阈值后继续推进。',
    '## 操作命令\nkubectl argo rollouts get rollout NAME -n NAMESPACE --watch；kubectl argo rollouts promote NAME -n NAMESPACE；kubectl argo rollouts abort NAME -n NAMESPACE。',
    '## 回滚条件\n错误率升高、P95 延迟超标、健康检查失败、关键业务指标下降或告警触发。分析模板不可用时停止自动推进。'
  ]),
  gitopsEntry('rollback', 'GitOps 发布失败回滚流程', '在应用同步或业务验证失败后恢复到已验证版本。', ['回滚', 'Incident'], [
    '## 判断顺序\n先区分 Git 渲染失败、资源部署失败和业务功能失败。记录失败版本、现象、事件、日志和指标。',
    '## 回滚步骤\n优先 revert Git Commit 并重新同步；紧急情况下使用 argocd app rollback APP_NAME HISTORY_ID；工作负载可临时使用 kubectl rollout undo，但必须随后修正 Git。',
    '## 验证\n确认 Argo CD Synced/Healthy、Deployment Available、副本稳定、Service Endpoint 正常、健康接口成功、错误率恢复。'
  ]),
  gitopsEntry('release-audit', 'GitOps 发布审计与证据留存', '让每次发布、失败和回滚都可以追踪和复盘。', ['审计', 'Evidence'], [
    '## 必备字段\n应用、环境、集群、Namespace、Git 仓库、Commit、镜像 Digest、发起人、审批人、开始时间、结束时间、同步结果、验证结果和回滚记录。',
    '## SmartOpsAgent 关联\n发布记录关联 RunRecord、Incident、KnowledgeItem 和 AgentTrace；敏感凭据、Token 和 Secret 必须脱敏。'
  ])
]
