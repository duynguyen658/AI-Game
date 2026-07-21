from decimal import Decimal

from app.business_impact.calculator import ImpactCalculator


def test_business_impact_formulas_are_decimal_safe() -> None:
    assert ImpactCalculator.minutes_saved(Decimal("60"), Decimal("12.345")) == Decimal(
        "47.66"
    )
    assert ImpactCalculator.minutes_saved(Decimal("5"), Decimal("8")) == Decimal("0.00")
    assert ImpactCalculator.automation_rate(3, 4) == Decimal("0.750000")
    assert ImpactCalculator.automation_rate(4, 0) == Decimal("1.000000")
    assert ImpactCalculator.first_pass_acceptance_rate(8, 10) == Decimal("0.800000")
    assert ImpactCalculator.revision_rate(2, 10) == Decimal("0.200000")
    assert ImpactCalculator.error_rate(1, 0) == Decimal("0.000000")
    assert ImpactCalculator.user_satisfaction([5, 4, 3]) == Decimal("4.00")
    assert ImpactCalculator.would_use_again_rate(3, 4) == Decimal("0.750000")
