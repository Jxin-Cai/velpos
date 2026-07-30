from abc import ABC, abstractmethod

from domain.team.model.flow_plan import FlowPlan, FlowStep


class FlowPlanRepository(ABC):
    @abstractmethod
    async def save(self, flow_plan: FlowPlan) -> None:
        pass

    @abstractmethod
    async def find_by_id(self, plan_id: str) -> FlowPlan | None:
        pass

    @abstractmethod
    async def find_active_by_card_id(self, card_id: str) -> FlowPlan | None:
        pass

    @abstractmethod
    async def find_active_by_team_id(self, team_id: str) -> list[FlowPlan]:
        pass

    @abstractmethod
    async def find_all_active(self) -> list[FlowPlan]:
        pass

    @abstractmethod
    async def find_step_by_execution_id(self, execution_id: str) -> FlowStep | None:
        pass

    @abstractmethod
    async def remove(self, flow_plan: FlowPlan) -> None:
        pass
