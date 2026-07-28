"""Create one Agents project per team agent and repair session ownership.

Revision ID: 0037_team_agent_projects
Revises: 0036_card_stage_outputs
Create Date: 2026-07-27 15:00:00
"""
from __future__ import annotations

import uuid
from datetime import datetime
import sqlalchemy as sa
from alembic import op

revision = "0037_team_agent_projects"
down_revision = "0036_card_stage_outputs"
branch_labels = None
depends_on = None

_ROLE_UNIQUE_CONSTRAINT = "uq_team_agent_slots_role"


def _new_project_id(connection: sa.Connection, projects: sa.Table) -> str:
    while True:
        project_id = uuid.uuid4().hex[:8]
        exists = connection.execute(
            sa.select(projects.c.id).where(projects.c.id == project_id)
        ).scalar_one_or_none()
        if exists is None:
            return project_id


def upgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    projects = sa.Table("projects", metadata, autoload_with=connection)
    teams = sa.Table("teams", metadata, autoload_with=connection)
    slots = sa.Table("team_agent_slots", metadata, autoload_with=connection)
    sessions = sa.Table("sessions", metadata, autoload_with=connection)
    executions = sa.Table("card_executions", metadata, autoload_with=connection)

    duplicate_agent = connection.execute(
        sa.select(slots.c.team_id, slots.c.role)
        .group_by(slots.c.team_id, slots.c.role)
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if duplicate_agent is not None:
        raise RuntimeError(
            "Cannot migrate team agents: a team contains the same agent more than once"
        )

    slot_rows = connection.execute(
        sa.select(
            slots.c.id,
            slots.c.name.label("slot_name"),
            slots.c.role,
            slots.c.workspace_ref,
            teams.c.name.label("team_name"),
        ).join(teams, teams.c.id == slots.c.team_id)
    ).mappings()

    now = datetime.now()
    for slot in slot_rows:
        project_id = connection.execute(
            sa.select(projects.c.id).where(
                projects.c.dir_path == slot["workspace_ref"]
            ).limit(1)
        ).scalar_one_or_none()
        agents = {"current": {"id": slot["role"], "language": "zh"}}
        project_name = f"{slot['team_name']}-{slot['slot_name']}"
        if project_id is None:
            project_id = _new_project_id(connection, projects)
            connection.execute(
                projects.insert().values(
                    id=project_id,
                    name=project_name,
                    dir_path=slot["workspace_ref"],
                    agents_json=agents,
                    plugins_json={},
                    sort_order=0,
                    project_type="single",
                    team_config_json={},
                    active_claude_md_revision_id="",
                    claude_md_file_hash="",
                    created_time=now,
                    updated_time=now,
                )
            )
        else:
            connection.execute(
                projects.update()
                .where(projects.c.id == project_id)
                .values(name=project_name, agents_json=agents)
            )

        execution_ids = sa.select(executions.c.id).where(
            executions.c.agent_slot_id == slot["id"]
        )
        connection.execute(
            sessions.update()
            .where(
                sa.or_(
                    sessions.c.agent_slot_id == slot["id"],
                    sessions.c.card_execution_id.in_(execution_ids),
                )
            )
            .values(project_id=project_id)
        )

    with op.batch_alter_table("team_agent_slots") as batch_op:
        batch_op.alter_column(
            "role",
            existing_type=sa.Text(),
            type_=sa.String(255),
            existing_nullable=False,
        )
        batch_op.create_unique_constraint(
            _ROLE_UNIQUE_CONSTRAINT,
            ["team_id", "role"],
        )


def downgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    teams = sa.Table("teams", metadata, autoload_with=connection)
    slots = sa.Table("team_agent_slots", metadata, autoload_with=connection)
    sessions = sa.Table("sessions", metadata, autoload_with=connection)
    executions = sa.Table("card_executions", metadata, autoload_with=connection)

    slot_rows = connection.execute(
        sa.select(
            slots.c.id,
            teams.c.project_id.label("team_project_id"),
        ).join(teams, teams.c.id == slots.c.team_id)
    ).mappings()
    for slot in slot_rows:
        execution_ids = sa.select(executions.c.id).where(
            executions.c.agent_slot_id == slot["id"]
        )
        connection.execute(
            sessions.update()
            .where(
                sa.or_(
                    sessions.c.agent_slot_id == slot["id"],
                    sessions.c.card_execution_id.in_(execution_ids),
                )
            )
            .values(project_id=slot["team_project_id"])
        )

    with op.batch_alter_table("team_agent_slots") as batch_op:
        batch_op.drop_constraint(_ROLE_UNIQUE_CONSTRAINT, type_="unique")
        batch_op.alter_column(
            "role",
            existing_type=sa.String(255),
            type_=sa.Text(),
            existing_nullable=False,
        )
