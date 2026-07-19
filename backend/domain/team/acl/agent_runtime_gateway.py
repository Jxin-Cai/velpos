from abc import ABC, abstractmethod

from domain.team.model.card_execution import CardExecution


class AgentRuntimeGateway(ABC):
    @abstractmethod
    def start_execution(
        self,
        execution: CardExecution,
        workspace_ref: str,
        prompt: str,
    ) -> str:
        pass

    @abstractmethod
    def cancel_execution(self, runtime_run_id: str) -> None:
        pass
