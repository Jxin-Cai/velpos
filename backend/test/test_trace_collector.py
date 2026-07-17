from __future__ import annotations

import unittest

from application.session.trace_collector import TraceCollector
from domain.session.model.trace_span import TraceSpan


class _RepositoryStub:
    async def save_batch(self, spans: list[TraceSpan]) -> None:
        pass

    async def update_batch(self, spans: list[TraceSpan]) -> None:
        pass

    async def commit(self) -> None:
        pass


class TraceCollectorTest(unittest.TestCase):

    def setUp(self) -> None:
        self.collector = TraceCollector(repository=_RepositoryStub())  # type: ignore[arg-type]
        self.session_id = "session1"
        self.run_id = "run1"

    def test_preserves_output_when_completing_turn_without_new_output(self) -> None:
        # Arrange
        span_id = self.collector.create_span(
            self.session_id,
            self.run_id,
            TraceSpan.SPAN_TYPE_LLM_TURN,
            "assistant",
            output_preview="I will inspect the repository.",
        )

        # Act
        self.collector.complete_span(span_id or "")

        # Assert
        span = self.collector.find_span_by_id(span_id or "")
        self.assertEqual(span.output_preview if span else None, "I will inspect the repository.")

    def test_reparents_existing_tool_when_turn_arrives_after_hook(self) -> None:
        # Arrange
        self.collector.ensure_run_span(self.session_id, self.run_id)
        main_agent = self.collector.find_main_agent_span(self.session_id, self.run_id)
        tool_id = self.collector.ensure_tool_span(
            self.session_id,
            self.run_id,
            "tool-use-1",
            "Read",
            main_agent.id if main_agent else None,
            input_preview='{"file_path":"README.md"}',
        )
        turn_id = self.collector.create_span(
            self.session_id,
            self.run_id,
            TraceSpan.SPAN_TYPE_LLM_TURN,
            "assistant",
            parent_span_id=main_agent.id if main_agent else None,
        )

        # Act
        self.collector.reconcile_turn_tools(
            self.session_id,
            self.run_id,
            turn_id or "",
            [{"id": "tool-use-1", "name": "Read", "input": {"file_path": "README.md"}}],
        )

        # Assert
        tool = self.collector.find_span_by_id(tool_id or "")
        self.assertEqual(tool.parent_span_id if tool else None, turn_id)

    def test_captures_result_when_stream_is_fallback_source(self) -> None:
        # Arrange
        tool_id = self.collector.ensure_tool_span(
            self.session_id,
            self.run_id,
            "tool-use-2",
            "Bash",
            None,
        )

        # Act
        self.collector.record_tool_result(
            self.session_id,
            self.run_id,
            "tool-use-2",
            "command completed",
        )

        # Assert
        tool = self.collector.find_span_by_id(tool_id or "")
        self.assertEqual(tool.output_preview if tool else None, "command completed")


if __name__ == "__main__":
    unittest.main()
