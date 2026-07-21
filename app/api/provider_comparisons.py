from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_actor
from app.schemas.provider import (
    ProviderCatalogItem,
    ProviderComparisonReport,
    ProviderComparisonRequest,
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


@router.post("/provider-comparisons", response_model=ProviderComparisonReport)
async def compare_providers(
    data: ProviderComparisonRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ProviderComparisonReport:
    AuthService().require_operator(actor)
    return ProviderComparisonService().compare(data)
