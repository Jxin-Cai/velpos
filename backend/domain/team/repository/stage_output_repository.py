from abc import ABC, abstractmethod

from domain.team.model.stage_output import StageOutput


class StageOutputRepository(ABC):
    @abstractmethod
    async def save(self, stage_output: StageOutput) -> None:
        pass

    @abstractmethod
    async def find_by_id(self, stage_output_id: str) -> StageOutput | None:
        pass

    @abstractmethod
    async def find_latest_by_execution_id(self, execution_id: str) -> StageOutput | None:
        pass

    @abstractmethod
    async def find_by_card_id(self, card_id: str) -> list[StageOutput]:
        pass

    @abstractmethod
    async def remove_by_card_id(self, card_id: str) -> None:
        pass
