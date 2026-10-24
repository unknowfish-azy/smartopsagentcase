from abc import ABC, abstractmethod


class AgentTool(ABC):

    name = ""

    description = ""

    risk_level = "LOW"

    requires_approval = False

    @abstractmethod
    def execute(
        self,
        **kwargs,
    ):
        raise NotImplementedError