# ops-service

这是智维Agent未来微服务拆分的部署占位目录。

建议职责：

- `ops-service`：与根目录对应模块保持单一职责。
- 对外接口通过Gateway暴露。
- 服务间调用使用明确超时、重试、审计和request_id。
- 生产镜像地址和版本由CI/CD注入。
