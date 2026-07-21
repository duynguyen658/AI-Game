from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.schemas.provider import (
    ProviderCatalogItem,
    ProviderComparisonCaseRead,
    ProviderComparisonCreate,
    ProviderComparisonRead,
    ProviderComparisonRun,
)
from app.service.auth_service import AuthService, AuthenticatedActor
from app.service.provider_comparison_service import ProviderComparisonService

router = APIRouter(tags=["Applied AI - Providers"])


@router.get("/providers", response_model=list[ProviderCatalogItem])
async def provider_catalog(
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> list[ProviderCatalogItem]:
    return [
        ProviderCatalogItem.model_validate(item)
        for item in ProviderComparisonService().catalog()
    ]


@router.post(
    "/provider-comparisons", response_model=ProviderComparisonRead, status_code=201
)
async def create_provider_comparison(
    data: ProviderComparisonCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ProviderComparisonRead:
    AuthService().require_operator(actor)
    return await ProviderComparisonService(session).create(data, actor=actor)


@router.get("/provider-comparisons", response_model=list[ProviderComparisonRead])
async def list_provider_comparisons(
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProviderComparisonRead]:
    return await ProviderComparisonService(session).list(limit=limit, offset=offset)


@router.get(
    "/provider-comparisons/{comparison_id}", response_model=ProviderComparisonRead
)
async def get_provider_comparison(
    comparison_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ProviderComparisonRead:
    return await ProviderComparisonService(session).get(comparison_id)


@router.post(
    "/provider-comparisons/{comparison_id}/run",
    response_model=ProviderComparisonRead,
    status_code=202,
)
async def run_provider_comparison(
    comparison_id: UUID,
    data: ProviderComparisonRun,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ProviderComparisonRead:
    AuthService().require_operator(actor)
    return await ProviderComparisonService(session).run(
        comparison_id, data, actor=actor
    )


@router.post(
    "/provider-comparisons/{comparison_id}/cancel",
    response_model=ProviderComparisonRead,
)
async def cancel_provider_comparison(
    comparison_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ProviderComparisonRead:
    AuthService().require_operator(actor)
    return await ProviderComparisonService(session).cancel(comparison_id)


@router.get(
    "/provider-comparisons/{comparison_id}/results",
    response_model=list[ProviderComparisonCaseRead],
)
async def get_provider_comparison_results(
    comparison_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> list[ProviderComparisonCaseRead]:
    return await ProviderComparisonService(session).results(comparison_id)
