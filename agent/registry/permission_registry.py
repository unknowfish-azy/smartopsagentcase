from agent.sdk.permission import Permission


class PermissionRegistry:

    def __init__(self) -> None:
        self._permissions: dict[
            str,
            Permission,
        ] = {}

    def register(
        self,
        permission: Permission,
    ) -> None:
        self._permissions[
            permission.key
        ] = permission

    def has(
        self,
        resource: str,
        action: str,
    ) -> bool:

        for permission in self._permissions.values():

            if (
                permission.resource == resource
                and permission.allows(action)
            ):
                return True

        return False

    def list(self):
        return list(self._permissions.values())