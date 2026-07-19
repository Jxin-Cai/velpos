from application.team_board.team_board_service import format_handoff_artifact_links
from domain.team.model.handoff import Handoff


def test_clickable_link_rendered_when_handoff_artifact_path_contains_spaces_and_markup() -> None:
    # Arrange
    handoff = Handoff.create(
        team_id="team-1",
        card_id="card-1",
        source_execution_id="execution-1",
        source_agent_slot_id="slot-1",
        target_agent_slot_id="slot-2",
        summary="Completed.",
    )
    handoff.add_artifact(
        name="result <final>.md",
        path='/tmp/team work/result "final".md',
        media_type="text/markdown",
    )

    # Act
    rendered = format_handoff_artifact_links(handoff)

    # Assert
    assert rendered == (
        '- <a class="file-path-link" '
        'data-file-path="/tmp/team work/result &quot;final&quot;.md" '
        'href="#" title="Click to open">result &lt;final&gt;.md</a> '
        '— `/tmp/team work/result "final".md`'
    )
