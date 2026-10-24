# Tool Plugin

Tool Plugin 是 SmartOps Harness 的工具能力扩展层。

Tool 是 Agent 真正能够调用的“执行能力”。

例如：

```text
docker.ps
docker.inspect
docker.logs
docker.compose
docker.restart

nginx.status
nginx.config_test
nginx.logs

mysql.status
mysql.variables
mysql.query_readonly

redis.info
redis.memory
redis.restart

kubernetes.get_pods
kubernetes.describe
kubernetes.logs