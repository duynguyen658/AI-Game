from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.constants import ProviderName
from app.core.exceptions import M7ValidationError
from app.llm.registry import build_provider_registry
from app.schemas.provider import ProviderComparisonReport, ProviderComparisonRequest


class ProviderComparisonService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = build_provider_registry(self.settings)

    def catalog(self) -> list[dict[str, object]]:
        return self.registry.catalog()

    def compare(self, data: ProviderComparisonRequest) -> ProviderComparisonReport:
        if data.fixture_metrics is None:
            raise M7ValidationError(
                "Provider comparison requires fixture metrics or a scheduled evaluation job"
            )
        rows = []
        scores: dict[ProviderName, float] = {}
        for provider in data.providers:
            self.registry.validate(provider, structured_output=True)
            metrics = data.fixture_metrics.get(provider)
            if metrics is None:
                raise M7ValidationError(
                    f"Missing metrics for provider {provider.value}"
                )
            score = (
                metrics.get("quality", 0)
                + metrics.get("schema_validity", 0)
                + metrics.get("success_rate", 0)
                - metrics.get("estimated_cost", 0)
                - metrics.get("latency", 0) * 0.01
            )
            scores[provider] = score
            rows.append(
                {
                    "provider": provider.value,
                    "model": data.model_by_provider.get(provider, ""),
                    "metrics": metrics,
                    "score": score,
                }
            )
        recommended = max(scores, key=lambda item: scores[item]) if scores else None
        return ProviderComparisonReport(
            prompt_version_id=data.prompt_version_id,
            dataset_id=data.dataset_id,
            comparisons=rows,
            recommended_provider=recommended,
        )
