class SmartOpsSDKError(Exception):
    """SDK基础异常。"""


class PluginError(SmartOpsSDKError):
    """插件异常。"""


class ManifestError(SmartOpsSDKError):
    """Manifest格式异常。"""


class PermissionError(SmartOpsSDKError):
    """权限异常。"""


class RiskError(SmartOpsSDKError):
    """风险定义异常。"""


class SandboxError(SmartOpsSDKError):
    """Sandbox异常。"""