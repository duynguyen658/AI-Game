from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.constants import AgentName
from app.core.exceptions import AgentRunAlreadyActiveError, PersistenceError
from app.schemas.agent_run import AgentRunCreate
from app.service.agent_run_service import AgentRunService


def integrity_error(constraint_name: str | None) -> IntegrityError:
    original = RuntimeError("postgres detail must stay internal")
    original.diag = SimpleNamespace(constraint_name=constraint_name)  # type: ignore[attr-defined]
    return IntegrityError("insert", {}, original)


def payload() -> AgentRunCreate:
    return AgentRunCreate(
        workflow_id=uuid4(),
        campaign_id="CL-SERVICE",
        agent_name=AgentName.BRIEF_ANALYST,
        model="mock",
        prompt_version="m4-v1",
    )


@pytest.mark.asyncio
async def test_create_run_maps_only_active_constraint() -> None:
    session = AsyncMock()
    service = AgentRunService(session)
    service.runs.find_active = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service.runs.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=integrity_error("uq_agent_runs_one_active_specialist")
    )

    with pytest.raises(AgentRunAlreadyActiveError) as captured:
        await service.create_run(payload())

    session.rollback.assert_awaited_once()
    assert isinstance(captured.value.__cause__, IntegrityError)
    assert "postgres detail" not in captured.value.message


@pytest.mark.asyncio
async def test_create_run_maps_unknown_constraint_to_safe_persistence_error() -> None:
    session = AsyncMock()
    service = AgentRunService(session)
    service.runs.find_active = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service.runs.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=integrity_error("fk_agent_runs_workflow_id")
    )

    with pytest.raises(
        PersistenceError, match="Unable to create agent run"
    ) as captured:
        await service.create_run(payload())

    session.rollback.assert_awaited_once()
    assert isinstance(captured.value.__cause__, IntegrityError)
    assert "postgres detail" not in captured.value.message
