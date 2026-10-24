class ServerStatusTool:

    name = "server.status"

    description = "查询服务器服务状态"

    risk_level = "LOW"

    requires_approval = False

    def execute(
        self,
        service: str,
    ):

        allowed_services = {
            "nginx",
            "mysql",
            "redis",
        }

        if service not in allowed_services:
            raise ValueError(
                f"不支持查询服务: {service}"
            )

        # 当前先返回模拟数据。
        # 后续接入 backend / Linux Agent。
        return {
            "service": service,
            "status": "RUNNING",
            "source": "mock",
        }