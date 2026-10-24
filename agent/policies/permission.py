class PermissionChecker:

    def __init__(
        self,
        allowed_roles=None,
    ):
        self.allowed_roles = (
            allowed_roles
            or {
                "admin",
                "operator",
            }
        )

    def check(
        self,
        role: str,
    ) -> bool:

        return role in self.allowed_roles