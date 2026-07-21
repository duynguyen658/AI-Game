from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.business_impact.calculator import ImpactCalculator
from app.schemas.business_impact import TaskImpactCreate, UserFeedbackCreate


def impact(**overrides: object) -> TaskImpactCreate:
    values: dict[str, object] = {
        "steps_before": 4,
        "automated_steps": 2,
        "editing_minutes": Decimal("0"),
        "rework_count": 0,
        "error_count": 0,
    }
    values.update(overrides)
    return TaskImpactCreate.model_validate(values)


def test_technical_completion_does_not_imply_acceptance() -> None:
    data = impact()
    assert data.output_accepted is None
    assert data.accepted_without_editing is False


def test_explicit_acceptance_and_rejection_are_distinct() -> None:
    accepted = impact(output_accepted=True, accepted_without_editing=True)
    rejected = impact(output_accepted=False)
    assert accepted.output_accepted is True
    assert accepted.accepted_without_editing is True
    assert rejected.output_accepted is False


@pytest.mark.parametrize(
    "values",
    [
        {"output_accepted": False, "accepted_without_editing": True},
        {
            "output_accepted": True,
            "accepted_without_editing": True,
            "editing_minutes": Decimal("15"),
        },
        {
            "output_accepted": True,
            "accepted_without_editing": True,
            "rework_count": 1,
        },
    ],
)
def test_first_pass_acceptance_rejects_inconsistent_fields(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        impact(**values)


def test_feedback_requires_explicit_acceptance_for_first_pass() -> None:
    with pytest.raises(ValidationError):
        UserFeedbackCreate(
            rating=5,
            helpfulness=5,
            accuracy=5,
            ease_of_use=5,
            accepted_without_editing=True,
            editing_minutes=Decimal("0"),
            rework_count=0,
            would_use_again=True,
        )


def test_acceptance_rate_uses_only_known_acceptance_denominator() -> None:
    assert ImpactCalculator.ratio(1, 2) == Decimal("0.500000")
    assert ImpactCalculator.ratio(0, 0) == Decimal("0.000000")
