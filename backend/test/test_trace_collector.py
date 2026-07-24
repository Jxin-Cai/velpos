from __future__ import annotations

import unittest

import pytest

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


class TraceCollectorAbandonTest(unittest.TestCase):

    def setUp(self) -> None:
        self.collector = TraceCollector(repository=_RepositoryStub())  # type: ignore[arg-type]
        self.session_id = "session1"
        self.run_id = "run1"

    def test_finish_run_marks_spans_abandoned_when_flag_set(self) -> None:
        self.collector.ensure_run_span(self.session_id, self.run_id)
        main = self.collector.find_main_agent_span(self.session_id, self.run_id)
        turn_id = self.collector.create_span(
            self.session_id, self.run_id,
            TraceSpan.SPAN_TYPE_LLM_TURN, "assistant",
            parent_span_id=main.id if main else None,
        )

        self.collector.finish_run(self.session_id, self.run_id, abandoned=True)

        turn = self.collector.find_span_by_id(turn_id or "")
        self.assertEqual(turn.status if turn else None, TraceSpan.STATUS_ABANDONED)
        run_span = self.collector.find_run_span(self.session_id, self.run_id)
        self.assertEqual(run_span.status if run_span else None, TraceSpan.STATUS_ABANDONED)

    def test_abandon_all_running_closes_all_sessions_spans(self) -> None:
        self.collector.ensure_run_span(self.session_id, self.run_id)
        self.collector.create_span(
            self.session_id, self.run_id,
            TraceSpan.SPAN_TYPE_LLM_TURN, "turn1",
        )
        self.collector.ensure_run_span(self.session_id, "run2")

        self.collector.abandon_all_running(self.session_id, reason="Process lost")

        running = [
            s for s in self.collector._buffer.values()
            if s.session_id == self.session_id and s.status == TraceSpan.STATUS_RUNNING
        ]
        self.assertEqual(len(running), 0)

    def test_find_subagent_by_tool_use_id_filters_by_run_id(self) -> None:
        self.collector.create_span(
            self.session_id, "run1",
            TraceSpan.SPAN_TYPE_SUBAGENT, "sub1",
            tool_use_id="tool-1",
        )
        self.collector.create_span(
            self.session_id, "run2",
            TraceSpan.SPAN_TYPE_SUBAGENT, "sub2",
            tool_use_id="tool-1",
        )

        result = self.collector.find_subagent_by_tool_use_id(
            self.session_id, "tool-1", run_id="run1"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "sub1")

    def test_find_latest_llm_turn_returns_most_recent_regardless_of_status(self) -> None:
        turn1_id = self.collector.create_span(
            self.session_id, self.run_id,
            TraceSpan.SPAN_TYPE_LLM_TURN, "turn1",
        )
        self.collector.complete_span(turn1_id or "")
        turn2_id = self.collector.create_span(
            self.session_id, self.run_id,
            TraceSpan.SPAN_TYPE_LLM_TURN, "turn2",
        )
        self.collector.complete_span(turn2_id or "")

        result = self.collector.find_latest_llm_turn(self.session_id, self.run_id)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, turn2_id)


@pytest.mark.asyncio
async def test_abandons_and_flushes_running_spans_when_collector_stops() -> None:
    # Arrange
    persisted: list[TraceSpan] = []

    class _CapturingRepository(_RepositoryStub):
        async def save_batch(self, spans: list[TraceSpan]) -> None:
            persisted.extend(spans)

    collector = TraceCollector(repository=_CapturingRepository())
    collector.ensure_run_span("session1", "run1")

    # Act
    await collector.stop()

    # Assert
    assert persisted
    assert all(span.status == TraceSpan.STATUS_ABANDONED for span in persisted)
