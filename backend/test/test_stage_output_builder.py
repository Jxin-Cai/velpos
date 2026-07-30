from domain.team.acl.session_context_collector import SessionArtifact
from domain.team.model.card_execution import CardExecution
from domain.team.model.wish_card import WishCard
from application.team_board.stage_output_builder import StageOutputBuilder


def test_structured_snapshot_created_when_final_output_has_handoff_sections() -> None:
    # Arrange
    card = WishCard.create(
        team_id="team-1",
        title="Improve Teams handoff",
        description="Pass bounded context between agents.",
    )
    execution = CardExecution.create(card.id, "slot-1")
    final_output = """## 阶段结论
The handoff model is ready.

## 已完成
- Added a versioned stage output.
- Removed transcript forwarding.

## 验证
- 29 tests passed.

## 下一步
Wire the snapshot into the target session.
"""

    # Act
    output = StageOutputBuilder.build(
        card=card,
        execution=execution,
        source_session_id="sess0001",
        final_output=final_output,
        artifacts=(
            SessionArtifact(
                path="/workspace/result.md",
                description="Agent output",
                artifact_type="text/markdown",
            ),
        ),
    )

    # Assert
    assert output.content["completed_work"] == [
        "Added a versioned stage output.",
        "Removed transcript forwarding.",
    ]
    assert output.content["validation"] == ["29 tests passed."]
    assert output.content["next_stage_brief"] == (
        "Wire the snapshot into the target session."
    )
    assert len(output.checksum) == 64


def test_snapshot_bounded_when_final_output_exceeds_limit() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Bound context")
    execution = CardExecution.create(card.id, "slot-1")
    final_output = "\n\n".join(
        f"Paragraph {index}: implementation detail " + ("x" * 400)
        for index in range(40)
    )

    # Act
    output = StageOutputBuilder.build(
        card=card,
        execution=execution,
        source_session_id="sess0001",
        final_output=final_output,
    )

    # Assert
    assert len(output.content["stage_summary"]) <= 8_000


def test_snapshot_does_not_include_other_conversation_messages_when_final_output_given() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Keep secrets out")
    execution = CardExecution.create(card.id, "slot-1")

    # Act
    output = StageOutputBuilder.build(
        card=card,
        execution=execution,
        source_session_id="sess0001",
        final_output="Completed the requested work.",
    )

    # Assert
    assert "Completed the requested work." in output.rendered_markdown
    assert "conversation" not in output.content


def test_sensitive_value_redacted_when_final_output_contains_token() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Configure integration")
    execution = CardExecution.create(card.id, "slot-1")

    # Act
    output = StageOutputBuilder.build(
        card=card,
        execution=execution,
        source_session_id="sess0001",
        final_output="Configured access_token=top-secret-token-value successfully.",
    )

    # Assert
    assert "top-secret-token-value" not in output.rendered_markdown
    assert "access_token=[REDACTED]" in output.rendered_markdown


def test_limits_artifacts_when_build_receives_unbounded_iterable() -> None:
    # Arrange
    card = WishCard.create(team_id="team-1", title="Bound artifacts")
    execution = CardExecution.create(card.id, "slot-1")
    artifacts = (
        SessionArtifact(
            path=f"/workspace/artifact-{index:03}.txt",
            description="Agent output",
            artifact_type="text/plain",
        )
        for index in range(StageOutputBuilder._MAX_ARTIFACTS + 10)
    )

    # Act
    output = StageOutputBuilder.build(
        card=card,
        execution=execution,
        source_session_id="sess0001",
        final_output="Completed.",
        artifacts=artifacts,
    )

    # Assert
    assert len(output.artifacts) == StageOutputBuilder._MAX_ARTIFACTS
