# OCR 图片运维笔记：Kubernetes、镜像源与节点拓扑

> 来源目录：`C:\Users\33908\Desktop\ocr`
>
> 这些内容由图片人工校正整理。图片 OCR 结果只能作为知识候选，发布前必须人工审核版本、路径、命令和环境差异。

## 1. Kubernetes 控制面与工作节点访问链路

对应图片：`1asynccode.webp`

### 结构

```text
kubectl
  ↓ 认证与控制请求
API Server
  ├── etcd：保存集群状态
  ├── Scheduler：为待调度 Pod 选择节点
  └── Controller Manager：持续协调期望状态

工作节点：
kubelet：向 API Server 汇报节点和 Pod 状态，调用容器运行时
kube-proxy：维护 Service 转发规则
Pod → Container：真正运行应用
```

### 操作步骤

1. 先确认客户端身份和上下文：`kubectl config current-context`、`kubectl auth can-i get pods -A`。
2. 查看控制面和节点状态：`kubectl get nodes -o wide`、`kubectl get pods -n kube-system -o wide`。
3. 发现 Pod 异常时，沿 `API Server → Scheduler/Controller → kubelet → Pod → Container` 链路收集证据。
4. 发现 Service 不通时，沿 `Service → EndpointSlice → Pod → kube-proxy` 链路核对，不要只看 Pod 是否 Running。

### 常见报错原因

* `The connection to the server ... was refused`：API Server 地址、端口、证书或网络不可达。
* Pod 长期 `Pending`：调度约束、资源不足、污点容忍、PVC 或调度器问题。
* Pod `CrashLoopBackOff`：进程退出、配置/Secret 错误、探针失败或依赖不可用。
* Service 有 ClusterIP 但无 Endpoint：Selector 与 Pod label 不匹配，或 Pod 未 Ready。

## 2. 单主与多主架构

对应图片：`2asynccode.webp`

### 单主多节点

```text
Master1 ── Node1
         ├─ Node2
         └─ Node3
```

控制面故障会影响 API 调度和控制能力，因此只适合学习、测试或能接受控制面单点的场景。

### 多主多节点

```text
Master1 ─┐
Master2 ─┼─ Node1 / Node2 / Node3
Master3 ─┘
```

多主并不自动等于高可用。还要验证 API Server 入口、负载均衡、etcd 仲裁、证书轮换、备份恢复和跨故障域分布。

## 3. Master / Node 拓扑图

对应图片：`3asynccode.webp`

图片中的 `master`、`node1`、`node2` 是逻辑角色示意，不是可直接执行的主机名。实际排障时必须使用：

```bash
kubectl get nodes -L kubernetes.io/role -o wide
kubectl get --raw='/readyz?verbose'
kubectl get componentstatuses  # 仅适用于仍支持该资源的旧版本，不能作为新集群唯一判断
```

## 4. Yum、Containerd 与 Docker 镜像源

对应图片：`5asynccode.png`

### Yum/DNF 软件源

* 目标：Linux 软件包安装与更新。
* 常见目录：`/etc/yum.repos.d/`。
* 刷新缓存：`dnf makecache` 或 `yum makecache`。
* 排障：先检查仓库 URL、DNS、代理、GPG key 和系统版本；不要直接使用 `dnf update -y` 作为故障修复。

### Containerd registry

* 新版推荐：`/etc/containerd/certs.d/<registry>/hosts.toml`。
* 修改后：`systemctl restart containerd`，再用 `ctr namespaces list` 和 `ctr -n k8s.io images list` 验证。
* Harbor 私有仓库需要 CA、认证和 pull 权限；Kubernetes 工作负载通常还需要 `imagePullSecret`。

### Docker registry

* 配置通常位于 `/etc/docker/daemon.json`。
* 修改后执行 `systemctl daemon-reload`、`systemctl restart docker`。
* 生产环境优先 HTTPS 和受信任 CA，避免把 `insecure-registries` 当作默认方案。

## 5. 初始化、快照与批量安装

对应图片：`6asynccode.webp`

图片对比了三种流程：

1. 每台机器单独初始化、安装，重复成本高。
2. 初始化后制作快照，再批量创建安装节点。
3. 使用 `./init.sh`、`./install.sh` 自动化初始化和安装，再从安装后节点制作快照。

### 推荐流程

```text
基线主机
  ↓
初始化 Yum / Containerd / Docker / kubeadm 依赖
  ↓
校验版本、内核参数、时间同步、磁盘和证书
  ↓
制作不可变快照
  ↓
从快照创建节点
  ↓
为每台节点注入唯一 hostname、IP、证书和凭据
  ↓
加入集群并执行健康检查
```

快照不能复制唯一身份。恢复后必须重新生成 machine-id、节点证书、SSH 主机密钥，并确认数据盘和 etcd 数据不会被误复制。

## 6. 节点上的工作负载与存储

对应图片：`asynccode.webp`

图片展示了多个 Node 上运行 Nginx、MySQL、Redis 和共享存储的示意。实际 Kubernetes 设计中：

* Nginx 等无状态工作负载使用 Deployment，并通过 Service 暴露。
* MySQL、Redis 等有状态服务必须明确 StatefulSet、持久卷、备份、主从/哨兵或托管服务方案。
* “存储”不是一个抽象圆柱就完成了设计，需要确认 PV/PVC、StorageClass、CSI、拓扑、备份和恢复演练。
* 应用是否健康要结合 Pod Ready、Service Endpoint、业务探针、日志、指标和数据一致性共同判断。

## 7. OCR 审核规则

导入图片时必须保存：原图相对路径、识别引擎、语言、平均置信度、识别块坐标、人工修订记录和审核状态。低置信度文本、命令、路径、版本号和 IP 地址必须人工复核；OCR 不得自动执行图片中识别出的命令。
