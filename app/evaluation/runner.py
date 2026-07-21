from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import EvaluationResultStatus, EvaluationRunStatus
from app.core.exceptions import EvaluationConflictError, EvaluationNotFoundError
from app.core.sanitization import sanitize_text
from app.database.session import AsyncSessionLocal
from app.evaluation.assertions import evaluate_assertions
from app.evaluation.metrics import deterministic_metrics
from app.evaluation.regression import aggregate_results, passes_regression_gate
from app.observability.tracing import traced_operation
from app.repositories.evaluation_repository import EvaluationRepository

logger = structlog.get_logger()
CancellationCheckpoint = Callable[[], Awaitable[None]]


class EvaluationRunner:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    ) -> None:
        self.session_factory = session_factory

    async def run(
        self,
        run_id: UUID,
        *,
        checkpoint: CancellationCheckpoint | None = None,
    ) -> None:
        async with self.session_factory() as session:
            repository = EvaluationRepository(session)
            run = await repository.get_run(run_id, for_update=True)
            if run is None:
                raise EvaluationNotFoundError("Evaluation run not found")
            if run.status == EvaluationRunStatus.SUCCEEDED.value:
                await session.commit()
                return
            if run.status == EvaluationRunStatus.RUNNING.value:
                raise EvaluationConflictError("Evaluation run is already active")
            await repository.mark_running(run)
            cases = await repository.list_cases(run.dataset_id)
            case_data = [
                (
                    case.evaluation_case_id,
                    case.name,
                    case.actual_output,
                    case.expected,
                    case.thresholds,
                )
                for case in cases
            ]
            await session.commit()

        try:
            with traced_operation("evaluation.run"):
                for case_id, name, actual, expected, thresholds in case_data:
                    if checkpoint is not None:
                        await checkpoint()
                    started = time.perf_counter()
                    assertions = evaluate_assertions(actual, expected)
                    metrics = deterministic_metrics(actual, expected, assertions)
                    duration_ms = max(int((time.perf_counter() - started) * 1000), 0)
                    input_tokens = max(int(actual.get("input_tokens", 0)), 0)
                    output_tokens = max(int(actual.get("output_tokens", 0)), 0)
                    estimated_cost = max(float(actual.get("estimated_cost", 0)), 0)
                    passed = all(assertions.values()) and float(
                        metrics["relevance"]
                    ) >= float(thresholds.get("min_relevance", 0))
                    async with self.session_factory() as session:
                        repository = EvaluationRepository(session)
                        await repository.upsert_result(
                            run_id=run_id,
                            case_id=case_id,
                            status=(
                                EvaluationResultStatus.PASSED
                                if passed
                                else EvaluationResultStatus.FAILED
                            ),
                            assertions=assertions,
                            metrics=metrics,
                            output_summary=sanitize_text(
                                actual.get("summary", name), max_characters=1000
                            ),
                            duration_ms=duration_ms,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            estimated_cost=estimated_cost,
                        )
                        await session.commit()
                await self._finish(run_id)
        except Exception as exc:
            await self._fail(run_id, exc)
            raise

    async def _finish(self, run_id: UUID) -> None:
        async with self.session_factory() as session:
            repository = EvaluationRepository(session)
            run = await repository.get_run(run_id, for_update=True)
            if run is None:
                raise EvaluationNotFoundError("Evaluation run not found")
            results = await repository.result_payloads(run_id)
            metrics = aggregate_results(results)
            run.completed_cases = len(results)
            run.metrics = metrics
            run.regression_passed = passes_regression_gate(metrics)
            run.status = EvaluationRunStatus.SUCCEEDED.value
            run.completed_at = datetime.now(UTC)
            await session.commit()
            logger.info(
                "evaluation_completed",
                evaluation_run_id=str(run_id),
                regression_passed=run.regression_passed,
            )

    async def _fail(self, run_id: UUID, error: Exception) -> None:
        async with self.session_factory() as session:
            repository = EvaluationRepository(session)
            run = await repository.get_run(run_id, for_update=True)
            if run is None:
                return
            run.status = EvaluationRunStatus.FAILED.value
            run.completed_at = datetime.now(UTC)
            run.error_code = "EVALUATION_RUN_FAILED"
            run.error_message = sanitize_text(error, max_characters=2000)
            await session.commit()
