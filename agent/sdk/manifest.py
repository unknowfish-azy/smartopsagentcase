from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.permission import Permission
from agent.sdk.risk import OperationRisk, RiskManifest


@dataclass
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    description: str = ""

    permissions: list[Permission] = field(
        default_factory=list
    )

    risk_manifest: RiskManifest | None = None

    dependencies: list[str] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @classmethod
    def from_yaml(
        cls,
        path: str | Path,
    ) -> "PluginManifest":

        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(file_path)

        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "解析 Manifest 需要安装 PyYAML：pip install pyyaml"
            ) from exc

        with file_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = yaml.safe_load(file) or {}

        plugin_data = data.get("plugin", {})
        permissions_data = data.get(
            "permissions",
            [],
        )

        permission_objects = []

        for item in permissions_data:
            permission_objects.append(
                Permission(
                    resource=item["resource"],
                    actions=frozenset(
                        item.get("actions", [])
                    ),
                )
            )

        operations = []

        risk_data = data.get("risk", {})

        for item in risk_data.get(
            "operations",
            [],
        ):
            operations.append(
                OperationRisk(
                    operation=item["operation"],
                    risk=RiskLevel(
                        item.get(
                            "risk",
                            "MEDIUM",
                        )
                    ),
                    approval_required=item.get(
                        "approval_required",
                        False,
                    ),
                    description=item.get(
                        "description",
                        "",
                    ),
                )
            )

        risk_manifest = RiskManifest(
            plugin_id=plugin_data["id"],
            operations=operations,
        )

        return cls(
            plugin_id=plugin_data["id"],
            name=plugin_data.get(
                "name",
                plugin_data["id"],
            ),
            version=plugin_data.get(
                "version",
                "0.1.0",
            ),
            description=plugin_data.get(
                "description",
                "",
            ),
            permissions=permission_objects,
            risk_manifest=risk_manifest,
            dependencies=data.get(
                "dependencies",
                [],
            ),
            metadata=data.get(
                "metadata",
                {},
            ),
        )