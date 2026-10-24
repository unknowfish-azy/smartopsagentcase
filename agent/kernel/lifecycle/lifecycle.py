from enum import Enum


class LifecycleState(str, Enum):
    CREATED = "CREATED"
    MOUNTING = "MOUNTING"
    MOUNTED = "MOUNTED"
    UNMOUNTING = "UNMOUNTING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class LifecycleManager:

    def __init__(self) -> None:
        self._states: dict[str, LifecycleState] = {}

    def set_state(
        self,
        component_id: str,
        state: LifecycleState,
    ) -> None:
        self._states[component_id] = state

    def get_state(self, component_id: str) -> LifecycleState | None:
        return self._states.get(component_id)

    def remove(self, component_id: str) -> None:
        self._states.pop(component_id, None)