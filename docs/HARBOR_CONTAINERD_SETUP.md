# Harbor 与 Containerd 接入说明

本文对应 SmartOpsAgent 的 Harbor 只读目录和 Containerd 仓库检查工具。它们不会在 Windows 前端中虚构项目、镜像或节点数据；必须先部署真实 Harbor，并把后端配置指向它。

## 1. 前置条件

Harbor 官方安装包需要 Linux 主机、Docker Engine 和 Docker Compose plugin。当前 Windows 开发机没有 Docker、Kubernetes 或 Linux 容器运行时，因此只能准备安装包，不能在本机完成 Harbor 部署。

下载后应校验 SHA256，再复制到 Linux 主机：

```bash
sha256sum harbor-online-installer-v2.15.2.tgz
tar -xzf harbor-online-installer-v2.15.2.tgz
cd harbor
cp harbor.yml.tmpl harbor.yml
```

在 `harbor.yml` 至少设置：

```yaml
hostname: harbor.example.com
https:
  port: 443
  certificate: /data/cert/harbor.crt
  private_key: /data/cert/harbor.key
data_volume: /data
```

生产环境使用受信任 CA 签发的 HTTPS 证书；不要把课程中的明文密码、HTTP 地址或默认管理员口令直接用于生产。执行安装并验证：

```bash
sudo ./install.sh --with-trivy
docker compose ps
curl --fail https://harbor.example.com/api/v2.0/health
```

## 2. SmartOpsAgent 后端配置

在启动后端的同一环境中设置：

```powershell
$env:SMARTOPS_HARBOR_URL = "https://harbor.example.com"
$env:SMARTOPS_HARBOR_USERNAME = "smartops-readonly"
$env:SMARTOPS_HARBOR_SECRET = "使用外部密钥管理器注入"
```

Linux 示例：

```bash
export SMARTOPS_HARBOR_URL=https://harbor.example.com
export SMARTOPS_HARBOR_USERNAME=smartops-readonly
export SMARTOPS_HARBOR_SECRET='从 Secret Manager 注入'
```

账号只需 Harbor 项目读取权限。后端只调用 `GET /api/v2.0/projects` 和 `GET /api/v2.0/projects/{project}/repositories`，不保存或返回密码，不执行推送、删除和权限修改。修改变量后必须重启后端，再在“Harbor 项目与镜像”工具中点击“重新检查连接”。

## 3. Containerd 连接 Harbor

在实际 Kubernetes 节点上确认 `containerd`、`ctr` 和节点时钟正常：

```bash
systemctl is-active containerd
ctr version
ctr namespaces list
```

推荐使用 `/etc/containerd/certs.d/harbor.example.com/hosts.toml`：

```toml
server = "https://harbor.example.com"

[host."https://harbor.example.com"]
  capabilities = ["pull", "resolve"]
  ca = "/etc/containerd/certs.d/harbor.example.com/ca.crt"
```

如果 Harbor 使用自签名证书，应把 CA 安全分发到节点并配置 `config_path = "/etc/containerd/certs.d"`，然后重启 containerd。不要通过关闭 TLS 校验掩盖证书问题。私有仓库认证应使用 Kubernetes `imagePullSecret` 或节点侧受控凭据，不要把密码写入命令历史。

验证只读状态：

```bash
ctr namespaces list
ctr -n k8s.io images list
ctr plugins ls
crictl info
```

SmartOpsAgent 的“Containerd 仓库检查”只执行上述查询。`ctr` 的 namespace 与 Kubernetes CRI namespace 可能不同；看不到镜像不等于镜像不存在，应先确认运行时和 namespace，再核对 Harbor 项目、TLS、认证及镜像架构。

## 4. 常见故障证据

* `Harbor 尚未配置`：后端没有读取到 `SMARTOPS_HARBOR_URL`，不是 Harbor 项目为空。
* `401/403`：地址可达，但账号或项目读取授权不足。
* TLS/超时：检查 DNS、路由、防火墙、证书 SAN、节点时间和代理配置。
* `ctr` 无法连接 socket：检查 containerd 服务、socket 路径和当前用户权限。
* `pull` 失败而 Harbor API 正常：继续检查 `hosts.toml`、CA、imagePullSecret、镜像 tag/digest 和 CPU 架构。

所有查询都会生成运行记录和 traceId；没有真实数据源时页面显示未配置或不可达，不生成虚假结果。
